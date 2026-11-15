"""Raise Home Assistant repair issues for boiler conditions that need a person.

* low water pressure, which ends in a lockout if nobody tops the system up;
* a fault the boiler reports, with its manufacturer code;
* a heat exchanger that gets dirty: in a settled space heating burn the flue gas of a clean
  condensing boiler runs a few kelvin above the return water, and the gap grows as deposits build.
  Burns with flue gas above 90 °C do not condense and are left out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SECONDS_PER_HOUR = 3600.0
MAXIMUM_STEP_SECONDS = 300.0

LOW_PRESSURE = 0.8
PRESSURE_RECOVERED = 0.9
LOW_PRESSURE_SECONDS = 600.0
FAULT_SECONDS = 60.0
# Flue gas above return in settled burns; averaged over a day of burning
FOULING_GAP = 12.0
FOULING_CLEARED = 9.0
FOULING_AVERAGING_HOURS = 24.0
FOULING_MINIMUM_HOURS = 6.0
# Flue gas this hot means the boiler does not condense (an older boiler, or very hot return
# water), where a large gap is normal and says nothing about the heat exchanger
CONDENSING_EXHAUST_LIMIT = 90.0


class BoilerDiagnostics:
    """Track boiler conditions and keep the matching repair issues up to date."""

    def __init__(self, hass: HomeAssistant, entry_id: str, title: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._title = title
        self._last_update: float | None = None

        self._low_pressure_since: float | None = None
        self._fault_since: float | None = None
        self._gap: float | None = None
        self._gap_hours = 0.0
        self._active: dict[str, bool] = {}

    @property
    def flue_return_gap(self) -> float | None:
        return None if self._gap is None else round(self._gap, 1)

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            "flue_return_gap": self.flue_return_gap,
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
    ) -> None:
        dt = (
            0.0 if self._last_update is None else min(now - self._last_update, MAXIMUM_STEP_SECONDS)
        )
        self._last_update = now

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

        # A reported fault
        faulty = fault or bool(fault_code)
        if faulty:
            if self._fault_since is None:
                self._fault_since = now
            if now - self._fault_since >= FAULT_SECONDS:
                self._set(
                    "boiler_fault", active=True, placeholders={"code": str(fault_code or "-")}
                )
        else:
            self._fault_since = None
            self._set("boiler_fault", active=False)

        # Heat exchanger fouling: the flue gas creeps away from the return water
        if (
            settled_heating_burn
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
