"""Running totals of what the boiler did, kept across restarts.

The totals only ever grow, so Home Assistant's statistics and the Energy dashboard turn them into
daily, weekly and monthly values. Many boilers, the De Dietrich Lumea among them, do not report
their own burner counters over OpenTherm.

The hot water cooling detector separates cylinder temperature drops that start right after a
heating demand ends, when a combi boiler swings its diverter valve and the pump overrun pulls
heating water through the cylinder coil, from the drops of tapping hot water.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0
# Totals are written at most this often; a crash loses at most this much
SAVE_INTERVAL_SECONDS = 600.0
MAXIMUM_STEP_SECONDS = 300.0
# Heating degree days against the usual 18 °C base
DEGREE_DAY_BASE = 18.0
# A cylinder drop of at least this much counts as one event
HOT_WATER_DROP = 1.5
# A drop that starts this soon after heating stopped is blamed on the pump overrun
AFTER_HEATING_STOP_SECONDS = 600.0
EVENT_WINDOW_SECONDS = SECONDS_PER_DAY

TOTALS = ("starts", "burn_hours", "heating_kwh", "hot_water_kwh", "gas_m3", "degree_days")


def boiler_stats_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.boiler_stats")


class BoilerStats:
    """Count burner starts, burner hours, heat, gas and degree days."""

    def __init__(self) -> None:
        self.totals: dict[str, float] = dict.fromkeys(TOTALS, 0.0)
        self._store: Store[dict[str, Any]] | None = None
        self._last_update: float | None = None
        self._last_save: float | None = None
        self._flame: bool | None = None

        self._reference: float | None = None
        self._events: deque[tuple[float, bool]] = deque()

    async def async_initialize(self, hass: HomeAssistant, entry_id: str) -> None:
        if self._store is not None:
            return

        self._store = boiler_stats_store(hass, entry_id)
        if (data := await self._store.async_load()) is None:
            return

        for key in TOTALS:
            if isinstance(value := data.get(key), int | float):
                self.totals[key] = float(value)

    def update(
        self,
        *,
        now: float,
        flame: bool,
        hot_water: bool,
        heat_kw: float | None,
        gas_m3_per_hour: float | None,
        outdoor: float | None,
        hot_water_temperature: float | None = None,
        heating_stopped_at: float | None = None,
    ) -> None:
        dt = (
            0.0 if self._last_update is None else min(now - self._last_update, MAXIMUM_STEP_SECONDS)
        )
        self._last_update = now

        if flame and self._flame is False:
            self.totals["starts"] += 1
        self._flame = flame

        if flame and dt > 0:
            self.totals["burn_hours"] += dt / SECONDS_PER_HOUR
            if heat_kw is not None:
                key = "hot_water_kwh" if hot_water else "heating_kwh"
                self.totals[key] += heat_kw * dt / SECONDS_PER_HOUR
            if gas_m3_per_hour is not None:
                self.totals["gas_m3"] += gas_m3_per_hour * dt / SECONDS_PER_HOUR

        if outdoor is not None and dt > 0:
            self.totals["degree_days"] += max(0.0, DEGREE_DAY_BASE - outdoor) * dt / SECONDS_PER_DAY

        self._track_hot_water(
            now,
            hot_water=hot_water,
            temperature=hot_water_temperature,
            heating_stopped_at=heating_stopped_at,
        )

        if self._store is not None and (
            self._last_save is None or now - self._last_save >= SAVE_INTERVAL_SECONDS
        ):
            self._last_save = now
            self._store.async_delay_save(lambda: dict(self.totals), 1)

    def _track_hot_water(
        self,
        now: float,
        *,
        hot_water: bool,
        temperature: float | None,
        heating_stopped_at: float | None,
    ) -> None:
        while self._events and now - self._events[0][0] > EVENT_WINDOW_SECONDS:
            self._events.popleft()

        if temperature is None:
            return

        # A reheat or any rise sets a new reference to measure the next drop from
        if hot_water or self._reference is None or temperature > self._reference:
            self._reference = temperature
            return

        if self._reference - temperature >= HOT_WATER_DROP:
            after_heating = (
                heating_stopped_at is not None
                and 0 <= now - heating_stopped_at <= AFTER_HEATING_STOP_SECONDS
            )
            self._events.append((now, after_heating))
            self._reference = temperature

    @property
    def hot_water_drops(self) -> int:
        return len(self._events)

    @property
    def hot_water_drops_after_heating(self) -> int:
        return sum(1 for _, after_heating in self._events if after_heating)
