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


def test_brief_glitches_do_not_make_a_trend() -> None:
    # A steady system whose gauge reads 1.1 instead of 1.6 bar for an hour on the later days
    clean, glitchy = PressureTrend(), PressureTrend()
    day = date(2026, 11, 1)
    for index in range(10):
        for step in range(24 * 12):
            reading = 1.6
            if index >= 5 and 120 <= step < 132:
                reading = 1.1
            clean.update(300, day.isoformat(), 1.6, 40.0)
            glitchy.update(300, day.isoformat(), reading, 40.0)
        day += timedelta(days=1)

    assert glitchy.per_day is not None
    assert abs(glitchy.per_day) < 0.001
    assert glitchy.drop < 0.005
    assert glitchy.spikes == 5 * 12
    assert glitchy.coefficient == clean.coefficient


def test_a_glitch_in_the_first_hour_of_a_day_still_counts() -> None:
    # Too little of the day is known yet to call a reading a glitch
    trend = PressureTrend()
    trend.update(300, "2026-11-01", 1.6, 40.0)
    trend.update(300, "2026-11-01", 1.1, 40.0)
    assert trend.spikes == 0


def test_a_top_up_during_the_day_shows_the_next_day() -> None:
    trend = PressureTrend()
    day, pressure = feed(
        trend, date(2026, 11, 1), 8, pressure=1.3, temperature=30, loss_per_day=0.03
    )
    assert trend.per_day is not None
    assert trend.per_day < 0

    # Topped up at noon: the rest of that day is left out, the next day starts a new history
    for step in range(24 * 12):
        reading = pressure if step < 144 else pressure + 0.5
        trend.update(300, day.isoformat(), reading, 30.0)
    day += timedelta(days=1)
    day, _ = feed(trend, day, 1, pressure=pressure + 0.5, temperature=30, swing=1.0)
    # The first reading of the following day closes the day before
    trend.update(300, day.isoformat(), pressure + 0.5, 30.0)

    assert trend.per_day is None
    assert trend.latest is not None
    assert trend.latest > pressure + 0.4
