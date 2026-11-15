"""Tests for learning the overshoot protection value from PWM burns."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from custom_components.sat.boiler import BoilerState
from custom_components.sat.const import BoilerStatus, PWMStatus
from custom_components.sat.overshoot_learner import OvershootLearner
from custom_components.sat.pwm import PWMState

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

MAXIMUM_SETPOINT = 43.0
PWM_ON = PWMState(enabled=True, status=PWMStatus.ON, duty_cycle=(900, 900))
PWM_OFF = PWMState(enabled=True, status=PWMStatus.OFF, duty_cycle=(900, 900))


def state(
    flame: bool,
    flow: float,
    setpoint: float = 35.0,
    hot_water: bool = False,
    demand: bool = True,
) -> BoilerState:
    return BoilerState(
        is_active=demand,
        is_inactive=not demand,
        status=BoilerStatus.AT_SETPOINT if flame else BoilerStatus.WAITING_FOR_FLAME,
        flame_active=flame,
        hot_water_active=hot_water,
        setpoint=setpoint,
        flow_temperature=flow,
        return_temperature=flow - 3,
        relative_modulation_level=0.0,
    )


def burn(
    learner: OvershootLearner,
    freezer: FrozenDateTimeFactory,
    flows: list[float],
    *,
    end_pwm: PWMState = PWM_ON,
    end_flow: float | None = None,
    hot_water: bool = False,
) -> None:
    learner.update(state(False, flows[0]), PWM_ON, MAXIMUM_SETPOINT)
    for flow in flows:
        freezer.tick(timedelta(seconds=60))
        learner.update(state(True, flow, hot_water=hot_water), None, MAXIMUM_SETPOINT)

    freezer.tick(timedelta(seconds=5))
    learner.update(state(False, end_flow or flows[-1]), end_pwm, MAXIMUM_SETPOINT)


def test_a_burn_the_boiler_stops_by_overheating_raises_the_value(
    freezer: FrozenDateTimeFactory,
) -> None:
    learner = OvershootLearner(35.0)
    burn(learner, freezer, [33.0, 38.0], end_flow=41.0)
    assert learner.value == 36.0


def test_a_long_burn_below_the_setpoint_lowers_the_value(freezer: FrozenDateTimeFactory) -> None:
    learner = OvershootLearner(35.0)
    burn(learner, freezer, [30.0] + [32.0] * 11, end_pwm=PWM_OFF)
    assert learner.value == 34.5


def test_a_settled_burn_near_the_setpoint_keeps_the_value(
    freezer: FrozenDateTimeFactory,
) -> None:
    learner = OvershootLearner(35.0)
    burn(learner, freezer, [33.0] + [35.0] * 11, end_pwm=PWM_OFF)
    assert learner.value == 35.0


def test_hot_water_burns_are_ignored(freezer: FrozenDateTimeFactory) -> None:
    learner = OvershootLearner(35.0)
    burn(learner, freezer, [33.0, 55.0], end_flow=60.0, hot_water=True)
    assert learner.value == 35.0


def test_an_on_phase_without_ignition_in_warm_water_raises_the_value(
    freezer: FrozenDateTimeFactory,
) -> None:
    learner = OvershootLearner(32.0)
    learner.update(state(False, 33.0, setpoint=10.0), PWM_OFF, MAXIMUM_SETPOINT)
    learner.update(state(False, 33.0, setpoint=10.0), PWM_ON, MAXIMUM_SETPOINT)
    for _ in range(5):
        freezer.tick(timedelta(seconds=60))
        learner.update(state(False, 33.0, setpoint=32.0), PWM_ON, MAXIMUM_SETPOINT)

    learner.update(state(False, 33.0, setpoint=10.0), PWM_OFF, MAXIMUM_SETPOINT)
    assert learner.value == 33.0


def test_an_on_phase_held_without_demand_keeps_the_value(
    freezer: FrozenDateTimeFactory,
) -> None:
    learner = OvershootLearner(32.0)
    learner.update(state(False, 33.0, setpoint=10.0, demand=False), PWM_OFF, MAXIMUM_SETPOINT)
    learner.update(state(False, 33.0, setpoint=10.0, demand=False), PWM_ON, MAXIMUM_SETPOINT)
    for _ in range(5):
        freezer.tick(timedelta(seconds=60))
        learner.update(state(False, 33.0, setpoint=32.0, demand=False), PWM_ON, MAXIMUM_SETPOINT)

    learner.update(state(False, 33.0, setpoint=10.0, demand=False), PWM_OFF, MAXIMUM_SETPOINT)
    assert learner.value == 32.0


def test_the_value_stays_below_the_maximum_setpoint(freezer: FrozenDateTimeFactory) -> None:
    learner = OvershootLearner(39.5)
    for _ in range(5):
        burn(learner, freezer, [35.0, 44.0], end_flow=46.0)
        freezer.tick(timedelta(seconds=900))

    assert learner.value == MAXIMUM_SETPOINT - 3


async def test_a_new_calibration_starts_the_learning_over(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage["sat.entry.overshoot_learner"] = {
        "version": 1,
        "minor_version": 1,
        "key": "sat.entry.overshoot_learner",
        "data": {"configured": 35.0, "learned": 38.0},
    }

    learner = OvershootLearner(35.0)
    await learner.async_initialize(hass, "entry")
    assert learner.value == 38.0

    recalibrated = OvershootLearner(36.0)
    await recalibrated.async_initialize(hass, "entry")
    assert recalibrated.value == 36.0
