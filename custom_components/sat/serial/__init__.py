from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import TYPE_CHECKING, Any, override

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify
from pyotgw import OpenThermGateway
from pyotgw import messages as gw_messages
from pyotgw import vars as gw_vars
from pyotgw.vars import (
    BOILER,
    DATA_CH_WATER_PRESS,
    DATA_CH_WATER_TEMP,
    DATA_CONTROL_SETPOINT,
    DATA_DHW_SETPOINT,
    DATA_DHW_TEMP,
    DATA_EXHAUST_TEMP,
    DATA_MASTER_CH_ENABLED,
    DATA_REL_MOD_LEVEL,
    DATA_RETURN_WATER_TEMP,
    DATA_SLAVE_CH_MIN_SETP,
    DATA_SLAVE_DHW_ACTIVE,
    DATA_SLAVE_DHW_MAX_SETP,
    DATA_SLAVE_DHW_MIN_SETP,
    DATA_SLAVE_FAULT_IND,
    DATA_SLAVE_FLAME_ON,
    DATA_SLAVE_MAX_CAPACITY,
    DATA_SLAVE_MAX_RELATIVE_MOD,
    DATA_SLAVE_MEMBERID,
    DATA_SLAVE_MIN_MOD_LEVEL,
    DATA_SLAVE_OEM_FAULT,
    DEFAULT_STATUS,
)
from serial import SerialException

from ..const import DOMAIN
from ..coordinator import DeviceState, SatDataUpdateCoordinator
from .id_scan import FAULT_ID, UNKNOWN, OpenThermIdScan

if TYPE_CHECKING:
    import re
    from collections.abc import Callable, Mapping
    from datetime import datetime

    from homeassistant.core import HomeAssistant

    from ..pwm import PWMState

_LOGGER: logging.Logger = logging.getLogger(__name__)

# Primary heat exchanger temperature (OpenTherm 4.x data ID 34). Thermostats rarely ask for it, so
# the gateway is told to ask the boiler once a minute with a priority message (PM=34).
HEAT_EXCHANGER_MESSAGE_ID = 34
DATA_HEAT_EXCHANGER_TEMP = str(getattr(gw_vars, "DATA_HEATEXCH_TEMP", "heat_exchanger_temp"))
HEAT_EXCHANGER_POLL_SECONDS = 60.0
# A boiler that answers Unknown-DataId never gives a value; ask again only once an hour
HEAT_EXCHANGER_UNANSWERED_POLLS = 5
HEAT_EXCHANGER_RETRY_SECONDS = 3600.0


# Fan speed (OpenTherm 4.x data ID 35): setpoint and actual, in Hz. Gateways ask for it on
# their own, but pyotgw up to 2.2.3 drops the answer as well.
FAN_SPEED_MESSAGE_ID = 35
DATA_FAN_SPEED_SETPOINT = str(
    getattr(gw_vars, "DATA_BOILER_FANSPD_SETP", "boiler_fan_speed_setpoint")
)
DATA_FAN_SPEED = str(getattr(gw_vars, "DATA_BOILER_FANSPD", "boiler_fan_speed"))


def _register_message(message_id: int, actions: list[tuple[str, tuple[str, ...], str]]) -> bool:
    """Teach pyotgw to decode a boiler answer; newer releases that decode it are left alone."""
    key = bytes([message_id])
    try:
        registry = gw_messages.REGISTRY
        if key in registry:
            return False
        registry[key] = {
            gw_messages.M2S: [],
            gw_messages.S2M: [
                {
                    gw_messages.FUNC: function,
                    gw_messages.ARGS: arguments,
                    gw_messages.RETURNS: (returns,),
                }
                for function, arguments, returns in actions
            ],
        }
    except AttributeError, TypeError:  # pragma: no cover - a pyotgw with another layout
        _LOGGER.debug("Cannot register OpenTherm data ID %d with pyotgw", message_id, exc_info=True)
        return False

    return True


def register_heat_exchanger_message() -> bool:
    """Decode data ID 34; pyotgw versions up to 2.2.3 drop the boiler's answer."""
    return _register_message(
        HEAT_EXCHANGER_MESSAGE_ID, [("_get_f8_8", ("msb", "lsb"), DATA_HEAT_EXCHANGER_TEMP)]
    )


def register_fan_speed_message() -> bool:
    """Decode data ID 35: the fan speed setpoint in the high byte, the actual speed in the low."""
    return _register_message(
        FAN_SPEED_MESSAGE_ID,
        [
            ("_get_u8", ("msb",), DATA_FAN_SPEED_SETPOINT),
            ("_get_u8", ("lsb",), DATA_FAN_SPEED),
        ],
    )


