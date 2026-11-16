"""Running totals of what the boiler did, kept across restarts.

The totals only ever grow, so Home Assistant's statistics and the Energy dashboard turn them into
daily, weekly and monthly values. Many boilers, the De Dietrich Lumea among them, do not report
their own burner counters over OpenTherm.

The hot water cooling detector separates cylinder temperature drops that start right after a
heating demand begins or ends, when a combi boiler swings its diverter valve and heating water
runs through the cylinder coil, from the drops of tapping hot water.

The heating gas of each day is also kept against that day's weather (see energy_signature), so a
week that burns clearly more than the weeks before explain stands out.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .energy_signature import EnergySignature

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
# A drop this soon after heating started or stopped is blamed on the diverter valve
NEAR_HEATING_CHANGE_SECONDS = 600.0
EVENT_WINDOW_SECONDS = SECONDS_PER_DAY

TOTALS = (
    "starts",
    "burn_hours",
    "heating_kwh",
    "hot_water_kwh",
    "gas_m3",
    "degree_days",
    "gas_cost",
)


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
        self._events: deque[tuple[float, str | None]] = deque()

        self.signature = EnergySignature()

    async def async_initialize(self, hass: HomeAssistant, entry_id: str) -> None:
        if self._store is not None:
            return

        self._store = boiler_stats_store(hass, entry_id)
        if (data := await self._store.async_load()) is None:
            return

        for key in TOTALS:
            if isinstance(value := data.get(key), int | float):
                self.totals[key] = float(value)
        self.signature.load(data.get("signature"))

    def update(
        self,
        *,
        now: float,
        flame: bool,
        hot_water: bool,
        heat_kw: float | None,
        gas_m3_per_hour: float | None,
        outdoor: float | None,
        indoor: float | None = None,
        hot_water_temperature: float | None = None,
        heating_stopped_at: float | None = None,
        heating_started_at: float | None = None,
        day: str | None = None,
        gas_price: float = 0.0,
    ) -> None:
        dt = (
            0.0 if self._last_update is None else min(now - self._last_update, MAXIMUM_STEP_SECONDS)
        )
        self._last_update = now

        if flame and self._flame is False:
            self.totals["starts"] += 1
        self._flame = flame

        heating_gas = 0.0
        if flame and dt > 0:
            self.totals["burn_hours"] += dt / SECONDS_PER_HOUR
            if heat_kw is not None:
                key = "hot_water_kwh" if hot_water else "heating_kwh"
                self.totals[key] += heat_kw * dt / SECONDS_PER_HOUR
            if gas_m3_per_hour is not None:
                gas = gas_m3_per_hour * dt / SECONDS_PER_HOUR
                self.totals["gas_m3"] += gas
                self.totals["gas_cost"] += gas * max(0.0, gas_price)
                if not hot_water:
                    heating_gas = gas

        if outdoor is not None and dt > 0:
            self.totals["degree_days"] += max(0.0, DEGREE_DAY_BASE - outdoor) * dt / SECONDS_PER_DAY

        if day is not None:
            self.signature.update(dt, day, heating_gas=heating_gas, indoor=indoor, outdoor=outdoor)

        self._track_hot_water(
            now,
            hot_water=hot_water,
            temperature=hot_water_temperature,
            heating_stopped_at=heating_stopped_at,
            heating_started_at=heating_started_at,
        )

        if self._store is not None and (
            self._last_save is None or now - self._last_save >= SAVE_INTERVAL_SECONDS
        ):
            self._last_save = now
            self._store.async_delay_save(self._data, 1)

    async def async_save(self) -> None:
        """Write the totals now; between saves a stop would lose up to ten minutes of them."""
        if self._store is not None:
            await self._store.async_save(self._data())

    def _data(self) -> dict[str, Any]:
        return {**self.totals, "signature": self.signature.to_dict()}

    @property
    def gas_use_ratio(self) -> float | None:
        """Heating gas of the last week against what the weeks before predict for its weather."""
        return self.signature.ratio

    def _track_hot_water(
        self,
        now: float,
        *,
        hot_water: bool,
        temperature: float | None,
        heating_stopped_at: float | None,
        heating_started_at: float | None,
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
            # The latest change of the heating demand within the window takes the blame
            cause: str | None = None
            latest = -1.0
            for name, changed_at in (("start", heating_started_at), ("stop", heating_stopped_at)):
                if (
                    changed_at is not None
                    and 0 <= now - changed_at <= NEAR_HEATING_CHANGE_SECONDS
                    and changed_at > latest
                ):
                    cause, latest = name, changed_at
            self._events.append((now, cause))
            self._reference = temperature

    @property
    def hot_water_drops(self) -> int:
        return len(self._events)

    @property
    def hot_water_drops_after_heating(self) -> int:
        """Drops that began right after the heating demand started or stopped."""
        return sum(1 for _, cause in self._events if cause is not None)

    @property
    def hot_water_drops_after_heating_start(self) -> int:
        return sum(1 for _, cause in self._events if cause == "start")

    @property
    def hot_water_drops_after_heating_stop(self) -> int:
        return sum(1 for _, cause in self._events if cause == "stop")
