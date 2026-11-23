"""Tests for the warm weather shutdown, hot water schedule and loop measurement in the climate."""

from typing import TYPE_CHECKING, Any
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import State
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry, mock_restore_cache_with_extra_data

from custom_components.sat.climate import SatClimate
from custom_components.sat.config_flow import SatFlowHandler
from custom_components.sat.const import (
    CONF_GAS_PRICE,
    CONF_HEATING_CURVE_COEFFICIENT,
    CONF_HEATING_SYSTEM,
    CONF_MAXIMUM_SETPOINT,
    CONF_MINIMUM_SETPOINT,
    CONF_PRESENCE_ENTITY_IDS,
    CONF_WARM_WEATHER_SHUTDOWN,
    CONF_WINDOW_DETECTION,
    DOMAIN,
    HEATING_SYSTEM_UNDERFLOOR,
    MINIMUM_SETPOINT,
)
from custom_components.sat.fake import SatFakeCoordinator
from custom_components.sat.hot_water_schedule import HotWaterPlan, HotWaterSchedule
from custom_components.sat.window_detection import TemperatureDropDetector
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
    climate.warm_weather.restore(20.0, active=True)
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


ENTITY_ID = "climate.mock_title"


async def test_a_window_pause_ends_after_a_restart(hass: HomeAssistant) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(
                    ENTITY_ID,
                    HVACMode.HEAT,
                    {
                        "temperature": 10.0,
                        "preset_mode": "activity",
                        "pre_activity_temperature": 21.5,
                        "window_open_detected": True,
                    },
                ),
                {"hvac_mode": HVACMode.HEAT, "target_temperature": 10.0, "preset_mode": "activity"},
            )
        ],
    )
    entry, climate, _ = await setup(hass, {CONF_WINDOW_DETECTION: True})
    assert climate.preset_mode == "activity"
    assert climate.extra_state_attributes is not None
    assert climate.extra_state_attributes["window_open_detected"] is True

    # The pause runs out: the target from before the window comes back
    with patch.object(TemperatureDropDetector, "update", return_value=False):
        await climate.async_control_heating_loop()

    assert climate.native_target_temperature == 21.5
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_an_absence_ends_after_a_restart(hass: HomeAssistant) -> None:
    hass.states.async_set("person.anna", "not_home")
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(
                    ENTITY_ID,
                    HVACMode.HEAT,
                    {
                        "temperature": 10.0,
                        "preset_mode": "away",
                        "presence_previous_preset": "none",
                    },
                ),
                {
                    "hvac_mode": HVACMode.HEAT,
                    "target_temperature": 10.0,
                    "preset_mode": "away",
                    "pre_custom_temperature": 21.0,
                },
            )
        ],
    )
    entry, climate, _ = await setup(hass, {CONF_PRESENCE_ENTITY_IDS: ["person.anna"]})
    assert climate.preset_mode == "away"

    hass.states.async_set("person.anna", "home")
    await climate.async_control_heating_loop()

    assert climate.preset_mode == "none"
    assert climate.native_target_temperature == 21.0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_burner_power_follows_how_the_boiler_reports_modulation(
    hass: HomeAssistant,
) -> None:
    entry, climate, coordinator = await setup(hass, {})

    # Nothing tells the power: no invented heat, the budget counts in minimum-power units
    assert climate._known_heating_power() is None
    assert climate._heating_power() == 5.0

    with (
        patch.object(
            SatFakeCoordinator, "boiler_capacity", new_callable=PropertyMock, return_value=33.0
        ),
        patch.object(
            SatFakeCoordinator,
            "minimum_relative_modulation_value",
            new_callable=PropertyMock,
            return_value=16.0,
        ),
    ):
        coordinator._relative_modulation_value = 16
        power = climate._known_heating_power()
        assert power is not None
        assert abs(power - 9.72) < 0.01

        # Held at minimum power this boiler reads 16 %: that is its minimum, not 16 % of the range
        for _ in range(5):
            climate._modulation_scale.observe_minimum(16.0, 16.0)
        power = climate._known_heating_power()
        assert power is not None
        assert abs(power - 5.28) < 0.01

    assert hass.states.get("sensor.mock_title_estimated_water_flow") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_service_report_button_shows_a_report(hass: HomeAssistant) -> None:
    entry, climate, _ = await setup(hass, {})
    climate.boiler_stats.totals["starts"] = 1234

    with patch("custom_components.sat.button.persistent_notification.async_create") as notify:
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.mock_title_service_report"}, blocking=True
        )

    notify.assert_called_once()
    report = notify.call_args.args[1]
    assert "1234" in report
    assert "Service report" in report
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_the_daily_summary_and_airing_sensors_exist(hass: HomeAssistant) -> None:
    entry, _, _ = await setup(hass, {"weather_forecast_entity_id": "weather.home"})

    assert hass.states.get("sensor.mock_title_yesterday_s_summary") is not None
    assert hass.states.get("binary_sensor.mock_title_worth_airing") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
