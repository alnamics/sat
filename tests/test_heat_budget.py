"""Tests for the heat budget: dosing in blocks, carrying heat over and learning the heat loss."""

import math
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.sat.const import PWMStatus
from custom_components.sat.heat_budget import HeatBudget, HeatBudgetInputs, _Hour, solar_elevation

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


def test_four_flame_losses_end_the_block_and_keep_the_heat_owed() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12)
    budget.update(inputs(1000))
    budget.update(inputs(1030, flame_active=True))
    losses = (1100.0, 1200.0, 1300.0)
    budget.update(inputs(1310, flame_loss_ends=losses))
    assert budget.status == PWMStatus.ON
    credit = budget.attributes["heat_credit_kwh"]

    budget.update(inputs(1410, flame_loss_ends=(*losses, 1400.0)))
    assert budget.status == PWMStatus.OFF
    # Unlike a cut-out, a lost flame does not cap what is still owed
    assert budget.attributes["heat_credit_kwh"] >= credit


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


def sunny_days(budget: HeatBudget, days: int, sun: float, free_heat: float = 0.0) -> None:
    """Step days of a flat losing 50 W/K that gains 1 kW in full sun, fitting every hour."""
    for day in range(days):
        for hour in range(24):
            shining = sun if 9 <= hour < 15 else 0.0
            kelvin_hours = 10.0 if 9 <= hour < 15 else 16.0
            budget._hours.append(
                _Hour(
                    heat_kwh=0.05 * kelvin_hours - 1.0 * shining - free_heat,
                    kelvin_hours=kelvin_hours,
                    sun_hours=shining,
                    seconds=3600.0,
                    indoor_start=22.0,
                    indoor_end=22.0,
                    wall_end=float(day * 24 + hour),
                )
            )
            budget._fit()


def test_the_heat_loss_comes_from_dark_hours_and_the_sun_from_the_rest() -> None:
    budget = HeatBudget()
    sunny_days(budget, 6, 0.3)

    assert abs(budget.heat_loss - 0.05) < 0.003
    assert abs(budget.solar_gain - 1.0) < 0.15


def test_a_grey_day_does_not_turn_free_heat_into_sun() -> None:
    # Overcast: a trace of sun while cooking and people give 0.3 kW in the day
    budget = HeatBudget()
    for day in range(4):
        for hour in range(24):
            daytime = 9 <= hour < 15
            budget._hours.append(
                _Hour(
                    heat_kwh=0.05 * 16.0 - (0.3 if daytime else 0.0),
                    kelvin_hours=16.0,
                    sun_hours=0.05 if daytime else 0.0,
                    seconds=3600.0,
                    indoor_start=22.0,
                    indoor_end=22.0,
                    wall_end=float(day * 24 + hour),
                )
            )
            budget._fit()

    assert budget.solar_gain == 0.0


def test_the_sun_learned_before_starts_over_and_the_heat_loss_is_kept() -> None:
    budget = HeatBudget()
    budget._load_learners(
        {
            "heat_loss": {"theta": [0.055, 2.8], "p": [[0.01, 0], [0, 0.25]], "updates": 90},
            "solar_gain": {"theta": [2.56], "p": [[0.25]], "updates": 40},
        }
    )

    assert budget.heat_loss == 0.055
    assert budget.solar_gain == 0.0
    assert budget.ready


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


