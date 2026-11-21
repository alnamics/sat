from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from statistics import median
from time import monotonic, time
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from .const import CONTROL_LOOP_STALL_TIME, DOMAIN, BoilerStatus, FlameStatus, PWMStatus

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.core import HomeAssistant

    from .boiler import BoilerState
    from .pwm import PWMState

_LOGGER = logging.getLogger(__name__)


def flame_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.flame")


@dataclass(frozen=True, slots=True)
class FlameState:
    is_active: bool
    is_inactive: bool
    health_status: FlameStatus

    latest_on_time_seconds: float | None
    average_on_time_seconds: float | None
    last_cycle_duration_seconds: float | None

    sample_count_4h: int
    cycles_last_hour: float
    duty_ratio_last_15m: float
    median_on_duration_seconds_4h: float | None

    last_cut_short_peak_flow: float | None
    last_cut_short_setpoint: float | None
    cut_short_burn_ends: tuple[float, ...]
    flame_loss_ends: tuple[float, ...] = ()


class Flame:
    """Tracks boiler flame on/off, maintains rolling statistics, and classifies health."""

    # Thresholds
    MAX_CYCLES_PER_HOUR_PWM: float = 8.0
    MAX_CYCLES_PER_HOUR_NON_PWM: float = 3.0
    MAX_CYCLES_PER_HOUR_MODULATING_STEADY: float = 2.0
    PWM_SHORT_BURNS_THRESHOLD: int = 2

    STUCK_OFF_SECONDS: float = 300.0
    STUCK_ON_WITHOUT_DEMAND_SECONDS: float = 120.0
    # A Remeha cuts out about 5 °C above the control setpoint
    IGNITION_OVERSHOOT_MARGIN: float = 4.0
    # The cut-out ends the burn 6 to 11 s after the peak; listeners are notified every 5 s
    IGNITION_CUT_OUT_SECONDS: float = 30.0
    # A hot water request can end before the listener batch that first shows the flame
    HOT_WATER_LEAD_SECONDS: float = 30.0
    # Hot water demand this soon after a heating burn ended means the boiler switched over
    # (the Lumea lights for the cylinder some 150 s after it stopped the heating burn, and
    # does not always flag it, so the reheat has to show in the water first)
    HOT_WATER_TAKEOVER_SECONDS: float = 300.0
    # A burn that ends this far below its setpoint lost its flame; a cut-out comes above it
    FLAME_LOSS_SETPOINT_MARGIN: float = 3.0
    FLAME_LOSS_WINDOW_SECONDS: float = 86400.0
    # A heating burn cuts out 5 to 7 °C above its setpoint; a Remeha preheat runs ~20 °C above
    UNFLAGGED_HOT_WATER_MARGIN: float = 10.0
    # Boilers heat to their own minimum, often 25 °C, when the setpoint is lower
    # Without the boiler's own lowest heating setpoint (OpenTherm ID 49)
    UNFLAGGED_HOT_WATER_SETPOINT_FLOOR: float = 25.0
    # The boiler's relight wait is learned from heating burns that had to wait for the flame
    RELIGHT_WAIT_MINIMUM_HELD_SECONDS: float = 60.0
    RELIGHT_WAIT_BOUNDS: tuple[float, float] = (120.0, 1800.0)
    RELIGHT_WAIT_MINIMUM_SAMPLES: int = 3
    UNFLAGGED_HOT_WATER_SETTLE_SECONDS: float = 20.0
    EXPECTED_MODULATING_DUTY_RATIO_WHEN_HEATING: float = 0.60

    # Windows
    DUTY_WINDOW_SECONDS: int = 15 * 60
    CYCLES_WINDOW_SECONDS: int = 60 * 60
    MEDIAN_WINDOW_SECONDS: int = 4 * 60 * 60

    # Debounce
    MEDIAN_TOLERANCE: float = 0.9
    MIN_ON_SAMPLES_FOR_HEALTH: int = 3
    # A hot water run pauses the flame while the flow cools from its peak, 42 s seen on a Remeha
    MAX_DOMESTIC_HOT_WATER_IDLE_OFF_SECONDS: float = 120.0

    # Status buckets
    _TRANSIENT_STATUSES: Iterable[BoilerStatus] = (
        BoilerStatus.PREHEATING,
        BoilerStatus.PUMP_STARTING,
    )

    _HEATING_STATUSES: Iterable[BoilerStatus] = (
        BoilerStatus.HEATING_UP,
        BoilerStatus.NEAR_SETPOINT,
        BoilerStatus.AT_SETPOINT,
        BoilerStatus.COOLING_DOWN,
        BoilerStatus.BELOW_SETPOINT,
        BoilerStatus.OVERSHOOT_HANDLING,
        BoilerStatus.OVERSHOOT_STABILIZED,
    )

    def __init__(
        self,
        smoothing_alpha: float = 0.2,
        *,
        boiler_anti_cycling_seconds: float = 0.0,
    ) -> None:
        if not (0.0 <= smoothing_alpha <= 1.0):
            msg = "smoothing_alpha must be within [0.0, 1.0]."
            raise ValueError(msg)

        # A boiler that waits longer than the default before relighting is not stuck off,
        # so the stuck-off timeout covers its wait plus a minute of margin
        if boiler_anti_cycling_seconds > 0:
            self.STUCK_OFF_SECONDS = max(
                Flame.STUCK_OFF_SECONDS, float(boiler_anti_cycling_seconds) + 60.0
            )

        self._smoothing_alpha: float = smoothing_alpha
        self._store: Store[dict[str, Any]] | None = None

        # Timing internals
        self._latest_on_time_seconds: float = 0.0
        self._average_on_time_seconds: float | None = None
        self._last_cycle_duration_seconds: float | None = None

        self._has_completed_first_cycle: bool = False
        self._flame_on_monotonic: float | None = None
        self._flame_off_monotonic: float | None = None
        self._demand_since_monotonic: float | None = None
        self._hot_water_since_monotonic: float | None = None
        self._demand_ended_monotonic: float | None = None
        self._waiting_for_flame_since_monotonic: float | None = None
        self._waited_for_flame_seconds: float = 0.0
        self._pwm_planned_on_seconds: float | None = None
        self._burn_peak_flow: float | None = None
        self._burn_peak_monotonic: float | None = None
        self._burn_hot_water: bool = False
        self._burn_ignition_flow: float | None = None
        self._burn_highest_setpoint: float | None = None
        self._hot_water_seen_monotonic: float | None = None
        self._burn_setpoint: float | None = None
        self._last_cut_short_peak_flow: float | None = None
        self._last_cut_short_setpoint: float | None = None
        self._pending_cut_out: tuple[float, float, float, float] | None = None

        # Stored states
        self._last_boiler_state: BoilerState | None = None
        self._last_pulse_width_modulation_state: PWMState | None = None
        self._pwm_state_updated_monotonic: float | None = None

        # Rolling windows
        self._last_update_monotonic: float | None = None
        self._cycle_end_times_window: deque[float] = deque()
        self._on_deltas_window: deque[tuple[float, float]] = deque()
        self._on_durations_window: deque[tuple[float, float]] = deque()
        self._pwm_burns_cut_short: deque[tuple[float, bool]] = deque(maxlen=3)
        self._flame_losses: deque[float] = deque(maxlen=200)
        self._relight_waits: deque[float] = deque(maxlen=10)
        self._last_burn_heating = False
        self._setpoint_floor = self.UNFLAGGED_HOT_WATER_SETPOINT_FLOOR

        # Health
        self._health_status: FlameStatus = FlameStatus.INSUFFICIENT_DATA

    async def async_initialize(self, hass: HomeAssistant, entry_id: str) -> None:
        # The climate is re-added without a reload when its entity id changes,
        # and the windows already hold everything stored
        if self._store is not None:
            return

        self._store = flame_store(hass, entry_id)

        if (data := await self._store.async_load()) is None:
            return

        # Stored as wall-clock times: monotonic time restarts with the process
        offset = monotonic() - time()

        self._average_on_time_seconds = data.get("average_on_time_seconds")
        self._last_cycle_duration_seconds = data.get("last_cycle_duration_seconds")
        self._last_cut_short_peak_flow = data.get("last_cut_short_peak_flow")
        self._last_cut_short_setpoint = data.get("last_cut_short_setpoint")
        self._has_completed_first_cycle = self._average_on_time_seconds is not None

        def stored(key: str) -> list[tuple[float, Any]]:
            return [(ended + offset, value) for ended, value in data.get(key, [])]

        # Anything recorded since setup goes after the stored entries,
        # so a full bounded window drops the oldest
        self._cycle_end_times_window = deque(
            [
                *(ended + offset for ended in data.get("cycle_end_times", [])),
                *self._cycle_end_times_window,
            ]
        )
        self._on_durations_window = deque([*stored("on_durations"), *self._on_durations_window])
        self._on_deltas_window = deque([*stored("on_deltas"), *self._on_deltas_window])
        self._pwm_burns_cut_short = deque(
            [*stored("pwm_burns_cut_short"), *self._pwm_burns_cut_short],
            maxlen=self._pwm_burns_cut_short.maxlen,
        )
        self._flame_losses = deque(
            [*(ended + offset for ended in data.get("flame_losses", [])), *self._flame_losses],
            maxlen=self._flame_losses.maxlen,
        )
        self._relight_waits = deque(
            [
                *(float(wait) for wait in data.get("relight_waits", [])),
                *self._relight_waits,
            ],
            maxlen=self._relight_waits.maxlen,
        )

        _LOGGER.debug("Loaded %d flame cycles from storage.", len(self._on_durations_window))

    def _data_to_save(self) -> dict[str, Any]:
        offset = time() - monotonic()

        return {
            "average_on_time_seconds": self._average_on_time_seconds,
            "last_cycle_duration_seconds": self._last_cycle_duration_seconds,
            "last_cut_short_peak_flow": self._last_cut_short_peak_flow,
            "last_cut_short_setpoint": self._last_cut_short_setpoint,
            "cycle_end_times": [ended + offset for ended in self._cycle_end_times_window],
            "on_durations": [(ended + offset, value) for ended, value in self._on_durations_window],
            "on_deltas": [(ended + offset, value) for ended, value in self._on_deltas_window],
            "pwm_burns_cut_short": [
                (ended + offset, value) for ended, value in self._pwm_burns_cut_short
            ],
            "flame_losses": [ended + offset for ended in self._flame_losses],
            "relight_waits": list(self._relight_waits),
        }

    @property
    def health_status(self) -> FlameStatus:
        return self._health_status

    @property
    def is_active(self) -> bool:
        return self._is_flame_active_internal()

    @property
    def is_inactive(self) -> bool:
        return not self._is_flame_active_internal()

    @property
    def on_since(self) -> float | None:
        if self._is_flame_active_internal() and self._flame_on_monotonic is not None:
            return self._flame_on_monotonic

        return None

    @property
    def latest_on_time_seconds(self) -> float | None:
        if self._is_flame_active_internal() and self._flame_on_monotonic is not None:
            return self._latest_on_time_seconds

        return None

    @property
    def average_on_time_seconds(self) -> float | None:
        return self._average_on_time_seconds if self._has_completed_first_cycle else None

    @property
    def last_cycle_duration_seconds(self) -> float | None:
        return self._last_cycle_duration_seconds

    @property
    def last_cut_short_peak_flow(self) -> float | None:
        return self._last_cut_short_peak_flow

    @property
    def last_cut_short_setpoint(self) -> float | None:
        return self._last_cut_short_setpoint

    @property
    def hot_water_burn(self) -> bool:
        """Return True while the running burn heats hot water, flagged by the boiler or not."""
        return self._is_flame_active_internal() and (
            self._burn_hot_water or self._burn_looks_like_hot_water(monotonic())
        )

    def _burn_looks_like_hot_water(self, now: float) -> bool:
        """Judge the running burn; the setpoint the boiler reports needs a moment to settle."""
        return (
            self._flame_on_monotonic is not None
            and now - self._flame_on_monotonic >= self.UNFLAGGED_HOT_WATER_SETTLE_SECONDS
            and self._burn_is_unflagged_hot_water()
        )

    def _burn_is_unflagged_hot_water(self) -> bool:
        """Tell a hot water burn the boiler does not flag from the water it heats.

        The water rises well above anything the boiler heats to for space heating. An exchanger
        still hot from hot water starts a heating burn near that level, so the rise since
        ignition has to be there too.
        """
        if (
            self._burn_peak_flow is None
            or self._burn_ignition_flow is None
            or self._burn_highest_setpoint is None
        ):
            return False
        heating_limit = max(self._burn_highest_setpoint, self._setpoint_floor)
        return (
            self._burn_peak_flow - self._burn_ignition_flow > self.UNFLAGGED_HOT_WATER_MARGIN
            and self._burn_peak_flow > heating_limit + self.UNFLAGGED_HOT_WATER_MARGIN
        )

    def _forgive_cut_out_before_hot_water(self, now: float) -> None:
        """Clear the cut-short mark of a burn the boiler stopped to reheat the cylinder."""
        if self._flame_losses and now - self._flame_losses[-1] <= self.HOT_WATER_TAKEOVER_SECONDS:
            self._flame_losses.pop()
        if (
            self._pwm_burns_cut_short
            and self._pwm_burns_cut_short[-1][1]
            and now - self._pwm_burns_cut_short[-1][0] <= self.HOT_WATER_TAKEOVER_SECONDS
        ):
            self._pwm_burns_cut_short[-1] = (self._pwm_burns_cut_short[-1][0], False)
            self._pending_cut_out = None

    def _report_cut_out(self, now: float) -> None:
        """Warn about an ignition cut-out once no hot water demand explains it."""
        if self._pending_cut_out is None:
            return
        ended, duration, peak, setpoint = self._pending_cut_out
        if now - ended <= self.HOT_WATER_TAKEOVER_SECONDS:
            return
        self._pending_cut_out = None
        self._last_cut_short_peak_flow = peak
        self._last_cut_short_setpoint = setpoint
        _LOGGER.warning(
            "The boiler stopped a PWM burn after %.0fs with the flow at %.1f°C "
            "against a %.1f°C setpoint; raise the overshoot protection value",
            duration,
            peak,
            setpoint,
        )
        if self._store:
            self._store.async_delay_save(self._data_to_save)

    @property
    def cut_short_burn_ends(self) -> tuple[float, ...]:
        return tuple(ended for ended, cut_short in self._pwm_burns_cut_short if cut_short)

    @property
    def flame_loss_ends(self) -> tuple[float, ...]:
        """When heating burns lost their flame well below the setpoint, oldest first."""
        return tuple(self._flame_losses)

    def set_setpoint_floor(self, minimum: float | None) -> None:
        """Take the boiler's lowest heating setpoint, which it raises lower setpoints to."""
        self._setpoint_floor = (
            float(minimum)
            if minimum is not None and 10 <= minimum <= 60  # noqa: PLR2004
            else self.UNFLAGGED_HOT_WATER_SETPOINT_FLOOR
        )

    @property
    def learned_relight_wait_seconds(self) -> float | None:
        """How long the boiler waits before it relights for heating, once seen often enough."""
        if len(self._relight_waits) < self.RELIGHT_WAIT_MINIMUM_SAMPLES:
            return None
        return median(self._relight_waits)

    @property
    def flame_losses_last_day(self) -> int:
        now = monotonic()
        return sum(
            1 for ended in self._flame_losses if now - ended <= self.FLAME_LOSS_WINDOW_SECONDS
        )

    @property
    def cycles_last_hour(self) -> float:
        return self._cycles_per_hour(monotonic())

    @property
    def duty_ratio_last_15m(self) -> float:
        return self._duty_ratio_last_window(monotonic())

    @property
    def median_on_duration_seconds_4h(self) -> float | None:
        median_value, _ = self._median_on_duration(monotonic())
        return median_value

    @property
    def sample_count_4h(self) -> int:
        _, count = self._median_on_duration(monotonic())
        return count

    def update(self, boiler_state: BoilerState, pwm_state: PWMState | None = None) -> None:

        now = monotonic()

        # Initialize the last update time if this is the first update
        if self._last_update_monotonic is None:
            self._last_update_monotonic = now

        # Accumulate duty time since the last tick when the previous flame state was ON
        currently_active = bool(boiler_state.flame_active)
        previously_active = self._is_flame_active_internal()
        elapsed = max(0.0, now - self._last_update_monotonic)

        # Update internal state tracking
        self._last_boiler_state = boiler_state
        if pwm_state is not None:
            self._last_pulse_width_modulation_state = pwm_state
            self._pwm_state_updated_monotonic = now
        if boiler_state.hot_water_active:
            self._hot_water_seen_monotonic = now
            self._forgive_cut_out_before_hot_water(now)

        self._report_cut_out(now)

        if previously_active and elapsed > 0.0:
            self._on_deltas_window.append((now, elapsed))

        self._prune_duty_window(now)

        # OFF -> ON
        if currently_active and not previously_active:
            self._learn_relight_wait(now)
            pwm = self._fresh_pulse_width_modulation_state(now)
            hot_water = (
                self._hot_water_seen_monotonic is not None
                and now - self._hot_water_seen_monotonic <= self.HOT_WATER_LEAD_SECONDS
                and (
                    self._flame_off_monotonic is None
                    or self._hot_water_seen_monotonic > self._flame_off_monotonic
                )
            )
            pwm_burn = (
                pwm is not None
                and pwm.status == PWMStatus.ON
                and pwm.duty_cycle is not None
                and not hot_water
            )
            self._pwm_planned_on_seconds = pwm.duty_cycle[0] if pwm_burn else None
            self._flame_on_monotonic = now
            self._flame_off_monotonic = None
            self._burn_peak_flow = boiler_state.flow_temperature
            self._burn_peak_monotonic = now
            self._burn_hot_water = hot_water
            self._burn_ignition_flow = boiler_state.flow_temperature
            self._burn_highest_setpoint = boiler_state.setpoint
            self._burn_setpoint = boiler_state.setpoint
            self._last_update_monotonic = now
            self._recompute_health(now)

            _LOGGER.debug("Flame transition OFF->ON")

            return

        # ON -> ON
        if currently_active and self._flame_on_monotonic is not None:
            self._latest_on_time_seconds = now - self._flame_on_monotonic
            self._burn_setpoint = boiler_state.setpoint
            if boiler_state.setpoint is not None and (
                self._burn_highest_setpoint is None
                or boiler_state.setpoint > self._burn_highest_setpoint
            ):
                self._burn_highest_setpoint = boiler_state.setpoint
            if self._burn_ignition_flow is None:
                self._burn_ignition_flow = boiler_state.flow_temperature
            if boiler_state.hot_water_active:
                self._burn_hot_water = True
                self._pwm_planned_on_seconds = None
            if boiler_state.flow_temperature is not None and (
                self._burn_peak_flow is None
                or boiler_state.flow_temperature >= self._burn_peak_flow
            ):
                self._burn_peak_flow = boiler_state.flow_temperature
                self._burn_peak_monotonic = now
            if self._burn_looks_like_hot_water(now):
                self._forgive_cut_out_before_hot_water(now)

            self._last_update_monotonic = now
            self._recompute_health(now)
            return

        # ON -> OFF
        if not currently_active and previously_active:
            duration = (
                (now - self._flame_on_monotonic) if self._flame_on_monotonic is not None else 0.0
            )

            self._flame_on_monotonic = None
            self._flame_off_monotonic = now
            # The setpoint drops to the minimum before the flame goes out, and an exchanger still
            # hot from hot water starts near its peak, so both limits need the burn's own history
            if self._burn_is_unflagged_hot_water():
                self._burn_hot_water = True
                self._pwm_planned_on_seconds = None
                self._forgive_cut_out_before_hot_water(now)
            self._last_burn_heating = not self._burn_hot_water

            self._prune_cycles_window(now)
            self._prune_median_window(now)

            # Hot water keep-warm burns last seconds by design and say nothing about heating cycles
            if not self._burn_hot_water:
                self._last_cycle_duration_seconds = duration
                self._average_on_time_seconds = (
                    duration
                    if self._average_on_time_seconds is None
                    else (1.0 - self._smoothing_alpha) * self._average_on_time_seconds
                    + self._smoothing_alpha * duration
                )
                self._cycle_end_times_window.append(now)
                self._on_durations_window.append((now, duration))

            # A burn that ends while PWM is still ON was ended by the boiler, not by PWM
            pwm = self._fresh_pulse_width_modulation_state(now)
            if self._pwm_planned_on_seconds is not None and pwm is not None:
                # A flow above the cut-out at ignition is residual heat, not an ignition spike
                lit_above_cut_out = (
                    self._burn_ignition_flow is not None
                    and self._burn_highest_setpoint is not None
                    and self._burn_ignition_flow
                    > self._burn_highest_setpoint + self.IGNITION_OVERSHOOT_MARGIN
                )
                cut_short = (
                    pwm.status == PWMStatus.ON
                    and duration < self._pwm_planned_on_seconds
                    and not lit_above_cut_out
                )
                # Far below the setpoint the boiler did not cut out, it lost the flame and
                # relights by itself; the water could take the heat
                if (
                    cut_short
                    and self._burn_peak_flow is not None
                    and self._burn_highest_setpoint is not None
                    and self._burn_peak_flow
                    < self._burn_highest_setpoint - self.FLAME_LOSS_SETPOINT_MARGIN
                ):
                    cut_short = False
                    self._flame_losses.append(now)
                    _LOGGER.info(
                        "The flame went out after %.0fs with the flow at %.1f°C, "
                        "well below the %.1f°C setpoint (%d in the last day).",
                        duration,
                        self._burn_peak_flow,
                        self._burn_highest_setpoint,
                        self.flame_losses_last_day,
                    )
                self._pwm_burns_cut_short.append((now, cut_short))

                if (
                    cut_short
                    and self._burn_peak_flow is not None
                    and self._burn_setpoint is not None
                    and self._burn_peak_flow > self._burn_setpoint + self.IGNITION_OVERSHOOT_MARGIN
                    and self._burn_peak_monotonic is not None
                    and now - self._burn_peak_monotonic <= self.IGNITION_CUT_OUT_SECONDS
                ):
                    # Reported once it is clear the boiler did not stop for a cylinder reheat
                    self._pending_cut_out = (
                        now,
                        duration,
                        self._burn_peak_flow,
                        self._burn_setpoint,
                    )

            self._pwm_planned_on_seconds = None

            self._has_completed_first_cycle = True
            self._last_update_monotonic = now

            if self._store:
                self._store.async_delay_save(self._data_to_save)

            _LOGGER.debug(
                "Flame transition ON->OFF: duration=%.1fs, cycles_last_hour=%.1f, samples_4h=%d",
                duration,
                self._cycles_per_hour(now),
                self.sample_count_4h,
            )

            self._recompute_health(now)
            return

        # OFF -> OFF
        if not currently_active:
            if self._flame_off_monotonic is None:
                self._flame_off_monotonic = now

            self._last_update_monotonic = now
            self._recompute_health(now)
            return

    def _learn_relight_wait(self, now: float) -> None:
        """Record the relight wait shown by a heating burn that had to wait under demand."""
        held = self._waited_for_flame_seconds + (
            now - self._waiting_for_flame_since_monotonic
            if self._waiting_for_flame_since_monotonic is not None
            else 0.0
        )
        if (
            not self._last_burn_heating
            or self._flame_off_monotonic is None
            or held < self.RELIGHT_WAIT_MINIMUM_HELD_SECONDS
            or (self._hot_water_seen_monotonic or 0.0) > self._flame_off_monotonic
        ):
            return
        wait = now - self._flame_off_monotonic
        low, high = self.RELIGHT_WAIT_BOUNDS
        if low <= wait <= high:
            self._relight_waits.append(round(wait))
            _LOGGER.debug("The boiler relit %.0f s after the last heating burn.", wait)

    def _recompute_health(self, now: float) -> None:
        state = self._last_boiler_state
        if state is None:
            self._health_status = FlameStatus.INSUFFICIENT_DATA
            return

        domestic_hot_water_active = bool(state.hot_water_active)
        heating_demand = bool(state.is_active) or (state.status in self._HEATING_STATUSES)

        if not heating_demand and not domestic_hot_water_active:
            if self._demand_since_monotonic is not None:
                self._demand_ended_monotonic = now
            self._demand_since_monotonic = None
        elif self._demand_since_monotonic is None:
            self._demand_since_monotonic = now

        # A hot water request can only be late since it began, not since a heating demand that
        # was already waiting (a boiler in anti-cycling keeps its heating demand)
        if not domestic_hot_water_active:
            self._hot_water_since_monotonic = None
        elif self._hot_water_since_monotonic is None:
            self._hot_water_since_monotonic = now

        # A Remeha keeps its CH mode bit on while it waits to relight, and relights only once the
        # flow has cooled below the setpoint, so the wait for the flame starts there
        if state.flame_active:
            self._waiting_for_flame_since_monotonic = None
            self._waited_for_flame_seconds = 0.0
        elif heating_demand and state.status == BoilerStatus.WAITING_FOR_FLAME:
            if self._waiting_for_flame_since_monotonic is None:
                self._waiting_for_flame_since_monotonic = now
        elif state.status not in self._TRANSIENT_STATUSES:
            # The boiler reports the OFF phase setpoint until a new ON phase setpoint is echoed
            # back, so IDLE pauses the wait for as long as PWM runs
            if (
                state.status == BoilerStatus.IDLE
                and (pwm := self._fresh_pulse_width_modulation_state(now)) is not None
                and pwm.status in (PWMStatus.ON, PWMStatus.OFF)
            ):
                if self._waiting_for_flame_since_monotonic is not None:
                    self._waited_for_flame_seconds += now - self._waiting_for_flame_since_monotonic
            else:
                self._waited_for_flame_seconds = 0.0
            self._waiting_for_flame_since_monotonic = None

        # The flame can only be late since the demand started, not since it last went out, and
        # only stuck on since the demand ended, not since it lit
        last_on_seconds = (
            (now - max(self._flame_on_monotonic, self._demand_ended_monotonic or 0.0))
            if (state.flame_active and self._flame_on_monotonic is not None)
            else 0.0
        )
        last_off_seconds = (
            (
                now
                - max(
                    self._flame_off_monotonic,
                    self._demand_since_monotonic or 0.0,
                    self._hot_water_since_monotonic or 0.0,
                )
            )
            if (not state.flame_active and self._flame_off_monotonic is not None)
            else 0.0
        )
        waiting_for_flame_seconds = self._waited_for_flame_seconds + (
            (now - self._waiting_for_flame_since_monotonic)
            if self._waiting_for_flame_since_monotonic is not None
            else 0.0
        )

        cycles_per_hour = self._cycles_per_hour(now)
        duty_ratio = self._duty_ratio_last_window(now)
        median_on_seconds, sample_count = self._median_on_duration(now)

        modulating_boiler = state.relative_modulation_level is not None and isinstance(
            state.relative_modulation_level, (int, float)
        )

        # Thin history: still allow stuck checks, avoid cycling judgments
        if sample_count < self.MIN_ON_SAMPLES_FOR_HEALTH:
            if not heating_demand and not domestic_hot_water_active:
                if state.flame_active and last_on_seconds > self.STUCK_ON_WITHOUT_DEMAND_SECONDS:
                    self._health_status = FlameStatus.STUCK_ON
                else:
                    self._health_status = FlameStatus.IDLE_OK

                return

            off_seconds, timeout = (
                (last_off_seconds, self.MAX_DOMESTIC_HOT_WATER_IDLE_OFF_SECONDS)
                if domestic_hot_water_active
                else (waiting_for_flame_seconds, self.STUCK_OFF_SECONDS)
            )
            if (
                (not state.flame_active)
                and off_seconds > timeout
                and state.status not in self._TRANSIENT_STATUSES
            ):
                self._health_status = FlameStatus.STUCK_OFF
            else:
                self._health_status = FlameStatus.HEALTHY

            return

        # No demand and not domestic hot water
        if not heating_demand and not domestic_hot_water_active:
            if state.flame_active and last_on_seconds > self.STUCK_ON_WITHOUT_DEMAND_SECONDS:
                self._health_status = FlameStatus.STUCK_ON
            else:
                self._health_status = FlameStatus.IDLE_OK

            return

        # Domestic hot water: allow continuous flame;
        # only stuck-off if off too long (and not transient)
        if domestic_hot_water_active:
            if (
                (not state.flame_active)
                and last_off_seconds > self.MAX_DOMESTIC_HOT_WATER_IDLE_OFF_SECONDS
                and state.status not in self._TRANSIENT_STATUSES
            ):
                self._health_status = FlameStatus.STUCK_OFF
            else:
                self._health_status = FlameStatus.HEALTHY

            return

        # Space heating demand
        if (
            (not state.flame_active)
            and waiting_for_flame_seconds > self.STUCK_OFF_SECONDS
            and state.status not in self._TRANSIENT_STATUSES
        ):
            self._health_status = FlameStatus.STUCK_OFF
            return

        # PWM-driven demand
        if (
            pwm := self._fresh_pulse_width_modulation_state(now)
        ) is not None and pwm.status == PWMStatus.ON:
            if cycles_per_hour > self.MAX_CYCLES_PER_HOUR_PWM:
                self._health_status = FlameStatus.SHORT_CYCLING
                return

            if (
                sum(
                    cut_short
                    for ended, cut_short in self._pwm_burns_cut_short
                    if ended >= now - self.MEDIAN_WINDOW_SECONDS
                )
                >= self.PWM_SHORT_BURNS_THRESHOLD
            ):
                self._health_status = FlameStatus.PWM_SHORT
                return

            self._health_status = FlameStatus.HEALTHY
            return

        # Non-PWM: internal regulation; do not require continuous flame
        if modulating_boiler:
            if (
                cycles_per_hour <= self.MAX_CYCLES_PER_HOUR_MODULATING_STEADY
                and duty_ratio >= 0.8 * self.EXPECTED_MODULATING_DUTY_RATIO_WHEN_HEATING
            ):
                self._health_status = FlameStatus.HEALTHY
                return

            if (
                median_on_seconds is not None
                and median_on_seconds < self.MEDIAN_TOLERANCE * 180
                and cycles_per_hour > self.MAX_CYCLES_PER_HOUR_NON_PWM
            ):
                self._health_status = FlameStatus.SHORT_CYCLING
                return

            self._health_status = FlameStatus.HEALTHY
            return

        # Non-modulating boiler
        if (
            median_on_seconds is not None
            and median_on_seconds < self.MEDIAN_TOLERANCE * 180
            and cycles_per_hour > self.MAX_CYCLES_PER_HOUR_NON_PWM
        ):
            self._health_status = FlameStatus.SHORT_CYCLING
            return

        self._health_status = FlameStatus.HEALTHY

    def _fresh_pulse_width_modulation_state(self, now: float) -> PWMState | None:
        # Only the control loop sends the PWM state,
        # so it goes stale while SAT is off, paused or offline
        if (
            self._pwm_state_updated_monotonic is None
            or now - self._pwm_state_updated_monotonic > CONTROL_LOOP_STALL_TIME.total_seconds()
        ):
            return None

        return self._last_pulse_width_modulation_state

    def _prune_duty_window(self, now: float) -> None:
        cutoff = now - self.DUTY_WINDOW_SECONDS
        while self._on_deltas_window and self._on_deltas_window[0][0] < cutoff:
            self._on_deltas_window.popleft()

    def _prune_cycles_window(self, now: float) -> None:
        cutoff = now - self.CYCLES_WINDOW_SECONDS
        while self._cycle_end_times_window and self._cycle_end_times_window[0] < cutoff:
            self._cycle_end_times_window.popleft()

    def _prune_median_window(self, now: float) -> None:
        cutoff = now - self.MEDIAN_WINDOW_SECONDS
        while self._on_durations_window and self._on_durations_window[0][0] < cutoff:
            self._on_durations_window.popleft()

    def _duty_ratio_last_window(self, now: float) -> float:
        self._prune_duty_window(now)
        on_seconds = sum(delta for _, delta in self._on_deltas_window)
        return min(1.0, max(0.0, on_seconds / float(self.DUTY_WINDOW_SECONDS)))

    def _cycles_per_hour(self, now: float) -> float:
        self._prune_cycles_window(now)
        return float(len(self._cycle_end_times_window))

    def _median_on_duration(self, now: float) -> tuple[float | None, int]:
        self._prune_median_window(now)
        if not self._on_durations_window:
            return None, 0

        durations = [duration for _, duration in self._on_durations_window]
        return float(median(durations)), len(durations)

    def _is_flame_active_internal(self) -> bool:
        return bool(self._last_boiler_state.flame_active) if self._last_boiler_state else False
