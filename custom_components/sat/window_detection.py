"""Spot an open window from a drop of the room temperature, without contact sensors.

Screed heating changes the air temperature by a few hundredths to a tenth of a degree per hour.
Outside air coming in is faster: a wide open window drops most of a degree within ten minutes,
a window left open for airing a few tenths within half an hour.

While a window is open the room keeps cooling by a tenth every quarter of an hour or so; that keeps
the pause going. Once the window closes the screed holds the room, the drops stop and the heating
resumes after the hold time. A pause never lasts longer than MAXIMUM_PAUSE_SECONDS.
"""

from __future__ import annotations

from collections import deque

DROP = 0.8
WINDOW_SECONDS = 600.0
# Airing with a window wide open for a longer time cools the room slower
SLOW_DROP = 0.3
SLOW_WINDOW_SECONDS = 1800.0
# While paused, each further tenth that comes this soon keeps the pause going
FURTHER_DROP = 0.1
FURTHER_DROP_SECONDS = 1500.0
# How long heating stays paused after the last drop
HOLD_SECONDS = 1800.0
MAXIMUM_PAUSE_SECONDS = 7200.0


class TemperatureDropDetector:
    """Report a window as open while the temperature falls fast, and for a while after."""

    def __init__(self, drop: float = DROP) -> None:
        self._drop = drop
        self._samples: deque[tuple[float, float]] = deque()
        self._open_until: float | None = None
        self._opened_at: float | None = None
        self._lowest: tuple[float, float] | None = None

    @property
    def open(self) -> bool:
        return self._open_until is not None

    def resume(self, now: float) -> None:
        """Continue a pause that began before a restart, for the full hold time."""
        self._open_until = now + HOLD_SECONDS
        self._opened_at = now
        self._lowest = None

    def update(self, now: float, temperature: float | None) -> bool:
        if temperature is not None:
            self._samples.append((now, temperature))
        while self._samples and now - self._samples[0][0] > SLOW_WINDOW_SECONDS:
            self._samples.popleft()

        if temperature is not None and (
            self._dropped(now, temperature) or (self.open and self._further_drop(now, temperature))
        ):
            self._hold(now, temperature)

        if self._open_until is not None and (
            now >= self._open_until
            or (self._opened_at is not None and now - self._opened_at >= MAXIMUM_PAUSE_SECONDS)
        ):
            self._open_until = None
            self._opened_at = None
            self._lowest = None
            # Measure the next drop from the closed-window temperature
            self._samples.clear()

        return self.open

    def _dropped(self, now: float, temperature: float) -> bool:
        fast = max(
            (value for when, value in self._samples if now - when <= WINDOW_SECONDS),
            default=temperature,
        )
        slow = max(value for _, value in self._samples)
        return fast - temperature >= self._drop or slow - temperature >= SLOW_DROP

    def _further_drop(self, now: float, temperature: float) -> bool:
        if self._lowest is None:
            return False
        lowest_at, lowest = self._lowest
        if temperature > lowest - FURTHER_DROP + 1e-9:
            return False
        return now - lowest_at <= FURTHER_DROP_SECONDS

    def _hold(self, now: float, temperature: float) -> None:
        if self._opened_at is None:
            self._opened_at = now
        self._open_until = now + HOLD_SECONDS
        if self._lowest is None or temperature < self._lowest[1]:
            self._lowest = (now, temperature)