def test_gaps_in_the_data_do_not_restart_the_learning() -> None:
    budget = HeatBudget()

    room, screed, now = 22.0, 26.0, 1000.0
    while now < 1000 + 4 * 86400:
        # A 45 minute outage every 10 hours, as from restarts or a sensor dropping out
        if (now - 1000) % 36000 < 2700:
            now += 30
            continue
        outdoor = 2 + 4 * math.sin(2 * math.pi * now / 86400)
        flame = budget.status == PWMStatus.ON if budget.ready else int(now // 1800) % 2 == 0
        budget.update(inputs(now, indoor=round(room, 1), outdoor=outdoor, flame_active=flame))
        floor = 0.65 * (screed - room)
        screed += ((MINIMUM_POWER if flame else 0) - floor) * (30 / 3600) / 2.4
        room += (floor - 0.15 * (room - outdoor)) * (30 / 3600) / 2.5
        now += 30

    assert budget.ready
    assert abs(budget.heat_loss - 0.15) < 0.02


def test_a_biased_forecast_only_adds_its_trend() -> None:
    plain = HeatBudget(heat_loss_kw_per_k=0.12)
    biased = HeatBudget(heat_loss_kw_per_k=0.12)

    # The forecast runs 3 K warmer than the local sensor but sees the same 2 K drop
    plain.update(inputs(1000, outdoor=2.0, outdoor_forecast=0.0, outdoor_forecast_now=2.0))
    biased.update(inputs(1000, outdoor=2.0, outdoor_forecast=3.0, outdoor_forecast_now=5.0))

    assert plain.attributes["heat_need_kw"] == biased.attributes["heat_need_kw"]
    assert plain.attributes["heat_need_kw"] == round(0.12 * (22 - 0), 2)


def test_the_day_window_is_saved_and_restored() -> None:
    hour = _Hour(1.2, 20.0, 0.1, 3600.0, 21.9, 22.0, 1_763_200_000.0)
    assert _Hour.from_list(hour.to_list()) == hour
    assert _Hour.from_list([1.0, "x"]) is None


def test_a_room_well_above_its_target_gets_no_heat() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12)
    budget.update(inputs(1000))
    assert budget.status == PWMStatus.ON

    # The target is lowered by a degree while a block runs
    budget.update(inputs(1030, target=21.0, flame_active=True))

    assert budget.status == PWMStatus.OFF
    assert budget.attributes["heat_need_kw"] == 0
    assert budget.attributes["heat_budget_room_too_warm"] is True
    burn(budget, 1060, 2 * 3600, target=21.0)
    assert budget.status == PWMStatus.OFF


def test_a_lower_target_is_reached_within_hours() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.12)

    # Two nodes: the screed takes the burner heat, the rooms lose 0.12 kW/K against 5 °C outside
    room, screed, now, flame = 22.0, 22.0 + 0.12 * 17 / 0.65, 0.0, False
    lowest = room
    while now < 34 * 3600:
        target = 22.0 if now < 10 * 3600 else 21.0
        budget.update(
            inputs(now, indoor=round(room, 1), target=target, outdoor=5.0, flame_active=flame)
        )
        flame = budget.status == PWMStatus.ON
        floor = 0.65 * (screed - room)
        screed += ((MINIMUM_POWER if flame else 0) - floor) * (30 / 3600) / 2.4
        room += (floor - 0.12 * (room - 5.0)) * (30 / 3600) / 2.5
        if now >= 20 * 3600:
            assert abs(room - 21.0) < 0.25
        lowest = min(lowest, room)
        now += 30

    assert lowest > 20.75


def test_a_lowered_target_coasts_without_heat() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.08)
    burn(budget, 0, 1800, indoor=22.5, target=22.5, outdoor=5.0)

    # The target goes down half a degree: nothing burns until the room is close to it
    now = burn(budget, 1800, 600, indoor=22.5, target=22.0, outdoor=5.0)
    assert budget.attributes["heat_budget_coasting"]
    assert budget.status == PWMStatus.OFF
    assert budget.attributes["heat_need_kw"] == 0

    burn(budget, now, 600, indoor=22.2, target=22.0, outdoor=5.0)
    assert not budget.attributes["heat_budget_coasting"]
    assert budget.attributes["heat_need_kw"] > 0


async def test_the_hour_being_measured_survives_a_restart() -> None:
    saved: dict[str, Any] = {}

    class FakeStore:
        async def async_load(self) -> dict[str, Any]:
            return saved

        def async_delay_save(self, data: Any, _delay: float) -> None:  # noqa: ANN401
            saved.clear()
            saved.update(data())

    start = datetime.now(UTC) - timedelta(minutes=40)
    budget = HeatBudget(heat_loss_kw_per_k=0.08)
    with patch("custom_components.sat.heat_budget.heat_budget_store", return_value=FakeStore()):
        await budget.async_initialize(MagicMock(), "entry")
        for step in range(81):
            budget.update(inputs(step * 30, wall_time=start + timedelta(seconds=step * 30)))

        restored = HeatBudget(heat_loss_kw_per_k=0.08)
        await restored.async_initialize(MagicMock(), "entry")

    # The 40 minutes measured before the restart are kept and the hour ends 20 minutes later
    assert restored._hour.seconds >= 35 * 60
    restored.update(inputs(10_000, wall_time=datetime.now(UTC)))
    assert restored._hour_started is not None
    assert 10_000 - restored._hour_started >= 35 * 60


