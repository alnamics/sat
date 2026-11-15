"""Tests for the boiler totals, the gas cost and the gas per degree day check."""

from datetime import date, timedelta

from custom_components.sat.boiler_stats import BoilerStats


def run_day(stats: BoilerStats, start: float, day: date, *, gas: float, outdoor: float) -> float:
    """One day with the burner on for gas / 0.5 hours at 0.5 m³/h."""
    now, burn = start, gas / 0.5 * 3600
    while now < start + 86400:
        flame = now - start < burn
        stats.update(
            now=now,
            flame=flame,
            hot_water=False,
            heat_kw=5.0 if flame else None,
            gas_m3_per_hour=0.5 if flame else None,
            outdoor=outdoor,
            day=day.isoformat(),
            gas_price=4.0,
        )
        now += 300
    return now


def test_gas_cost_and_more_gas_per_degree_day() -> None:
    stats = BoilerStats()
    now, day = 0.0, date(2026, 10, 1)
    for _ in range(28):
        now = run_day(stats, now, day, gas=2.0, outdoor=8.0)
        day += timedelta(days=1)
    assert stats.gas_per_degree_day_ratio == 1.0

    for _ in range(8):
        now = run_day(stats, now, day, gas=3.0, outdoor=8.0)
        day += timedelta(days=1)

    assert abs(stats.totals["gas_cost"] - stats.totals["gas_m3"] * 4.0) < 1e-6
    ratio = stats.gas_per_degree_day_ratio
    assert ratio is not None
    assert 1.3 <= ratio <= 1.6
