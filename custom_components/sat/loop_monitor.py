"""Watch the underfloor loops through the room thermostats that open their actuators.

* which loops are open now, and what share of the last day each one was open;
* how warm each room runs against the others over the last day;
* how much water each loop carries, learned by regressing the estimated system flow on the
  open/closed pattern of the thermostats (the always-open loops end up in the base flow);
* from that, a hint per room on whether its rotameter should go down or up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SECONDS_PER_HOUR = 3600.0
# Specific heat of water in kJ/(kg·K), with 1 kg per litre
WATER_SPECIFIC_HEAT = 4.186
MINIMUM_FLOW_RETURN_DIFFERENCE = 1.5

# Room statistics follow the last day
AVERAGING_HOURS = 24.0
# Advice only after the averages have seen a good part of a day
MINIMUM_ADVICE_HOURS = 6.0
# A room this much warmer than the others, or a valve closed this often, gets too much water
WARM_OFFSET = 0.5
COLD_OFFSET = -0.5
OPEN_SHARE_LIMIT = 0.85
FULL_OPEN_SHARE = 0.95
# Flow regression: about a week of burns of memory, and samples per state before a loop counts
FLOW_FORGETTING = 0.995
MINIMUM_SAMPLES_PER_STATE = 5
MAXIMUM_STEP_SECONDS = 300.0


def estimate_water_flow(heat_kw: float, flow: float, return_temperature: float) -> float | None:
    """Return the water flow in l/min that carries this heat over this spread, P = m·c·ΔT."""
    difference = flow - return_temperature
    if heat_kw <= 0 or difference < MINIMUM_FLOW_RETURN_DIFFERENCE:
        return None
    return heat_kw / (WATER_SPECIFIC_HEAT * difference) * 60


@dataclass(slots=True)
class RoomReading:
    """One room thermostat: whether its actuator is open and the room temperature."""

    open: bool | None
    temperature: float | None


@dataclass(slots=True)
class _Room:
    open: bool | None = None
    open_share: float | None = None
    offset: float | None = None
    open_samples: int = 0
    closed_samples: int = 0


class LoopMonitor:
    """Follow the room loops and learn how much water each one takes."""

    def __init__(self, rooms: list[str]) -> None:
        self._names = list(rooms)
        self._rooms = {name: _Room() for name in self._names}
        self._last_update: float | None = None
        self._observed_hours = 0.0

        size = len(self._names) + 1
        self._theta = [10.0] + [1.5] * len(self._names)
        self._p = [[100.0 if i == j else 0.0 for j in range(size)] for i in range(size)]
        self._flow_samples = 0

    @property
    def rooms(self) -> list[str]:
        return list(self._names)

    @property
    def open_rooms(self) -> list[str]:
        return [name for name, room in self._rooms.items() if room.open is True]

    def update(
        self, now: float, readings: dict[str, RoomReading], flow_sample: float | None
    ) -> None:
        dt = (
            0.0 if self._last_update is None else min(now - self._last_update, MAXIMUM_STEP_SECONDS)
        )
        self._last_update = now
        weight = min(1.0, dt / (AVERAGING_HOURS * SECONDS_PER_HOUR))
        self._observed_hours += dt / SECONDS_PER_HOUR

        temperatures = [
            reading.temperature for reading in readings.values() if reading.temperature is not None
        ]
        mean = sum(temperatures) / len(temperatures) if temperatures else None

        for name, room in self._rooms.items():
            reading = readings.get(name)
            room.open = None if reading is None else reading.open
            if reading is None:
                continue

            if reading.open is not None:
                share = 1.0 if reading.open else 0.0
                room.open_share = (
                    share
                    if room.open_share is None
                    else room.open_share + (share - room.open_share) * weight
                )

            if reading.temperature is not None and mean is not None and len(temperatures) > 1:
                offset = reading.temperature - mean
                room.offset = (
                    offset if room.offset is None else room.offset + (offset - room.offset) * weight
                )

        if flow_sample is not None:
            self._learn_flow(flow_sample)

    def _learn_flow(self, flow: float) -> None:
        states = [self._rooms[name].open for name in self._names]
        if any(state is None for state in states):
            return

        x = [1.0] + [1.0 if state is True else 0.0 for state in states]
        size = len(x)
        px = [sum(self._p[i][j] * x[j] for j in range(size)) for i in range(size)]
        denominator = FLOW_FORGETTING + sum(x[i] * px[i] for i in range(size))
        gain = [value / denominator for value in px]
        error = flow - sum(self._theta[i] * x[i] for i in range(size))
        self._theta = [max(0.0, self._theta[i] + gain[i] * error) for i in range(size)]
        self._p = [
            [(self._p[i][j] - gain[i] * px[j]) / FLOW_FORGETTING for j in range(size)]
            for i in range(size)
        ]
        self._flow_samples += 1

        for name, state in zip(self._names, states, strict=True):
            if state is True:
                self._rooms[name].open_samples += 1
            else:
                self._rooms[name].closed_samples += 1

    def loop_flow(self, name: str) -> float | None:
        """Learned water flow of one room loop in l/min, once it was seen open and closed."""
        room = self._rooms[name]
        if (
            room.open_samples < MINIMUM_SAMPLES_PER_STATE
            or room.closed_samples < MINIMUM_SAMPLES_PER_STATE
        ):
            return None
        return round(self._theta[1 + self._names.index(name)], 2)

    @property
    def base_flow(self) -> float | None:
        """Flow through the loops that were never seen closed, in l/min.

        The loops without an actuator and the rooms whose valve never closed cannot be told
        apart, so only their sum is known.
        """
        if self._flow_samples < MINIMUM_SAMPLES_PER_STATE:
            return None

        base = self._theta[0]
        for index, name in enumerate(self._names):
            if self._rooms[name].closed_samples < MINIMUM_SAMPLES_PER_STATE:
                base += self._theta[1 + index]
        return round(base, 1)

    def advice(self, name: str) -> tuple[str, int]:
        """Return ("reduce" | "increase" | "ok" | "learning", percent) for a room's rotameter."""
        room = self._rooms[name]
        if self._observed_hours < MINIMUM_ADVICE_HOURS or room.open_share is None:
            return "learning", 0

        offset = room.offset or 0.0
        if room.open_share < OPEN_SHARE_LIMIT or offset > WARM_OFFSET:
            percent = (
                10
                + 20 * max(offset - WARM_OFFSET, 0.0)
                + 50 * max(OPEN_SHARE_LIMIT - room.open_share, 0.0)
            )
            return "reduce", int(min(30, round(percent / 5) * 5))

        if offset < COLD_OFFSET and room.open_share >= FULL_OPEN_SHARE:
            percent = 10 + 20 * (COLD_OFFSET - offset)
            return "increase", int(min(30, round(percent / 5) * 5))

        return "ok", 0

    @property
    def attributes(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "base_flow_lpm": self.base_flow,
            "flow_samples": self._flow_samples,
        }
        for name in self._names:
            room = self._rooms[name]
            advice, percent = self.advice(name)
            result[name] = {
                "open": room.open,
                "open_share_24h": None if room.open_share is None else round(room.open_share * 100),
                "offset_24h": None if room.offset is None else round(room.offset, 2),
                "flow_lpm": self.loop_flow(name),
                "advice": advice,
                "advice_percent": percent,
            }
        return result

    @property
    def rooms_to_adjust(self) -> int:
        return sum(1 for name in self._names if self.advice(name)[0] in ("reduce", "increase"))
