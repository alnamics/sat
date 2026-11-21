"""Raise Home Assistant repair issues for boiler conditions that need a person.

* low water pressure, which ends in a lockout if nobody tops the system up;
* water pressure that keeps falling over days, a leak or a failing expansion vessel, raised
  long before the pressure is low (corrected for the water temperature, see pressure_trend);
* a fault the boiler reports, with its manufacturer code;
* a heat exchanger that gets dirty: in a settled space heating burn near minimum power the flue
  gas of a clean condensing boiler runs a few kelvin above the return water, and the gap grows
  as deposits build. At higher power the gap is larger by design, so only burns near the minimum
  count, and burns with flue gas above 90 °C do not condense and are left out;
* flow water hotter than a screed floor should get;
* on underfloor heating, a large flow/return spread in settled burns, which means too little
  water moves (closed loops, a blocked filter or air). Radiators run such spreads by design;
* a boiler service that is due;
* gas use per degree day clearly above the weeks before;
* a hot water cylinder that cools when a heating burn starts: with no tap open it should lose
  well under a kelvin in ten minutes, so a regular drop of a few kelvin means heating water
  gets into the cylinder coil (a diverter valve that does not close fully).
"""

from __future__ import annotations

import calendar
from collections import deque
from statistics import median
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .pressure_trend import PressureTrend

if TYPE_CHECKING:
    from datetime import date

    from homeassistant.core import HomeAssistant

SECONDS_PER_HOUR = 3600.0
MAXIMUM_STEP_SECONDS = 300.0

LOW_PRESSURE = 0.8
PRESSURE_RECOVERED = 0.9
LOW_PRESSURE_SECONDS = 600.0
# A fall of 0.05 bar a week over at least four days is a leak
PRESSURE_FALLING_PER_DAY = -0.007
PRESSURE_STEADY_PER_DAY = -0.003
PRESSURE_FALLING_MINIMUM_DROP = 0.1

FAULT_SECONDS = 60.0
# Heating burns that lost their flame in a day: a few happen, this many want a service visit
FLAME_LOSSES_PER_DAY = 6
FLAME_LOSSES_CLEARED = 2
# Flue gas above return in settled burns; averaged over a day of burning
FOULING_GAP = 12.0
FOULING_CLEARED = 9.0
FOULING_AVERAGING_HOURS = 24.0
FOULING_MINIMUM_HOURS = 6.0
# Burn time between two saves of the flue gas average
GAP_SAVE_HOURS = 0.1
# Flue gas this hot means the boiler does not condense (an older boiler, or very hot return
# water), where a large gap is normal and says nothing about the heat exchanger
CONDENSING_EXHAUST_LIMIT = 90.0

SCREED_OVERHEAT_SECONDS = 180.0
# The issue stays up for a day after the last time, so nobody misses it
SCREED_ISSUE_HOLD_SECONDS = 24 * SECONDS_PER_HOUR
LOW_FLOW_SPREAD = 20.0
LOW_FLOW_CLEARED_SPREAD = 12.0
LOW_FLOW_SECONDS = 300.0

# Cylinder temperature fall in the first minutes of a heating burn
CYLINDER_WINDOW_SECONDS = 600.0
# A shorter burn says too little
CYLINDER_MINIMUM_BURN_SECONDS = 180.0
CYLINDER_SAMPLES = 10
CYLINDER_MINIMUM_SAMPLES = 5
CYLINDER_DROP = 2.0
CYLINDER_DROP_CLEARED = 1.0

GAS_USE_INCREASED = 1.3
GAS_USE_NORMAL = 1.15


