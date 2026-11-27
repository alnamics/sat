"""The flow guard learns which open valves cut ignitions out and lets a block wait."""

from custom_components.sat.flow_guard import (
    AFTER_HOT_WATER_SECONDS,
    MAXIMUM_WAIT_SECONDS,
    FlowGuard,
)

KIDS = frozenset({"climate.kids"})
KIDS_AND_LIVING = frozenset({"climate.kids", "climate.living"})


def ignition(guard: FlowGuard, now: float, loops: frozenset[str], seconds: float) -> float:
    """Light in an on-phase and burn this long; return the time after it."""
    guard.update(now, flame=True, hot_water=False, on_phase=True, loops=loops)
    guard.update(now + seconds, flame=False, hot_water=False, on_phase=True, loops=loops)
    # The block ends and a new one starts later
    guard.update(now + seconds + 1, flame=False, hot_water=False, on_phase=False, loops=loops)
    return now + seconds + 600


def test_a_valve_set_that_cuts_ignitions_out_is_learned() -> None:
    guard = FlowGuard()
    now = 0.0
    for _ in range(3):
        now = ignition(guard, now, KIDS, 15)
    now = ignition(guard, now, KIDS_AND_LIVING, 1500)

    assert guard.too_little_flow(KIDS)
    assert not guard.too_little_flow(KIDS_AND_LIVING)
    assert guard.attributes["flow_guard_sets"]["climate.kids"][1] > 2


def test_a_block_waits_for_another_valve_and_then_lights() -> None:
    guard = FlowGuard()
    now = 0.0
    for _ in range(3):
        now = ignition(guard, now, KIDS, 15)

    guard.update(now, flame=False, hot_water=False, on_phase=True, loops=KIDS)
    assert guard.wait(now, flame=False, loops=KIDS)
    assert guard.wait(now + 600, flame=False, loops=KIDS)
    # The living room opens: the block lights, and does not wait again in this block
    assert not guard.wait(now + 900, flame=False, loops=KIDS_AND_LIVING)
    assert not guard.wait(now + 960, flame=False, loops=KIDS)
    assert guard.waits == 1


def test_the_wait_has_a_limit() -> None:
    guard = FlowGuard()
    now = 0.0
    for _ in range(3):
        now = ignition(guard, now, KIDS, 15)

    assert guard.wait(now, flame=False, loops=KIDS)
    assert guard.wait(now + MAXIMUM_WAIT_SECONDS - 1, flame=False, loops=KIDS)
    assert not guard.wait(now + MAXIMUM_WAIT_SECONDS, flame=False, loops=KIDS)


def test_ignitions_after_hot_water_teach_nothing() -> None:
    guard = FlowGuard()
    now = 0.0
    for _ in range(3):
        guard.update(now, flame=True, hot_water=True, on_phase=True, loops=KIDS)
        now += 100
        now = ignition(guard, now + AFTER_HOT_WATER_SECONDS / 2, KIDS, 15)

    assert not guard.too_little_flow(KIDS)


def test_unknown_valves_and_good_burns_never_wait() -> None:
    guard = FlowGuard()
    assert not guard.wait(0.0, flame=False, loops=KIDS)
    now = 0.0
    for _ in range(4):
        now = ignition(guard, now, KIDS, 1500)
    assert not guard.wait(now, flame=False, loops=KIDS)


def test_the_learned_sets_survive_a_restart() -> None:
    guard = FlowGuard()
    now = 0.0
    for _ in range(3):
        now = ignition(guard, now, frozenset(), 15)

    restored = FlowGuard()
    restored.restore(guard.attributes["flow_guard_sets"])
    assert restored.too_little_flow(frozenset())
