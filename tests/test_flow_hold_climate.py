"""The climate holds a heating ignition with heating left enabled, so the pump runs."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import PropertyMock, patch

from homeassistant.components.climate import HVACMode
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sat.climate import MINIMUM_SETPOINT
from custom_components.sat.const import (
    CONF_FORCE_PULSE_WIDTH_MODULATION,
    CONF_HEATING_CURVE_COEFFICIENT,
    CONF_HEATING_SYSTEM,
    CONF_MAXIMUM_SETPOINT,
    CONF_MINIMUM_SETPOINT,
    CONF_ROOMS,
    DOMAIN,
    HEATING_SYSTEM_RADIATORS,
    PWMStatus,
)
from custom_components.sat.fake import SatFakeCoordinator
from tests.const import DEFAULT_USER_DATA

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

ROOM = "climate.room"
HEATING = {"hvac_action": "heating", "temperature": 23.0, "current_temperature": 19.0}


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set("sensor.test_inside_sensor", "20.9")
    hass.states.async_set("sensor.test_outside_sensor", "9.9")
    hass.states.async_set(ROOM, HVACMode.HEAT, HEATING)
    data: dict[str, Any] = {
        **DEFAULT_USER_DATA,
        CONF_ROOMS: [ROOM],
        CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS,
        CONF_MINIMUM_SETPOINT: 57,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options={
            CONF_HEATING_CURVE_COEFFICIENT: 1.8,
            CONF_FORCE_PULSE_WIDTH_MODULATION: True,
            CONF_MAXIMUM_SETPOINT: 75,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate = entry.runtime_data.climate
    await entry.runtime_data.coordinator.async_set_boiler_temperature(57)
    await climate.async_set_target_temperature(21.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    return entry


async def test_the_hold_after_hot_water_keeps_the_pump_running(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator

    with (
        patch.object(
            SatFakeCoordinator, "heating_hot_water", new_callable=PropertyMock
        ) as hot_water,
        patch.object(SatFakeCoordinator, "hot_water_active", new_callable=PropertyMock) as flagged,
        patch.object(SatFakeCoordinator, "flame_active", new_callable=PropertyMock) as flame,
    ):
        hot_water.return_value = False
        flagged.return_value = False
        flame.return_value = False
        await climate.async_control_heating_loop()
        assert climate.pwm.status == PWMStatus.ON
        assert coordinator.setpoint == 57

        # A cylinder reheat: the heating setpoint is down already, with heating enabled
        hot_water.return_value = True
        flagged.return_value = True
        await climate.async_control_heating_loop()
        assert coordinator.setpoint == MINIMUM_SETPOINT
        assert coordinator.device_active

        # The hand back with the heat exchanger still hot
        hot_water.return_value = False
        flagged.return_value = False
        await coordinator.async_set_boiler_temperature(62)
        await climate.async_control_heating_loop()

        assert climate.pwm.status == PWMStatus.ON
        assert coordinator.setpoint == MINIMUM_SETPOINT
        # Heating stays enabled while it holds, so the pump carries the heat away
        assert coordinator.device_active

        # A minute on, the flow is down to 10 °C below the on-phase setpoint: it lights
        freezer.tick(timedelta(seconds=61))
        await coordinator.async_set_boiler_temperature(46)
        await climate.async_control_heating_loop()
        assert coordinator.setpoint == 57
        assert coordinator.device_active

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_block_waits_for_flow_with_heating_enabled(hass: HomeAssistant) -> None:
    entry = await setup(hass)
    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator
    # Ignitions with only this room open were cut out
    climate.flow_guard.restore({ROOM: [3.0, 3.0]})

    with patch.object(SatFakeCoordinator, "flame_active", new_callable=PropertyMock) as flame:
        flame.return_value = False
        await climate.async_control_heating_loop()

        assert climate.pwm.status == PWMStatus.ON
        assert coordinator.setpoint == MINIMUM_SETPOINT
        assert coordinator.device_active
        attributes = climate.extra_state_attributes
        assert attributes is not None
        assert attributes["flow_guard_sets"] == {ROOM: [3.0, 3.0]}
        assert attributes["flow_guard_waits"] == 1

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_valve_switching_each_minute_is_not_an_open_loop(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    climate = entry.runtime_data.climate
    other = "climate.other"

    # The room open since startup counts; one that just started asking does not yet
    assert climate._open_room_loops() == frozenset({ROOM})
    climate._loops.seen(other, open_=True, now=climate_now())
    assert climate._open_room_loops() == frozenset({ROOM})

    # Asking for heat for a minute, then a pause: never long enough to count
    for _ in range(5):
        freezer.tick(timedelta(seconds=60))
        climate._loops.seen(other, open_=False, now=climate_now())
        freezer.tick(timedelta(seconds=10))
        climate._loops.seen(other, open_=True, now=climate_now())
        assert other not in climate._open_room_loops()

    # Three minutes without a break: open
    freezer.tick(timedelta(seconds=181))
    assert climate._open_room_loops() == frozenset({ROOM, other})

    # Closing the first room is seen through the state change
    hass.states.async_set(ROOM, HVACMode.HEAT, {**HEATING, "hvac_action": "idle"})
    await hass.async_block_till_done()
    assert climate._open_room_loops() == frozenset({other})

    assert await hass.config_entries.async_unload(entry.entry_id)


def climate_now() -> float:
    from custom_components.sat import climate  # noqa: PLC0415

    return climate.monotonic()
