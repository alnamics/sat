"""Learn how the boiler reports its modulation, so the burner power can be worked out.

OpenTherm defines the relative modulation level as a share of the range between the boiler's
minimum and maximum power, so 0 % is the minimum. Many boilers report a share of the maximum
power instead, and read for example 16 % at their minimum. Taking such a reading as a share of
the range would nearly double the power at the minimum.

While SAT caps the modulation at its minimum the burner runs at its lowest power, so the reading
in those burns is what the boiler reports at minimum power. Readings are rescaled from there:
that reading is 0, and 100 % is the maximum power.
"""

from __future__ import annotations

SMOOTHING = 0.2
MINIMUM_SAMPLES = 5
# A capped burner that reads this far above the boiler's minimum level ignores the cap
CAP_TOLERANCE = 8.0
# Without a known minimum level, readings above this are not taken as the minimum
MAXIMUM_PLAUSIBLE_MINIMUM = 40.0
FULL_SCALE = 100.0


class ModulationScale:
    """Turn the reported modulation into a share of the burner's power range."""

    def __init__(self) -> None:
        self._at_minimum: float | None = None
        self._samples = 0

    @property
    def reading_at_minimum(self) -> float:
        """What the boiler reports at minimum power; 0 until it has been seen."""
        if self._at_minimum is None or self._samples < MINIMUM_SAMPLES:
            return 0.0
        return self._at_minimum

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
