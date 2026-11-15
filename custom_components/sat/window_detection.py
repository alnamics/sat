"""Spot an open window from a fast drop of the room temperature, without contact sensors.

Screed heating changes the air temperature by tenths of a degree per hour, so a drop of most of a
degree within ten minutes means outside air is coming in.
"""

from __future__ import annotations

from collections import deque

DROP = 0.8
WINDOW_SECONDS = 600.0
# How long heating stays paused after the last fast drop
HOLD_SECONDS = 1800.0


class TemperatureDropDetector:
    """Report a window as open while the temperature falls fast, and for a while after."""

    def __init__(self, drop: float = DROP) -> None:
        self._drop = drop
        self._samples: deque[tuple[float, float]] = deque()
        self._open_until: float | None = None

    @property
    def open(self) -> bool:
        return self._open_until is not None

    def update(self, now: float, temperature: float | None) -> bool:
        if temperature is not None:
            self._samples.append((now, temperature))
        while self._samples and now - self._samples[0][0] > WINDOW_SECONDS:
            self._samples.popleft()

        if self._samples and temperature is not None:
            highest = max(value for _, value in self._samples)
            if highest - temperature >= self._drop:
                self._open_until = now + HOLD_SECONDS

        if self._open_until is not None and now >= self._open_until:
            self._open_until = None
            # Measure the next drop from the closed-window temperature
            self._samples.clear()

        return self.open
