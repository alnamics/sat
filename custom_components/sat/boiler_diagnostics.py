"""Raise Home Assistant repair issues for boiler conditions that need a person.

* low water pressure, which ends in a lockout if nobody tops the system up;
* water pressure that keeps falling over days, a leak or a failing expansion vessel, raised
  long before the pressure is low;
* a fault the boiler reports, with its manufacturer code;
* a heat exchanger that gets dirty: in a settled space heating burn the flue gas of a clean
  condensing boiler runs a few kelvin above the return water, and the gap grows as deposits build.
  Burns with flue gas above 90 °C do not condense and are left out;
* flow water hotter than a screed floor should get;
* a large flow/return spread in settled burns, which means too little water moves (closed
  loops, a blocked filter or air);
* a boiler service that is due;
* gas use per degree day clearly above the weeks before.
"""

from __future__ import annotations

import calendar
from collections import deque
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from datetime import date

    from homeassistant.core import HomeAssistant

SECONDS_PER_HOUR = 3600.0
MAXIMUM_STEP_SECONDS = 300.0

LOW_PRESSURE = 0.8
PRESSURE_RECOVERED = 0.9
LOW_PRESSURE_SECONDS = 600.0
# Daily minimum pressures; a fall of 0.05 bar a week over at least four days is a leak
PRESSURE_HISTORY_DAYS = 14
PRESSURE_TREND_MINIMUM_DAYS = 4
PRESSURE_FALLING_PER_DAY = -0.007
PRESSURE_STEADY_PER_DAY = -0.003
PRESSURE_FALLING_MINIMUM_DROP = 0.1

FAULT_SECONDS = 60.0
# Flue gas above return in settled burns; averaged over a day of burning
FOULING_GAP = 12.0
FOULING_CLEARED = 9.0
FOULING_AVERAGING_HOURS = 24.0
FOULING_MINIMUM_HOURS = 6.0
# Flue gas this hot means the boiler does not condense (an older boiler, or very hot return
# water), where a large gap is normal and says nothing about the heat exchanger
CONDENSING_EXHAUST_LIMIT = 90.0

SCREED_OVERHEAT_SECONDS = 180.0
# The issue stays up for a day after the last time, so nobody misses it
SCREED_ISSUE_HOLD_SECONDS = 24 * SECONDS_PER_HOUR
LOW_FLOW_SPREAD = 20.0
LOW_FLOW_CLEARED_SPREAD = 12.0
LOW_FLOW_SECONDS = 300.0

GAS_USE_INCREASED = 1.3
GAS_USE_NORMAL = 1.15


def boiler_diagnostics_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.boiler_diagnostics")


def pressure_trend(minima: list[float]) -> float | None:
    """Least squares slope of daily pressures, in bar per day."""
    count = len(minima)
    if count < PRESSURE_TREND_MINIMUM_DAYS:
        return None
    mean_x = (count - 1) / 2
    mean_y = sum(minima) / count
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(minima))
    denominator = sum((x - mean_x) ** 2 for x in range(count))
    return numerator / denominator


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    # The last day of the month when the day does not exist there
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