register_heat_exchanger_message()
register_fan_speed_message()


# A flame lost early in a burn may leave a fault code for only seconds, and the thermostat asks
# for it about every 45 s, so SAT asks every 10 s from the ignition until a minute past the flame
FAULT_WATCH_INTERVAL_SECONDS = 10.0
FAULT_WATCH_BURN_SECONDS = 240.0
FAULT_WATCH_AFTER_FLAME_SECONDS = 60.0
FAULT_WATCH_MAXIMUM_SECONDS = 300.0


def id_scan_store(hass: HomeAssistant, port: str) -> Store[dict[str, Any]]:
    """Keep the last OpenTherm ID scan of the gateway on this port."""
    return Store(hass, 1, f"{DOMAIN}.serial.{slugify(port)}.opentherm_ids")


def message_processor(api: OpenThermGateway) -> Any:  # noqa: ANN401 - a private pyotgw object
    """Return pyotgw's message processor of the current connection, if there is one."""
    return getattr(getattr(api, "_protocol", None), "message_processor", None)


def listen_to_messages(
    api: OpenThermGateway, callback: Callable[[str, str], None]
) -> Callable[[], None] | None:
    """Pass each raw OpenTherm message to `callback(source, frame)`; return the undo, or None.

    pyotgw only hands out the values it decodes, so SAT taps its message processor.
    """
    processor = message_processor(api)
    submit = getattr(processor, "submit_matched_message", None)
    if processor is None or submit is None:
        return None

    def _submit(match: re.Match[str]) -> object:
        try:
            callback(match.group(1), match.group(2))
        except Exception:  # a listener must never break the gateway
            _LOGGER.debug("OpenTherm message listener failed", exc_info=True)
        return submit(match)

    processor.submit_matched_message = _submit

    def _undo() -> None:
        if getattr(processor, "submit_matched_message", None) is _submit:
            processor.submit_matched_message = submit

    return _undo


# Sensors
TRANSLATE_SOURCE = {
    gw_vars.OTGW: None,
    gw_vars.BOILER: "Boiler",
    gw_vars.THERMOSTAT: "Thermostat",
}


