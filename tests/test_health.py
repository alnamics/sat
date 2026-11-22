"""Tests for the SAT health binary sensor and repair issues."""

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.sat.const import (
    CONF_DEVICE,
    CONF_MODE,
    CONF_MQTT_TOPIC,
    DOMAIN,
    MINIMUM_SETPOINT,
    MODE_MQTT_OPENTHERM,
    BoilerStatus,
    PWMStatus,
)
from custom_components.sat.coordinator import DeviceState
from tests.const import DEFAULT_USER_DATA

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory

ENTITY_ID = "binary_sensor.mock_title_heating_control"
BOILER_HEALTH = "binary_sensor.mock_title_boiler_health"


async def setup_heating(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set("sensor.test_inside_sensor", "19.5")
    hass.states.async_set("sensor.test_outside_sensor", "5.0")

    entry = MockConfigEntry(domain=DOMAIN, data={**DEFAULT_USER_DATA, "minimum_setpoint": 45})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await climate.async_control_heating_loop()
    await hass.async_block_till_done()

    return entry


async def test_healthy_while_controlling(hass: HomeAssistant) -> None:
    entry = await setup_heating(hass)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes["problems"] == []
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_flags_a_stalled_control_loop(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_heating(hass)

    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["problems"] == ["control_loop_stalled"]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_healthy_while_paused(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry = await setup_heating(hass)

    async with entry.runtime_data.climate.async_calibrating():
        freezer.tick(timedelta(minutes=3))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        state = hass.states.get(ENTITY_ID)
        assert state is not None
        assert state.attributes["problems"] == []

    assert entry.runtime_data.climate.control_problems == []
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_healthy_right_after_turning_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate

    await climate.async_set_hvac_mode(HVACMode.OFF)
    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    await climate.async_set_hvac_mode(HVACMode.HEAT)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["problems"] == []
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_healthy_while_home_assistant_starts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.set_state(CoreState.starting)
    hass.states.async_set("sensor.test_inside_sensor", "19.5")
    hass.states.async_set("sensor.test_outside_sensor", "5.0")
    entry = MockConfigEntry(domain=DOMAIN, data={**DEFAULT_USER_DATA, "minimum_setpoint": 45})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)

    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["problems"] == []
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_flags_missing_inputs_and_recovers(hass: HomeAssistant) -> None:
    entry = await setup_heating(hass)

    hass.states.async_set("sensor.test_inside_sensor", "unavailable")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["problems"] == ["inputs_missing"]
    assert state.state == STATE_ON

    hass.states.async_set("sensor.test_inside_sensor", "19.6")
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_flags_missing_boiler_data(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_heating(hass)
    freezer.tick(timedelta(minutes=3))

    await entry.runtime_data.coordinator.async_set_boiler_temperature(None)
    await entry.runtime_data.climate.async_control_heating_loop()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["problems"] == ["boiler_data_missing"]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_healthy_while_the_first_boiler_data_arrives(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set("sensor.test_inside_sensor", "19.5")
    hass.states.async_set("sensor.test_outside_sensor", "5.0")
    entry = MockConfigEntry(domain=DOMAIN, data={**DEFAULT_USER_DATA, "minimum_setpoint": 45})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate = entry.runtime_data.climate
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await climate.async_control_heating_loop()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    state = hass.states.get(BOILER_HEALTH)
    assert state is not None
    assert state.state == STATE_OFF

    freezer.tick(timedelta(minutes=3))
    await climate.async_control_heating_loop()
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["problems"] == ["boiler_data_missing"]
    state = hass.states.get(BOILER_HEALTH)
    assert state is not None
    assert state.state == STATE_ON
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_failed_setup_raises_a_repair_issue_after_retrying(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="otgw",
        data={
            **DEFAULT_USER_DATA,
            CONF_MODE: MODE_MQTT_OPENTHERM,
            CONF_DEVICE: "otgw",
            CONF_MQTT_TOPIC: "OTGW",
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"setup_failed_{entry.entry_id}") is None

    for _ in range(6):
        freezer.tick(timedelta(seconds=90))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"setup_failed_{entry.entry_id}")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.config_entry_id == entry.entry_id

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"setup_failed_{entry.entry_id}") is None


async def test_successful_setup_clears_the_repair_issue(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=DEFAULT_USER_DATA)
    entry.add_to_hass(hass)
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"setup_failed_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="setup_failed",
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, f"setup_failed_{entry.entry_id}") is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_synchro_sensors_ignore_the_room_thermostat_while_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator

    await climate.async_set_hvac_mode(HVACMode.OFF)
    await coordinator.async_set_control_setpoint(30)
    await coordinator.async_set_heater_state(DeviceState.ON)
    climate.async_write_ha_state()
    freezer.tick(timedelta(seconds=61))
    climate.async_write_ha_state()

    state = hass.states.get("binary_sensor.mock_title_control_setpoint_synchro")
    assert state is not None
    assert state.state == STATE_OFF
    state = hass.states.get("binary_sensor.mock_title_central_heating_synchro")
    assert state is not None
    assert state.state == STATE_OFF
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_central_heating_synchro_follows_the_boiler_between_climate_writes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator

    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await coordinator.async_set_heater_state(DeviceState.OFF)
    await climate.async_control_heating_loop()
    assert climate.setpoint is not None
    await coordinator.async_set_heater_state(DeviceState.OFF)
    climate.async_write_ha_state()
    assert climate.hvac_action == HVACAction.IDLE

    await coordinator.async_set_heater_state(DeviceState.ON)
    coordinator.async_update_listeners()
    freezer.tick(timedelta(seconds=61))
    coordinator.async_update_listeners()

    state = hass.states.get("binary_sensor.mock_title_central_heating_synchro")
    assert state is not None
    assert state.state == STATE_OFF
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_control_setpoint_stays_within_the_maximum_setpoint(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator

    hass.states.async_set("sensor.test_inside_sensor", "12.0")
    hass.states.async_set("sensor.test_outside_sensor", "-20.0")
    await hass.async_block_till_done()
    await climate.async_control_heating_loop()
    freezer.tick(timedelta(seconds=61))
    await climate.async_control_heating_loop()

    assert climate.setpoint == coordinator.maximum_setpoint
    state = hass.states.get("binary_sensor.mock_title_control_setpoint_synchro")
    assert state is not None
    assert state.state == STATE_OFF
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_control_setpoint_synchro_ignores_the_idle_setpoint(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    # SAT asks for no heat and the boiler answers with its own lowest setpoint
    climate._setpoint = MINIMUM_SETPOINT
    coordinator._setpoint = 25.0
    climate.async_write_ha_state()
    freezer.tick(timedelta(seconds=61))
    climate.async_write_ha_state()
    state = hass.states.get("binary_sensor.mock_title_control_setpoint_synchro")
    assert state is not None
    assert state.state == STATE_OFF

    # A setpoint SAT does ask for and the boiler does not have is a problem
    climate._setpoint = 42.0
    coordinator._setpoint = 30.0
    climate.async_write_ha_state()
    freezer.tick(timedelta(seconds=61))
    climate.async_write_ha_state()
    state = hass.states.get("binary_sensor.mock_title_control_setpoint_synchro")
    assert state is not None
    assert state.state == STATE_ON
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_boiler_with_heating_disabled_is_idle(hass: HomeAssistant) -> None:
    entry = await setup_heating(hass)
    coordinator = entry.runtime_data.coordinator

    # The boiler answers with its own lowest setpoint while the water is warmer
    coordinator._setpoint = 25.0
    await coordinator.async_set_boiler_temperature(31.0)
    await coordinator.async_set_heater_state(DeviceState.OFF)
    assert coordinator.device_status == BoilerStatus.IDLE

    # Heating enabled but no flame: the boiler waits out its anti-cycling time
    await coordinator.async_set_heater_state(DeviceState.ON)
    with patch.object(
        type(coordinator), "flame_active", new_callable=PropertyMock, return_value=False
    ):
        assert coordinator.device_status == BoilerStatus.ANTI_CYCLING
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_heating_kept_on_between_pwm_phases_shows_as_idle(hass: HomeAssistant) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator

    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await coordinator.async_set_heater_state(DeviceState.ON)
    climate.async_write_ha_state()
    assert climate.hvac_action == HVACAction.HEATING

    # The control loop left heating enabled through a PWM off-phase
    climate._pwm_off_since = 1.0
    climate.async_write_ha_state()
    assert climate.heating_kept_on
    assert climate.hvac_action == HVACAction.IDLE

    climate._pwm_off_since = None
    climate.async_write_ha_state()
    assert climate.hvac_action == HVACAction.HEATING


@pytest.mark.parametrize(
    ("flow", "suspended"), [(60.0, False), (30.0, True)], ids=["hot_water", "heating"]
)
async def test_a_flame_between_pwm_phases_suspends_keep_heating_only_for_heating(
    hass: HomeAssistant, flow: float, suspended: bool
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator
    climate._keep_heating_in_pwm_off = True
    clock = [1000.0]

    with (
        patch("custom_components.sat.climate.monotonic", side_effect=lambda: clock[0]),
        patch.object(
            type(climate), "pulse_width_modulation_enabled", new_callable=PropertyMock
        ) as enabled,
        patch.object(type(climate.pwm), "status", new_callable=PropertyMock) as status,
        patch.object(type(coordinator), "flame_active", new_callable=PropertyMock) as flame,
        patch.object(type(coordinator), "hot_water_active", new_callable=PropertyMock) as water,
        patch.object(type(coordinator), "setpoint", new_callable=PropertyMock) as setpoint,
        patch.object(
            type(coordinator), "boiler_temperature", new_callable=PropertyMock
        ) as boiler_temperature,
        patch.object(
            type(coordinator), "heating_hot_water", new_callable=PropertyMock
        ) as heating_hot_water,
    ):
        heating_hot_water.return_value = False
        enabled.return_value = True
        status.return_value = PWMStatus.OFF
        water.return_value = False
        setpoint.return_value = 25.0
        flame.return_value = False
        boiler_temperature.return_value = 30.0
        assert climate._heating_kept_on_in_pwm_off()

        # The boiler lights well after the on-phase ended; the hot water flag never comes
        clock[0] += 120
        flame.return_value = True
        boiler_temperature.return_value = flow
        assert climate._heating_kept_on_in_pwm_off()
        # The flame tracker tells the unflagged reheat from the water within the minute
        heating_hot_water.return_value = flow > 50
        clock[0] += 90
        assert climate._heating_kept_on_in_pwm_off() is not suspended

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_short_burn_between_pwm_phases_releases_keep_heating(
    hass: HomeAssistant,
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator
    climate._keep_heating_in_pwm_off = True
    clock = [1000.0]

    with (
        patch("custom_components.sat.climate.monotonic", side_effect=lambda: clock[0]),
        patch.object(
            type(climate), "pulse_width_modulation_enabled", new_callable=PropertyMock
        ) as enabled,
        patch.object(type(climate.pwm), "status", new_callable=PropertyMock) as status,
        patch.object(type(coordinator), "flame_active", new_callable=PropertyMock) as flame,
        patch.object(type(coordinator), "setpoint", new_callable=PropertyMock) as setpoint,
        patch.object(
            type(coordinator), "boiler_temperature", new_callable=PropertyMock
        ) as boiler_temperature,
        patch.object(
            type(coordinator), "heating_hot_water", new_callable=PropertyMock
        ) as heating_hot_water,
    ):
        heating_hot_water.return_value = False
        enabled.return_value = True
        status.return_value = PWMStatus.OFF
        setpoint.return_value = 25.0
        boiler_temperature.return_value = 32.0
        flame.return_value = False
        assert climate._heating_kept_on_in_pwm_off()

        # Ten minutes on, the anti-cycling runs out and the boiler lights for a few seconds
        clock[0] += 600
        flame.return_value = True
        assert climate._heating_kept_on_in_pwm_off()
        clock[0] += 12
        flame.return_value = False
        assert not climate._heating_kept_on_in_pwm_off()
        clock[0] += 60
        assert not climate._heating_kept_on_in_pwm_off()

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_keep_heating_is_released_before_the_water_reaches_the_boiler_minimum(
    hass: HomeAssistant,
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator
    climate._keep_heating_in_pwm_off = True
    clock = [1000.0]

    with (
        patch("custom_components.sat.climate.monotonic", side_effect=lambda: clock[0]),
        patch.object(
            type(climate), "pulse_width_modulation_enabled", new_callable=PropertyMock
        ) as enabled,
        patch.object(type(climate.pwm), "status", new_callable=PropertyMock) as status,
        patch.object(type(coordinator), "flame_active", new_callable=PropertyMock) as flame,
        patch.object(type(coordinator), "setpoint", new_callable=PropertyMock) as setpoint,
        patch.object(
            type(coordinator), "boiler_temperature", new_callable=PropertyMock
        ) as boiler_temperature,
        patch.object(
            type(coordinator), "heating_hot_water", new_callable=PropertyMock
        ) as heating_hot_water,
    ):
        heating_hot_water.return_value = False
        enabled.return_value = True
        status.return_value = PWMStatus.OFF
        flame.return_value = False
        # Just after the on-phase the boiler still reports its setpoint
        setpoint.return_value = coordinator.minimum_setpoint
        boiler_temperature.return_value = 33.0
        assert climate._heating_kept_on_in_pwm_off()

        # The boiler raised the off-phase setpoint to 25 °C; the water is still warm
        clock[0] += 600
        setpoint.return_value = 25.0
        boiler_temperature.return_value = 27.0
        assert climate._heating_kept_on_in_pwm_off()
        assert climate.heating_kept_on

        # It cools to within a kelvin of the boiler's minimum: heating is released
        clock[0] += 1200
        boiler_temperature.return_value = 25.9
        assert not climate._heating_kept_on_in_pwm_off()
        assert not climate.heating_kept_on
        boiler_temperature.return_value = 27.0
        assert not climate._heating_kept_on_in_pwm_off()

        # An idle step between off-phases does not enable heating again
        status.return_value = PWMStatus.IDLE
        assert not climate._heating_kept_on_in_pwm_off()
        status.return_value = PWMStatus.OFF
        clock[0] += 120
        boiler_temperature.return_value = 28.0
        assert not climate._heating_kept_on_in_pwm_off()

        # The next off-phase after an on-phase keeps heating on again
        status.return_value = PWMStatus.ON
        assert not climate._heating_kept_on_in_pwm_off()
        status.return_value = PWMStatus.OFF
        assert climate._heating_kept_on_in_pwm_off()

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_on_phase_burn_runs_out_without_suspending_keep_heating(
    hass: HomeAssistant,
) -> None:
    entry = await setup_heating(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator
    climate._keep_heating_in_pwm_off = True
    clock = [1000.0]

    with (
        patch("custom_components.sat.climate.monotonic", side_effect=lambda: clock[0]),
        patch.object(
            type(climate), "pulse_width_modulation_enabled", new_callable=PropertyMock
        ) as enabled,
        patch.object(type(climate.pwm), "status", new_callable=PropertyMock) as status,
        patch.object(type(coordinator), "flame_active", new_callable=PropertyMock) as flame,
        patch.object(type(coordinator), "setpoint", new_callable=PropertyMock) as setpoint,
        patch.object(
            type(coordinator), "boiler_temperature", new_callable=PropertyMock
        ) as boiler_temperature,
        patch.object(
            type(coordinator), "heating_hot_water", new_callable=PropertyMock
        ) as heating_hot_water,
    ):
        heating_hot_water.return_value = False
        enabled.return_value = True
        setpoint.return_value = 25.0
        boiler_temperature.return_value = 32.0

        # The block ends while the burner runs; the boiler stops it by itself minutes later
        status.return_value = PWMStatus.OFF
        flame.return_value = True
        assert climate._heating_kept_on_in_pwm_off()
        clock[0] += 200
        assert climate._heating_kept_on_in_pwm_off()

        # Once the flame is out heating stays enabled, with no suspension
        flame.return_value = False
        clock[0] += 10
        assert climate._heating_kept_on_in_pwm_off()
        assert climate._keep_heating_suspended_until is None
        clock[0] += 300
        assert climate._heating_kept_on_in_pwm_off()

        # A burn that does not end is stopped by disabling heating
        status.return_value = PWMStatus.ON
        assert not climate._heating_kept_on_in_pwm_off()
        status.return_value = PWMStatus.OFF
        flame.return_value = True
        assert climate._heating_kept_on_in_pwm_off()
        clock[0] += 601
        assert not climate._heating_kept_on_in_pwm_off()
        flame.return_value = False
        clock[0] += 10
        assert climate._heating_kept_on_in_pwm_off()

    assert await hass.config_entries.async_unload(entry.entry_id)
