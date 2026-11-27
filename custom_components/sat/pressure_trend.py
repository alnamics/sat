"""Follow the heating water pressure over days, to spot a slow loss before it gets low.

The pressure of a sealed system rises and falls with the water temperature, by an amount that
depends on the water volume and the expansion vessel. Comparing raw pressures would call the end
of the heating season, when the water cools for good, a leak. So the pressure is first related to
the water temperature, from how the two move together within the last days, and each day's mean
pressure is corrected to a common temperature. A leak then shows as a fall of the corrected
pressure over days. A jump up is someone topping the system up and starts a new history.
"""

from __future__ import annotations

from collections import deque
from typing import Any

SECONDS_PER_HOUR = 3600.0
HISTORY_DAYS = 14
# A day counts once this much of it was measured
MINIMUM_DAY_HOURS = 6.0
MINIMUM_DAYS = 4
# Pressure against temperature: about three days of memory, used once it has seen enough
FIT_HOURS = 72.0
FIT_MINIMUM_HOURS = 12.0
FIT_MINIMUM_VARIANCE = 4.0
FIT_MAXIMUM_BAR_PER_K = 0.03
# A rise this large from one day to the next is a top-up
TOP_UP_RISE = 0.15
# A reading this far off the day's mean so far is a glitch or the brief swing of a valve
# changing over (a Lumea read 1.1 bar for a few minutes between 1.6 bar readings): it is left
# out of the day's mean and of the temperature fit. A leak never moves this much within a
# day; a top-up shows as the next day's jump
SPIKE_BAR = 0.2
SPIKE_MINIMUM_SECONDS = 3600.0


def slope(values: list[float]) -> float | None:
    """Least squares slope per step of evenly spaced values."""
    count = len(values)
    if count < MINIMUM_DAYS:
        return None
    mean_x = (count - 1) / 2
    mean_y = sum(values) / count
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(values))
    denominator = sum((x - mean_x) ** 2 for x in range(count))
    return numerator / denominator


class PressureTrend:
    """Daily mean pressures corrected for the water temperature."""

    def __init__(self) -> None:
        self._days: deque[tuple[float, float | None]] = deque(maxlen=HISTORY_DAYS)
        self._day: str | None = None
        self._pressure_seconds = 0.0
        self._pressure_sum = 0.0
        self._temperature_seconds = 0.0
        self._temperature_sum = 0.0

        # Running means of T, p, T² and T·p
        self._fit: list[float] | None = None
        self._fit_hours = 0.0
        # Readings left out as glitches since the start
        self.spikes = 0

    @property
    def coefficient(self) -> float:
        """Pressure change per kelvin of water temperature, in bar/K; 0 until it is known."""
        if self._fit is None or self._fit_hours < FIT_MINIMUM_HOURS:
            return 0.0
        mean_t, mean_p, mean_tt, mean_tp = self._fit
        variance = mean_tt - mean_t * mean_t
        if variance < FIT_MINIMUM_VARIANCE:
            return 0.0
        return min(max((mean_tp - mean_t * mean_p) / variance, 0.0), FIT_MAXIMUM_BAR_PER_K)

    def corrected(self) -> list[float]:
        """Return the daily pressures, each brought to the mean temperature of the days."""
        temperatures = [temperature for _, temperature in self._days if temperature is not None]
        if not temperatures:
            return [pressure for pressure, _ in self._days]

        reference = sum(temperatures) / len(temperatures)
        coefficient = self.coefficient
        return [
            pressure if temperature is None else pressure - coefficient * (temperature - reference)
            for pressure, temperature in self._days
        ]

    @property
    def per_day(self) -> float | None:
        """Change of the corrected pressure in bar per day, once there are enough days."""
        return slope(self.corrected())

    @property
    def drop(self) -> float:
        """How far the latest day is below the highest day."""
        values = self.corrected()
        return max(values) - values[-1] if values else 0.0

    @property
    def latest(self) -> float | None:
        return self._days[-1][0] if self._days else None

    def update(self, dt: float, day: str, pressure: float, temperature: float | None) -> bool:
        """Feed one reading; return True when a day was completed."""
        completed = False
        if day != self._day:
            completed = self._close_day()
            self._day = day

        if (
            self._pressure_seconds >= SPIKE_MINIMUM_SECONDS
            and abs(pressure - self._pressure_sum / self._pressure_seconds) > SPIKE_BAR
        ):
            self.spikes += 1
            return completed

        self._pressure_seconds += dt
        self._pressure_sum += pressure * dt
        if temperature is not None:
            self._temperature_seconds += dt
            self._temperature_sum += temperature * dt
            self._learn(dt, pressure, temperature)
        return completed

    def _learn(self, dt: float, pressure: float, temperature: float) -> None:
        sample = [temperature, pressure, temperature * temperature, temperature * pressure]
        if self._fit is None:
            self._fit = sample
            return

        weight = min(1.0, dt / (FIT_HOURS * SECONDS_PER_HOUR))
        self._fit = [
            mean + (value - mean) * weight for mean, value in zip(self._fit, sample, strict=True)
        ]
        self._fit_hours += dt / SECONDS_PER_HOUR

    def _close_day(self) -> bool:
        seconds, total = self._pressure_seconds, self._pressure_sum
        temperature_seconds, temperature_total = self._temperature_seconds, self._temperature_sum
        self._pressure_seconds = self._pressure_sum = 0.0
        self._temperature_seconds = self._temperature_sum = 0.0
        if self._day is None or seconds < MINIMUM_DAY_HOURS * SECONDS_PER_HOUR:
            return False

        temperature = (
            temperature_total / temperature_seconds if temperature_seconds >= seconds / 2 else None
        )
        self._days.append((total / seconds, temperature))
        values = self.corrected()
        if len(values) > 1 and values[-1] - values[-2] >= TOP_UP_RISE:
            # Topped up: the days before say nothing about what is lost from here on
            latest = self._days[-1]
            self._days.clear()
            self._days.append(latest)
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": [list(day) for day in self._days],
            "fit": self._fit,
            "fit_hours": self._fit_hours,
        }

    def load(self, data: object) -> None:
        if not isinstance(data, dict):
            return

        for day in data.get("days") or []:
            if (
                isinstance(day, list)
                and len(day) == 2  # noqa: PLR2004
                and isinstance(day[0], int | float)
                and (day[1] is None or isinstance(day[1], int | float))
            ):
                self._days.append((float(day[0]), None if day[1] is None else float(day[1])))

        fit, hours = data.get("fit"), data.get("fit_hours")
        if (
            isinstance(fit, list)
            and len(fit) == 4  # noqa: PLR2004
            and all(isinstance(value, int | float) for value in fit)
            and isinstance(hours, int | float)
        ):
            self._fit = [float(value) for value in fit]
            self._fit_hours = float(hours)
