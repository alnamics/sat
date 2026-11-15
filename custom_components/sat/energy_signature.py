"""Tell when the house starts using more gas for heating than the weather explains.

The heating gas of a day goes up in a straight line with the mean indoor-outdoor temperature
difference of that day (the energy signature of a building). The line does not pass through
zero: sun, people and appliances heat the house for free, so a mild day needs less gas per
kelvin than a cold one. Dividing gas by degree days would therefore call every cold snap an
anomaly. Instead the line is fitted to the four weeks before, and the last week's gas is compared
with what that line predicts for the last week's weather. Hot water burns are left out.
"""

from __future__ import annotations

from collections import deque
from typing import Any

SECONDS_PER_DAY = 86400.0
HISTORY_DAYS = 60
RECENT_DAYS = 7
REFERENCE_DAYS = 28
MINIMUM_REFERENCE_DAYS = 14
# A day counts once this much of it was measured; its gas is scaled to the whole day
MINIMUM_DAY_SECONDS = 20 * 3600.0
# Below this mean difference there is too little heating to judge
MINIMUM_DIFFERENCE = 5.0
# The reference days must differ this much (standard deviation) for a line to be fitted
MINIMUM_SPREAD = 2.0
# How far the last week's weather may lie outside the reference weather
WEATHER_MARGIN = 3.0
# Less predicted gas than this for the week says too little
MINIMUM_PREDICTED_GAS = 1.0


class EnergySignature:
    """Daily heating gas against the daily mean indoor-outdoor difference."""

    def __init__(self) -> None:
        # Completed days as (date, gas in m³, mean difference in K)
        self._days: deque[tuple[str, float, float]] = deque(maxlen=HISTORY_DAYS)
        self._day: str | None = None
        self._seconds = 0.0
        self._gas = 0.0
        self._kelvin_seconds = 0.0

    def update(
        self,
        dt: float,
        day: str,
        *,
        heating_gas: float,
        indoor: float | None,
        outdoor: float | None,
    ) -> None:
        """Feed the heating gas burned in this step (m³) and the temperatures."""
        if day != self._day:
            self._close_day()
            self._day = day

        if indoor is None or outdoor is None:
            return
        self._seconds += dt
        self._gas += heating_gas
        self._kelvin_seconds += max(0.0, indoor - outdoor) * dt

    def _close_day(self) -> None:
        day, seconds, gas, kelvin_seconds = (
            self._day,
            self._seconds,
            self._gas,
            self._kelvin_seconds,
        )
        self._seconds = self._gas = self._kelvin_seconds = 0.0
        if day is None or seconds < MINIMUM_DAY_SECONDS:
            return
        self._days.append((day, gas * SECONDS_PER_DAY / seconds, kelvin_seconds / seconds))

    @property
    def ratio(self) -> float | None:
        """Heating gas of the last week against what the weeks before predict for its weather."""
        days = list(self._days)
        if len(days) < RECENT_DAYS + MINIMUM_REFERENCE_DAYS:
            return None

        recent = days[-RECENT_DAYS:]
        reference = days[-(RECENT_DAYS + REFERENCE_DAYS) : -RECENT_DAYS]
        recent_x = [difference for _, _, difference in recent]
        recent_mean = sum(recent_x) / len(recent_x)
        if recent_mean < MINIMUM_DIFFERENCE:
            return None

        xs = [difference for _, _, difference in reference]
        ys = [gas for _, gas, _ in reference]
        count = len(xs)
        mean_x, mean_y = sum(xs) / count, sum(ys) / count
        spread = sum((x - mean_x) ** 2 for x in xs)
        slope = (
            sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / spread
            if spread / count >= MINIMUM_SPREAD**2
            else 0.0
        )

        if slope > 0:
            if not min(xs) - WEATHER_MARGIN <= recent_mean <= max(xs) + WEATHER_MARGIN:
                return None
            intercept = mean_y - slope * mean_x
            predicted = sum(max(0.0, intercept + slope * x) for x in recent_x)
        else:
            # The weather barely varied: only a week of the same weather can be compared
            if abs(recent_mean - mean_x) > WEATHER_MARGIN or mean_x <= 0:
                return None
            predicted = sum(mean_y / mean_x * x for x in recent_x)

        if predicted < MINIMUM_PREDICTED_GAS:
            return None
        return round(sum(gas for _, gas, _ in recent) / predicted, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": [list(day) for day in self._days],
            "day": self._day,
            "current": [self._seconds, self._gas, self._kelvin_seconds],
        }

    def load(self, data: object) -> None:
        if not isinstance(data, dict):
            return

        for item in data.get("days") or []:
            if (
                isinstance(item, list)
                and len(item) == 3  # noqa: PLR2004
                and isinstance(item[0], str)
                and isinstance(item[1], int | float)
                and isinstance(item[2], int | float)
            ):
                self._days.append((item[0], float(item[1]), float(item[2])))

        day, current = data.get("day"), data.get("current")
        if (
            isinstance(day, str)
            and isinstance(current, list)
            and len(current) == 3  # noqa: PLR2004
            and all(isinstance(value, int | float) for value in current)
        ):
            self._day = day
            self._seconds, self._gas, self._kelvin_seconds = (float(value) for value in current)
