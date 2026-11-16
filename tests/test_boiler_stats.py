"""Tests for the boiler totals and the gas cost."""

from custom_components.sat.boiler_stats import BoilerStats


def run(stats: BoilerStats, start: float, seconds: float, **changes: float | bool | None) -> float:
    now = start
    while now < start + seconds:
        stats.update(
            now=now,
            flame=bool(changes.get("flame", True)),
            hot_water=bool(changes.get("hot_water", False)),
            heat_kw=changes.get("heat_kw", 5.0),
            gas_m3_per_hour=changes.get("gas", 0.5),
            outdoor=8.0,
            indoor=21.0,
            day="2026-11-15",
            gas_price=4.0,
        )
        now += 60
    return now


def test_heat_gas_and_cost_are_counted_per_use() -> None:
    stats = BoilerStats()
    now = run(stats, 0, 3600)
    now = run(stats, now, 1800, hot_water=True, heat_kw=16.0, gas=1.6)
    run(stats, now, 3600, flame=False, heat_kw=None, gas=None)

    assert abs(stats.totals["heating_kwh"] - 5.0) < 0.1
    assert abs(stats.totals["hot_water_kwh"] - 8.0) < 0.3
    assert abs(stats.totals["gas_m3"] - (0.5 + 0.8)) < 0.03
    assert abs(stats.totals["gas_cost"] - stats.totals["gas_m3"] * 4.0) < 1e-6
    assert abs(stats.totals["burn_hours"] - 1.5) < 0.02
    # 10 K below the 18 °C base for two and a half hours
    assert abs(stats.totals["degree_days"] - 10 * 2.5 / 24) < 0.01


def test_an_unknown_burner_power_counts_no_heat_or_gas() -> None:
    stats = BoilerStats()
    run(stats, 0, 3600, heat_kw=None, gas=None)

    assert stats.totals["heating_kwh"] == 0.0
    assert stats.totals["gas_m3"] == 0.0
    assert stats.totals["burn_hours"] > 0.9


def test_cylinder_drop_at_heating_start_is_blamed_on_heating() -> None:
    stats = BoilerStats()
    now = 0.0

    def step(temperature: float, started: float | None, stopped: float | None) -> None:
        nonlocal now
        stats.update(
            now=now,
            flame=False,
            hot_water=False,
            heat_kw=None,
            gas_m3_per_hour=None,
            outdoor=5.0,
            hot_water_temperature=temperature,
            heating_started_at=started,
            heating_stopped_at=stopped,
        )
        now += 60

    step(50.0, None, None)
    # Heating starts and the cylinder loses 3 K at once
    started = now
    step(47.0, started, None)
    assert stats.hot_water_drops_after_heating_start == 1

    # Heating stopped long ago and started long ago: a drop now is tapping
    now += 3600
    step(44.0, started, started + 900)
    assert stats.hot_water_drops == 2
    assert stats.hot_water_drops_after_heating == 1

    # A drop right after the stop goes to the stop, the later of the two changes
    stopped = now
    step(42.0, stopped - 300, stopped)
    assert stats.hot_water_drops_after_heating_stop == 1
    assert stats.hot_water_drops_after_heating == 2
