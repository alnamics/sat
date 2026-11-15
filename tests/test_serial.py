from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from pyotgw.vars import (
    BOILER,
    DATA_CONTROL_SETPOINT,
    DATA_SLAVE_FLAME_ON,
    OTGW,
    OTGW_ABOUT,
    THERMOSTAT,
)
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sat.const import (
    CONF_DEVICE,
    CONF_MODE,
    CONF_SIMULATION,
    DOMAIN,
    MODE_SERIAL,
)
from custom_components.sat.serial import SatSerialCoordinator
from tests.const import DEFAULT_USER_DATA

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_unload_in_simulation_sends_nothing_to_the_gateway(hass: HomeAssistant) -> None:
    with patch("custom_components.sat.serial.OpenThermGateway") as gateway:
        api = gateway.return_value
        api.set_control_setpoint = AsyncMock()
        api.set_max_relative_mod = AsyncMock()
        api.disconnect = AsyncMock()
        coordinator = SatSerialCoordinator(
            hass, "socket://otgw:25238", DEFAULT_USER_DATA, {CONF_SIMULATION: True}
        )

        await coordinator.async_will_remove_from_hass()

    api.set_control_setpoint.assert_not_awaited()
    api.set_max_relative_mod.assert_not_awaited()
    api.disconnect.assert_awaited_once()


async def test_serial_entities_are_named_after_the_device(hass: HomeAssistant) -> None:
    status = {
        BOILER: {DATA_CONTROL_SETPOINT: 40.0, DATA_SLAVE_FLAME_ON: True},
        OTGW: {OTGW_ABOUT: "OpenTherm Gateway 6.5"},
        THERMOSTAT: {},
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room",
        data={**DEFAULT_USER_DATA, CONF_MODE: MODE_SERIAL, CONF_DEVICE: "socket://otgw:25238"},
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.sat.serial.DEFAULT_STATUS", status),
        patch("custom_components.sat.serial.OpenThermGateway", autospec=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    names = {
        "sensor.test_boiler_control_setpoint": "Living Room Control setpoint (Boiler)",
        "sensor.test_gateway_otgw_about": "Living Room Gateway firmware version",
        "binary_sensor.test_boiler_slave_flame_on": "Living Room Boiler flame (Boiler)",
    }
    for entity_id, name in names.items():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.attributes["friendly_name"] == name
