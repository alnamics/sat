"""The tests for the climate component."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.climate import PRESET_AWAY, HVACAction, HVACMode
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.template import DOMAIN as TEMPLATE_DOMAIN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.sat.config_flow import SatFlowHandler
from custom_components.sat.const import (
    CONF_FORCE_PULSE_WIDTH_MODULATION,
    CONF_HEATING_CURVE_COEFFICIENT,
    CONF_HEATING_SYSTEM,
    CONF_MAXIMUM_SETPOINT,
    CONF_MINIMUM_SETPOINT,
    CONF_MODE,
    CONF_OUTSIDE_SENSOR_ENTITY_ID,
    CONF_RADIATORS,
    CONF_ROOMS,
    CONF_THERMOSTAT,
    DOMAIN,
    HEATING_SYSTEM_RADIATORS,
    HEATING_SYSTEM_UNDERFLOOR,
    MODE_FAKE,
    PWMStatus,
)
from custom_components.sat.errors import Error
from tests.const import DEFAULT_USER_DATA

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

    from custom_components.sat.climate import SatClimate
    from custom_components.sat.fake import SatFakeCoordinator


@pytest.mark.parametrize(
    *[
        "domains, data, options, config",
        [
            (
                [(TEMPLATE_DOMAIN, 1)],
                {
                    CONF_MODE: MODE_FAKE,
                    CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS,
                    CONF_MINIMUM_SETPOINT: 57,
                },
                {
                    CONF_HEATING_CURVE_COEFFICIENT: 1.8,
                    CONF_FORCE_PULSE_WIDTH_MODULATION: True,
                    CONF_MAXIMUM_SETPOINT: 75,
                },
                {
                    TEMPLATE_DOMAIN: [
                        {
                            SENSOR_DOMAIN: [
                                {
                                    "name": "test_inside_sensor",
                                    "state": "{{ 20.9 | float }}",
                                },
                                {
                                    "name": "test_outside_sensor",
                                    "state": "{{ 9.9 | float }}",
                                },
                            ]
                        },
                    ],
                },
            )
        ],
    ]
)
async def test_scenario_1(
    climate: SatClimate,
    coordinator: SatFakeCoordinator,
) -> None:
    await coordinator.async_set_boiler_temperature(57)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate.schedule_control_heating_loop(force=True)

    assert climate.setpoint == 57
    assert climate.heating_curve.value == 32.2

    assert climate.pulse_width_modulation_enabled
    assert climate.pwm is not None
    assert climate.pwm.last_duty_cycle_percentage == 23.83
    assert climate.pwm.duty_cycle == (285, 914)


@pytest.mark.parametrize(
    *[
        "domains, data, options, config",
        [
            (
                [(TEMPLATE_DOMAIN, 1)],
                {
                    CONF_MODE: MODE_FAKE,
                    CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS,
                    CONF_MINIMUM_SETPOINT: 58,
                    CONF_MAXIMUM_SETPOINT: 75,
                },
                {
                    CONF_HEATING_CURVE_COEFFICIENT: 1.3,
                    CONF_FORCE_PULSE_WIDTH_MODULATION: True,
                },
                {
                    TEMPLATE_DOMAIN: [
                        {
                            SENSOR_DOMAIN: [
                                {
                                    "name": "test_inside_sensor",
                                    "state": "{{ 18.99 | float }}",
                                },
                                {
                                    "name": "test_outside_sensor",
                                    "state": "{{ 11.1 | float }}",
                                },
                            ]
                        },
                    ],
                },
            )
        ],
    ]
)
async def test_scenario_2(
    climate: SatClimate,
    coordinator: SatFakeCoordinator,
) -> None:
    await coordinator.async_set_boiler_temperature(58)
    await climate.async_set_target_temperature(19.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate.schedule_control_heating_loop(force=True)

    assert climate.setpoint == 10
    assert climate.heating_curve.value == 27.8
    assert climate.requested_setpoint == 28.0

    assert climate.pulse_width_modulation_enabled
    assert climate.pwm is not None
    assert climate.pwm.last_duty_cycle_percentage == 2.6
    assert climate.pwm.duty_cycle == (0, 2400)


@pytest.mark.parametrize(
    *[
        "domains, data, options, config",
        [
            (
                [(TEMPLATE_DOMAIN, 1)],
                {
                    CONF_MODE: MODE_FAKE,
                    CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS,
                    CONF_MINIMUM_SETPOINT: 41,
                    CONF_MAXIMUM_SETPOINT: 75,
                },
                {
                    CONF_HEATING_CURVE_COEFFICIENT: 0.9,
                    CONF_FORCE_PULSE_WIDTH_MODULATION: True,
                },
                {
                    TEMPLATE_DOMAIN: [
                        {
                            SENSOR_DOMAIN: [
                                {
                                    "name": "test_inside_sensor",
                                    "state": "{{ 19.9 | float }}",
                                },
                                {
                                    "name": "test_outside_sensor",
                                    "state": "{{ -2.2 | float }}",
                                },
                            ]
                        },
                    ],
                },
            )
        ],
    ]
)
async def test_scenario_3(
    climate: SatClimate,
    coordinator: SatFakeCoordinator,
) -> None:
    await coordinator.async_set_boiler_temperature(41)
    await climate.async_set_target_temperature(20.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    climate.schedule_control_heating_loop(force=True)

    assert climate.setpoint == 41.0
    assert climate.heating_curve.value == 32.5
    assert climate.requested_setpoint == 34.6

    assert climate.pulse_width_modulation_enabled
    assert climate.pwm is not None
    assert climate.pwm.last_duty_cycle_percentage == 53.62
    assert climate.pwm.duty_cycle == (643, 556)


async def test_pid_uses_the_configured_heating_system(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.test_inside_sensor", "20.9")
    hass.states.async_set("sensor.test_outside_sensor", "9.9")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=SatFlowHandler.VERSION,
        data={
            **DEFAULT_USER_DATA,
            CONF_HEATING_SYSTEM: HEATING_SYSTEM_UNDERFLOOR,
            CONF_MINIMUM_SETPOINT: 10,
            CONF_MAXIMUM_SETPOINT: 55,
        },
        options={CONF_HEATING_CURVE_COEFFICIENT: 1.8},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate = entry.runtime_data.climate
    climate.pid.update_reset(
        error=Error("sensor.test_inside_sensor", 0.0), heating_curve_value=30.0
    )

    assert climate.pid.kp == 13.5


ROOM = "climate.room"
HEATING_ROOM = {"hvac_action": "heating", "temperature": 23.0, "current_temperature": 19.0}
IDLE_RADIATOR = {"hvac_action": "idle", "temperature": 21.0, "current_temperature": 21.0}


async def setup_rooms(
    hass: HomeAssistant, data: dict[str, Any] | None = None, options: dict[str, Any] | None = None
) -> MockConfigEntry:
    hass.states.async_set("sensor.test_inside_sensor", "20.9")
    hass.states.async_set("sensor.test_outside_sensor", "9.9")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**DEFAULT_USER_DATA, CONF_ROOMS: [ROOM], **(data or {})},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    return entry


async def test_room_turned_off_adds_no_error(hass: HomeAssistant) -> None:
    hass.states.async_set(ROOM, HVACMode.OFF, {"temperature": 23.0, "current_temperature": 19.0})
    entry = await setup_rooms(hass)
    climate = entry.runtime_data.climate

    await climate.async_set_target_temperature(21.0)

    assert len(climate.areas.errors) == 0
    assert climate.max_error.entity_id == climate.entity_id
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_blocked_room_adds_no_error_and_no_open_valve(hass: HomeAssistant) -> None:
    hass.states.async_set("climate.radiator", HVACMode.HEAT, IDLE_RADIATOR)
    hass.states.async_set(
        ROOM, HVACMode.HEAT, {**HEATING_ROOM, "heating_blocked_by": "valve_maintenance"}
    )
    entry = await setup_rooms(hass, {CONF_RADIATORS: ["climate.radiator"]})
    climate = entry.runtime_data.climate

    await climate.async_set_target_temperature(21.0)

    assert len(climate.areas.errors) == 0
    assert climate.max_error.entity_id == climate.entity_id
    assert climate.valves_open is False
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "blocked_by",
    [
        {},
        {"heating_blocked_by": None},
        {"heating_blocked_by": ""},
        {"heating_blocked_by": "[]"},
        {"heating_blocked_by": []},
    ],
    ids=["missing", "none", "empty", "json-empty", "empty-list"],
)
async def test_unblocked_room_keeps_its_error_and_open_valve(
    hass: HomeAssistant, blocked_by: dict[str, Any]
) -> None:
    hass.states.async_set("climate.radiator", HVACMode.HEAT, IDLE_RADIATOR)
    hass.states.async_set(ROOM, HVACMode.HEAT, {**HEATING_ROOM, **blocked_by})
    entry = await setup_rooms(hass, {CONF_RADIATORS: ["climate.radiator"]})
    climate = entry.runtime_data.climate

    assert len(climate.areas.errors) == 1
    assert climate.valves_open is True
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unblocking_a_room_restores_its_error(hass: HomeAssistant) -> None:
    hass.states.async_set(ROOM, HVACMode.HEAT, {**HEATING_ROOM, "heating_blocked_by": "startup"})
    entry = await setup_rooms(hass)
    climate = entry.runtime_data.climate
    await climate.async_set_target_temperature(21.0)
    assert climate.max_error.entity_id == climate.entity_id

    hass.states.async_set(ROOM, HVACMode.HEAT, {**HEATING_ROOM, "heating_blocked_by": None})
    await hass.async_block_till_done()

    assert climate.max_error.entity_id == ROOM
    assert climate.pid.last_error == 4.0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_missing_temperature_attributes_do_not_break_the_loop(hass: HomeAssistant) -> None:
    hass.states.async_set("climate.radiator", HVACMode.HEAT, {"current_temperature": 19.0})
    entry = await setup_rooms(
        hass,
        {CONF_RADIATORS: ["climate.radiator"], CONF_OUTSIDE_SENSOR_ENTITY_ID: ["weather.home"]},
    )
    hass.states.async_set("weather.home", "sunny", {})
    climate = entry.runtime_data.climate

    assert climate.valves_open is False
    assert climate.current_outside_temperature is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_thermostat_without_a_setpoint_keeps_the_target(hass: HomeAssistant) -> None:
    hass.states.async_set("climate.thermostat", HVACMode.HEAT, {"temperature": 20.0})
    entry = await setup_rooms(hass, {CONF_THERMOSTAT: "climate.thermostat"})
    climate = entry.runtime_data.climate
    await climate.async_set_target_temperature(21.0)

    hass.states.async_set("climate.thermostat", HVACMode.OFF, {"temperature": None})
    await hass.async_block_till_done()

    assert climate.native_target_temperature == 21.0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_rooms_attribute_follows_the_room_targets(hass: HomeAssistant) -> None:
    hass.states.async_set(ROOM, HVACMode.HEAT, {"temperature": 21.0, "current_temperature": 20.0})
    entry = await setup_rooms(hass)
    await entry.runtime_data.climate.async_set_preset_mode(PRESET_AWAY)

    hass.states.async_set(ROOM, HVACMode.HEAT, {"temperature": 22.0, "current_temperature": 20.0})
    await hass.async_block_till_done()

    assert entry.runtime_data.climate.extra_state_attributes["rooms"] == {ROOM: 22.0}
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_control_loop_applies_an_error_change_from_inside_the_sample_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_rooms(hass, {CONF_ROOMS: []})
    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    freezer.tick(timedelta(seconds=61))
    hass.states.async_set("sensor.test_inside_sensor", "20.5")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=10))
    hass.states.async_set("sensor.test_inside_sensor", "20.3")
    await hass.async_block_till_done()
    assert climate.pid.last_error == 0.5

    freezer.tick(timedelta(seconds=61))
    await climate.async_control_heating_loop()

    assert climate.pid.last_error == 0.7
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_climate_uses_no_deprecated_members(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await setup_rooms(hass)
    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await climate.async_control_heating_loop()

    assert "deprecated SatClimate." not in caplog.text
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_steady_error_keeps_the_integral(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_rooms(hass, {CONF_ROOMS: []})
    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    for _ in range(7):
        freezer.tick(timedelta(hours=1))
        hass.states.async_set("sensor.test_inside_sensor", "20.9", force_update=True)
        await hass.async_block_till_done()
        await climate.async_control_heating_loop()

    assert climate.pid.integral != 0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_inside_sensor_reporting_the_same_value_is_not_stale(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_rooms(hass, {CONF_ROOMS: []})
    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    for _ in range(7):
        freezer.tick(timedelta(hours=1))
        hass.states.async_set("sensor.test_inside_sensor", "20.9")
        await hass.async_block_till_done()
        await climate.async_control_heating_loop()

    assert climate.native_current_temperature == 20.9
    assert climate.pid.integral != 0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_inside_sensor_outage_resets_the_integral(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_rooms(hass, {CONF_ROOMS: []})
    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    for _ in range(3):
        freezer.tick(timedelta(hours=1))
        hass.states.async_set("sensor.test_inside_sensor", "20.9", force_update=True)
        await hass.async_block_till_done()
        await climate.async_control_heating_loop()
    assert climate.pid.integral != 0

    freezer.tick(timedelta(hours=7))
    await climate.async_control_heating_loop()
    hass.states.async_set("sensor.test_inside_sensor", "20.9", force_update=True)
    await hass.async_block_till_done()

    assert climate.pid.integral == 0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_non_numeric_outside_sensor_falls_back_to_the_next_entity(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("sensor.outdoor", "-")
    hass.states.async_set("weather.home", "sunny", {"temperature": 4.0})
    entry = await setup_rooms(
        hass, {CONF_OUTSIDE_SENSOR_ENTITY_ID: ["sensor.outdoor", "weather.home"]}
    )

    assert entry.runtime_data.climate.current_outside_temperature == 4.0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_stale_outside_sensor_falls_back_to_the_next_entity(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set("sensor.outdoor", "9.9")
    hass.states.async_set("weather.home", "sunny", {"temperature": 4.0})
    entry = await setup_rooms(
        hass, {CONF_OUTSIDE_SENSOR_ENTITY_ID: ["sensor.outdoor", "weather.home"]}
    )
    climate = entry.runtime_data.climate
    assert climate.current_outside_temperature == 9.9

    freezer.tick(timedelta(hours=7))
    hass.states.async_set("weather.home", "sunny", {"temperature": 4.0}, force_update=True)

    assert climate.current_outside_temperature == 4.0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_control_loop_moves_the_curve_to_the_next_outside_source_when_one_goes_stale(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set("sensor.outdoor", "9.9")
    hass.states.async_set("weather.home", "sunny", {"temperature": -4.0})
    entry = await setup_rooms(
        hass, {CONF_ROOMS: [], CONF_OUTSIDE_SENSOR_ENTITY_ID: ["sensor.outdoor", "weather.home"]}
    )
    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await climate.async_control_heating_loop()
    curve_from_the_sensor = climate.heating_curve.value

    freezer.tick(timedelta(hours=7))
    hass.states.async_set("sensor.test_inside_sensor", "20.9")
    hass.states.async_set("weather.home", "sunny", {"temperature": -4.0})
    await hass.async_block_till_done()
    await climate.async_control_heating_loop()

    assert climate.heating_curve.value > curve_from_the_sensor
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_weather_entity_without_a_temperature_falls_back_to_the_next_entity(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("weather.broken", "sunny", {})
    hass.states.async_set("weather.home", "sunny", {"temperature": 4.0})
    entry = await setup_rooms(
        hass, {CONF_OUTSIDE_SENSOR_ENTITY_ID: ["weather.broken", "weather.home"]}
    )

    assert entry.runtime_data.climate.current_outside_temperature == 4.0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_an_expired_outside_sensor_is_published_without_a_state_change(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_rooms(hass, {CONF_ROOMS: []})
    climate = entry.runtime_data.climate
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    freezer.tick(timedelta(hours=3))
    hass.states.async_set("sensor.test_inside_sensor", "20.8")
    await hass.async_block_till_done()
    assert climate.extra_state_attributes["outside_temperature"] == 9.9

    freezer.tick(timedelta(hours=3, seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert climate.extra_state_attributes["outside_temperature"] is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_handing_back_publishes_the_cleared_setpoint_and_recovery_resets_the_pid(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_rooms(hass, {CONF_ROOMS: []})
    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(40)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await climate.async_control_heating_loop()
    assert climate.extra_state_attributes["setpoint"] is not None

    for delta in (timedelta(hours=7), timedelta(minutes=11)):
        freezer.tick(delta)
        hass.states.async_set("sensor.test_inside_sensor", "20.9")
        await hass.async_block_till_done()
        await climate.async_control_heating_loop()

    assert climate.extra_state_attributes["setpoint"] is None

    freezer.tick(timedelta(hours=1))
    hass.states.async_set("sensor.test_inside_sensor", "20.92")
    hass.states.async_set("sensor.test_outside_sensor", "5.0")
    await hass.async_block_till_done()
    await climate.async_control_heating_loop()

    assert climate.pid.integral == 0
    assert climate.pid.last_error == 0.08
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_outside_temperature_is_missing_until_a_stale_sensor_reports_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_rooms(hass)
    climate = entry.runtime_data.climate

    freezer.tick(timedelta(hours=7))
    assert climate.current_outside_temperature is None

    hass.states.async_set("sensor.test_outside_sensor", "9.9")
    assert climate.current_outside_temperature == 9.9
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_room_target_change_keeps_the_pwm_phase(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(ROOM, HVACMode.HEAT, {"temperature": 21.0, "current_temperature": 20.7})
    entry = await setup_rooms(
        hass,
        {CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS, CONF_MINIMUM_SETPOINT: 57},
        {
            CONF_HEATING_CURVE_COEFFICIENT: 1.8,
            CONF_FORCE_PULSE_WIDTH_MODULATION: True,
            CONF_MAXIMUM_SETPOINT: 75,
        },
    )
    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(57)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    await climate.async_control_heating_loop()
    assert climate.pwm.status == PWMStatus.ON
    assert climate.pwm.duty_cycle is not None

    freezer.tick(timedelta(seconds=climate.pwm.duty_cycle[0] + 1))
    await climate.async_control_heating_loop()
    assert climate.pwm.status == PWMStatus.OFF

    hass.states.async_set(ROOM, HVACMode.HEAT, {"temperature": 21.2, "current_temperature": 20.7})
    await hass.async_block_till_done()
    await climate.async_control_heating_loop()

    assert climate.max_error.entity_id == ROOM
    assert climate.pwm.status == PWMStatus.OFF
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_frost_protection_heats_while_off(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.test_inside_sensor", "5.5")
    hass.states.async_set("sensor.test_outside_sensor", "-10.0")
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=SatFlowHandler.VERSION,
        data={**DEFAULT_USER_DATA, CONF_MINIMUM_SETPOINT: 30, CONF_MAXIMUM_SETPOINT: 55},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator
    await climate.async_set_hvac_mode(HVACMode.OFF)
    await climate.async_control_heating_loop()

    assert climate.hvac_action == HVACAction.HEATING
    assert coordinator.setpoint == 30
    assert coordinator.device_active
    assert climate.extra_state_attributes is not None
    assert climate.extra_state_attributes["frost_protection_active"] is True

    # Half a degree warmer is not enough; a degree ends it
    hass.states.async_set("sensor.test_inside_sensor", "6.5")
    await climate.async_control_heating_loop()
    assert climate.hvac_action == HVACAction.HEATING
    hass.states.async_set("sensor.test_inside_sensor", "7.0")
    await climate.async_control_heating_loop()
    assert climate.hvac_action == HVACAction.OFF
    assert not coordinator.device_active
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_humid_room_raises_the_mould_risk(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(
        ROOM,
        HVACMode.HEAT,
        {"temperature": 21.0, "current_temperature": 21.0, "current_humidity": 65.0},
    )
    entry = await setup_rooms(hass)
    climate = entry.runtime_data.climate
    hass.states.async_set("sensor.test_outside_sensor", "0.0")
    await hass.async_block_till_done()

    for _ in range(13 * 12):
        # A reading older than six hours counts as a stalled sensor
        hass.states.async_set("sensor.test_outside_sensor", "0.0", force_update=True)
        climate._update_mould()
        freezer.tick(timedelta(minutes=5))

    attributes = climate.extra_state_attributes or {}
    assert attributes["mould_risk"][ROOM]["surface_humidity_24h"] >= 80
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"mould_risk_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["rooms"]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_mould_risk_reads_the_humidity_sensor_of_the_thermostat(
    hass: HomeAssistant,
) -> None:
    # Z-Wave thermostats report the humidity as a sensor of their device
    zwave = MockConfigEntry(domain="zwave_js")
    zwave.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=zwave.entry_id, identifiers={("zwave_js", "node-11")}
    )
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "climate", "zwave_js", "node-11-climate", device_id=device.id, suggested_object_id="room"
    )
    humidity = registry.async_get_or_create(
        "sensor",
        "zwave_js",
        "node-11-humidity",
        device_id=device.id,
        suggested_object_id="room_humidity",
        original_device_class="humidity",
    )
    hass.states.async_set(humidity.entity_id, "48.0")
    hass.states.async_set(ROOM, HVACMode.HEAT, {"temperature": 21.0, "current_temperature": 21.0})
    entry = await setup_rooms(hass)
    climate = entry.runtime_data.climate

    climate._update_mould()

    attributes = climate.extra_state_attributes or {}
    assert attributes["mould_risk"][ROOM]["dew_point"] == pytest.approx(9.6, abs=0.2)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_an_outdoor_humidity_sensor_feeds_the_airing_advice(hass: HomeAssistant) -> None:
    hass.states.async_set(
        ROOM,
        HVACMode.HEAT,
        {"temperature": 21.0, "current_temperature": 21.0, "current_humidity": 65.0},
    )
    hass.states.async_set("sensor.airly_humidity", "85.0")
    entry = await setup_rooms(hass, options={"outside_humidity_entity_id": "sensor.airly_humidity"})
    climate = entry.runtime_data.climate

    climate._update_mould()

    assert climate.airing is not None
    assert climate.airing["worth_airing"]
    assert hass.states.get("binary_sensor.mock_title_worth_airing") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