def test_closed_valves_build_up_no_heat_debt() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.08)
    now = burn(budget, 0, 2 * 3600, heating_allowed=False)
    assert budget.status == PWMStatus.OFF
    assert budget.attributes["heat_credit_kwh"] <= 0

    # Once a loop opens the block is planned for the need from now on, not the hours before
    burn(budget, now, 60)
    on_time, _ = budget.duty_cycle
    assert on_time < 3600


def windy_days(budget: HeatBudget, sensitivity: float) -> None:
    """Dark days of a flat losing 50 W/K, more on the windier days, fitted every hour."""
    for day in range(12):
        wind = (5.0, 30.0, 12.0, 35.0, 8.0, 22.0)[day % 6]
        for hour in range(24):
            kelvin_hours = 16.0
            measured = _Hour(
                heat_kwh=0.05 * kelvin_hours * (1 + sensitivity * (wind - 20.0)),
                kelvin_hours=kelvin_hours,
                seconds=3600.0,
                indoor_start=22.0,
                indoor_end=22.0,
                wall_end=float(day * 24 + hour),
                wind_kelvin_hours=kelvin_hours * wind,
                wind_hours=wind,
                wind_seconds=3600.0,
            )
            budget._track_wind(measured)
            budget._hours.append(measured)
            budget._fit()


def test_the_wind_effect_is_learned_and_used_once_clear() -> None:
    budget = HeatBudget()
    windy_days(budget, 0.01)

    assert abs(budget.heat_loss - 0.05) < 0.005
    assert abs(budget.wind_sensitivity - 0.01) < 0.003
    assert budget.wind_correction_active
    assert budget.attributes["wind_heat_loss_percent_per_10kmh"] > 7

    # More heat in a gale than in a calm
    assert budget._wind_factor(0.0) < 1 < budget._wind_factor(50.0)


def test_a_house_the_wind_does_not_reach_gets_no_correction() -> None:
    budget = HeatBudget()
    windy_days(budget, 0.0)

    assert budget.wind_sensitivity < 0.001
    assert not budget.wind_correction_active
    assert budget._wind_factor(50.0) == 1.0


def test_hours_saved_before_the_wind_are_loaded() -> None:
    hour = _Hour.from_list([1.2, 20.0, 0.1, 3600.0, 21.9, 22.0, 1_763_200_000.0])
    assert hour is not None
    assert hour.wind_seconds == 0.0
    assert not hour.has_wind


def test_the_heat_capacity_is_learned_from_days_the_room_changed() -> None:
    # A house losing 50 W/K that stores 8 kWh per kelvin; the room rises and falls by a degree
    budget = HeatBudget()
    for day in range(10):
        warming = (1.0, -1.0, 0.5, -0.5, 0.0)[day % 5] / 24
        for hour in range(24):
            start = 21.0 + warming * hour
            budget._hours.append(
                _Hour(
                    heat_kwh=0.05 * 16.0 + 8.0 * warming,
                    kelvin_hours=16.0,
                    seconds=3600.0,
                    indoor_start=start,
                    indoor_end=start + warming,
                    wall_end=float(day * 24 + hour),
                )
            )
            budget._fit()

    assert abs(budget.heat_loss - 0.05) < 0.003
    assert abs(budget.heat_capacity - 8.0) < 1.0


def test_a_steady_room_keeps_the_capacity_at_the_heat_loss_times_80_hours() -> None:
    budget = HeatBudget()
    windy_days(budget, 0.0)

    assert budget.heat_loss == pytest.approx(0.05, abs=0.003)
    assert budget.heat_capacity == pytest.approx(4.0, rel=0.1)
    assert budget.attributes["heat_capacity_kwh_per_k"] == pytest.approx(4.0, abs=0.4)


