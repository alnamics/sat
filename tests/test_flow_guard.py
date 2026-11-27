"""The flow guard learns which open valves cut ignitions out and lets a block wait."""

from custom_components.sat.flow_guard import (
    AFTER_HOT_WATER_SECONDS,
    LOOP_SETTLE_SECONDS,
    MAXIMUM_WAIT_SECONDS,
    FlowGuard,
    LoopTracker,
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


def test_a_valve_counts_once_it_has_had_time_to_open() -> None:
    loops = LoopTracker()
    loops.seen("climate.kids", open_=True, now=0.0)
    assert loops.open_loops(LOOP_SETTLE_SECONDS - 1) == frozenset()
    assert loops.open_loops(LOOP_SETTLE_SECONDS) == KIDS


def test_a_thermostat_switching_each_minute_never_counts() -> None:
    loops = LoopTracker()
    now = 0.0
    for _ in range(20):
        loops.seen("climate.living", open_=True, now=now)
        now += 60
        assert loops.open_loops(now) == frozenset()
        loops.seen("climate.living", open_=False, now=now)
        now += 5


def test_a_repeated_heating_report_keeps_the_start() -> None:
    loops = LoopTracker()
    loops.seen("climate.kids", open_=True, now=0.0)
    loops.seen("climate.kids", open_=True, now=100.0)
    assert loops.open_loops(LOOP_SETTLE_SECONDS) == KIDS


def test_valves_open_at_startup_have_had_their_time() -> None:
    loops = LoopTracker()
    loops.seen("climate.kids", open_=True, now=500.0, settled=True)
    assert loops.open_loops(500.0) == KIDS


def test_a_longer_configured_opening_time_is_kept() -> None:
    loops = LoopTracker(settle_seconds=300.0)
    loops.seen("climate.kids", open_=True, now=0.0)
    assert loops.open_loops(200.0) == frozenset()
    assert loops.open_loops(300.0) == KIDS
    # A shorter one is raised to the actuator's time
    assert LoopTracker(settle_seconds=30.0).settle_seconds == LOOP_SETTLE_SECONDS


def test_a_cut_out_after_a_reheat_and_a_burn_off_phase_are_not_learned() -> None:
    guard = FlowGuard()
    # A burn the off-phase carries on, ending shortly: not an ignition cut out
    guard.update(0.0, flame=True, hot_water=False, on_phase=True, loops=KIDS)
    guard.update(30.0, flame=False, hot_water=False, on_phase=False, loops=KIDS)
    # A burn that lights outside an on-phase
    guard.update(100.0, flame=True, hot_water=False, on_phase=False, loops=KIDS)
    guard.update(110.0, flame=False, hot_water=False, on_phase=False, loops=KIDS)
    assert guard.attributes["flow_guard_sets"] == {}


def test_a_long_burn_counts_while_it_burns() -> None:
    guard = FlowGuard()
    guard.update(0.0, flame=True, hot_water=False, on_phase=True, loops=KIDS_AND_LIVING)
    guard.update(200.0, flame=True, hot_water=False, on_phase=True, loops=KIDS_AND_LIVING)
    assert guard.attributes["flow_guard_sets"]["climate.kids,climate.living"] == [1.0, 0.0]
    # Its end does not count it twice
    guard.update(1500.0, flame=False, hot_water=False, on_phase=True, loops=KIDS_AND_LIVING)
    assert guard.attributes["flow_guard_sets"]["climate.kids,climate.living"] == [1.0, 0.0]


def test_good_ignitions_clear_a_set_again() -> None:
    guard = FlowGuard()
    now = 0.0
    for _ in range(3):
        now = ignition(guard, now, KIDS, 15)
    assert guard.too_little_flow(KIDS)
    # More water came (a pump or a bypass): the same valves now burn on
    for _ in range(4):
        now = ignition(guard, now, KIDS, 1500)
    assert not guard.too_little_flow(KIDS)


def test_a_broken_restore_is_ignored() -> None:
    guard = FlowGuard()
    guard.restore({"climate.kids": "x", 3: [1, 1], "climate.a": [1.0]})
    guard.restore(None)
    assert guard.attributes["flow_guard_sets"] == {}
