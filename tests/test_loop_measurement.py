"""Tests for measuring the loop flows one room at a time."""

from typing import TYPE_CHECKING

from homeassistant.components.climate import HVACMode

from custom_components.sat.loop_measurement import LoopMeasurement

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