def test_steady_days_raise_a_low_heat_loss_instead_of_the_capacity() -> None:
    # A learned state that is too light on loss: 50 W/K with long memory, the house loses 70
    budget = HeatBudget()
    budget._learner.theta = [0.05, 4.0]
    budget._learner.p = [[1e-6, 0.0], [0.0, 0.05]]
    budget._learner.updates = 200
    for day in range(6):
        for hour in range(24):
            # The room creeps up by a tenth of a kelvin a day, as a house a little short does
            start = 21.4 + 0.1 * (day * 24 + hour) / 24
            budget._hours.append(
                _Hour(
                    heat_kwh=0.07 * 20.0,
                    kelvin_hours=20.0,
                    seconds=3600.0,
                    indoor_start=start,
                    indoor_end=start + 0.1 / 24,
                    wall_end=float(day * 24 + hour),
                )
            )
            budget._fit()

    assert budget.heat_loss > 0.062
    assert budget.heat_capacity / budget.heat_loss <= 200.0


def test_a_capacity_set_by_hand_is_not_learned() -> None:
    budget = HeatBudget(heat_capacity_kwh_per_k=6.0)
    for day in range(10):
        warming = (1.0, -1.0, 0.5, -0.5, 0.0)[day % 5] / 24
        for hour in range(24):
            start = 21.0 + warming * hour
            budget._hours.append(
                _Hour(
                    heat_kwh=0.05 * 16.0 + 12.0 * warming,
                    kelvin_hours=16.0,
                    seconds=3600.0,
                    indoor_start=start,
                    indoor_end=start + warming,
                    wall_end=float(day * 24 + hour),
                )
            )
            budget._fit()

    assert budget.heat_capacity == 6.0
    assert abs(budget.heat_loss - 0.05) < 0.005


def test_the_next_block_is_announced() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.03)
    now = burn(budget, 1000, 30)
    attributes = budget.attributes
    start = datetime.fromisoformat(attributes["next_block_start"])
    end = datetime.fromisoformat(attributes["next_block_end"])
    wall = WALL + timedelta(seconds=now - 30)

    # 0.6 kW a period is too little for a 10 minute burn, so the block waits a period or more
    assert start > wall
    assert timedelta(minutes=10) <= end - start <= timedelta(minutes=60)

    # A room well above its target is owed nothing
    budget.update(inputs(now, indoor=23.0))
    assert budget.attributes["next_block_start"] is None


def test_a_room_that_stays_below_its_target_gets_more_heat_over_the_hours() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.045)

    # Steady at 0.6 K below the target: the integral takes up what the model misses
    budget.update(inputs(0.0, indoor=21.4))
    first = budget.attributes["heat_need_kw"]
    for minute in range(1, 6 * 60):
        budget.update(inputs(minute * 60.0, indoor=21.4))

    assert budget.attributes["heat_need_kw"] > first + 0.05


def test_the_integral_waits_while_the_house_recovers_from_a_raised_target() -> None:
    budget = HeatBudget(heat_loss_kw_per_k=0.045)

    budget.update(inputs(0.0, indoor=21.0, target=21.0))
    budget.update(inputs(60.0, indoor=21.0, target=22.0))
    first = budget.attributes["heat_need_kw"]
    for minute in range(2, 3 * 60):
        budget.update(inputs(minute * 60.0, indoor=21.0, target=22.0))

    assert budget.attributes["heat_need_kw"] == pytest.approx(first, abs=0.01)


def test_an_aired_hour_and_the_next_are_left_out_of_the_learning() -> None:
    budget = HeatBudget()

    def hour(start: float, *, aired: bool) -> float:
        now = start
        for minute in range(60):
            indoor = 21.5 if aired and 10 <= minute < 20 else 22.0
            budget.update(inputs(now, indoor=indoor))
            now += 60
        return now

    # An hour is filed one step after it ends, so the counts trail the loop by an hour
    now = hour(0.0, aired=False)
    now = hour(now, aired=False)
    now = hour(now, aired=True)
    before = len(budget._hours)
    now = hour(now, aired=False)
    now = hour(now, aired=False)
    assert len(budget._hours) == before
    hour(now, aired=False)
    assert len(budget._hours) == before + 1


async def test_a_model_saved_before_the_airing_fix_learns_capacity_and_wind_anew() -> None:
    saved = {
        "heat_balance": {"theta": [0.046, 1.0], "p": [[0.01, 0.0], [0.0, 0.2]], "updates": 50},
        "wind": {"theta": [0.018], "p": [[1e-4]], "updates": 60, "mean": 12.0, "square": 160.0},
        "hours": [[1.0, 20.0, 0.0, 3600.0, 22.0, 22.0, datetime.now(UTC).timestamp()]],
    }

    class FakeStore:
        async def async_load(self) -> dict[str, Any]:
            return saved

    budget = HeatBudget()
    with patch("custom_components.sat.heat_budget.heat_budget_store", return_value=FakeStore()):
        await budget.async_initialize(MagicMock(), "entry")

    assert budget.heat_loss == pytest.approx(0.046)
    assert budget.heat_capacity == pytest.approx(0.046 * 80)
    assert budget.wind_sensitivity == 0.0
    assert len(budget._hours) == 0


