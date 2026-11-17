from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

from pyotgw import vars as gw_vars
from pyotgw.messageprocessor import MessageProcessor
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
from custom_components.sat.serial import (
    DATA_HEAT_EXCHANGER_TEMP,
    HEAT_EXCHANGER_RETRY_SECONDS,
    HEAT_EXCHANGER_UNANSWERED_POLLS,
    SatSerialCoordinator,
    register_heat_exchanger_message,
)
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


def _status(boiler: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {BOILER: boiler, OTGW: {}, THERMOSTAT: {}}


async def test_pyotgw_decodes_the_heat_exchanger_temperature() -> None:
    # Registering again leaves the entry alone
    assert register_heat_exchanger_message() is False

    status_manager = MagicMock()
    processor = MessageProcessor(MagicMock(), status_manager)
    try:
        # Read-Ack from the boiler for data ID 34: 0x2A80 = 42.5 °C
        await processor._process_msg(("B", gw_vars.READ_ACK, b"\x22", b"\x2a", b"\x80"))
    finally:
        await processor.cleanup()

    status_manager.submit_partial_update.assert_called_once_with(
        BOILER, {DATA_HEAT_EXCHANGER_TEMP: 42.5}
    )


def _coordinator(
    hass: HomeAssistant,
    options: dict[str, Any] | None = None,
    command: AsyncMock | None = None,
) -> tuple[SatSerialCoordinator, MagicMock]:
    api = MagicMock()
    api.set_control_setpoint = AsyncMock()
    api.set_max_relative_mod = AsyncMock()
    api.disconnect = AsyncMock()
    api.send_transparent_command = command or AsyncMock()
    with patch("custom_components.sat.serial.OpenThermGateway", return_value=api):
        coordinator = SatSerialCoordinator(hass, "socket://otgw:25238", DEFAULT_USER_DATA, options)

    return coordinator, api


async def test_the_gateway_asks_for_the_heat_exchanger_once_a_minute(hass: HomeAssistant) -> None:
    coordinator, api = _coordinator(hass, command=AsyncMock(return_value="34"))

    assert coordinator.heat_exchanger_temperature is None

    await coordinator._async_request_heat_exchanger_temperature(now=1000.0)
    api.send_transparent_command.assert_awaited_once_with("PM", "34", timeout=2)

    await coordinator._async_request_heat_exchanger_temperature(now=1030.0)
    assert api.send_transparent_command.await_count == 1

    coordinator.async_set_updated_data(_status({DATA_HEAT_EXCHANGER_TEMP: 41.25}))
    assert coordinator.heat_exchanger_temperature == 41.25

    await coordinator._async_request_heat_exchanger_temperature(now=1060.0)
    assert api.send_transparent_command.await_count == 2

    await coordinator.async_will_remove_from_hass()


async def test_an_unanswered_heat_exchanger_request_backs_off(hass: HomeAssistant) -> None:
    coordinator, api = _coordinator(hass, command=AsyncMock(side_effect=TimeoutError))

    now = 0.0
    for _ in range(HEAT_EXCHANGER_UNANSWERED_POLLS + 3):
        await coordinator._async_request_heat_exchanger_temperature(now=now)
        now += 60.0
    assert api.send_transparent_command.await_count == HEAT_EXCHANGER_UNANSWERED_POLLS

    last = (HEAT_EXCHANGER_UNANSWERED_POLLS - 1) * 60.0
    await coordinator._async_request_heat_exchanger_temperature(
        now=last + HEAT_EXCHANGER_RETRY_SECONDS
    )
    assert api.send_transparent_command.await_count == HEAT_EXCHANGER_UNANSWERED_POLLS + 1

    await coordinator.async_will_remove_from_hass()


async def test_simulation_does_not_ask_for_the_heat_exchanger(hass: HomeAssistant) -> None:
    coordinator, api = _coordinator(hass, {CONF_SIMULATION: True})

    await coordinator._async_request_heat_exchanger_temperature(now=0.0)
    api.send_transparent_command.assert_not_awaited()

    await coordinator.async_will_remove_from_hass()


async def test_the_heat_exchanger_sensor_appears_with_its_first_value(hass: HomeAssistant) -> None:
    status = _status({DATA_CONTROL_SETPOINT: 40.0})
    status[OTGW] = {OTGW_ABOUT: "OpenTherm Gateway 6.8"}
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

    entity_id = "sensor.test_boiler_heat_exchanger_temp"
    assert hass.states.get(entity_id) is None

    coordinator = entry.runtime_data.coordinator
    coordinator.async_set_updated_data(
        {**status, BOILER: {DATA_CONTROL_SETPOINT: 40.0, DATA_HEAT_EXCHANGER_TEMP: 38.5}}
    )
    await coordinator.async_notify_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "38.5"
    assert state.attributes["friendly_name"] == "Living Room Heat exchanger temperature (Boiler)"
