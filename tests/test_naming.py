"""Tests for entity and device naming."""

from typing import TYPE_CHECKING

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sat.const import (
    CONF_MODE,
    CONF_SIMULATED_COOLING,
    CONF_SIMULATED_HEATING,
    CONF_SIMULATED_WARMING_UP,
    DOMAIN,
    MODE_SIMULATOR,
)
from tests.const import DEFAULT_USER_DATA

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_entities_are_named_after_the_device(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Living Room", data=DEFAULT_USER_DATA)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device is not None
    assert device.name == "Living Room"
    assert device.area_id is None

    state = hass.states.get("climate.living_room")
    assert state is not None
    assert state.attributes["friendly_name"] == "Living Room"
    state = hass.states.get("sensor.living_room_heating_curve")
    assert state is not None
    assert state.attributes["friendly_name"] == "Living Room Heating curve"
    state = hass.states.get("sensor.living_room_boiler_status")
    assert state is not None
    assert state.attributes["friendly_name"] == "Living Room Boiler status"
    state = hass.states.get("binary_sensor.living_room_central_heating_synchro")
    assert state is not None
    assert state.attributes["friendly_name"] == "Living Room Central heating synchro"


async def test_simulator_entities_are_named_after_the_device(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room",
        data={
            **DEFAULT_USER_DATA,
            CONF_MODE: MODE_SIMULATOR,
            CONF_SIMULATED_HEATING: 20,
            CONF_SIMULATED_COOLING: 5,
            CONF_SIMULATED_WARMING_UP: "00:00:15",
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_setpoint")
    assert state is not None
    assert state.attributes["friendly_name"] == "Living Room Current setpoint (Boiler)"
    state = hass.states.get("sensor.test_boiler_temperature")
    assert state is not None
    assert state.attributes["friendly_name"] == "Living Room Current temperature (Boiler)"
    assert await hass.config_entries.async_unload(entry.entry_id)
