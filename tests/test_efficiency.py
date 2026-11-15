"""Tests for the boiler efficiency estimate."""

from itertools import pairwise

from custom_components.sat.efficiency import (
    PROPANE,
    EfficiencyTracker,
    fuel_for,
    gross_efficiency,
)


def test_a_cool_flue_condenses_and_a_hot_one_does_not() -> None:
    # Published gross efficiencies of condensing boilers: about 97 % at a 30 °C return,
    # 91 % at 50 °C, and 88 % or less once the flue is above the dew point
    assert 0.965 <= gross_efficiency(30) <= 0.98
    assert 0.90 <= gross_efficiency(50) <= 0.925
    assert 0.875 <= gross_efficiency(65) <= 0.895
    assert gross_efficiency(150) < gross_efficiency(65)


def test_the_estimate_falls_with_the_flue_temperature() -> None:
    values = [gross_efficiency(t) for t in range(20, 200, 5)]
    assert all(a >= b for a, b in pairwise(values))


def test_propane_is_chosen_by_its_energy_content() -> None:
    assert fuel_for(24.0) is PROPANE
    assert fuel_for(10.2) is not PROPANE


def test_the_tracker_uses_the_exhaust_then_the_return() -> None:
    tracker = EfficiencyTracker()
    tracker.update(0, flame=True, hot_water=False, exhaust=33.0, return_temperature=29.0)
    assert tracker.source == "exhaust"
    assert tracker.current is not None
    assert 0.96 <= tracker.current <= 0.97

    tracker.update(60, flame=True, hot_water=True, exhaust=None, return_temperature=50.0)
    assert tracker.source == "return"
    assert tracker.hot_water_average is not None
    assert tracker.hot_water_average < 0.92
    assert tracker.attributes["heating_average"] == 96.6


def test_no_estimate_for_a_non_condensing_boiler_without_a_flue_sensor() -> None:
    tracker = EfficiencyTracker(condensing=False)
    tracker.update(0, flame=True, hot_water=False, exhaust=None, return_temperature=50.0)
    assert tracker.current is None

    tracker.update(60, flame=True, hot_water=False, exhaust=140.0, return_temperature=50.0)
    assert tracker.current is not None
    assert tracker.current < 0.88