class SatSerialCoordinator(SatDataUpdateCoordinator):
    """Class to manage to fetch data from the OTGW Gateway using pyotgw."""

    def __init__(
        self,
        hass: HomeAssistant,
        port: str,
        config_data: Mapping[str, Any],
        options: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize."""
        super().__init__(hass, config_data, options)
        self.async_set_updated_data(DEFAULT_STATUS)

        self._port: str = port
        self._hass_loop = hass.loop
        self._api: OpenThermGateway = OpenThermGateway()

        async def _publish(data: dict[str, Any]) -> None:
            self._hass_loop.call_soon_threadsafe(self.async_set_updated_data, data)

        self._publish_callback = _publish
        self._api.subscribe(self._publish_callback)

        self._heat_exchanger_requested_at: float | None = None
        self._heat_exchanger_unanswered: int = 0
        self._heat_exchanger_reported: bool = False
        self._heat_exchanger_missing_logged: bool = False

        self.id_scan = OpenThermIdScan()
        self._id_scan_task: asyncio.Task[None] | None = None
        self._id_scan_store: Store[dict[str, Any]] | None = None
        self._listening_to: object | None = None
        self._fault_watch_task: asyncio.Task[None] | None = None
        self._stop_listening: Callable[[], None] | None = None

    @override
    @property
    def device_id(self) -> str:
        return self._port

    @property
    def simulation(self) -> bool:
        return self._simulation

    @override
    @property
    def device_type(self) -> str:
        return "OpenThermGateway (via serial)"

    @override
    @property
    def device_active(self) -> bool:
        return bool(self.get(DATA_MASTER_CH_ENABLED) or False)

    @override
    @property
    def hot_water_active(self) -> bool:
        return bool(self.get(DATA_SLAVE_DHW_ACTIVE) or False)

    @override
    @property
    def supports_setpoint_management(self) -> bool:
        return True

    @override
    @property
    def supports_hot_water_setpoint_management(self) -> bool:
        return True

    @override
    @property
    def supports_maximum_setpoint_management(self) -> bool:
        return True

    @override
    @property
    def supports_relative_modulation(self) -> bool:
        return True

    @override
    @property
    def setpoint(self) -> float | None:
        if (setpoint := self.get(DATA_CONTROL_SETPOINT)) is not None:
            return float(setpoint)

        return None

    @override
    @property
    def hot_water_setpoint(self) -> float | None:
        if (setpoint := self.get(DATA_DHW_SETPOINT)) is not None:
            return float(setpoint)

        return super().hot_water_setpoint

    @override
    @property
    def boiler_temperature(self) -> float | None:
        if (value := self.get(DATA_CH_WATER_TEMP)) is not None:
            return float(value)

        return super().boiler_temperature

    @override
    @property
    def return_temperature(self) -> float | None:
        if (value := self.get(DATA_RETURN_WATER_TEMP)) is not None:
            return float(value)

        return super().return_temperature

    @override
    @property
    def water_pressure(self) -> float | None:
        # Boilers without a pressure sensor report 0
        if (value := self.get(DATA_CH_WATER_PRESS)) is not None and value > 0:
            return float(value)

        return None

    @override
    @property
    def exhaust_temperature(self) -> float | None:
        if (value := self.get(DATA_EXHAUST_TEMP)) is not None and value > 0:
            return float(value)

        return None

    @override
    @property
    def heat_exchanger_temperature(self) -> float | None:
        if (value := self.get(DATA_HEAT_EXCHANGER_TEMP)) is not None:
            return float(value)

        return None

    @override
    @property
    def boiler_fault_reported(self) -> bool:
        return bool(self.get(DATA_SLAVE_FAULT_IND))

    @override
    @property
    def boiler_fault_code_reported(self) -> int | None:
        if (value := self.get(DATA_SLAVE_OEM_FAULT)) is not None and value > 0:
            return int(value)

        return None

    @override
    @property
    def hot_water_temperature(self) -> float | None:
        if (value := self.get(DATA_DHW_TEMP)) is not None and value > 0:
            return float(value)

        return None

    @override
    @property
    def minimum_hot_water_setpoint(self) -> float:
        if (setpoint := self.get(DATA_SLAVE_DHW_MIN_SETP)) is not None:
            return float(setpoint)

        return super().minimum_hot_water_setpoint

    @override
    @property
    def maximum_hot_water_setpoint(self) -> float:
        if (setpoint := self.get(DATA_SLAVE_DHW_MAX_SETP)) is not None:
            return float(setpoint)

        return super().maximum_hot_water_setpoint

    @override
    @property
    def relative_modulation_value(self) -> float | None:
        if (value := self.get(DATA_REL_MOD_LEVEL)) is not None:
            return float(value)

        return super().relative_modulation_value

    @override
    @property
    def boiler_capacity(self) -> float | None:
        if (value := self.get(DATA_SLAVE_MAX_CAPACITY)) is not None:
            return float(value)

        return super().boiler_capacity

    @override
    @property
    def minimum_heating_setpoint(self) -> float | None:
        if (value := self.get(DATA_SLAVE_CH_MIN_SETP)) is not None and value > 0:
            return float(value)

        return None

    @override
    @property
    def minimum_relative_modulation_value(self) -> float | None:
        if (value := self.get(DATA_SLAVE_MIN_MOD_LEVEL)) is not None:
            return float(value)

        return super().minimum_relative_modulation_value

    @override
    @property
    def maximum_relative_modulation_value(self) -> float | None:
        if (value := self.get(DATA_SLAVE_MAX_RELATIVE_MOD)) is not None:
            return float(value)

        return super().maximum_relative_modulation_value

    @override
    @property
    def member_id(self) -> int | None:
        if (value := self.get(DATA_SLAVE_MEMBERID)) is not None:
            return int(value)

        return None

    @override
    @property
    def flame_active(self) -> bool:
        return bool(self.get(DATA_SLAVE_FLAME_ON))

    def get(self, key: str) -> float | None:
        """Get the value for the given `key` from the boiler data."""
        value = self.data[BOILER].get(key)
        return value if isinstance(value, float | int) else None

    async def async_connect(self) -> SatSerialCoordinator:
        try:
            await self._api.connect(port=self._port, timeout=5)
        except (TimeoutError, ConnectionError, SerialException) as exception:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="serial_connect_failed",
                translation_placeholders={"port": self._port, "error": str(exception)},
            ) from exception

        return self

    @override
    async def async_setup(self) -> None:
        await self.async_connect()

        self._id_scan_store = id_scan_store(self.hass, self._port)
        try:
            if (data := await self._id_scan_store.async_load()) is not None:
                self.id_scan.load(data)
        except Exception:  # an unreadable scan only means asking again
            _LOGGER.debug("Cannot load the last OpenTherm ID scan", exc_info=True)

        self._ensure_listening()

    def _ensure_listening(self) -> bool:
        """Listen to the raw messages of the current connection; a reconnect brings a new one."""
        if self._simulation:
            return False

        processor = message_processor(self._api)
        if processor is None:
            return False
        if processor is self._listening_to:
            return True

        if self._stop_listening is not None:
            self._stop_listening()
        self._stop_listening = listen_to_messages(self._api, self._on_message)
        self._listening_to = processor if self._stop_listening is not None else None
        return self._stop_listening is not None

    def _on_message(self, source: str, frame: str) -> None:
        """Keep the boiler's answers, its parameters among them, as the messages pass."""
        parameters = dict(self.id_scan.parameters)
        faults = len(self.id_scan.fault_events)
        flame = self.id_scan.flame
        self.id_scan.observe(source, frame)

        if flame is False and self.id_scan.flame is True:
            self._hass_loop.call_soon_threadsafe(self._start_fault_watch)
        if (
            self.id_scan.parameters != parameters or len(self.id_scan.fault_events) != faults
        ) and self._id_scan_store is not None:
            self._hass_loop.call_soon_threadsafe(self._schedule_id_scan_save)

    def _start_fault_watch(self) -> None:
        if self._simulation or (
            self._fault_watch_task is not None and not self._fault_watch_task.done()
        ):
            return
        self._fault_watch_task = self.hass.async_create_background_task(
            self._async_watch_faults(), "SAT boiler fault watch"
        )

    async def _async_watch_faults(
        self,
        interval: float = FAULT_WATCH_INTERVAL_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Ask for the fault code (ID 5) often while a burn starts, when flames get lost."""
        started = clock()
        flame_off_at: float | None = None
        while True:
            try:
                await self._api.send_transparent_command(
                    gw_vars.OTGW_CMD_PRIO_MSG, str(FAULT_ID), timeout=2
                )
            except Exception:  # a lost request must not end the watch
                _LOGGER.debug("Requesting OpenTherm ID 5 failed", exc_info=True)
            await asyncio.sleep(interval)

            now = clock()
            if self.id_scan.flame is True:
                flame_off_at = None
            elif flame_off_at is None:
                flame_off_at = now

            elapsed = now - started
            if elapsed >= FAULT_WATCH_MAXIMUM_SECONDS:
                return
            if elapsed >= FAULT_WATCH_BURN_SECONDS and (
                flame_off_at is None or now - flame_off_at >= FAULT_WATCH_AFTER_FLAME_SECONDS
            ):
                return

    def _schedule_id_scan_save(self) -> None:
        if self._id_scan_store is not None:
            self._id_scan_store.async_delay_save(self.id_scan.to_dict, 60)

    def async_start_id_scan(self) -> bool:
        """Start asking the boiler for every OpenTherm ID; False when one is already running."""
        if self._simulation or self.id_scan.running:
            return False

        self._id_scan_task = self.hass.async_create_background_task(
            self._async_scan_ids(), "SAT OpenTherm ID scan"
        )
        return True

    async def _async_scan_ids(self) -> None:
        """Ask the boiler once for every readable OpenTherm ID and keep its answers."""
        if not self._ensure_listening():
            _LOGGER.warning("Cannot listen to the gateway's messages; the ID scan is not possible")
            return

        async def _ask(data_id: int) -> None:
            await self._api.send_transparent_command(
                gw_vars.OTGW_CMD_PRIO_MSG, str(data_id), timeout=2
            )

        _LOGGER.info("Scanning the OpenTherm IDs of the boiler; this takes about 10 minutes")
        self.id_scan.running = True
        self.async_update_listeners()
        try:
            await self.id_scan.async_run(_ask)
        finally:
            self.async_update_listeners()

        if self._id_scan_store is not None:
            await self._id_scan_store.async_save(self.id_scan.to_dict())

    @override
    async def async_will_remove_from_hass(self) -> None:
        if self._id_scan_task is not None:
            self._id_scan_task.cancel()
            self._id_scan_task = None

        if self._fault_watch_task is not None:
            self._fault_watch_task.cancel()
            self._fault_watch_task = None

        if self._stop_listening is not None:
            self._stop_listening()
            self._stop_listening = None
            self._listening_to = None

        if self._publish_callback is not None:
            try:
                self._api.unsubscribe(self._publish_callback)
            except Exception:  # pragma: no cover - best effort cleanup
                _LOGGER.debug("Failed to unsubscribe serial listener", exc_info=True)
            finally:
                self._publish_callback = None

        await self._graceful_disconnect()

        await super().async_will_remove_from_hass()

    @override
    async def async_control_heating_loop(
        self, pwm_state: PWMState | None = None, _time: datetime | None = None
    ) -> None:
        await super().async_control_heating_loop(pwm_state, _time)
        self._ensure_listening()
        await self._async_request_heat_exchanger_temperature()

    async def _async_request_heat_exchanger_temperature(self, now: float | None = None) -> None:
        """Ask the boiler for data ID 34 through the gateway, at most once a minute."""
        # The scan asks for it as well, and an Unknown-DataId answer settles it for good
        if (
            self._simulation
            or self.id_scan.running
            or self.id_scan.answer(HEAT_EXCHANGER_MESSAGE_ID) == UNKNOWN
        ):
            return

        now = monotonic() if now is None else now
        answered = self.heat_exchanger_temperature is not None
        if answered:
            self._heat_exchanger_unanswered = 0
            if not self._heat_exchanger_reported:
                self._heat_exchanger_reported = True
                _LOGGER.info(
                    "The boiler reports its heat exchanger temperature (OpenTherm ID 34): %.1f °C",
                    self.heat_exchanger_temperature,
                )

        since_request = (
            None
            if self._heat_exchanger_requested_at is None
            else now - self._heat_exchanger_requested_at
        )
        interval = HEAT_EXCHANGER_POLL_SECONDS
        if not answered and self._heat_exchanger_unanswered >= HEAT_EXCHANGER_UNANSWERED_POLLS:
            interval = HEAT_EXCHANGER_RETRY_SECONDS
            if (
                not self._heat_exchanger_missing_logged
                and since_request is not None
                and since_request >= HEAT_EXCHANGER_POLL_SECONDS
            ):
                self._heat_exchanger_missing_logged = True
                _LOGGER.info(
                    "The boiler did not answer OpenTherm ID 34 (heat exchanger temperature) "
                    "%d times, most likely Unknown-DataId; asking once an hour from now on",
                    HEAT_EXCHANGER_UNANSWERED_POLLS,
                )
        if since_request is not None and since_request < interval:
            return

        if not answered:
            self._heat_exchanger_unanswered += 1

        self._heat_exchanger_requested_at = now
        try:
            await self._api.send_transparent_command(
                gw_vars.OTGW_CMD_PRIO_MSG, str(HEAT_EXCHANGER_MESSAGE_ID), timeout=2
            )
        except Exception:  # a lost request must not stop the control loop
            _LOGGER.debug("Requesting OpenTherm ID 34 failed", exc_info=True)

    @override
    async def async_set_control_setpoint(self, value: float) -> None:
        if not self._simulation:
            await self._api.set_control_setpoint(value)

        await super().async_set_control_setpoint(value)

    @override
    async def async_set_control_hot_water_setpoint(self, value: float) -> None:
        if not self._simulation:
            await self._api.set_dhw_setpoint(value)

        await super().async_set_control_hot_water_setpoint(value)

    @override
    async def async_set_control_thermostat_setpoint(self, value: float) -> None:
        if not self._simulation:
            await self._api.set_target_temp(value)

        await super().async_set_control_thermostat_setpoint(value)

    @override
    async def async_set_heater_state(self, state: DeviceState) -> None:
        if not self._simulation:
            await self._api.set_ch_enable_bit(1 if state == DeviceState.ON else 0)

        await super().async_set_heater_state(state)

    @override
    async def async_release_control(self) -> None:
        if not self._simulation:
            await self._api.set_control_setpoint(0)
            await self._api.set_max_relative_mod("-")

        await super().async_release_control()

    @override
    async def async_set_control_max_relative_modulation(self, value: int) -> None:
        if not self._simulation:
            await self._api.set_max_relative_mod(value)

        await super().async_set_control_max_relative_modulation(value)

    @override
    async def async_set_control_max_setpoint(self, value: float) -> None:
        if not self._simulation:
            await self._api.set_max_ch_setpoint(value)

        await super().async_set_control_max_setpoint(value)

    async def _graceful_disconnect(self) -> None:
        if not self._simulation:
            try:
                await self._api.set_control_setpoint(0)
                await self._api.set_max_relative_mod("-")
            except Exception:  # pragma: no cover - best effort cleanup
                _LOGGER.debug(
                    "Failed to reset serial gateway state before disconnect", exc_info=True
                )

        try:
            await self._api.disconnect()
        except Exception:  # pragma: no cover - best effort cleanup
            _LOGGER.debug("Error while disconnecting serial gateway", exc_info=True)
