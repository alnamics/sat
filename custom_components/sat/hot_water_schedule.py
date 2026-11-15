"""Hot water temperature by schedule, with a weekly legionella boost.

A cylinder kept at 50-55 °C around the clock loses heat through its jacket all day and gets
reheated for it. A lower temperature outside the hours hot water is used cuts those losses. Once
a week the cylinder is held at 60 °C for an hour, the usual guidance against legionella.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

SECONDS_PER_HOUR = 3600.0
LEGIONELLA_TEMPERATURE = 60.0
# The cylinder counts as hot once it is this close to the boost temperature
LEGIONELLA_REACHED_MARGIN = 2.0
LEGIONELLA_HOLD_SECONDS = SECONDS_PER_HOUR
# A boost that never reaches its temperature gives up after this long
LEGIONELLA_TIMEOUT_SECONDS = 4 * SECONDS_PER_HOUR


@dataclass(frozen=True, slots=True)
class HotWaterPlan:
    comfort_temperature: float
    eco_temperature: float | None = None
    legionella_weekday: int | None = None
    legionella_start_seconds: float = 3 * SECONDS_PER_HOUR


class HotWaterSchedule:
    """Decide the hot water setpoint from the schedule and the weekly boost."""

    def __init__(self, plan: HotWaterPlan) -> None:
        self._plan = plan
        self._boost_started: datetime | None = None
        self._boost_reached: datetime | None = None
        self._last_boost_week: tuple[int, int] | None = None

    @property
    def boosting(self) -> bool:
        return self._boost_started is not None

    @property
    def attributes(self) -> dict[str, object]:
        return {
            "hot_water_legionella_boost": self.boosting,
            "hot_water_last_boost_week": (
                None
                if self._last_boost_week is None
                else "-W".join(map(str, self._last_boost_week))
            ),
        }

    def restore_last_boost(self, week: object) -> None:
        """Take the week of the last boost back from its attribute form, such as 2026-W47."""
        if not isinstance(week, str):
            return
        year, _, number = week.partition("-W")
        if year.isdigit() and number.isdigit():
            self._last_boost_week = (int(year), int(number))

    def target(
        self,
        now: datetime,
        *,
        comfort: bool | None,
        temperature: float | None,
        maximum: float = LEGIONELLA_TEMPERATURE,
    ) -> float:
        """Return the hot water setpoint for this moment (local time).

        A boiler that cannot heat hot water to 60 °C is boosted to its own maximum.
        """
        boost = min(LEGIONELLA_TEMPERATURE, maximum)
        if self._boost(now, temperature, boost):
            return boost

        if comfort is False and self._plan.eco_temperature is not None:
            return self._plan.eco_temperature
        return self._plan.comfort_temperature

    def _boost(self, now: datetime, temperature: float | None, boost: float) -> bool:
        weekday = self._plan.legionella_weekday
        if weekday is None:
            return False

        iso = now.isocalendar()
        week = (iso.year, iso.week)

        if self._boost_started is None:
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = midnight + timedelta(seconds=self._plan.legionella_start_seconds)
            if now.weekday() != weekday or now < start or self._last_boost_week == week:
                return False
            self._boost_started = now
            self._boost_reached = None

        if (
            temperature is not None
            and self._boost_reached is None
            and temperature >= boost - LEGIONELLA_REACHED_MARGIN
        ):
            self._boost_reached = now

        held = (
            self._boost_reached is not None
            and (now - self._boost_reached).total_seconds() >= LEGIONELLA_HOLD_SECONDS
        )
        timed_out = (now - self._boost_started).total_seconds() >= LEGIONELLA_TIMEOUT_SECONDS
        if held or timed_out:
            self._boost_started = None
            self._boost_reached = None
            self._last_boost_week = week
            return False

        return True
