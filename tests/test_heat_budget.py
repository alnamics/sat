"""Tests for the heat budget: dosing in blocks, carrying heat over and learning the heat loss."""

import math
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

from custom_components.sat.const import PWMStatus
from custom_components.sat.heat_budget import HeatBudget, HeatBudgetInputs, solar_elevation

MINIMUM_POWER = 5.28
WALL = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def inputs(now: float, **changes: Any) -> HeatBudgetInputs:  # noqa: ANN401
    values: dict[str, Any] = {
        "now": now,
        "wall_time": WALL + timedelta(seconds=now),
        "indoor": 22.0,
        "target": 22.0,
        "outdoor": 2.0,
        "heating_power_kw": MINIMUM_POWER,
        "minimum_power_kw": MINIMUM_POWER,
        "flame_active": False,
        "hot_water_active": False,
    }
    values.update(changes)
    return HeatBudgetInputs(**values)


def burn(budget: HeatBudget, start: float, seconds: float, **changes: Any) -> float:  # noqa: ANN401
    """Step the budget with the flame following its status."""
    now = start
    while now < start + seconds:
        hot_water = bool(changes.get("hot_water_active", False))
        flame = budget.status == PWMStatus.ON and not hot_water
        budget.update(inputs(now, **{**changes, "flame_active": flame}))
        now += 30
    return now


def test_the_heat_of_a_period_burns_in_one_block() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12)
    budget.update(inputs(1000))

    # 0.12 kW/K over 20 K is 2.4 kW, so about 27 minutes at 5.28 kW
    on_time, off_time = budget.duty_cycle
    assert 1500 <= on_time <= 1800
    assert on_time + off_time == 3600
    assert budget.status == PWMStatus.ON

    # Count ignitions from the status history, one sample per step
    statuses: list[PWMStatus] = [budget.status]
    now = 1030.0
    while now < 1000 + 6 * 3600:
        budget.update(inputs(now, flame_active=statuses[-1] == PWMStatus.ON))
        statuses.append(budget.status)
        now += 30
    starts = sum(
        1
        for before, after in pairwise(statuses)
        if after == PWMStatus.ON and before != PWMStatus.ON
    )
    assert 4 <= starts <= 6


def test_a_need_below_the_minimum_burn_is_carried_over() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12, minimum_burn_seconds=600)
    burn(budget, 1000, 4 * 3600, indoor=21.0, target=21.0, outdoor=20.5)

    assert budget.status == PWMStatus.OFF
    assert budget.attributes["heat_credit_kwh"] > 0.2


def test_a_high_need_burns_continuously() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.2)
    burn(budget, 1000, 3 * 3600, outdoor=-15.0)

    assert budget.duty_cycle == (3600, 0)
    assert budget.status == PWMStatus.ON


def test_hot_water_does_not_shorten_the_heating_block() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12)
    budget.update(inputs(1000))
    planned = budget.duty_cycle[0]

    heating_seconds = 0
    now = 1030.0
    while now < 1000 + 3600:
        hot_water = 1600 <= now < 2500
        budget.update(
            inputs(
                now,
                flame_active=budget.status == PWMStatus.ON and not hot_water,
                hot_water_active=hot_water,
            )
        )
        if budget.status == PWMStatus.ON and not hot_water:
            heating_seconds += 30
        now += 30

    assert abs(heating_seconds - planned) <= 120


def test_two_boiler_cut_outs_end_the_block() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12)
    budget.update(inputs(1000))
    budget.update(inputs(1030, flame_active=True))
    budget.update(inputs(1060, cut_short_burn_ends=(1045.0,)))
    assert budget.status == PWMStatus.ON

    budget.update(inputs(1700, cut_short_burn_ends=(1045.0, 1690.0)))
    assert budget.status == PWMStatus.OFF

    for now in range(1730, 4500, 30):
        budget.update(inputs(now))
    assert budget.status == PWMStatus.OFF


