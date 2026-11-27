"""Tests for the boiler repair issues."""

from datetime import date, timedelta
from time import monotonic, time
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from homeassistant.helpers import issue_registry as ir

from custom_components.sat.boiler_diagnostics import BoilerDiagnostics, add_months
from custom_components.sat.const import DOMAIN
from custom_components.sat.curve_advisor import CurveAdvisor

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


async def test_frequent_flame_losses_raise_an_issue(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")

    def update(losses: int) -> None:
        diagnostics.update(
            0.0,
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=None,
            return_temperature=None,
            settled_heating_burn=False,
            flame_losses_last_day=losses,
        )

    update(5)
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "frequent_flame_loss_entry")
    update(7)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "frequent_flame_loss_entry")
    # It stays up until the flame holds again
    update(4)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "frequent_flame_loss_entry")
    update(1)
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "frequent_flame_loss_entry")


def burn_with_cylinder(diagnostics: BoilerDiagnostics, start: float, drop: float) -> float:
    """Ten idle minutes, then a twenty minute heating burn that cools the cylinder."""
    now = start
    for _ in range(10):
        diagnostics.update(
            now,
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=None,
            return_temperature=None,
            settled_heating_burn=False,
            cylinder_temperature=50.0,
        )
        now += 60
    for minute in range(20):
        diagnostics.update(
            now,
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=None,
            return_temperature=None,
            settled_heating_burn=False,
            heating_burn=True,
            cylinder_temperature=50.0 - (drop if minute >= 2 else 0.0),
        )
        now += 60
    return now


async def test_a_cylinder_cooled_by_heating_raises_an_issue(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    now = 0.0
    for _ in range(4):
        now = burn_with_cylinder(diagnostics, now, 3.5)
    # Too few burns yet
    assert diagnostics.cylinder_drop is None
    now = burn_with_cylinder(diagnostics, now, 3.5)
    assert diagnostics.cylinder_drop == 3.5
    assert ir.async_get(hass).async_get_issue(DOMAIN, "cylinder_cools_in_heating_entry")

    # After the valve is fixed the drop goes away
    for _ in range(10):
        now = burn_with_cylinder(diagnostics, now, 0.2)
    assert diagnostics.cylinder_drop == 0.2
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "cylinder_cools_in_heating_entry")


