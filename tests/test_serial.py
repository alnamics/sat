import re
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import entity_registry as er
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
    DATA_FAN_SPEED,
    DATA_FAN_SPEED_SETPOINT,
    DATA_HEAT_EXCHANGER_TEMP,
    HEAT_EXCHANGER_RETRY_SECONDS,
    HEAT_EXCHANGER_UNANSWERED_POLLS,
    SatSerialCoordinator,
    listen_to_messages,
    register_fan_speed_message,
    register_heat_exchanger_message,
)
from custom_components.sat.serial.id_scan import (
    INVALID,
    NO_ANSWER,
    SUPPORTED,
    UNKNOWN,
    OpenThermIdScan,
)
from tests.const import DEFAULT_USER_DATA

if TYPE_CHECKING:
    import pytest
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

    ids = hass.states.get("sensor.test_opentherm_ids")
    assert ids is not None
    assert ids.attributes["scan"] == "not_run"

    # The scan only runs on request
    registry = er.async_get(hass)
    button = registry.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}-scan-opentherm-ids")
    assert button is not None
    assert hass.states.get(button) is not None


async def test_the_id_scan_records_each_kind_of_answer() -> None:
    scan = OpenThermIdScan(ids=(34, 35, 36, 113, 25))
    asked: list[int] = []

    async def _ask(data_id: int) -> None:
        asked.append(data_id)
        answers = {34: "F0220000", 35: "C0233A00", 36: "E0240000"}
        if (frame := answers.get(data_id)) is not None:
            scan.observe("R", f"00{data_id:02X}0000")
            scan.observe("B", frame)
        # The thermostat's own traffic counts as well, so ID 25 is not asked
        scan.observe("T", "00190000")
        scan.observe("B", "40192F80")

    await scan.async_run(_ask, answer_seconds=0.01, pause=0)

    assert scan.finished
    assert asked == [34, 35, 36, 113]
    assert scan.ids(SUPPORTED) == [25, 35]
    assert scan.ids(INVALID) == [36]
    assert scan.ids(UNKNOWN) == [34]
    assert scan.ids(NO_ANSWER) == [113]
    assert scan.supported()["35 Fan speed (setpoint / actual)"].startswith("3A00 (")
    assert "hb 58, lb 0" in scan.supported()["35 Fan speed (setpoint / actual)"]
    assert "f8.8 47.50" in scan.supported()["25 Boiler water temperature"]


async def test_the_id_scan_collects_the_boiler_parameters() -> None:
    scan = OpenThermIdScan(ids=(10, 11))
    asked: list[int] = []

    async def _ask(data_id: int) -> None:
        asked.append(data_id)
        if data_id == 10:
            # Three parameters; the gateway then reads them one by one
            scan.observe("B", "C00A0300")
            for frame in ("C00B0007", "C00B0150", "C00B0201"):
                scan.observe("B", frame)

    # A count already seen in the traffic is asked again, as only the answer to the gateway's
    # own request makes it read the parameters
    scan.observe("B", "C00A0300")
    await scan.async_run(_ask, answer_seconds=0.01, pause=0, parameter_settle_seconds=0)

    assert asked == [10]
    assert scan.parameter_count == 3
    assert scan.parameters == {0: 7, 1: 80, 2: 1}

    restored = OpenThermIdScan()
    restored.load(scan.to_dict())
    assert restored.parameters == scan.parameters
    assert restored.parameter_count == 3
    assert restored.answer(11) == SUPPORTED
    assert restored.finished


def test_a_damaged_scan_is_left_out() -> None:
    scan = OpenThermIdScan()
    scan.load({"answers": {"x": ["supported", "0000"], "34": "unknown"}, "parameters": {"1": "a"}})

    assert scan.answers == {}
    assert scan.parameters == {}
    assert not scan.finished


async def test_the_id_scan_never_asks_for_the_thermostat_status() -> None:
    asked: list[int] = []

    async def _ask(data_id: int) -> None:
        asked.append(data_id)

    await OpenThermIdScan().async_run(_ask, answer_seconds=0.001, pause=0)

    assert asked
    assert not set(asked) & {0, 1, 2, 4, 7, 8, 14, 16, 24, 70, 101}


def test_listening_to_messages_taps_pyotgw_and_undoes_it() -> None:
    seen: list[tuple[str, str]] = []
    submitted: list[str] = []

    class _Processor:
        def submit_matched_message(self, match: re.Match[str]) -> None:
            submitted.append(match.group(0))

    api = MagicMock()
    api._protocol.message_processor = processor = _Processor()

    undo = listen_to_messages(api, lambda source, frame: seen.append((source, frame)))
    assert undo is not None
    match = re.match(r"^(T|B|R|A|E)([0-9A-F]{8})$", "BF0220000")
    assert match is not None
    processor.submit_matched_message(match)
    undo()
    processor.submit_matched_message(match)

    assert seen == [("B", "F0220000")]
    assert submitted == ["BF0220000", "BF0220000"]


