"""Learn the overshoot protection value from PWM burns during normal operation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from .const import COLD_SETPOINT, DOMAIN, MINIMUM_SETPOINT, PWMStatus

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .boiler import BoilerState
    from .pwm import PWMState

_LOGGER = logging.getLogger(__name__)

# A burn the boiler stops this far above its setpoint overheated the water at minimum power
OVERHEAT_MARGIN = 4.0
# A long burn that stays this far below its setpoint shows the boiler can hold a lower value
UNDERSHOOT_MARGIN = 2.0
# Water this close to the setpoint for a whole on-phase keeps the burner from lighting
NO_IGNITION_MARGIN = 1.0
# Only burns this long have settled enough to show where the flow levels off
MINIMUM_SETTLED_BURN_SECONDS = 600.0
# An on-phase shorter than this says nothing about ignition
MINIMUM_ON_PHASE_SECONDS = 180.0
# Raise quickly to stop cut-outs, lower slowly to avoid hunting
RAISE_STEP = 1.0
LOWER_STEP = 0.5
# The learned value keeps this much room below the maximum setpoint
MAXIMUM_SETPOINT_MARGIN = 3.0
MINIMUM_VALUE = COLD_SETPOINT + 1.8
# The control loop sends the PWM state at least this often while it runs
PWM_STATE_MAX_AGE_SECONDS = 120.0


def overshoot_learner_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.overshoot_learner")


@dataclass(slots=True)
class _Burn:
    planned_on_seconds: float
    started: float
    ignition_flow: float | None
    peak_flow: float | None
    setpoint: float | None
    valid: bool = True


@dataclass(slots=True)
class _OnPhase:
    started: float
    lowest_flow: float | None
    setpoint: float | None
    burned: bool = False
    # Only an on-phase that asked the boiler for heat can say it failed to light
    demanded: bool = False


class OvershootLearner:
    """Adjust the overshoot protection value from how PWM burns end."""

    def __init__(self, configured: float, maximum_setpoint: float | None = None) -> None:
        self._configured: float = configured
        self._maximum_setpoint: float | None = maximum_setpoint
        self._value: float = configured
        self._store: Store[dict[str, Any]] | None = None

        self._flame_active: bool | None = None
        self._pwm_status: PWMStatus | None = None
        self._pwm_duty_cycle: tuple[int, int] | None = None
        self._pwm_updated: float | None = None

        self._burn: _Burn | None = None
        self._on_phase: _OnPhase | None = None

    @property
    def value(self) -> float:
        return self._value

    async def async_initialize(self, hass: HomeAssistant, entry_id: str) -> None:
        if self._store is not None:
            return

        self._store = overshoot_learner_store(hass, entry_id)
        if (data := await self._store.async_load()) is None:
            return

        # A new calibration or a manual value starts the learning over
        if data.get("configured") != self._configured or data.get("learned") is None:
            return

        self._value = float(data["learned"])

        # A maximum setpoint lowered since the value was learned caps it again
        if self._maximum_setpoint is not None:
            self._value = min(
                self._value,
                max(self._configured, self._maximum_setpoint - MAXIMUM_SETPOINT_MARGIN),
            )

        _LOGGER.debug("Loaded learned overshoot protection value %.1f°C.", self._value)

    def update(
        self, boiler: BoilerState, pwm_state: PWMState | None, maximum_setpoint: float
    ) -> None:
        now = monotonic()

        if pwm_state is not None:
            self._update_pwm(boiler, pwm_state, now, maximum_setpoint)

        self._update_on_phase(boiler)
        self._update_burn(boiler, now, maximum_setpoint)

    def _pwm_on(self, now: float) -> bool:
        return (
            self._pwm_status == PWMStatus.ON
            and self._pwm_updated is not None
            and now - self._pwm_updated <= PWM_STATE_MAX_AGE_SECONDS
        )

    def _update_pwm(
        self, boiler: BoilerState, pwm_state: PWMState, now: float, maximum_setpoint: float
    ) -> None:
        was_on = self._pwm_on(now)
        self._pwm_status = pwm_state.status
        self._pwm_duty_cycle = pwm_state.duty_cycle
        self._pwm_updated = now
        is_on = pwm_state.status == PWMStatus.ON

        if is_on and not was_on:
            self._on_phase = _OnPhase(
                started=now, lowest_flow=boiler.flow_temperature, setpoint=boiler.setpoint
            )
            return

        if was_on and not is_on and (phase := self._on_phase) is not None:
            self._on_phase = None
            if (
                not phase.burned
                and phase.demanded
                and now - phase.started >= MINIMUM_ON_PHASE_SECONDS
                and phase.lowest_flow is not None
                and phase.setpoint is not None
                and phase.lowest_flow >= phase.setpoint - NO_IGNITION_MARGIN
            ):
                self._change(
                    RAISE_STEP,
                    maximum_setpoint,
                    f"the burner did not light in an on-phase with the flow at "
                    f"{phase.lowest_flow:.1f}°C",
                )

    def _update_on_phase(self, boiler: BoilerState) -> None:
        if (phase := self._on_phase) is None:
            return

        if boiler.flame_active:
            phase.burned = True

        if boiler.is_active:
            phase.demanded = True

        if boiler.setpoint is not None and boiler.setpoint > MINIMUM_SETPOINT:
            phase.setpoint = boiler.setpoint

        if boiler.flow_temperature is not None and (
            phase.lowest_flow is None or boiler.flow_temperature < phase.lowest_flow
        ):
            phase.lowest_flow = boiler.flow_temperature

    def _update_burn(self, boiler: BoilerState, now: float, maximum_setpoint: float) -> None:
        was_active, self._flame_active = self._flame_active, bool(boiler.flame_active)

        # OFF -> ON: only heating burns lit during a PWM on-phase say anything
        if boiler.flame_active and was_active is not True:
            self._burn = None
            if (
                was_active is not None
                and self._pwm_on(now)
                and self._pwm_duty_cycle is not None
                and not boiler.hot_water_active
            ):
                self._burn = _Burn(
                    planned_on_seconds=float(self._pwm_duty_cycle[0]),
                    started=now,
                    ignition_flow=boiler.flow_temperature,
                    peak_flow=boiler.flow_temperature,
                    setpoint=boiler.setpoint,
                )
            return

        if (burn := self._burn) is None:
            return

        # ON -> ON
        if boiler.flame_active:
            if boiler.hot_water_active:
                burn.valid = False
            if boiler.flow_temperature is not None and (
                burn.peak_flow is None or boiler.flow_temperature > burn.peak_flow
            ):
                burn.peak_flow = boiler.flow_temperature
            if boiler.setpoint is not None and boiler.setpoint > MINIMUM_SETPOINT:
                burn.setpoint = boiler.setpoint
            return

        # ON -> OFF: the flow often peaks between two readings, right as the boiler cuts out
        self._burn = None
        if boiler.flow_temperature is not None and (
            burn.peak_flow is None or boiler.flow_temperature > burn.peak_flow
        ):
            burn.peak_flow = boiler.flow_temperature

        if not burn.valid or burn.setpoint is None or burn.peak_flow is None:
            return

        duration = now - burn.started
        pwm_on = self._pwm_on(now)

        # Residual heat above the cut-out at ignition is not an overheat at minimum power
        lit_hot = (
            burn.ignition_flow is not None and burn.ignition_flow > burn.setpoint + OVERHEAT_MARGIN
        )

        if (
            pwm_on
            and duration < burn.planned_on_seconds
            and not lit_hot
            and burn.peak_flow > burn.setpoint + OVERHEAT_MARGIN
        ):
            self._change(
                RAISE_STEP,
                maximum_setpoint,
                f"the boiler stopped a burn at {burn.peak_flow:.1f}°C "
                f"against a {burn.setpoint:.1f}°C setpoint",
            )
            return

        if (
            not pwm_on
            and duration >= MINIMUM_SETTLED_BURN_SECONDS
            and burn.peak_flow <= burn.setpoint - UNDERSHOOT_MARGIN
        ):
            self._change(
                -LOWER_STEP,
                maximum_setpoint,
                f"a {duration / 60:.0f} min burn levelled off at {burn.peak_flow:.1f}°C "
                f"below the {burn.setpoint:.1f}°C setpoint",
            )

    def _change(self, delta: float, maximum_setpoint: float, reason: str) -> None:
        upper = max(MINIMUM_VALUE, maximum_setpoint - MAXIMUM_SETPOINT_MARGIN)
        new_value = round(min(max(self._value + delta, MINIMUM_VALUE), upper), 1)
        if new_value == self._value:
            return

        _LOGGER.info(
            "Learned overshoot protection value %.1f°C -> %.1f°C: %s",
            self._value,
            new_value,
            reason,
        )
        self._value = new_value

        if self._store is not None:
            self._store.async_delay_save(self._data_to_save, 60)

    def _data_to_save(self) -> dict[str, Any]:
        return {"configured": self._configured, "learned": self._value}
