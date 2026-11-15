"""Tests for the warm weather shutdown, hot water schedule and loop measurement in the climate."""

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sat.climate import SatClimate
from custom_components.sat.config_flow import SatFlowHandler
from custom_components.sat.const import (
    CONF_GAS_PRICE,
    CONF_HEATING_CURVE_COEFFICIENT,
    CONF_HEATING_SYSTEM,
    CONF_MAXIMUM_SETPOINT,
    CONF_MINIMUM_SETPOINT,
    CONF_WARM_WEATHER_SHUTDOWN,
    DOMAIN,
    HEATING_SYSTEM_UNDERFLOOR,
    MINIMUM_SETPOINT,
)
from custom_components.sat.fake import SatFakeCoordinator
from custom_components.sat.hot_water_schedule import HotWaterPlan, HotWaterSchedule
from custom_components.sat.warm_weather import WarmWeatherShutdown
from tests.const import DEFAULT_USER_DATA

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def setup(
    hass: HomeAssistant, options: dict[str, Any]
) -> tuple[MockConfigEntry, SatClimate, SatFakeCoordinator]:
    hass.states.async_set("sensor.test_inside_sensor", "20.0")
    hass.states.async_set("sensor.test_outside_sensor", "18.0")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=SatFlowHandler.VERSION,
        data={
            **DEFAULT_USER_DATA,
            CONF_HEATING_SYSTEM: HEATING_SYSTEM_UNDERFLOOR,
            CONF_MINIMUM_SETPOINT: 30,
        },
        options={CONF_HEATING_CURVE_COEFFICIENT: 1.3, CONF_MAXIMUM_SETPOINT: 45, **options},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate = entry.runtime_data.climate
    coordinator = entry.runtime_data.coordinator
    assert isinstance(climate, SatClimate)
    assert isinstance(coordinator, SatFakeCoordinator)
    return entry, climate, coordinator


async def test_warm_weather_switches_central_heating_off(hass: HomeAssistant) -> None:
    entry, climate, coordinator = await setup(hass, {CONF_WARM_WEATHER_SHUTDOWN: 16})
    assert climate.warm_weather is not None

    await climate.async_set_target_temperature(22.0)
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    with patch.object(WarmWeatherShutdown, "update", return_value=True):
        await climate.async_control_heating_loop()

    assert coordinator.setpoint == MINIMUM_SETPOINT
    assert not coordinator.device_active
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_hot_water_schedule_sends_the_setpoint(hass: HomeAssistant) -> None:
    entry, climate, coordinator = await setup(hass, {})
    coordinator.config.supports_hot_water_setpoint_management = True
    climate.hot_water_schedule = HotWaterSchedule(HotWaterPlan(comfort_temperature=48))

    await climate.async_control_heating_loop()

    assert climate.extra_state_attributes is not None
    assert climate.extra_state_attributes["hot_water_setpoint_sent"] == 48
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_loop_measurement_needs_room_thermostats(hass: HomeAssistant) -> None:
    entry, climate, _ = await setup(hass, {})
    await climate.async_set_hvac_mode(HVACMode.HEAT)

    with pytest.raises(ServiceValidationError):
        await climate.async_measure_loops()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_gas_price_adds_the_cost_sensor(hass: HomeAssistant) -> None:
    entry, _, _ = await setup(hass, {CONF_GAS_PRICE: 4.2, "minimum_consumption": 0.5})

    state = hass.states.get("sensor.mock_title_estimated_gas_cost")
    assert state is not None
    assert state.attributes["unit_of_measurement"] == hass.config.currency
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_efficiency_sensor_exists(hass: HomeAssistant) -> None:
    entry, climate, _ = await setup(hass, {})

    state = hass.states.get("sensor.mock_title_estimated_boiler_efficiency")
    assert state is not None
    assert state.attributes["unit_of_measurement"] == "%"

    climate.efficiency.update(0, flame=True, hot_water=False, exhaust=33.0, return_temperature=29)
    assert climate.efficiency.current is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