def test_the_heat_loss_is_learned() -> None:
    budget = HeatBudget()
    assert budget.attributes["heat_budget_ready"] is False

    # Two nodes: the screed takes the burner heat, the rooms lose 0.15 kW/K
    room, screed, now = 22.0, 26.0, 1000.0
    while now < 1000 + 4 * 86400:
        outdoor = 2 + 4 * math.sin(2 * math.pi * now / 86400)
        flame = budget.status == PWMStatus.ON if budget.ready else int(now // 1800) % 2 == 0
        budget.update(inputs(now, indoor=round(room, 1), outdoor=outdoor, flame_active=flame))
        floor = 0.65 * (screed - room)
        screed += ((MINIMUM_POWER if flame else 0) - floor) * (30 / 3600) / 2.4
        room += (floor - 0.15 * (room - outdoor)) * (30 / 3600) / 2.5
        now += 30

    assert budget.ready
    assert abs(budget.heat_loss - 0.15) < 0.015


def test_the_recovery_from_a_setback_starts_early() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12)
    change = WALL + timedelta(hours=6)
    schedule = {"comfort": False, "next_comfort_change": change, "setback": 1.5}

    budget.update(inputs(0, indoor=20.5, **schedule))
    assert budget.effective_target == 20.5

    preheat = budget.preheat_hours(1.5)
    budget.update(inputs(6 * 3600 - preheat * 3600 + 60, indoor=20.5, **schedule))
    assert budget.effective_target == 22.0


def test_comfort_ends_an_hour_early() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12)
    stop = WALL + timedelta(hours=10)
    schedule = {"comfort": True, "next_comfort_change": stop, "setback": 1.5}

    budget.update(inputs(10 * 3600 - 7200, **schedule))
    assert budget.effective_target == 22.0

    budget.update(inputs(10 * 3600 - 1800, **schedule))
    assert budget.effective_target == 20.5


def test_the_solar_elevation_matches_warsaw() -> None:
    noon_november = datetime(2026, 11, 14, 11, 0, tzinfo=UTC)
    noon_june = datetime(2026, 6, 21, 10, 55, tzinfo=UTC)

    assert abs(solar_elevation(noon_november, 52.23, 21.01) - 19.4) < 1.0
    assert abs(solar_elevation(noon_june, 52.23, 21.01) - 61.2) < 1.0


def test_a_house_beyond_the_minimum_power_is_handed_to_modulation() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.3)

    # 0.3 kW/K over 37 K is about 11 kW, twice the minimum power, and the room stays cold
    now = burn(budget, 0, 3600, indoor=20.5, outdoor=-15.0)
    assert not budget.overloaded
    now = burn(budget, now, 2 * 3600, indoor=20.5, outdoor=-15.0)
    assert budget.overloaded
    assert budget.attributes["heat_budget_overloaded"] is True

    # Modulation brings the room back, but the need stays above the minimum power
    now = burn(budget, now, 3 * 3600, outdoor=-15.0)
    assert budget.overloaded

    # A thaw ends it once the need has stayed low for an hour
    now = burn(budget, now, 1800, outdoor=12.0)
    assert budget.overloaded
    burn(budget, now, 3 * 3600, outdoor=12.0)
    assert not budget.overloaded


def test_a_warm_room_never_hands_over() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.3)
    burn(budget, 0, 6 * 3600, outdoor=-15.0)

    assert not budget.overloaded


def test_a_hot_water_reheat_brings_the_next_block_forward() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.1)
    budget.update(inputs(1000))
    on_time = budget.duty_cycle[0]

    # Let the block finish, then reheat hot water late in the period
    now = burn(budget, 1030, on_time + 600)
    assert budget.status == PWMStatus.OFF
    late = 1000 + 3600 - 900
    burn(budget, now, late - now)
    budget.update(inputs(late, hot_water_active=True, flame_active=True))
    budget.update(inputs(late + 300, hot_water_active=False))

    assert budget.status == PWMStatus.ON
    assert budget.attributes["hot_water_piggybacks"] == 1
