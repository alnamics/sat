"""Tests for the loop monitor and the boiler totals."""

import random

from custom_components.sat.boiler_stats import BoilerStats
from custom_components.sat.loop_monitor import LoopMonitor, RoomReading, estimate_water_flow

ROOMS = ["climate.a", "climate.b", "climate.c", "climate.d"]


def test_the_water_flow_follows_from_heat_and_spread() -> None:
    flow = estimate_water_flow(5.28, 33.6, 29.0)

    assert flow is not None
    assert abs(flow - 16.45) < 0.05
    assert estimate_water_flow(5.28, 30.0, 29.0) is None


def test_the_flow_of_each_loop_is_learned_from_the_thermostats() -> None:
    loop_flows = {"climate.a": 2.2, "climate.b": 1.6, "climate.c": 2.0, "climate.d": 1.1}
    monitor = LoopMonitor(ROOMS)
    rng = random.Random(3)  # noqa: S311 - reproducible noise

    for step in range(400):
        states = {room: rng.random() < 0.7 for room in ROOMS}
        flow = 7.5 + sum(loop_flows[room] for room in ROOMS if states[room])
        readings = {room: RoomReading(open=states[room], temperature=21.5) for room in ROOMS}
        monitor.update(step * 300.0, readings, flow + rng.gauss(0, 0.4))

    for room in ROOMS:
        learned = monitor.loop_flow(room)
        assert learned is not None
        assert abs(learned - loop_flows[room]) < 0.4


def test_a_loop_never_seen_closed_has_no_flow() -> None:
    monitor = LoopMonitor(ROOMS)
    for step in range(50):
        readings = {room: RoomReading(open=True, temperature=21.5) for room in ROOMS}
        monitor.update(step * 300.0, readings, 16.0)

    assert all(monitor.loop_flow(room) is None for room in ROOMS)


def test_rotameter_advice_follows_room_temperatures_and_valves() -> None:
    monitor = LoopMonitor(ROOMS)
    temperatures = {"climate.a": 23.2, "climate.b": 22.0, "climate.c": 21.0, "climate.d": 22.0}
    assert monitor.advice("climate.a") == ("learning", 0)

    now = 0.0
    while now < 30 * 3600:
        hour = (now / 3600) % 24
        readings = {
            room: RoomReading(
                open=hour < 12 if room == "climate.a" else True,
                temperature=temperatures[room],
            )
            for room in ROOMS
        }
        monitor.update(now, readings, None)
        now += 60

    assert monitor.advice("climate.a")[0] == "reduce"
    assert monitor.advice("climate.c")[0] == "increase"
    assert monitor.advice("climate.b") == ("ok", 0)
    assert monitor.rooms_to_adjust == 2


def test_the_totals_count_starts_hours_heat_and_degree_days() -> None:
    stats = BoilerStats()
    now = 0.0
    for minute in range(24 * 60):
        flame = minute % 30 < 15
        stats.update(
            now=now,
            flame=flame,
            hot_water=False,
            heat_kw=5.28 if flame else None,
            gas_m3_per_hour=0.5 if flame else None,
            outdoor=2.0,
        )
        now += 60

    assert 47 <= stats.totals["starts"] <= 48
    assert abs(stats.totals["burn_hours"] - 12.0) < 0.3
    assert abs(stats.totals["gas_m3"] - 6.0) < 0.2
    assert abs(stats.totals["degree_days"] - 16.0) < 0.1


def test_a_cylinder_drop_right_after_heating_stops_is_told_apart() -> None:
    stats = BoilerStats()
    now = 0.0

    def step(temperature: float, stopped: float | None, *, hot_water: bool = False) -> None:
        nonlocal now
        stats.update(
            now=now,
            flame=False,
            hot_water=hot_water,
            heat_kw=None,
            gas_m3_per_hour=None,
            outdoor=5.0,
            hot_water_temperature=temperature,
            heating_stopped_at=stopped,
        )
        now += 30

    step(50.0, None)
    stopped = now
    for temperature in (49.8, 49.0, 48.2):
        step(temperature, stopped)
    step(50.0, stopped, hot_water=True)
    for _ in range(40):
        step(50.0, stopped)
    step(48.0, stopped)

    assert stats.hot_water_drops == 2
    assert stats.hot_water_drops_after_heating == 1
