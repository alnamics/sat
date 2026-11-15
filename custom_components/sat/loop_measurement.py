"""Measure the water flow of each heating loop by opening the loops one at a time.

With all room thermostats off only the loops without an actuator carry water; that gives the base
flow. Each room is then opened alone, and its loop's flow is the rise over the base. The flow
itself comes from the burner power and the flow/return spread of settled burns, so SAT keeps the
burner on at minimum power for the whole run. The room thermostats are put back as they were.

How the thermostats were set is saved before anything is changed. Should Home Assistant stop in
the middle of a run, the next start puts them back from that record.
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
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .const import DOMAIN

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


def loop_measurement_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.loop_measurement")


async def _async_call(hass: HomeAssistant, service: str, data: dict[str, Any]) -> None:
    await hass.services.async_call(CLIMATE_DOMAIN, service, data, blocking=True)


async def _async_restore(
    hass: HomeAssistant, saved: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Put the room thermostats back to their saved mode and target.

    Return the ones that could not be restored, such as thermostats that are not available yet.
    """
    remaining: dict[str, dict[str, Any]] = {}
    for entity_id, values in saved.items():
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            remaining[entity_id] = values
            continue
        try:
            await _async_call(
                hass,
                SERVICE_SET_HVAC_MODE,
                {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode(values["mode"])},
            )
            if (temperature := values.get("temperature")) is not None:
                await _async_call(
                    hass,
                    SERVICE_SET_TEMPERATURE,
                    {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: temperature},
                )
        except (ValueError, KeyError) as error:
            _LOGGER.warning("Cannot restore %s after the loop measurement: %s", entity_id, error)
        except HomeAssistantError as error:
            _LOGGER.debug("Restoring %s failed, trying again later: %s", entity_id, error)
            remaining[entity_id] = values
    return remaining


async def async_load_interrupted(store: Store[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return the thermostat settings of a measurement that was interrupted, if any."""
    data = await store.async_load()
    saved = data.get("rooms") if isinstance(data, dict) else None
    if not isinstance(saved, dict):
        return {}
    return {
        entity_id: values
        for entity_id, values in saved.items()
        if isinstance(entity_id, str) and isinstance(values, dict)
    }


async def async_restore_interrupted(
    hass: HomeAssistant, store: Store[dict[str, Any]], saved: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Restore what can be restored now and keep the rest on record for the next try."""
    remaining = await _async_restore(hass, saved)
    if len(remaining) < len(saved):
        _LOGGER.warning(
            "A loop measurement was interrupted; put %d room thermostat(s) back as they were.",
            len(saved) - len(remaining),
        )
    if remaining:
        await store.async_save({"rooms": remaining})
    else:
        await store.async_remove()
    return remaining


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
        store: Store[dict[str, Any]] | None = None,
        poll_seconds: float = POLL_SECONDS,
        settle_seconds: float = SETTLE_SECONDS,
    ) -> None:
        self._hass = hass
        self._rooms = rooms
        self._valve_seconds = valve_seconds
        self._sample = sample
        self._store = store
        self._poll = poll_seconds
        self._settle = settle_seconds
        self.step: str | None = None
        self.result = MeasurementResult()
        # Set when Home Assistant stops or the entry unloads during the run
        self.abandoned = False

    @property
    def running(self) -> bool:
        return self.step is not None

    async def async_run(self) -> MeasurementResult:
        saved: dict[str, dict[str, Any]] = {}
        for entity_id in self._rooms:
            state = self._hass.states.get(entity_id)
            if state is not None and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                saved[entity_id] = {
                    "mode": state.state,
                    "temperature": state.attributes.get(ATTR_TEMPERATURE),
                }
        if self._store is not None:
            await self._store.async_save({"rooms": saved})

        try:
            self.step = "base"
            for entity_id in self._rooms:
                await self._set_mode(entity_id, HVACMode.OFF)
            await asyncio.sleep(self._valve_seconds + self._settle)
            self.result.base_lpm = await self._measure()

            for entity_id in self._rooms:
                self.step = entity_id
                await self._set_mode(entity_id, HVACMode.HEAT)
                await _async_call(
                    self._hass,
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
            # When Home Assistant stops, the thermostats may already be going away; the record
            # stays and the next start puts them back
            if not self.abandoned:
                remaining = await _async_restore(self._hass, saved)
                if self._store is not None:
                    if remaining:
                        await self._store.async_save({"rooms": remaining})
                    else:
                        await self._store.async_remove()

        return self.result

    async def _measure(self) -> float | None:
        samples: list[float] = []
        waited = 0.0
        while len(samples) < SAMPLES and waited < STEP_TIMEOUT_SECONDS:
            if (value := self._sample()) is not None:
                samples.append(value)
            await asyncio.sleep(self._poll)
            waited += max(self._poll, 1.0)
        return median(samples) if samples else None

    async def _set_mode(self, entity_id: str, mode: HVACMode) -> None:
        await _async_call(
            self._hass, SERVICE_SET_HVAC_MODE, {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: mode}
        )
