"""Measure the water flow of each heating loop by opening the loops one at a time.

With all room thermostats off only the loops without an actuator carry water; that gives the base
flow. Each room is then opened alone, and its loop's flow is the rise over the base. The flow
itself comes from the burner power and the flow/return spread of settled burns, so SAT keeps the
burner on at minimum power for the whole run. The room thermostats are put back as they were.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from statistics import median
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

POLL_SECONDS = 30.0
SAMPLES = 10
# Extra wait after the valves moved, for the loop temperatures to settle
SETTLE_SECONDS = 300.0
STEP_TIMEOUT_SECONDS = 1800.0
OPEN_TARGET = 30.0


@dataclass
class MeasurementResult:
    base_lpm: float | None = None
    loops_lpm: dict[str, float | None] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "base_lpm": None if self.base_lpm is None else round(self.base_lpm, 1),
            "loops_lpm": {
                entity_id: None if flow is None else round(flow, 1)
                for entity_id, flow in self.loops_lpm.items()
            },
        }


class LoopMeasurement:
    """Run one measurement of all loops; the climate keeps the burner on while it runs."""

    def __init__(
        self,
        hass: HomeAssistant,
        rooms: list[str],
        *,
        valve_seconds: float,
        sample: Callable[[], float | None],
        poll_seconds: float = POLL_SECONDS,
        settle_seconds: float = SETTLE_SECONDS,
    ) -> None:
        self._hass = hass
        self._rooms = rooms
        self._valve_seconds = valve_seconds
        self._sample = sample
        self._poll = poll_seconds
        self._settle = settle_seconds
        self.step: str | None = None
        self.result = MeasurementResult()

    @property
    def running(self) -> bool:
        return self.step is not None

    async def async_run(self) -> MeasurementResult:
        saved = {
            entity_id: state
            for entity_id in self._rooms
            if (state := self._hass.states.get(entity_id)) is not None
        }
        try:
            self.step = "base"
            for entity_id in self._rooms:
                await self._set_mode(entity_id, HVACMode.OFF)
            await asyncio.sleep(self._valve_seconds + self._settle)
            self.result.base_lpm = await self._measure()

            for entity_id in self._rooms:
                self.step = entity_id
                await self._set_mode(entity_id, HVACMode.HEAT)
                await self._call(
                    SERVICE_SET_TEMPERATURE,
                    {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: OPEN_TARGET},
                )
                await asyncio.sleep(self._valve_seconds + self._settle)
                flow = await self._measure()
                base = self.result.base_lpm
                self.result.loops_lpm[entity_id] = (
                    None if flow is None or base is None else max(0.0, flow - base)
                )
                await self._set_mode(entity_id, HVACMode.OFF)
        finally:
            self.step = None
            for entity_id, state in saved.items():
                try:
                    await self._set_mode(entity_id, HVACMode(state.state))
                    if (temperature := state.attributes.get(ATTR_TEMPERATURE)) is not None:
                        await self._call(
                            SERVICE_SET_TEMPERATURE,
                            {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: temperature},
                        )
                except ValueError, HomeAssistantError:
                    _LOGGER.warning("Could not restore %s to %s.", entity_id, state.state)

        return self.result

    async def _measure(self) -> float | None:
        samples: list[float] = []
        waited = 0.0
        while len(samples) < SAMPLES and waited < STEP_TIMEOUT_SECONDS:
            if (value := self._sample()) is not None:
                samples.append(value)
            await asyncio.sleep(self._poll)
            waited += self._poll
        return median(samples) if samples else None

    async def _set_mode(self, entity_id: str, mode: HVACMode) -> None:
        await self._call(SERVICE_SET_HVAC_MODE, {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: mode})

    async def _call(self, service: str, data: dict[str, Any]) -> None:
        await self._hass.services.async_call(CLIMATE_DOMAIN, service, data, blocking=True)
