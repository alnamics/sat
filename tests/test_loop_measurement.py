"""Tests for measuring the loop flows one room at a time."""

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.climate import HVACMode

from custom_components.sat.loop_measurement import (
    LoopMeasurement,
    async_load_interrupted,
    async_restore_interrupted,
    loop_measurement_store,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

FLOWS = {"climate.a": 3.0, "climate.b": 2.0}


async def test_each_loop_is_measured_against_the_base(hass: HomeAssistant) -> None:
    for entity_id in FLOWS:
        hass.states.async_set(entity_id, HVACMode.HEAT, {"temperature": 22})

    async def set_mode(call: ServiceCall) -> None:
        state = hass.states.get(call.data["entity_id"])
        attributes = dict(state.attributes) if state else {}
        hass.states.async_set(call.data["entity_id"], call.data["hvac_mode"], attributes)

    async def set_temperature(call: ServiceCall) -> None:
        state = hass.states.get(call.data["entity_id"])
        mode = state.state if state else HVACMode.HEAT
        hass.states.async_set(
            call.data["entity_id"], mode, {"temperature": call.data["temperature"]}
        )

    hass.services.async_register("climate", "set_hvac_mode", set_mode)
    hass.services.async_register("climate", "set_temperature", set_temperature)

    def sample() -> float:
        flow = 8.0
        for entity_id, loop in FLOWS.items():
            state = hass.states.get(entity_id)
            if state is not None and state.state == HVACMode.HEAT:
                flow += loop
        return flow

    measurement = LoopMeasurement(
        hass,
        list(FLOWS),
        valve_seconds=0,
        sample=sample,
        poll_seconds=0,
        settle_seconds=0,
    )
    result = await measurement.async_run()

    assert result.base_lpm == 8.0
    assert result.loops_lpm == {"climate.a": 3.0, "climate.b": 2.0}
    for entity_id in FLOWS:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == HVACMode.HEAT
        assert state.attributes["temperature"] == 22


async def test_an_interrupted_measurement_is_put_back_at_the_next_start(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass.states.async_set("climate.a", HVACMode.OFF, {"temperature": 30})
    calls: list[tuple[str, dict[str, Any]]] = []

    async def record(call: ServiceCall) -> None:
        calls.append((call.service, dict(call.data)))

    hass.services.async_register("climate", "set_hvac_mode", record)
    hass.services.async_register("climate", "set_temperature", record)

    store = loop_measurement_store(hass, "entry")
    hass_storage[store.key] = {
        "version": 1,
        "minor_version": 1,
        "key": store.key,
        "data": {
            "rooms": {
                "climate.a": {"mode": "heat", "temperature": 22},
                "climate.b": {"mode": "heat", "temperature": 23},
            }
        },
    }

    saved = await async_load_interrupted(store)
    assert set(saved) == {"climate.a", "climate.b"}

    # climate.b is not available yet, as Z-Wave thermostats right after a start
    remaining = await async_restore_interrupted(hass, store, saved)
    assert calls == [
        ("set_hvac_mode", {"entity_id": "climate.a", "hvac_mode": HVACMode.HEAT}),
        ("set_temperature", {"entity_id": "climate.a", "temperature": 22}),
    ]
    assert set(remaining) == {"climate.b"}
    assert set(await async_load_interrupted(store)) == {"climate.b"}

    hass.states.async_set("climate.b", HVACMode.OFF, {"temperature": 30})
    assert await async_restore_interrupted(hass, store, remaining) == {}
    assert ("set_temperature", {"entity_id": "climate.b", "temperature": 23}) in calls
    assert await async_load_interrupted(store) == {}


async def test_a_measurement_stopped_by_home_assistant_keeps_its_record(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("climate.a", HVACMode.HEAT, {"temperature": 22})

    async def set_mode(call: ServiceCall) -> None:
        hass.states.async_set(call.data["entity_id"], call.data["hvac_mode"], {"temperature": 30})

    async def set_temperature(_call: ServiceCall) -> None:
        return

    hass.services.async_register("climate", "set_hvac_mode", set_mode)
    hass.services.async_register("climate", "set_temperature", set_temperature)

    store = loop_measurement_store(hass, "entry")
    measurement = LoopMeasurement(
        hass, ["climate.a"], valve_seconds=3600, sample=lambda: None, store=store
    )
    # A plain task, so Home Assistant's own waiting does not wait for the hour-long valve time
    task = asyncio.get_running_loop().create_task(measurement.async_run())
    for _ in range(20):
        await asyncio.sleep(0)
    assert measurement.running

    measurement.abandoned = True
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await async_load_interrupted(store) == {"climate.a": {"mode": "heat", "temperature": 22}}
