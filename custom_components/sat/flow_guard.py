"""Hold a heating ignition while too few floor loops are open for the boiler to take it.

With most room valves closed a combi boiler at its ignition power heats the little water that
still flows by some 18 K within seconds and cuts out above its setpoint, then waits its
anti-cycling time. When the boiler's highest setpoint is already in use there is no room to
raise it, so the only cure is more water: the guard learns which sets of open room valves end
the ignitions that way and lets a block wait for another valve to open, up to a limit.
"""

from __future__ import annotations

from typing import Any

# A heating burn this short in an on-phase was cut out; one this long was taken
CUT_OUT_SECONDS = 60.0
TAKEN_SECONDS = 180.0
# Each new ignition weighs this much against the older ones of the same valves
MEMORY = 0.8
# A set of valves is avoided once three ignitions (weighted) went mostly this way
MINIMUM_ATTEMPTS = 2.0
CUT_OUT_SHARE = 0.6
# A block waits at most this long for another valve, then lights anyway
MAXIMUM_WAIT_SECONDS = 2700.0
# Ignitions this soon after hot water cut out on the hot heat exchanger, not on the flow
AFTER_HOT_WATER_SECONDS = 300.0
# Only so many sets are kept
MAXIMUM_SETS = 32


# A thermal actuator takes minutes to open: a room valve counts as open once its thermostat has
# asked for heat this long without a break, so one switching every minute never counts
LOOP_SETTLE_SECONDS = 180.0


class LoopTracker:
    """Follow since when each room thermostat asks for heat, without a break."""

    def __init__(self, settle_seconds: float = LOOP_SETTLE_SECONDS) -> None:
        self.settle_seconds = max(LOOP_SETTLE_SECONDS, settle_seconds)
        self._since: dict[str, float] = {}

    def seen(self, entity_id: str, *, open_: bool, now: float, settled: bool = False) -> None:
        """Note a thermostat's state; a valve found open at startup has had its time."""
        if not open_:
            self._since.pop(entity_id, None)
        elif entity_id not in self._since:
            self._since[entity_id] = now - self.settle_seconds if settled else now

    def open_loops(self, now: float) -> frozenset[str]:
        """Return the room valves that have been open long enough to carry water."""
        return frozenset(
            entity_id
            for entity_id, since in self._since.items()
            if now - since >= self.settle_seconds
        )


def _key(loops: frozenset[str]) -> str:
    return ",".join(sorted(loops))


class FlowGuard:
    """Learn which open room valves cut ignitions out, and hold a block while they are all."""

    def __init__(self, maximum_wait_seconds: float = MAXIMUM_WAIT_SECONDS) -> None:
        self.maximum_wait_seconds = max(0.0, maximum_wait_seconds)
        # Weighted ignitions and cut-outs per set of open room valves
        self._sets: dict[str, list[float]] = {}
        # When the heating burn started and its open valves; no valves to learn after hot water
        self._burn: tuple[float, str | None] | None = None
        self._hot_water_ended: float | None = None
        self._waiting_since: float | None = None
        self._released = False
        self.waits = 0

    # ---------------------------------------------------------------- learning

    def update(
        self,
        now: float,
        *,
        flame: bool,
        hot_water: bool,
        on_phase: bool,
        loops: frozenset[str],
    ) -> None:
        """Follow the burns: when a heating burn starts and how long it lasted."""
        if hot_water:
            self._hot_water_ended = now
            self._burn = None
            return

        if not on_phase:
            # A new on-phase may wait again
            self._waiting_since = None
            self._released = False

        if flame and self._burn is None and on_phase:
            after_hot_water = (
                self._hot_water_ended is not None
                and now - self._hot_water_ended <= AFTER_HOT_WATER_SECONDS
            )
            self._burn = (now, None if after_hot_water else _key(loops))
            # Lit: this block no longer waits
            self._released = True
            self._waiting_since = None
            return

        if not flame and self._burn is not None:
            started, key = self._burn
            self._burn = None
            duration = now - started
            if key is None or not on_phase:
                return
            if duration < CUT_OUT_SECONDS:
                self._record(key, cut_out=True)
            elif duration >= TAKEN_SECONDS:
                self._record(key, cut_out=False)
            return

        if flame and self._burn is not None and on_phase:
            started, key = self._burn
            if key is not None and now - started >= TAKEN_SECONDS:
                # A long burn counts once it is clearly taken, not only when it ends
                self._record(key, cut_out=False)
                self._burn = (started, None)

    def _record(self, key: str, *, cut_out: bool) -> None:
        attempts, cut_outs = self._sets.get(key, [0.0, 0.0])
        self._sets[key] = [attempts * MEMORY + 1.0, cut_outs * MEMORY + (1.0 if cut_out else 0.0)]
        if len(self._sets) > MAXIMUM_SETS:
            # Drop the set seen least
            least = min(self._sets, key=lambda name: self._sets[name][0])
            del self._sets[least]

    def too_little_flow(self, loops: frozenset[str]) -> bool:
        """Return True if ignitions with these valves open were mostly cut out."""
        attempts, cut_outs = self._sets.get(_key(loops), [0.0, 0.0])
        return attempts >= MINIMUM_ATTEMPTS and cut_outs / attempts >= CUT_OUT_SHARE

    # ----------------------------------------------------------------- waiting

    def wait(self, now: float, *, flame: bool, loops: frozenset[str]) -> bool:
        """Return True while an on-phase holds its ignition for another valve to open."""
        if flame or self._released or self.maximum_wait_seconds <= 0:
            return False
        if not self.too_little_flow(loops):
            if self._waiting_since is not None:
                self._released = True
                self._waiting_since = None
            return False
        if self._waiting_since is None:
            self._waiting_since = now
            self.waits += 1
        if now - self._waiting_since >= self.maximum_wait_seconds:
            self._released = True
            self._waiting_since = None
            return False
        return True

    # ----------------------------------------------------------------- storage

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            "flow_guard_sets": {
                key or "-": [round(attempts, 2), round(cut_outs, 2)]
                for key, (attempts, cut_outs) in self._sets.items()
            },
            "flow_guard_waits": self.waits,
        }

    def restore(self, sets: object) -> None:
        if not isinstance(sets, dict):
            return
        for key, value in sets.items():
            if (
                isinstance(key, str)
                and isinstance(value, list | tuple)
                and len(value) == 2  # noqa: PLR2004
                and all(isinstance(number, int | float) for number in value)
            ):
                self._sets["" if key == "-" else key] = [float(value[0]), float(value[1])]
