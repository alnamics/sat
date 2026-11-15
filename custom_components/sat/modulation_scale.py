"""Learn how the boiler reports its modulation, so the burner power can be worked out.

OpenTherm defines the relative modulation level as a share of the range between the boiler's
minimum and maximum power, so 0 % is the minimum. Many boilers report a share of the maximum
power instead, and read for example 16 % at their minimum. Taking such a reading as a share of
the range would nearly double the power at the minimum.

Two things tell what the boiler reads at minimum power. While SAT caps the modulation at its
minimum the burner runs at its lowest power, so the reading in those burns is it. And a boiler
whose lowest reading over many burns is its own reported minimum modulation level, never less,
reports a share of the maximum. Readings are rescaled from there: that reading is 0, and 100 % is
the maximum power.
"""

from __future__ import annotations

SMOOTHING = 0.2
MINIMUM_SAMPLES = 5
# A capped burner that reads this far above the boiler's minimum level ignores the cap
CAP_TOLERANCE = 8.0
# Without a known minimum level, readings above this are not taken as the minimum
MAXIMUM_PLAUSIBLE_MINIMUM = 40.0
# Readings of settled burns before their lowest counts, and how close it must be to the
# boiler's minimum level to be that level
LOWEST_MINIMUM_SAMPLES = 60
LOWEST_TOLERANCE = 2.0
# A minimum level below this is too close to 0 to tell the two meanings apart, and close enough
# not to matter
SMALLEST_MINIMUM_LEVEL = 5.0
FULL_SCALE = 100.0


class ModulationScale:
    """Turn the reported modulation into a share of the burner's power range."""

    def __init__(self) -> None:
        self._at_minimum: float | None = None
        self._samples = 0
        self._lowest: float | None = None
        self._lowest_samples = 0
        self._minimum_level: float | None = None

    @property
    def reading_at_minimum(self) -> float:
        """What the boiler reports at minimum power; 0 until it has been seen."""
        if self._at_minimum is not None and self._samples >= MINIMUM_SAMPLES:
            return self._at_minimum

        if (
            self._lowest is not None
            and self._minimum_level is not None
            and self._lowest_samples >= LOWEST_MINIMUM_SAMPLES
            and self._minimum_level >= SMALLEST_MINIMUM_LEVEL
            and abs(self._lowest - self._minimum_level) <= LOWEST_TOLERANCE
        ):
            return self._lowest
        return 0.0

    def observe(self, reading: float, minimum_level: float | None) -> None:
        """Feed a reading from any settled space heating burn."""
        if reading < 0:
            return
        self._minimum_level = minimum_level
        self._lowest = reading if self._lowest is None else min(self._lowest, reading)
        self._lowest_samples += 1

    def observe_minimum(self, reading: float, minimum_level: float | None) -> None:
        """Feed a reading from a settled burn that SAT capped at minimum modulation."""
        limit = (
            MAXIMUM_PLAUSIBLE_MINIMUM if minimum_level is None else minimum_level + CAP_TOLERANCE
        )
        if reading < 0 or reading > limit:
            return

        self._at_minimum = (
            reading
            if self._at_minimum is None
            else self._at_minimum + (reading - self._at_minimum) * SMOOTHING
        )
        self._samples += 1

    def share(self, reading: float) -> float:
        """Return 0..1 for where a reading lies between minimum and maximum power."""
        minimum = self.reading_at_minimum
        if minimum >= FULL_SCALE:
            return 0.0
        return min(max((reading - minimum) / (FULL_SCALE - minimum), 0.0), 1.0)
