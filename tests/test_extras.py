"""Tests for hot water scheduling, warm weather shutdown, presence, window and curve advice."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.sat.const import HEATING_SYSTEM_UNDERFLOOR
from custom_components.sat.curve_advisor import CurveAdvisor
from custom_components.sat.heating_curve import HeatingCurve
from custom_components.sat.hot_water_schedule import (
    LEGIONELLA_TEMPERATURE,
    HotWaterPlan,
    HotWaterSchedule,
)
from custom_components.sat.presence import Occupancy, PresenceTracker, is_home
from custom_components.sat.warm_weather import WarmWeatherShutdown
from custom_components.sat.window_detection import TemperatureDropDetector

# A Sunday
SUNDAY = datetime(2026, 11, 15, 0, 0, tzinfo=ZoneInfo("Europe/Warsaw"))


def test_hot_water_follows_the_schedule() -> None:
    schedule = HotWaterSchedule(HotWaterPlan(comfort_temperature=50, eco_temperature=40))

    assert schedule.target(SUNDAY, comfort=True, temperature=48) == 50
    assert schedule.target(SUNDAY, comfort=False, temperature=48) == 40
    assert schedule.target(SUNDAY, comfort=None, temperature=48) == 50


def test_the_legionella_boost_holds_an_hour_once_a_week() -> None:
    schedule = HotWaterSchedule(
        HotWaterPlan(
            comfort_temperature=50,
            eco_temperature=40,
            legionella_weekday=6,
            legionella_start_seconds=3 * 3600,
        )
    )

    assert schedule.target(SUNDAY + timedelta(hours=2), comfort=False, temperature=45) == 40

    start = SUNDAY + timedelta(hours=3)
    assert schedule.target(start, comfort=False, temperature=45) == LEGIONELLA_TEMPERATURE
    assert schedule.boosting

    reached = start + timedelta(minutes=40)
    assert schedule.target(reached, comfort=False, temperature=59) == LEGIONELLA_TEMPERATURE
    held = reached + timedelta(minutes=61)
    assert schedule.target(held, comfort=False, temperature=60) == 40
    assert not schedule.boosting

    # Not again the same week, but the next one
    later = held + timedelta(hours=2)
    assert schedule.target(later, comfort=False, temperature=60) == 40
    next_week = start + timedelta(days=7)
    assert schedule.target(next_week, comfort=False, temperature=45) == LEGIONELLA_TEMPERATURE


def test_a_boost_that_never_heats_up_gives_up() -> None:
    schedule = HotWaterSchedule(
        HotWaterPlan(comfort_temperature=50, legionella_weekday=6, legionella_start_seconds=0)
    )
    assert schedule.target(SUNDAY, comfort=None, temperature=45) == LEGIONELLA_TEMPERATURE
    assert schedule.target(SUNDAY + timedelta(hours=4), comfort=None, temperature=50) == 50


def feed(
    shutdown: WarmWeatherShutdown, start: float, hours: float, outdoor: float, **kw: float
) -> float:
    now = start
    while now < start + hours * 3600:
        shutdown.update(now, outdoor, kw.get("forecast"))
        now += 300
    return now


def test_warm_weather_stops_and_restarts_the_heating() -> None:
    shutdown = WarmWeatherShutdown(16.0)

    # A warm reading right after a start does not stop the heating
    now = feed(shutdown, 0, 5, 20.0)
    assert not shutdown.active
    now = feed(shutdown, now, 2, 20.0)
    assert shutdown.active

    # A cool evening is not enough to restart it
    now = feed(shutdown, now, 3, 12.0)
    assert shutdown.active
    feed(shutdown, now, 48, 8.0)
    assert not shutdown.active


def test_a_cold_forecast_keeps_the_heating_on() -> None:
    shutdown = WarmWeatherShutdown(16.0)
    feed(shutdown, 0, 12, 18.0, forecast=8.0)
    assert not shutdown.active


def test_presence() -> None:
    assert is_home("home") is True
    assert is_home("not_home") is False
    assert is_home("2") is True
    assert is_home("0") is False
    assert is_home("unavailable") is None

    tracker = PresenceTracker(return_distance_km=10)
    assert tracker.update(0, home=False, distance_km=50) == Occupancy.HOME
    assert tracker.update(1900, home=False, distance_km=50) == Occupancy.AWAY
    assert tracker.update(5000, home=False, distance_km=8) == Occupancy.RETURNING
    assert tracker.update(6000, home=True, distance_km=0) == Occupancy.HOME


def test_a_fast_temperature_drop_means_an_open_window() -> None:
    detector = TemperatureDropDetector()

    # Slow cooling of a floor heated room is not a window
    for minute in range(60):
        assert not detector.update(minute * 60, 22.0 - minute * 0.005)

    assert not detector.update(3660, 21.6)
    assert detector.update(3900, 20.9)
    assert detector.update(3900 + 1700, 21.2)
    assert not detector.update(3900 + 1900, 21.4)


def test_the_curve_advice_matches_the_house() -> None:
    advisor = CurveAdvisor()
    curve = HeatingCurve(HEATING_SYSTEM_UNDERFLOOR, 1.3)
    assert advisor.suggest(curve, heat_loss_kw_per_k=0.12, target=22, water_flow_lpm=16) is None

    # 5.3 kW into a floor whose water runs 31 °C against a 22 °C room: 0.59 kW/K
    for _ in range(30):
        advisor.update(heat_kw=5.3, flow=33.5, return_temperature=28.5, indoor=22.0)

    suggested = advisor.suggest(curve, heat_loss_kw_per_k=0.12, target=22, water_flow_lpm=16)
    assert suggested is not None
    assert 0.5 <= suggested <= 2.5
