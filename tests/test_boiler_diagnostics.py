"""Tests for the boiler repair issues."""

from typing import TYPE_CHECKING

from homeassistant.helpers import issue_registry as ir

from custom_components.sat.boiler_diagnostics import BoilerDiagnostics
from custom_components.sat.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def run(diagnostics: BoilerDiagnostics, hours: float, **readings: float | None) -> None:
    now = 0.0
    while now <= hours * 3600:
        diagnostics.update(
            now,
            pressure=readings.get("pressure", 1.5),
            fault=False,
            fault_code=None,
            exhaust=readings.get("exhaust"),
            return_temperature=readings.get("return_temperature"),
            settled_heating_burn=True,
        )
        now += 60


async def test_a_dirty_condensing_heat_exchanger_raises_an_issue(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    run(diagnostics, 8, exhaust=48.0, return_temperature=30.0)

    assert ir.async_get(hass).async_get_issue(DOMAIN, "heat_exchanger_fouling_entry")


async def test_a_non_condensing_boiler_is_not_reported(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    run(diagnostics, 8, exhaust=140.0, return_temperature=50.0)

    assert diagnostics.flue_return_gap is None
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "heat_exchanger_fouling_entry")


async def test_low_water_pressure_raises_an_issue(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    run(diagnostics, 0.5, pressure=0.6)

    assert ir.async_get(hass).async_get_issue(DOMAIN, "low_water_pressure_entry")
