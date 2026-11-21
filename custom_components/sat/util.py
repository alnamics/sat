from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .budget_pwm import BudgetPWM
from .const import (
    CONF_AUTOMATIC_DUTY_CYCLE,
    CONF_AUTOMATIC_GAINS,
    CONF_AUTOMATIC_GAINS_VALUE,
    CONF_CYCLES_PER_HOUR,
    CONF_DERIVATIVE,
    CONF_DERIVATIVE_TIME_WEIGHT,
    CONF_DUTY_CYCLE,
    CONF_FORCE_PULSE_WIDTH_MODULATION,
    CONF_HEATING_CURVE_COEFFICIENT,
    CONF_HEATING_SYSTEM,
    CONF_INTEGRAL,
    CONF_MODE,
    CONF_PID_CONTROLLER_VERSION,
    CONF_PROPORTIONAL,
    CONF_PWM_SHORT_BURNS_THRESHOLD,
    CONF_SAMPLE_TIME,
    HEATING_SYSTEM_UNKNOWN,
    MODE_SWITCH,
)
from .heating_curve import HeatingCurve
from .helpers import convert_time_str_to_seconds
from .pid import PID
from .pwm import PWM, CycleConfig

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .heat_budget import HeatBudget


def create_pid_controller(config_data: Mapping[str, Any], config_options: Mapping[str, Any]) -> PID:
    """Create and return a PID controller instance with the given configuration options."""
    # Extract the configuration options
    kp = float(config_options[CONF_PROPORTIONAL])
    ki = float(config_options[CONF_INTEGRAL])
    kd = float(config_options[CONF_DERIVATIVE])

    heating_system = config_data.get(CONF_HEATING_SYSTEM, HEATING_SYSTEM_UNKNOWN)
    version = int(config_options[CONF_PID_CONTROLLER_VERSION])
    automatic_gains = bool(config_options[CONF_AUTOMATIC_GAINS])
    automatic_gains_value = float(config_options[CONF_AUTOMATIC_GAINS_VALUE])
    derivative_time_weight = float(config_options[CONF_DERIVATIVE_TIME_WEIGHT])
    heating_curve_coefficient = float(config_options[CONF_HEATING_CURVE_COEFFICIENT])
    sample_time_limit = convert_time_str_to_seconds(config_options[CONF_SAMPLE_TIME])

    # Return a new PID controller instance with the given configuration options
    return PID(
        version=version,
        heating_system=heating_system,
        automatic_gain_value=automatic_gains_value,
        derivative_time_weight=derivative_time_weight,
        heating_curve_coefficient=heating_curve_coefficient,
        kp=kp,
        ki=ki,
        kd=kd,
        automatic_gains=automatic_gains,
        sample_time_limit=sample_time_limit,
    )


def create_heating_curve_controller(
    config_data: Mapping[str, Any], config_options: Mapping[str, Any]
) -> HeatingCurve:
    """Create and return a Heating Curve controller with the given configuration options."""
    # Extract the configuration options
    heating_system = config_data.get(CONF_HEATING_SYSTEM, HEATING_SYSTEM_UNKNOWN)
    coefficient = float(config_options[CONF_HEATING_CURVE_COEFFICIENT])

    # Return a new Heating Curve controller instance with the given configuration options
    return HeatingCurve(heating_system=heating_system, coefficient=coefficient)


def create_pwm_controller(
    heating_curve: HeatingCurve,
    config_data: Mapping[str, Any],
    config_options: Mapping[str, Any],
    heat_budget: HeatBudget | None = None,
) -> PWM:
    """Create and return a PWM controller instance with the given configuration options."""
    # Extract the configuration options
    max_duty_cycles = int(config_options[CONF_CYCLES_PER_HOUR])
    automatic_duty_cycle = bool(config_options[CONF_AUTOMATIC_DUTY_CYCLE])
    max_cycle_time = int(convert_time_str_to_seconds(config_options[CONF_DUTY_CYCLE]))
    force = bool(config_data.get(CONF_MODE) == MODE_SWITCH) or bool(
        config_options[CONF_FORCE_PULSE_WIDTH_MODULATION]
    )

    short_burns_threshold = int(config_options[CONF_PWM_SHORT_BURNS_THRESHOLD])

    # Extra settings
    cycles = CycleConfig(maximum_count=max_duty_cycles, maximum_time=max_cycle_time)

    # The heat budget drives the blocks once it has learned the house
    if heat_budget is not None:
        return BudgetPWM(
            heating_curve=heating_curve,
            cycles=cycles,
            automatic_duty_cycle=automatic_duty_cycle,
            force=force,
            short_burns_threshold=short_burns_threshold,
            heat_budget=heat_budget,
        )

    # Return a new PWM controller instance with the given configuration options
    return PWM(
        heating_curve=heating_curve,
        cycles=cycles,
        automatic_duty_cycle=automatic_duty_cycle,
        force=force,
        short_burns_threshold=short_burns_threshold,
    )
