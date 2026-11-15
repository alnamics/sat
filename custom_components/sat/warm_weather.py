"""Switch central heating off while the weather is warm (warm weather shutdown).

The decision follows the outside temperature averaged over about a day, so a sunny afternoon
does not stop the heating and a cold night does not restart it. A forecast keeps the heating off
when warm weather returns soon, and keeps it on when a cold spell is coming.
"""

from __future__ import annotations

import math

SECONDS_PER_HOUR = 3600.0
AVERAGING_HOURS = 24.0
# Ignore the first hours after a start, so a warm afternoon reading cannot stop the heating
MINIMUM_AVERAGING_HOURS = 6.0
MAXIMUM_STEP_SECONDS = 600.0
# After this long without readings the average says nothing about today, so it starts over
RESET_GAP_SECONDS = 3600.0
HYSTERESIS = 2.0


class WarmWeatherShutdown:
    """Track the daily mean outside temperature against a threshold."""

    def __init__(self, threshold: float) -> None:
        self._threshold = threshold
        self._mean: float | None = None
        self._hours = 0.0
        self._last_update: float | None = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def mean(self) -> float | None:
        return None if self._mean is None else round(self._mean, 1)

    @property
    def attributes(self) -> dict[str, object]:
        return {"warm_weather_shutdown": self._active, "outside_temperature_mean": self.mean}

    def restore(self, mean: float, *, active: bool) -> None:
        """Continue from the average and state saved shortly before a restart."""
        self._mean = mean
        self._hours = MINIMUM_AVERAGING_HOURS
        self._active = active

    def update(self, now: float, outdoor: float | None, forecast: float | None = None) -> bool:
        """Feed the outside temperature and the forecast mean of the next hours."""
        if self._last_update is not None and now - self._last_update > RESET_GAP_SECONDS:
            self._mean = None
            self._hours = 0.0
            self._active = False

        dt = (
            0.0 if self._last_update is None else min(now - self._last_update, MAXIMUM_STEP_SECONDS)
        )
        self._last_update = now
        if outdoor is None:
            return self._active

        if self._mean is None:
            self._mean = outdoor
        else:
            weight = 1 - math.exp(-dt / (AVERAGING_HOURS * SECONDS_PER_HOUR))
            self._mean += (outdoor - self._mean) * weight
        self._hours += dt / SECONDS_PER_HOUR

        if self._hours < MINIMUM_AVERAGING_HOURS:
            return self._active

        if self._active:
            # Stay off while the coming hours are warm again
            if self._mean < self._threshold - HYSTERESIS and (
                forecast is None or forecast < self._threshold
            ):
                self._active = False
        elif self._mean >= self._threshold and (
            forecast is None or forecast >= self._threshold - HYSTERESIS
        ):
            self._active = True

        return self._active
