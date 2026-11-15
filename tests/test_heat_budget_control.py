"""Tests for how the heat budget takes and hands back the control of the boiler."""

from typing import TYPE_CHECKING, Any
from unittest.mock import PropertyMock, patch

from homeassistant.components.climate import HVACMode
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sat.budget_pwm import BudgetPWM
from custom_components.sat.climate import SatClimate
from custom_components.sat.config_flow import SatFlowHandler
from custom_components.sat.const import (
    CONF_FORCE_PULSE_WIDTH_MODULATION,
    CONF_HEAT_BUDGET_MODE,
    CONF_HEAT_LOSS_COEFFICIENT,
    CONF_HEATING_CURVE_COEFFICIENT,
    CONF_HEATING_SYSTEM,
    CONF_MAXIMUM_SETPOINT,
    CONF_MINIMUM_SETPOINT,
    CONF_OVERSHOOT_PROTECTION,
    DOMAIN,
    HEAT_BUDGET_ON,
    HEATING_SYSTEM_RADIATORS,
    HEATING_SYSTEM_UNDERFLOOR,
    PWMStatus,
)
from custom_components.sat.heat_budget import HeatBudget
from tests.const import DEFAULT_USER_DATA

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def setup_budget(
    hass: HomeAssistant, heating_system: str, options: dict[str, Any]
) -> tuple[MockConfigEntry, SatClimate]:
    hass.states.async_set("sensor.test_inside_sensor", "20.9")
    hass.states.async_set("sensor.test_outside_sensor", "-15.0")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=SatFlowHandler.VERSION,
        data={
            **DEFAULT_USER_DATA,
            CONF_HEATING_SYSTEM: heating_system,
            CONF_MINIMUM_SETPOINT: 45,
            # Without overshoot protection the normal control never uses low-load cycles
            CONF_OVERSHOOT_PROTECTION: False,
        },
        options={
            CONF_HEATING_CURVE_COEFFICIENT: 1.3,
            CONF_MAXIMUM_SETPOINT: 45,
            CONF_HEAT_BUDGET_MODE: HEAT_BUDGET_ON,
            CONF_HEAT_LOSS_COEFFICIENT: 120,
            **options,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    climate = entry.runtime_data.climate
    assert isinstance(climate, SatClimate)
    return entry, climate


async def test_the_budget_drives_underfloor_heating(hass: HomeAssistant) -> None:
    entry, climate = await setup_budget(hass, HEATING_SYSTEM_UNDERFLOOR, {})

    assert isinstance(climate.pwm, BudgetPWM)
    assert climate.heat_budget is not None
    assert climate.heat_budget.ready
    assert climate.pulse_width_modulation_enabled
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_an_overloaded_budget_hands_over_to_modulation(hass: HomeAssistant) -> None:
    entry, climate = await setup_budget(
        hass, HEATING_SYSTEM_UNDERFLOOR, {CONF_FORCE_PULSE_WIDTH_MODULATION: True}
    )

    # Even with Force PWM the boiler may modulate while the house needs more than the minimum
    with patch.object(HeatBudget, "overloaded", new_callable=PropertyMock, return_value=True):
        assert not climate.pulse_width_modulation_enabled
        await climate.async_set_target_temperature(21.0)
        await climate.async_set_hvac_mode(HVACMode.HEAT)
        await climate.async_control_heating_loop()
        assert climate.pwm.status == PWMStatus.IDLE

    assert climate.pulse_width_modulation_enabled
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_radiators_only_learn(hass: HomeAssistant) -> None:
    entry, climate = await setup_budget(hass, HEATING_SYSTEM_RADIATORS, {})

    assert climate.heat_budget is not None
    assert not isinstance(climate.pwm, BudgetPWM)
    assert climate.extra_state_attributes is not None
    assert climate.extra_state_attributes["heat_budget_mode"] == "shadow"
    assert not climate.pulse_width_modulation_enabled
    assert await hass.config_entries.async_unload(entry.entry_id)
