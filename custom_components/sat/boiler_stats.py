"""Running totals of what the boiler did, kept across restarts.

The totals only ever grow, so Home Assistant's statistics and the Energy dashboard turn them into
daily, weekly and monthly values. Many boilers, the De Dietrich Lumea among them, do not report
their own burner counters over OpenTherm.

The hot water cooling detector separates cylinder temperature drops that start right after a
heating demand ends, when a combi boiler swings its diverter valve and the pump overrun pulls
heating water through the cylinder coil, from the drops of tapping hot water.

Gas and degree days are also kept per day, so a week that burns clearly more gas per degree day
than the weeks before it stands out: an open window, a closed loop or a dirty heat exchanger.
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

TOTALS = (
    "starts",
    "burn_hours",
    "heating_kwh",
    "hot_water_kwh",
    "gas_m3",
    "degree_days",
    "gas_cost",
)
HISTORY_DAYS = 60
RECENT_DAYS = 7
REFERENCE_DAYS = 28
# Below these the weather was too mild for gas per degree day to mean much
RECENT_MINIMUM_DEGREE_DAYS = 15.0
REFERENCE_MINIMUM_DEGREE_DAYS = 40.0


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

        # Completed days as (date, gas m³, degree days), and the day being counted
        self._days: deque[tuple[str, float, float]] = deque(maxlen=HISTORY_DAYS)
        self._day: str | None = None
        self._day_start: tuple[float, float] | None = None

    async def async_initialize(self, hass: HomeAssistant, entry_id: str) -> None:
        if self._store is not None:
            return

        self._store = boiler_stats_store(hass, entry_id)
        if (data := await self._store.async_load()) is None:
            return

        for key in TOTALS:
            if isinstance(value := data.get(key), int | float):
                self.totals[key] = float(value)
        self._load_days(data)

    def _load_days(self, data: dict[str, Any]) -> None:
        days = data.get("days")
        if isinstance(days, list):
            for item in days:
                if (
                    isinstance(item, list)
                    and len(item) == 3  # noqa: PLR2004
                    and isinstance(item[0], str)
                    and isinstance(item[1], int | float)
                    and isinstance(item[2], int | float)
                ):
                    self._days.append((item[0], float(item[1]), float(item[2])))

        day, start = data.get("day"), data.get("day_start")
        if isinstance(day, str) and isinstance(start, list) and len(start) == 2:  # noqa: PLR2004
            self._day = day
            self._day_start = (float(start[0]), float(start[1]))

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

        if flame and dt > 0:
            self.totals["burn_hours"] += dt / SECONDS_PER_HOUR
            if heat_kw is not None:
                key = "hot_water_kwh" if hot_water else "heating_kwh"
                self.totals[key] += heat_kw * dt / SECONDS_PER_HOUR
            if gas_m3_per_hour is not None:
                gas = gas_m3_per_hour * dt / SECONDS_PER_HOUR
                self.totals["gas_m3"] += gas
                self.totals["gas_cost"] += gas * max(0.0, gas_price)

        if outdoor is not None and dt > 0:
            self.totals["degree_days"] += max(0.0, DEGREE_DAY_BASE - outdoor) * dt / SECONDS_PER_DAY

        if day is not None:
            self._track_day(day)

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
            self._store.async_delay_save(self._data, 1)

    def _data(self) -> dict[str, Any]:
        return {
            **self.totals,
            "days": [list(item) for item in self._days],
            "day": self._day,
            "day_start": None if self._day_start is None else list(self._day_start),
        }

    def _track_day(self, day: str) -> None:
        current = (self.totals["gas_m3"], self.totals["degree_days"])
        if self._day is None or self._day_start is None:
            self._day, self._day_start = day, current
            return
        if day == self._day:
            return

        gas = current[0] - self._day_start[0]
        degree_days = current[1] - self._day_start[1]
        self._days.append((self._day, gas, degree_days))
        self._day, self._day_start = day, current

    @property
    def gas_per_degree_day_ratio(self) -> float | None:
        """Gas per degree day of the last week against the four weeks before it."""
        days = list(self._days)
        if len(days) < RECENT_DAYS + REFERENCE_DAYS // 2:
            return None

        recent = days[-RECENT_DAYS:]
        reference = days[-(RECENT_DAYS + REFERENCE_DAYS) : -RECENT_DAYS]
        recent_dd = sum(item[2] for item in recent)
        reference_dd = sum(item[2] for item in reference)
        if recent_dd < RECENT_MINIMUM_DEGREE_DAYS or reference_dd < REFERENCE_MINIMUM_DEGREE_DAYS:
            return None

        reference_rate = sum(item[1] for item in reference) / reference_dd
        if reference_rate <= 0:
            return None
        return round(sum(item[1] for item in recent) / recent_dd / reference_rate, 2)

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