async def test_a_cylinder_reheat_is_not_counted(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    now = 0.0
    for _ in range(8):
        for second in range(0, 1800, 60):
            diagnostics.update(
                now + second,
                pressure=1.5,
                fault=False,
                fault_code=None,
                exhaust=None,
                return_temperature=None,
                settled_heating_burn=False,
                heating_burn=second >= 600,
                hot_water=600 <= second < 900,
                cylinder_temperature=40.0 if second >= 900 else 50.0,
            )
        now += 1800
    assert diagnostics.cylinder_drop is None


async def test_low_water_pressure_raises_an_issue(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    run(diagnostics, 0.5, pressure=0.6)

    assert ir.async_get(hass).async_get_issue(DOMAIN, "low_water_pressure_entry")


async def test_a_slowly_falling_pressure_raises_an_issue(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    start, now = date(2026, 11, 1), 0.0
    for day in range(8):
        for _ in range(24 * 12):
            diagnostics.update(
                now,
                pressure=1.3 - day * 0.02,
                fault=False,
                fault_code=None,
                exhaust=None,
                return_temperature=None,
                settled_heating_burn=False,
                today=start + timedelta(days=day),
                system_temperature=30.0,
            )
            now += 300

    assert diagnostics.pressure_trend_per_week is not None
    assert diagnostics.pressure_trend_per_week < -0.1
    assert ir.async_get(hass).async_get_issue(DOMAIN, "pressure_falling_entry")


async def test_flow_water_too_hot_for_the_screed(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT", screed_limit=55)
    for second in range(0, 600, 30):
        diagnostics.update(
            float(second),
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=None,
            return_temperature=None,
            settled_heating_burn=False,
            flow=58.0,
            heating_burn=True,
        )

    assert ir.async_get(hass).async_get_issue(DOMAIN, "screed_overheat_entry")


def spread(diagnostics: BoilerDiagnostics) -> None:
    """Ten minutes of a settled burn with the flow 23 K above the return."""
    for second in range(0, 600, 30):
        diagnostics.update(
            float(second),
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=None,
            return_temperature=25.0,
            settled_heating_burn=True,
            flow=48.0,
            heating_burn=True,
        )


async def test_a_wide_spread_is_normal_for_radiators(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    spread(diagnostics)

    assert not ir.async_get(hass).async_get_issue(DOMAIN, "low_water_flow_entry")


async def test_the_heat_exchanger_is_only_judged_near_minimum_power(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    now = 0.0
    while now <= 8 * 3600:
        diagnostics.update(
            now,
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=58.0,
            return_temperature=40.0,
            settled_heating_burn=True,
            near_minimum_power=False,
        )
        now += 60

    assert diagnostics.flue_return_gap is None
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "heat_exchanger_fouling_entry")


async def test_too_little_water_flow(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT", underfloor=True)
    for second in range(0, 600, 30):
        diagnostics.update(
            float(second),
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=None,
            return_temperature=25.0,
            settled_heating_burn=True,
            flow=48.0,
            heating_burn=True,
        )

    assert ir.async_get(hass).async_get_issue(DOMAIN, "low_water_flow_entry")


async def test_service_and_gas_use_issues(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT", last_service=date(2025, 11, 1))
    diagnostics.update(
        0.0,
        pressure=1.5,
        fault=False,
        fault_code=None,
        exhaust=None,
        return_temperature=None,
        settled_heating_burn=False,
        today=date(2026, 11, 15),
        gas_use_ratio=1.4,
    )

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "boiler_service_due_entry")
    assert registry.async_get_issue(DOMAIN, "gas_use_increased_entry")


def test_add_months_keeps_the_end_of_the_month() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 15), 12) == date(2027, 11, 15)


def test_the_curve_advisor_continues_after_a_restart() -> None:
    advisor = CurveAdvisor()
    assert advisor.transfer_kw_per_k is None
    advisor.restore(0.625)
    assert advisor.transfer_kw_per_k == 0.625
    # Learning goes on from there
    advisor.update(heat_kw=5.3, flow=36.0, return_temperature=31.0, indoor=22.0)
    transfer = advisor.transfer_kw_per_k
    assert transfer is not None
    assert transfer < 0.625


async def test_the_water_meter_keeps_taps_out_and_counts_dry_reheats(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    now, litres = 0.0, 1000.0

    def step(*, burn: bool = False, hot_water: bool = False, cylinder: float = 50.0) -> None:
        nonlocal now
        diagnostics.update(
            now,
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=None,
            return_temperature=None,
            settled_heating_burn=False,
            heating_burn=burn,
            hot_water=hot_water,
            cylinder_temperature=cylinder,
            water_litres=litres,
        )
        now += 60

    # Five heating starts, each with a shower running: no sample
    for _ in range(5):
        for _ in range(10):
            step()
        for minute in range(15):
            if minute < 5:
                litres += 8
            step(burn=True, cylinder=50.0 - (6.0 if minute >= 2 else 0.0))
    assert diagnostics.cylinder_drop is None

    # An hour later the cylinder is reheated with no water drawn
    for _ in range(70):
        step()
    step(hot_water=True)
    step(hot_water=True)
    attributes = diagnostics.attributes
    assert attributes["cylinder_reheats_24h"] == 1
    assert attributes["cylinder_reheats_without_draw_24h"] == 1

    # A reheat right after a tap is not dry
    litres += 10
    step()
    step(hot_water=True)
    attributes = diagnostics.attributes
    assert attributes["cylinder_reheats_24h"] == 2
    assert attributes["cylinder_reheats_without_draw_24h"] == 1


async def test_without_a_water_meter_no_reheat_counts_are_shown(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    run(diagnostics, 0.1)
    assert "cylinder_reheats_24h" not in diagnostics.attributes


async def test_the_last_day_of_reheats_survives_a_restart(hass: HomeAssistant) -> None:
    diagnostics = BoilerDiagnostics(hass, "entry", "SAT")
    start = monotonic()

    def step(target: BoilerDiagnostics, now: float, litres: float, *, hot_water: bool) -> None:
        target.update(
            now,
            pressure=1.5,
            fault=False,
            fault_code=None,
            exhaust=None,
            return_temperature=None,
            settled_heating_burn=False,
            hot_water=hot_water,
            water_litres=litres,
        )

    # Two dry reheats and one after a shower, all within the last few hours
    now = start - 4 * 3600
    step(diagnostics, now, 1000.0, hot_water=False)
    step(diagnostics, now + 60, 1000.0, hot_water=True)
    step(diagnostics, now + 7200, 1000.0, hot_water=False)
    step(diagnostics, now + 7260, 1000.0, hot_water=True)
    step(diagnostics, now + 9000, 1020.0, hot_water=False)
    step(diagnostics, now + 9060, 1020.0, hot_water=True)
    step(diagnostics, start, 1020.0, hot_water=False)
    assert diagnostics.attributes["cylinder_reheats_24h"] == 3
    saved = diagnostics._data()

    class FakeStore:
        async def async_load(self) -> dict[str, Any]:
            return saved

    restarted = BoilerDiagnostics(hass, "entry", "SAT")
    with patch(
        "custom_components.sat.boiler_diagnostics.boiler_diagnostics_store",
        return_value=FakeStore(),
    ):
        await restarted.async_initialize()
    step(restarted, monotonic(), 1020.0, hot_water=False)

    attributes = restarted.attributes
    assert attributes["cylinder_reheats_24h"] == 3
    assert attributes["cylinder_reheats_without_draw_24h"] == 2


async def test_reheats_older_than_a_day_are_not_restored(hass: HomeAssistant) -> None:
    saved = {"reheats": [[time() - 30 * 3600, True], [time() - 3600, True], ["x", True]]}

    class FakeStore:
        async def async_load(self) -> dict[str, Any]:
            return saved

    restarted = BoilerDiagnostics(hass, "entry", "SAT")
    with patch(
        "custom_components.sat.boiler_diagnostics.boiler_diagnostics_store",
        return_value=FakeStore(),
    ):
        await restarted.async_initialize()
    restarted.update(
        monotonic(),
        pressure=1.5,
        fault=False,
        fault_code=None,
        exhaust=None,
        return_temperature=None,
        settled_heating_burn=False,
        hot_water=False,
        water_litres=500.0,
    )
    assert restarted.attributes["cylinder_reheats_24h"] == 1