class BoilerDiagnostics:
    """Track boiler conditions and keep the matching repair issues up to date."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        title: str,
        *,
        screed_limit: float | None = None,
        last_service: date | None = None,
        service_interval_months: int = 12,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._title = title
        self._screed_limit = screed_limit
        self._service_due = (
            None if last_service is None else add_months(last_service, service_interval_months)
        )
        self._store: Store[dict[str, Any]] | None = None
        self._last_update: float | None = None

        self._low_pressure_since: float | None = None
        self._pressure_day: str | None = None
        self._pressure_minimum: float | None = None
        self._pressure_days: deque[float] = deque(maxlen=PRESSURE_HISTORY_DAYS)

        self._fault_since: float | None = None
        self._gap: float | None = None
        self._gap_hours = 0.0
        self._screed_hot_since: float | None = None
        self._screed_last: float | None = None
        self._low_flow_since: float | None = None
        self._active: dict[str, bool] = {}

    async def async_initialize(self) -> None:
        if self._store is not None:
            return
        self._store = boiler_diagnostics_store(self._hass, self._entry_id)
        if (data := await self._store.async_load()) is None:
            return
        days = data.get("pressure_days")
        if isinstance(days, list):
            self._pressure_days.extend(float(v) for v in days if isinstance(v, int | float))

    @property
    def flue_return_gap(self) -> float | None:
        return None if self._gap is None else round(self._gap, 1)

    @property
    def pressure_trend_per_week(self) -> float | None:
        trend = pressure_trend(list(self._pressure_days))
        return None if trend is None else round(trend * 7, 3)

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            "flue_return_gap": self.flue_return_gap,
            "pressure_trend_bar_per_week": self.pressure_trend_per_week,
            "boiler_service_due": None if self._service_due is None else str(self._service_due),
            "active_issues": sorted(key for key, on in self._active.items() if on),
        }

    def update(
        self,
        now: float,
        *,
        pressure: float | None,
        fault: bool,
        fault_code: int | None,
        exhaust: float | None,
        return_temperature: float | None,
        settled_heating_burn: bool,
        today: date | None = None,
        flow: float | None = None,
        heating_burn: bool = False,
        gas_use_ratio: float | None = None,
    ) -> None:
        dt = (
            0.0 if self._last_update is None else min(now - self._last_update, MAXIMUM_STEP_SECONDS)
        )
        self._last_update = now

        self._update_pressure(now, pressure, today)
        self._update_fault(now, fault=fault, fault_code=fault_code)
        self._update_fouling(
            dt, exhaust=exhaust, return_temperature=return_temperature, settled=settled_heating_burn
        )
        self._update_screed(now, flow=flow, heating_burn=heating_burn)
        self._update_low_flow(
            now, flow=flow, return_temperature=return_temperature, settled=settled_heating_burn
        )

        if self._service_due is not None and today is not None:
            if today >= self._service_due:
                self._set(
                    "boiler_service_due", active=True, placeholders={"due": str(self._service_due)}
                )
            else:
                self._set("boiler_service_due", active=False)

        if gas_use_ratio is not None:
            if gas_use_ratio >= GAS_USE_INCREASED:
                self._set(
                    "gas_use_increased",
                    active=True,
                    placeholders={"percent": f"{(gas_use_ratio - 1) * 100:.0f}"},
                )
            elif gas_use_ratio < GAS_USE_NORMAL:
                self._set("gas_use_increased", active=False)

    def _update_pressure(self, now: float, pressure: float | None, today: date | None) -> None:
        # Low water pressure, with a margin before clearing
        if pressure is not None and pressure < LOW_PRESSURE:
            if self._low_pressure_since is None:
                self._low_pressure_since = now
            if now - self._low_pressure_since >= LOW_PRESSURE_SECONDS:
                self._set(
                    "low_water_pressure",
                    active=True,
                    placeholders={"pressure": f"{pressure:.2f}"},
                )
        elif pressure is None or pressure >= PRESSURE_RECOVERED:
            self._low_pressure_since = None
            self._set("low_water_pressure", active=False)

        if pressure is None or today is None:
            return

        # The lowest pressure of each day, when the system is coolest, shows a slow loss
        day = today.isoformat()
        if day != self._pressure_day:
            if self._pressure_day is not None and self._pressure_minimum is not None:
                self._pressure_days.append(self._pressure_minimum)
                self._evaluate_pressure_trend()
                if self._store is not None:
                    self._store.async_delay_save(
                        lambda: {"pressure_days": list(self._pressure_days)}, 1
                    )
            self._pressure_day = day
            self._pressure_minimum = pressure
        elif self._pressure_minimum is None or pressure < self._pressure_minimum:
            self._pressure_minimum = pressure

    def _evaluate_pressure_trend(self) -> None:
        days = list(self._pressure_days)
        trend = pressure_trend(days)
        if trend is None:
            return
        if (
            trend <= PRESSURE_FALLING_PER_DAY
            and max(days) - days[-1] >= PRESSURE_FALLING_MINIMUM_DROP
        ):
            self._set(
                "pressure_falling",
                active=True,
                placeholders={
                    "per_week": f"{-trend * 7:.2f}",
                    "pressure": f"{days[-1]:.2f}",
                },
            )
        elif trend >= PRESSURE_STEADY_PER_DAY:
            self._set("pressure_falling", active=False)

    def _update_fault(self, now: float, *, fault: bool, fault_code: int | None) -> None:
        if fault or bool(fault_code):
            if self._fault_since is None:
                self._fault_since = now
            if now - self._fault_since >= FAULT_SECONDS:
                self._set(
                    "boiler_fault", active=True, placeholders={"code": str(fault_code or "-")}
                )
        else:
            self._fault_since = None
            self._set("boiler_fault", active=False)

    def _update_fouling(
        self,
        dt: float,
        *,
        exhaust: float | None,
        return_temperature: float | None,
        settled: bool,
    ) -> None:
        # Heat exchanger fouling: the flue gas creeps away from the return water
        if (
            settled
            and exhaust is not None
            and exhaust <= CONDENSING_EXHAUST_LIMIT
            and return_temperature is not None
            and dt
        ):
            gap = exhaust - return_temperature
            weight = min(1.0, dt / (FOULING_AVERAGING_HOURS * SECONDS_PER_HOUR))
            self._gap = gap if self._gap is None else self._gap + (gap - self._gap) * weight
            self._gap_hours += dt / SECONDS_PER_HOUR

        if self._gap is not None and self._gap_hours >= FOULING_MINIMUM_HOURS:
            if self._gap > FOULING_GAP:
                self._set(
                    "heat_exchanger_fouling",
                    active=True,
                    placeholders={"gap": f"{self._gap:.0f}"},
                )
            elif self._gap < FOULING_CLEARED:
                self._set("heat_exchanger_fouling", active=False)

    def _update_screed(self, now: float, *, flow: float | None, heating_burn: bool) -> None:
        if self._screed_limit is None:
            return

        if heating_burn and flow is not None and flow > self._screed_limit:
            if self._screed_hot_since is None:
                self._screed_hot_since = now
            if now - self._screed_hot_since >= SCREED_OVERHEAT_SECONDS:
                self._screed_last = now
                self._set(
                    "screed_overheat",
                    active=True,
                    placeholders={"flow": f"{flow:.0f}", "limit": f"{self._screed_limit:.0f}"},
                )
        else:
            self._screed_hot_since = None

        if self._screed_last is not None and now - self._screed_last >= SCREED_ISSUE_HOLD_SECONDS:
            self._screed_last = None
            self._set("screed_overheat", active=False)

    def _update_low_flow(
        self,
        now: float,
        *,
        flow: float | None,
        return_temperature: float | None,
        settled: bool,
    ) -> None:
        if not settled or flow is None or return_temperature is None:
            self._low_flow_since = None
            return

        spread = flow - return_temperature
        if spread > LOW_FLOW_SPREAD:
            if self._low_flow_since is None:
                self._low_flow_since = now
            if now - self._low_flow_since >= LOW_FLOW_SECONDS:
                self._set("low_water_flow", active=True, placeholders={"spread": f"{spread:.0f}"})
        else:
            self._low_flow_since = None
            if spread < LOW_FLOW_CLEARED_SPREAD:
                self._set("low_water_flow", active=False)

    def _set(self, key: str, *, active: bool, placeholders: dict[str, str] | None = None) -> None:
        previous = self._active.get(key)
        if previous == active:
            return

        issue_id = f"{key}_{self._entry_id}"
        if active:
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=key,
                translation_placeholders={"title": self._title, **(placeholders or {})},
            )
        else:
            # Also clears an issue left over from before a restart
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)

        self._active[key] = active
