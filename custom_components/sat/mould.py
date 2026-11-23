"""Mould risk at the coldest surfaces of the rooms, from their temperature and humidity.

An outside wall corner or a window reveal is colder than the room around it. EN ISO 13788 rates
such a spot by its temperature factor fRsi = (Tsi - Te) / (Ti - Te), and Polish building rules ask
for at least 0.72 since 2021. Mould grows where the air at a surface stays at about 80 % relative
humidity or more, so SAT works out the humidity at a surface with that factor and warns when its
daily mean reaches 80 % in a room. The humidity a room thermostat reports and its temperature give
the water vapour in the room; the outside temperature gives how cold the corner gets.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

SECONDS_PER_HOUR = 3600.0
# The temperature factor of the coldest spot (EN ISO 13788; WT 2021 minimum for new buildings)
SURFACE_TEMPERATURE_FACTOR = 0.72
# Mould grows at a surface that stays this humid; the warning clears below the second value
MOULD_SURFACE_HUMIDITY = 80.0
MOULD_CLEARED_SURFACE_HUMIDITY = 75.0
# The mean follows the surface humidity over about a day
MEAN_HOURS = 24.0
# A room is judged once its mean covers this many hours
MINIMUM_HOURS = 12.0
# Longer gaps between readings count as this much; a saved mean older than the last value is reset
MAXIMUM_STEP_SECONDS = 900.0
STALE_SECONDS = 6 * SECONDS_PER_HOUR
SAVE_INTERVAL_SECONDS = 1800.0
MAXIMUM_HUMIDITY = 100.0


def saturation_pressure(temperature: float) -> float:
    """Return the water vapour pressure of saturated air in Pa (Magnus formula)."""
    return 610.94 * math.exp(17.625 * temperature / (temperature + 243.04))


def dew_point(temperature: float, humidity: float) -> float:
    """Return the dew point in °C of air at this temperature and relative humidity."""
    gamma = math.log(max(humidity, 1.0) / 100.0) + 17.625 * temperature / (temperature + 243.04)
    return 243.04 * gamma / (17.625 - gamma)


def absolute_humidity(temperature: float, humidity: float) -> float:
    """Return the water in the air in g/m³."""
    vapour = humidity / 100.0 * saturation_pressure(temperature)
    return 2.1674 * vapour / (273.15 + temperature)


def humidity_at(temperature: float, absolute: float) -> float:
    """Return the relative humidity in % that this much water gives air at this temperature."""
    vapour = absolute * (273.15 + temperature) / 2.1674
    return min(100.0, 100.0 * vapour / saturation_pressure(temperature))


def surface_humidity(indoor: float, humidity: float, outdoor: float) -> float:
    """Return the relative humidity in % at the coldest surface of a room."""
    surface = outdoor + SURFACE_TEMPERATURE_FACTOR * (indoor - outdoor)
    surface = min(surface, indoor)
    return min(100.0, humidity * saturation_pressure(indoor) / saturation_pressure(surface))


def mould_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.mould")


# Airing is worth it once the outside air holds this much less water per cubic metre
AIRING_MINIMUM_DRYING = 1.0
# and the flat needs drying: a room this humid, or a corner this close to mould
AIRING_ROOM_HUMIDITY = 60.0
AIRING_SURFACE_HUMIDITY = 70.0


def airing_advice(
    rooms: Mapping[str, tuple[float, float]],
    *,
    outdoor: float | None,
    outdoor_humidity: float | None,
) -> dict[str, Any] | None:
    """Tell whether opening the windows dries the flat, from the water inside and outside.

    Cold outside air holds little water even when its relative humidity is high, so once warmed
    to room temperature it is dry. Warm, damp summer air can hold more than the air inside, and
    airing then makes the rooms more humid.
    """
    if outdoor is None or outdoor_humidity is None or not rooms:
        return None

    readings = [
        (indoor, humidity)
        for indoor, humidity in rooms.values()
        if 0 < humidity <= MAXIMUM_HUMIDITY
    ]
    if not readings:
        return None

    indoor = sum(temperature for temperature, _ in readings) / len(readings)
    inside = sum(absolute_humidity(t, h) for t, h in readings) / len(readings)
    outside = absolute_humidity(outdoor, outdoor_humidity)
    highest = max(humidity for _, humidity in readings)
    corner = max(surface_humidity(t, h, outdoor) for t, h in readings)
    drying = inside - outside
    needed = highest >= AIRING_ROOM_HUMIDITY or corner >= AIRING_SURFACE_HUMIDITY
    return {
        "worth_airing": needed and drying >= AIRING_MINIMUM_DRYING,
        "airing_needed": needed,
        "airing_dries": drying >= AIRING_MINIMUM_DRYING,
        "indoor_absolute_humidity": round(inside, 1),
        "outdoor_absolute_humidity": round(outside, 1),
        # The room humidity once the air is fully replaced and warmed to room temperature
        "humidity_after_airing": round(humidity_at(indoor, outside), 0),
        "highest_room_humidity": round(highest, 0),
    }


class MouldRisk:
    """Follow the daily mean humidity at the coldest surface of every room."""

    def __init__(self) -> None:
        self._means: dict[str, float] = {}
        self._hours: dict[str, float] = {}
        self._current: dict[str, tuple[float, float]] = {}
        self._last: dict[str, float] = {}
        self._at_risk: set[str] = set()
        self._store: Store[dict[str, Any]] | None = None
        self._last_save: float | None = None

    async def async_initialize(self, hass: HomeAssistant, entry_id: str, wall: float) -> None:
        if self._store is not None:
            return

        self._store = mould_store(hass, entry_id)
        data = await self._store.async_load()
        if not isinstance(data, dict) or not isinstance(rooms := data.get("rooms"), dict):
            return

        # A mean that stopped long ago says nothing about the rooms now
        saved_at = data.get("saved_at")
        if not isinstance(saved_at, int | float) or wall - saved_at > STALE_SECONDS:
            return

        for room, values in rooms.items():
            if not isinstance(values, dict):
                continue
            mean, hours = values.get("mean"), values.get("hours")
            if isinstance(mean, int | float) and isinstance(hours, int | float):
                self._means[room] = float(mean)
                self._hours[room] = float(hours)
                if values.get("at_risk"):
                    self._at_risk.add(room)

    def update(
        self,
        now: float,
        wall: float,
        *,
        rooms: Mapping[str, tuple[float, float]],
        outdoor: float | None,
    ) -> None:
        """Take the temperature and humidity of each room, keyed by its name."""
        if outdoor is None:
            return

        for room, (indoor, humidity) in rooms.items():
            if not 0 < humidity <= MAXIMUM_HUMIDITY:
                continue
            value = surface_humidity(indoor, humidity, outdoor)
            self._current[room] = (value, dew_point(indoor, humidity))

            last = self._last.get(room)
            self._last[room] = now
            if room not in self._means:
                self._means[room] = value
                self._hours[room] = 0.0
                continue
            if last is None:
                continue

            step = min(max(now - last, 0.0), MAXIMUM_STEP_SECONDS) / SECONDS_PER_HOUR
            self._means[room] += (value - self._means[room]) * min(1.0, step / MEAN_HOURS)
            self._hours[room] = min(self._hours[room] + step, MEAN_HOURS)

            if self._hours[room] < MINIMUM_HOURS:
                continue
            if self._means[room] >= MOULD_SURFACE_HUMIDITY:
                self._at_risk.add(room)
            elif self._means[room] < MOULD_CLEARED_SURFACE_HUMIDITY:
                self._at_risk.discard(room)

        if self._store is not None and (
            self._last_save is None or now - self._last_save >= SAVE_INTERVAL_SECONDS
        ):
            self._last_save = now
            self._store.async_delay_save(lambda: self._data(wall), 1)

    async def async_save(self, wall: float) -> None:
        if self._store is not None:
            await self._store.async_save(self._data(wall))

    def _data(self, wall: float) -> dict[str, Any]:
        return {
            "saved_at": wall,
            "rooms": {
                room: {
                    "mean": round(mean, 2),
                    "hours": round(self._hours.get(room, 0.0), 3),
                    "at_risk": room in self._at_risk,
                }
                for room, mean in self._means.items()
            },
        }

    @property
    def rooms_at_risk(self) -> list[str]:
        return sorted(self._at_risk)

    @property
    def highest_mean(self) -> float | None:
        means = [self._means[room] for room in self._at_risk if room in self._means]
        return round(max(means), 0) if means else None

    @property
    def attributes(self) -> dict[str, Any]:
        """The humidity at the coldest surface, now and as the daily mean, with the dew point."""
        return {
            room: {
                "surface_humidity": round(current[0], 0),
                "surface_humidity_24h": (
                    round(self._means[room], 0)
                    if self._hours.get(room, 0.0) >= MINIMUM_HOURS
                    else None
                ),
                "dew_point": round(current[1], 1),
            }
            for room, current in sorted(self._current.items())
        }
