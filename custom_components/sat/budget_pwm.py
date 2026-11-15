"""Pulse width modulation driven by the heat budget once it has learned the house."""

from __future__ import annotations

import logging
from time import monotonic
from typing import TYPE_CHECKING, override

from .const import PWMStatus
from .flame import Flame
from .pwm import PWM, CycleConfig

if TYPE_CHECKING:
    from .boiler import BoilerState
    from .flame import FlameState
    from .heat_budget import HeatBudget
    from .heating_curve import HeatingCurve

_LOGGER = logging.getLogger(__name__)


class BudgetPWM(PWM):
    """Follow the heat budget's blocks; fall back to the duty cycle until it is ready."""

    def __init__(
        self,
        cycles: CycleConfig,
        heating_curve: HeatingCurve,
        *,
        automatic_duty_cycle: bool,
        heat_budget: HeatBudget,
        force: bool = True,
        short_burns_threshold: int = Flame.PWM_SHORT_BURNS_THRESHOLD,
    ) -> None:
        self._heat_budget = heat_budget
        super().__init__(
            cycles,
            heating_curve,
            automatic_duty_cycle=automatic_duty_cycle,
            force=force,
            short_burns_threshold=short_burns_threshold,
        )

    @override
    async def update(
        self, boiler: BoilerState, flame: FlameState, requested_setpoint: float | None
    ) -> None:
        if not self._heat_budget.ready:
            await super().update(boiler, flame, requested_setpoint)
            return

        status = self._heat_budget.status
        if status != self._status:
            _LOGGER.info(
                "Heat budget switches the burner %s (block %d min).",
                "on" if status == PWMStatus.ON else "off",
                self._heat_budget.duty_cycle[0] // 60,
            )
            self._status = status
            self._last_update = monotonic()

        on_time, off_time = self._heat_budget.duty_cycle
        self._duty_cycle = (on_time, off_time)
        self._last_duty_cycle_percentage = on_time / max(1, on_time + off_time)
