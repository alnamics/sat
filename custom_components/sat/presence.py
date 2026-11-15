"""Lower the target while nobody is home, and raise it again before people return.

Home is read from people, device trackers, zones (the number of people in them), groups or any
on/off entity. With a distance sensor (the Proximity integration) the house counts as occupied
again as soon as someone is within the return distance, so a slow floor starts warming early.
"""

from __future__ import annotations

from enum import StrEnum

AWAY_DELAY_SECONDS = 1800.0
HOME_STATES = frozenset({"home", "on", "true"})


class Occupancy(StrEnum):
    HOME = "home"
    AWAY = "away"
    RETURNING = "returning"


def is_home(state: str | None) -> bool | None:
    """Return whether one entity state says someone is home, or None when it is unknown."""
    if state is None or state in {"unknown", "unavailable", ""}:
        return None
    if state in HOME_STATES:
        return True
    try:
        return float(state) > 0
    except ValueError:
        return False


class PresenceTracker:
    """Turn presence readings into home, away or returning."""

    def __init__(self, return_distance_km: float = 0.0) -> None:
        self._return_distance = return_distance_km
        self._absent_since: float | None = None
        self._state = Occupancy.HOME

    @property
    def state(self) -> Occupancy:
        return self._state

    def update(self, now: float, *, home: bool | None, distance_km: float | None) -> Occupancy:
        if home is None:
            return self._state

        if home:
            self._absent_since = None
            self._state = Occupancy.HOME
            return self._state

        if self._absent_since is None:
            self._absent_since = now

        if now - self._absent_since < AWAY_DELAY_SECONDS:
            return self._state

        if (
            self._return_distance > 0
            and distance_km is not None
            and distance_km <= self._return_distance
        ):
            self._state = Occupancy.RETURNING
        else:
            self._state = Occupancy.AWAY
        return self._state
