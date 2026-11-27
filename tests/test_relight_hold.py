"""The heating ignition right after a cylinder reheat waits for the boiler to cool."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from custom_components.sat.climate import (
    HOT_WATER_RELIGHT_MAXIMUM_SECONDS,
    HOT_WATER_RELIGHT_MINIMUM_SECONDS,
    SatClimate,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def climate() -> SimpleNamespace:
    return SimpleNamespace(
        _coordinator=SimpleNamespace(
            heating_hot_water=False,
            hot_water_active=False,
            flame_active=False,
            boiler_temperature=30.0,
        ),
        minimum_setpoint_value=45.0,
        _relight_margin=10.0,
        _relight_hold_since=None,
        _relight_hot_water_seen=False,
    )


def hold(entity: SimpleNamespace) -> bool:
    return SatClimate._hold_relight_after_hot_water(cast("SatClimate", entity), on_phase=True)


def reheat(entity: SimpleNamespace, clock: Clock) -> None:
    """Heat the cylinder, then hand back with the flow still hot."""
    entity._coordinator.heating_hot_water = True
    entity._coordinator.hot_water_active = True
    entity._coordinator.flame_active = True
    entity._coordinator.boiler_temperature = 63.0
    # Held down already while the boiler flags the reheat
    assert hold(entity)
    clock.now += 5
    entity._coordinator.heating_hot_water = False
    entity._coordinator.hot_water_active = False
    entity._coordinator.flame_active = False
    # The control loop sees the end of the reheat at once
    assert hold(entity)


def test_no_reheat_lights_at_once() -> None:
    clock = Clock()
    entity = climate()
    with patch("custom_components.sat.climate.monotonic", clock):
        assert not hold(entity)


def test_the_ignition_waits_a_minute_and_for_the_flow_to_cool() -> None:
    clock = Clock()
    entity = climate()
    with patch("custom_components.sat.climate.monotonic", clock):
        reheat(entity, clock)

        # Cooled quickly, but the exchanger itself still needs the minute
        entity._coordinator.boiler_temperature = 34.0
        clock.now += HOT_WATER_RELIGHT_MINIMUM_SECONDS - 10
        assert hold(entity)

        clock.now += 10
        assert not hold(entity)
        # The hold ends once; the rest of the block lights normally
        entity._coordinator.boiler_temperature = 40.0
        assert not hold(entity)


def test_a_flow_that_stays_warm_waits_at_most_three_minutes() -> None:
    clock = Clock()
    entity = climate()
    with patch("custom_components.sat.climate.monotonic", clock):
        reheat(entity, clock)
        entity._coordinator.boiler_temperature = 40.0
        clock.now += HOT_WATER_RELIGHT_MAXIMUM_SECONDS - 1
        assert hold(entity)
        clock.now += 1
        assert not hold(entity)


def test_a_heating_burn_already_under_way_is_not_stopped() -> None:
    clock = Clock()
    entity = climate()
    with patch("custom_components.sat.climate.monotonic", clock):
        reheat(entity, clock)
        entity._coordinator.boiler_temperature = 45.0
        clock.now += 20
        entity._coordinator.flame_active = True
        assert not hold(entity)


def test_a_late_control_step_after_the_reheat_still_holds() -> None:
    # The boiler hands back between two control steps: the setpoint was already down during
    # the reheat, and the hold counts from the first step that sees the end
    clock = Clock()
    entity = climate()
    with patch("custom_components.sat.climate.monotonic", clock):
        entity._coordinator.heating_hot_water = True
        entity._coordinator.hot_water_active = True
        entity._coordinator.boiler_temperature = 60.0
        assert hold(entity)
        clock.now += 40
        entity._coordinator.heating_hot_water = False
        entity._coordinator.hot_water_active = False
        entity._coordinator.boiler_temperature = 40.0
        assert hold(entity)
        clock.now += HOT_WATER_RELIGHT_MINIMUM_SECONDS - 1
        entity._coordinator.boiler_temperature = 33.0
        assert hold(entity)
        clock.now += 1
        assert not hold(entity)


def test_an_unflagged_reheat_is_held_only_after_it() -> None:
    # Told from the burn alone, it may be a heating burn running hot: not stopped while it lasts
    clock = Clock()
    entity = climate()
    with patch("custom_components.sat.climate.monotonic", clock):
        entity._coordinator.heating_hot_water = True
        entity._coordinator.flame_active = True
        entity._coordinator.boiler_temperature = 60.0
        assert not hold(entity)
        clock.now += 5
        entity._coordinator.heating_hot_water = False
        entity._coordinator.flame_active = False
        assert hold(entity)


def test_a_zero_margin_never_holds() -> None:
    clock = Clock()
    entity = climate()
    entity._relight_margin = 0.0
    with patch("custom_components.sat.climate.monotonic", clock):
        entity._coordinator.heating_hot_water = True
        entity._coordinator.hot_water_active = True
        assert not hold(entity)
        entity._coordinator.heating_hot_water = False
        entity._coordinator.hot_water_active = False
        entity._coordinator.boiler_temperature = 60.0
        assert not hold(entity)


def test_a_wider_margin_waits_for_a_cooler_flow() -> None:
    clock = Clock()
    entity = climate()
    entity._relight_margin = 15.0
    with patch("custom_components.sat.climate.monotonic", clock):
        reheat(entity, clock)
        entity._coordinator.boiler_temperature = 34.0
        clock.now += HOT_WATER_RELIGHT_MINIMUM_SECONDS
        # 34 °C is 11 K below 45 °C: not yet 15 K
        assert hold(entity)
        entity._coordinator.boiler_temperature = 30.0
        assert not hold(entity)