async def test_an_unknown_heat_exchanger_id_is_not_asked_again(hass: HomeAssistant) -> None:
    coordinator, api = _coordinator(hass)
    coordinator.id_scan.observe("B", "F0220000")

    await coordinator._async_request_heat_exchanger_temperature(now=0.0)

    api.send_transparent_command.assert_not_awaited()
    await coordinator.async_will_remove_from_hass()


async def test_the_scan_asks_the_gateway_with_priority_messages(hass: HomeAssistant) -> None:
    coordinator, api = _coordinator(hass)
    coordinator.id_scan = OpenThermIdScan(ids=(35,))

    async def _answer(*_args: object, **_kwargs: object) -> str:
        coordinator.id_scan.observe("B", "C0233A00")
        return "35"

    api.send_transparent_command.side_effect = _answer
    with patch.object(coordinator, "_ensure_listening", return_value=True):
        await coordinator._async_scan_ids()

    api.send_transparent_command.assert_awaited_once_with("PM", "35", timeout=2)
    assert coordinator.id_scan.ids(SUPPORTED) == [35]
    assert not coordinator.id_scan.running
    await coordinator.async_will_remove_from_hass()


async def test_simulation_does_not_scan(hass: HomeAssistant) -> None:
    coordinator, api = _coordinator(hass, {CONF_SIMULATION: True})

    assert coordinator.async_start_id_scan() is False
    api.send_transparent_command.assert_not_awaited()
    await coordinator.async_will_remove_from_hass()


async def test_pyotgw_decodes_the_fan_speed() -> None:
    assert register_fan_speed_message() is False

    status_manager = MagicMock()
    processor = MessageProcessor(MagicMock(), status_manager)
    try:
        # Read-Ack for data ID 35: setpoint 58 Hz, actual 41 Hz
        await processor._process_msg(("B", gw_vars.READ_ACK, b"\x23", b"\x3a", b"\x29"))
    finally:
        await processor.cleanup()

    status_manager.submit_partial_update.assert_called_once_with(
        BOILER, {DATA_FAN_SPEED_SETPOINT: 58, DATA_FAN_SPEED: 41}
    )


async def test_the_boiler_parameters_are_heard_as_the_thermostat_reads_them(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    class _Processor:
        def submit_matched_message(self, match: re.Match[str]) -> None:
            pass

    coordinator, api = _coordinator(hass)
    api._protocol.message_processor = processor = _Processor()
    assert coordinator._ensure_listening()

    def _send(line: str) -> None:
        match = re.match(r"^(T|B|R|A|E)([0-9A-F]{8})$", line)
        assert match is not None
        processor.submit_matched_message(match)

    # The thermostat reads parameter 12, then writes 10 to it
    _send("T000B0C00")
    _send("BC00B0C07")
    assert coordinator.id_scan.parameters == {12: 7}
    with patch("custom_components.sat.serial.persistent_notification.async_create") as notify:
        _send("T900B0C0A")
        _send("BD00B0C0A")
        await hass.async_block_till_done()
    assert coordinator.id_scan.parameters == {12: 10}
    assert "Boiler parameter 12 (OpenTherm TSP) changed: 7 -> 10" in caplog.text
    assert coordinator.id_scan.parameter_changes[-1]["old"] == 7
    assert coordinator.id_scan.parameter_changes[-1]["new"] == 10
    notify.assert_called_once()
    assert "12" in notify.call_args.args[1]

    # A reconnect brings a new processor, which is tapped on the next check
    api._protocol.message_processor = second = _Processor()
    assert coordinator._ensure_listening()
    match = re.match(r"^(T|B|R|A|E)([0-9A-F]{8})$", "BC00B0D01")
    assert match is not None
    second.submit_matched_message(match)
    assert coordinator.id_scan.parameters == {12: 10, 13: 1}

    await coordinator.async_will_remove_from_hass()


def test_each_boiler_fault_is_kept_once() -> None:
    scan = OpenThermIdScan()
    for frame in ("C0050000", "C0050880", "C0050880", "C0050000", "C0050881"):
        scan.observe("B", frame)

    assert [(event["code"], event["flags"]) for event in scan.fault_events] == [
        (128, "0x08"),
        (129, "0x08"),
    ]

    restored = OpenThermIdScan()
    restored.load(scan.to_dict())
    assert restored.fault_events == scan.fault_events


async def test_a_burn_start_is_watched_for_faults(hass: HomeAssistant) -> None:
    coordinator, api = _coordinator(hass)

    with patch.object(coordinator, "_start_fault_watch") as start:
        coordinator._on_message("B", "40000000")
        coordinator._on_message("B", "40000008")
        await hass.async_block_till_done()
    start.assert_called_once()

    # The flame went out before the watch began: it asks until four minutes have passed
    coordinator.id_scan.flame = False
    times = iter(range(0, 1000, 10))
    await coordinator._async_watch_faults(interval=0, clock=lambda: float(next(times)))

    assert api.send_transparent_command.await_count == 24
    api.send_transparent_command.assert_awaited_with("PM", "5", timeout=2)
    await coordinator.async_will_remove_from_hass()
