import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from pyotgw.vars import OTGW

from custom_components.sat.const import CONF_SIMULATION
from custom_components.sat.serial import SatSerialCoordinator
from custom_components.sat.serial.binary_sensor import BINARY_SENSOR_INFO
from custom_components.sat.serial.sensor import SENSOR_INFO
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


def test_every_serial_entity_has_a_translated_name() -> None:
    translations = Path(__file__).parents[1] / "custom_components/sat/translations/en.json"
    entity = json.loads(translations.read_text())["entity"]

    for domain, infos in (("sensor", SENSOR_INFO), ("binary_sensor", BINARY_SENSOR_INFO)):
        for key, info in infos.items():
            name = entity[domain][key]["name"]
            assert ("{source}" in name) is (info.status_sources != [OTGW]), key