async def test_a_model_with_a_runaway_capacity_starts_it_over_and_keeps_the_hours() -> None:
    now = datetime.now(UTC).timestamp()
    saved = {
        "model": 2,
        "heat_balance": {"theta": [0.055, 20.0], "p": [[1e-6, 1e-4], [1e-4, 1.0]], "updates": 207},
        "wind": {"theta": [0.004], "p": [[1e-5]], "updates": 60, "mean": 12.0, "square": 160.0},
        "hours": [[1.0, 20.0, 0.0, 3600.0, 22.0, 22.0, now]],
    }

    class FakeStore:
        async def async_load(self) -> dict[str, Any]:
            return saved

    budget = HeatBudget()
    with patch("custom_components.sat.heat_budget.heat_budget_store", return_value=FakeStore()):
        await budget.async_initialize(MagicMock(), "entry")

    assert budget.heat_loss == pytest.approx(0.055)
    assert budget.heat_capacity == pytest.approx(0.055 * 80)
    assert budget._learner.p[0][0] >= 1e-3
    assert budget.wind_sensitivity == pytest.approx(0.004)
    assert len(budget._hours) == 1


async def test_a_capacity_set_by_hand_overrides_the_saved_one() -> None:
    saved = {
        "model": 3,
        "heat_balance": {"theta": [0.055, 9.0], "p": [[1e-4, 0.0], [0.0, 0.05]], "updates": 50},
    }

    class FakeStore:
        async def async_load(self) -> dict[str, Any]:
            return saved

    budget = HeatBudget(heat_capacity_kwh_per_k=6.0)
    with patch("custom_components.sat.heat_budget.heat_budget_store", return_value=FakeStore()):
        await budget.async_initialize(MagicMock(), "entry")

    assert budget.heat_capacity == 6.0
    assert budget._learner.p[1][1] == 0.0


def learned_day(budget: HeatBudget, heat_loss: float) -> None:
    """Steady dark hours of a house losing this much, fitted every hour."""
    for hour in range(24):
        budget._hours.append(
            _Hour(
                heat_kwh=heat_loss * 22.0,
                kelvin_hours=22.0,
                seconds=3600.0,
                indoor_start=21.6,
                indoor_end=21.6,
                wall_end=float(hour),
            )
        )
        budget._fit()


def test_a_higher_heat_loss_takes_over_the_integral() -> None:
    # The integral made up 0.42 kW for a heat loss learned too low; H is then learned right
    budget = HeatBudget()
    budget._learner.theta = [0.056, 4.5]
    budget._learner.p = [[1e-3, 0.0], [0.0, 0.05]]
    budget._learner.updates = 208
    budget._integral = 7.5
    budget._last_difference = 22.0
    learned_day(budget, 0.087)

    assert budget.heat_loss == pytest.approx(0.087, abs=0.003)
    assert budget._integral == 0.0


def test_a_small_correction_of_the_heat_loss_takes_only_its_share() -> None:
    budget = HeatBudget()
    budget._learner.theta = [0.080, 4.5]
    budget._learner.p = [[1e-3, 0.0], [0.0, 0.05]]
    budget._learner.updates = 208
    budget._integral = 4.0
    budget._last_difference = 22.0
    learned_day(budget, 0.084)

    # 0.32 kW of integral, of which H now covers about 0.09 kW
    assert budget.heat_loss == pytest.approx(0.084, abs=0.002)
    assert budget._integral * budget.heat_loss == pytest.approx(0.32 - 0.088, abs=0.03)


def test_a_heat_loss_moving_against_the_integral_leaves_it() -> None:
    budget = HeatBudget()
    budget._learner.theta = [0.080, 4.5]
    budget._learner.p = [[1e-3, 0.0], [0.0, 0.05]]
    budget._learner.updates = 208
    budget._integral = 2.0
    budget._last_difference = 22.0
    learned_day(budget, 0.070)

    assert budget._integral == 2.0
