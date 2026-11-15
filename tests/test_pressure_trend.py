"""Tests for following the heating water pressure over days."""

import math
from datetime import date, timedelta

from custom_components.sat.pressure_trend import PressureTrend

BAR_PER_K = 0.01


def feed(
    trend: PressureTrend,
    day: date,
    days: int,
    *,
    pressure: float,
    temperature: float,
    loss_per_day: float = 0.0,
    swing: float = 8.0,
) -> tuple[date, float]:
    """Feed whole days of a system whose pressure follows its water temperature."""
    for _ in range(days):
        for step in range(24 * 12):
            water = temperature + swing * math.sin(2 * math.pi * step / 36)
            reading = pressure + BAR_PER_K * (water - 30)
            trend.update(300, day.isoformat(), round(reading, 2), water)
        pressure -= loss_per_day
        day += timedelta(days=1)
    return day, pressure


def test_a_leak_shows_as_a_falling_pressure() -> None:
    trend = PressureTrend()
    day, pressure = feed(trend, date(2026, 11, 1), 3, pressure=1.5, temperature=30)
    feed(trend, day, 8, pressure=pressure, temperature=30, loss_per_day=0.02)

    assert trend.per_day is not None
    assert trend.per_day < -0.01
    assert trend.drop > 0.1


def test_the_end_of_the_heating_season_is_not_a_leak() -> None:
    trend = PressureTrend()
    day, _ = feed(trend, date(2026, 4, 1), 6, pressure=1.5, temperature=35)

    # The water cools by 15 K over a few days, which alone takes 0.15 bar off the reading
    for cooler in (30, 26, 23, 21, 20, 20):
        day, _ = feed(trend, day, 1, pressure=1.5, temperature=cooler, swing=1.0)

    assert abs(trend.coefficient - BAR_PER_K) < 0.003
    assert trend.per_day is not None
    assert abs(trend.per_day) < 0.005
    assert trend.drop < 0.06


def test_a_top_up_starts_a_new_history() -> None:
    trend = PressureTrend()
    day, pressure = feed(
        trend, date(2026, 11, 1), 8, pressure=1.4, temperature=30, loss_per_day=0.03
    )
    assert trend.per_day is not None

    feed(trend, day, 2, pressure=pressure + 0.5, temperature=30)

    assert trend.per_day is None
    assert trend.drop < 0.01


def test_the_history_survives_a_restart() -> None:
    trend = PressureTrend()
    feed(trend, date(2026, 11, 1), 8, pressure=1.5, temperature=30, loss_per_day=0.02)

    restored = PressureTrend()
    restored.load(trend.to_dict())

    assert restored.per_day == trend.per_day
    assert restored.coefficient == trend.coefficient