def boiler_diagnostics_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.boiler_diagnostics")


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
        underfloor: bool = False,
        screed_limit: float | None = None,
        last_service: date | None = None,
        service_interval_months: int = 12,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._title = title
        self._underfloor = underfloor
        self._screed_limit = screed_limit
        self._service_due = (
            None if last_service is None else add_months(last_service, service_interval_months)
        )
        self._store: Store[dict[str, Any]] | None = None
        self._last_update: float | None = None

        self._low_pressure_since: float | None = None
        self._pressure = PressureTrend()

        self._fault_since: float | None = None
        self._gap: float | None = None
        self._gap_hours = 0.0
        self._gap_saved_at: float | None = None
        self._screed_hot_since: float | None = None
        self._screed_last: float | None = None
        self._low_flow_since: float | None = None
        self._cylinder_idle: float | None = None
        self._cylinder_burn: tuple[float, float] | None = None
        self._cylinder_drops: deque[float] = deque(maxlen=CYLINDER_SAMPLES)
        self._active: dict[str, bool] = {}

    async def async_initialize(self) -> None:
        if self._store is not None:
            return
        self._store = boiler_diagnostics_store(self._hass, self._entry_id)
        if (data := await self._store.async_load()) is None:
            return
        self._pressure.load(data.get("pressure"))
        gap, hours = data.get("flue_return_gap"), data.get("flue_return_gap_hours")
        if isinstance(gap, int | float) and isinstance(hours, int | float):
            self._gap, self._gap_hours = float(gap), max(0.0, float(hours))
        drops = data.get("cylinder_drops")
        if isinstance(drops, list):
            self._cylinder_drops.extend(
                float(drop) for drop in drops if isinstance(drop, int | float)
            )

    async def async_save(self) -> None:
        if self._store is not None:
            await self._store.async_save(self._data())

    def _data(self) -> dict[str, Any]:
        return {
            "pressure": self._pressure.to_dict(),
            "flue_return_gap": self._gap,
            "flue_return_gap_hours": self._gap_hours,
            "cylinder_drops": list(self._cylinder_drops),
        }

    @property
    def flue_return_gap(self) -> float | None:
        return None if self._gap is None else round(self._gap, 1)

    @property
    def cylinder_drop(self) -> float | None:
        """Median fall of the cylinder temperature in the first minutes of a heating burn."""
        if len(self._cylinder_drops) < CYLINDER_MINIMUM_SAMPLES:
            return None
        return round(median(self._cylinder_drops), 1)

    @property
    def pressure_trend_per_week(self) -> float | None:
        trend = self._pressure.per_day
        return None if trend is None else round(trend * 7, 3)

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            "flue_return_gap": self.flue_return_gap,
            "pressure_trend_bar_per_week": self.pressure_trend_per_week,
            "cylinder_drop_at_heating_start": self.cylinder_drop,
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
        near_minimum_power: bool = True,
        system_temperature: float | None = None,
        hot_water: bool = False,
        flame_losses_last_day: int = 0,
        cylinder_temperature: float | None = None,
    ) -> None:
        dt = (
            0.0 if self._last_update is None else min(now - self._last_update, MAXIMUM_STEP_SECONDS)
        )
        self._last_update = now

        self._update_low_pressure(now, pressure)
        if pressure is not None and today is not None and not hot_water:
            self._update_pressure_trend(dt, today, pressure, system_temperature)
        self._update_fault(now, fault=fault, fault_code=fault_code)
        self._update_flame_losses(flame_losses_last_day)
        self._update_fouling(
            dt,
            exhaust=exhaust,
            return_temperature=return_temperature,
            settled=settled_heating_burn and near_minimum_power,
        )
        self._update_screed(now, flow=flow, heating_burn=heating_burn)
        self._update_cylinder(
            now, temperature=cylinder_temperature, heating_burn=heating_burn, hot_water=hot_water
        )
        if self._underfloor:
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

    def _update_low_pressure(self, now: float, pressure: float | None) -> None:
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

    def _update_pressure_trend(
        self, dt: float, today: date, pressure: float, temperature: float | None
    ) -> None:
        if not self._pressure.update(dt, today.isoformat(), pressure, temperature):
            return

        if self._store is not None:
            self._store.async_delay_save(self._data, 1)

        trend, latest = self._pressure.per_day, self._pressure.latest
        if trend is None or latest is None:
            # Too few days, or a fresh start after a top-up
            self._set("pressure_falling", active=False)
        elif (
            trend <= PRESSURE_FALLING_PER_DAY
            and self._pressure.drop >= PRESSURE_FALLING_MINIMUM_DROP
        ):
            self._set(
                "pressure_falling",
                active=True,
                placeholders={"per_week": f"{-trend * 7:.2f}", "pressure": f"{latest:.2f}"},
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

    def _update_flame_losses(self, losses: int) -> None:
        if losses >= FLAME_LOSSES_PER_DAY:
            self._set("frequent_flame_loss", active=True, placeholders={"count": str(losses)})
        elif losses <= FLAME_LOSSES_CLEARED:
            self._set("frequent_flame_loss", active=False)

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
            # The average builds over hours of burning, so a restart must not start it again
            if self._store is not None and (
                self._gap_saved_at is None or self._gap_hours - self._gap_saved_at >= GAP_SAVE_HOURS
            ):
                self._gap_saved_at = self._gap_hours
                self._store.async_delay_save(self._data, 1)

        if self._gap is not None and self._gap_hours >= FOULING_MINIMUM_HOURS:
            if self._gap > FOULING_GAP:
                self._set(
                    "heat_exchanger_fouling",
                    active=True,
                    placeholders={"gap": f"{self._gap:.0f}"},
                )
            elif self._gap < FOULING_CLEARED:
                self._set("heat_exchanger_fouling", active=False)

    def _update_cylinder(
        self, now: float, *, temperature: float | None, heating_burn: bool, hot_water: bool
    ) -> None:
        if temperature is None or hot_water:
            # A reheat or a tap says nothing about the heating water
            self._cylinder_burn = None
            if hot_water:
                self._cylinder_idle = None
            return

        if not heating_burn:
            if self._cylinder_burn is not None:
                start, before = self._cylinder_burn
                self._cylinder_burn = None
                if now - start >= CYLINDER_MINIMUM_BURN_SECONDS:
                    self._add_cylinder_drop(before - temperature)
            self._cylinder_idle = temperature
            return

        if self._cylinder_burn is None:
            if self._cylinder_idle is None:
                return
            self._cylinder_burn = (now, self._cylinder_idle)
            self._cylinder_idle = None
            return

        start, before = self._cylinder_burn
        if now - start >= CYLINDER_WINDOW_SECONDS:
            self._cylinder_burn = None
            self._add_cylinder_drop(before - temperature)

    def _add_cylinder_drop(self, drop: float) -> None:
        self._cylinder_drops.append(round(drop, 2))
        if self._store is not None:
            self._store.async_delay_save(self._data, 1)

        if (drop := self.cylinder_drop) is None:
            return
        if drop >= CYLINDER_DROP:
            self._set(
                "cylinder_cools_in_heating", active=True, placeholders={"drop": f"{drop:.1f}"}
            )
        elif drop <= CYLINDER_DROP_CLEARED:
            self._set("cylinder_cools_in_heating", active=False)

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
