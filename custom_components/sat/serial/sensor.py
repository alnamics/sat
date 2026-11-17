"""Sensor platform for SAT."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from homeassistant.components import sensor
from homeassistant.const import (
    EntityCategory,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfRatio,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import async_generate_entity_id
from pyotgw.vars import (
    BOILER,
    DATA_CH_PUMP_HOURS,
    DATA_CH_PUMP_STARTS,
    DATA_CH_WATER_PRESS,
    DATA_CH_WATER_TEMP,
    DATA_CH_WATER_TEMP_2,
    DATA_CONTROL_SETPOINT,
    DATA_CONTROL_SETPOINT_2,
    DATA_COOLING_CONTROL,
    DATA_DHW_BURNER_HOURS,
    DATA_DHW_BURNER_STARTS,
    DATA_DHW_FLOW_RATE,
    DATA_DHW_PUMP_HOURS,
    DATA_DHW_PUMP_STARTS,
    DATA_DHW_TEMP,
    DATA_DHW_TEMP_2,
    DATA_EXHAUST_TEMP,
    DATA_MASTER_MEMBERID,
    DATA_MASTER_OT_VERSION,
    DATA_MASTER_PRODUCT_TYPE,
    DATA_MASTER_PRODUCT_VERSION,
    DATA_MAX_CH_SETPOINT,
    DATA_OEM_DIAG,
    DATA_OUTSIDE_TEMP,
    DATA_REL_MOD_LEVEL,
    DATA_RETURN_WATER_TEMP,
    DATA_ROOM_SETPOINT,
    DATA_ROOM_SETPOINT_2,
    DATA_ROOM_SETPOINT_OVRD,
    DATA_ROOM_TEMP,
    DATA_SLAVE_CH_MAX_SETP,
    DATA_SLAVE_CH_MIN_SETP,
    DATA_SLAVE_DHW_MAX_SETP,
    DATA_SLAVE_DHW_MIN_SETP,
    DATA_SLAVE_MAX_CAPACITY,
    DATA_SLAVE_MAX_RELATIVE_MOD,
    DATA_SLAVE_MEMBERID,
    DATA_SLAVE_MIN_MOD_LEVEL,
    DATA_SLAVE_OEM_FAULT,
    DATA_SLAVE_OT_VERSION,
    DATA_SLAVE_PRODUCT_TYPE,
    DATA_SLAVE_PRODUCT_VERSION,
    DATA_SOLAR_COLL_TEMP,
    DATA_SOLAR_STORAGE_TEMP,
    DATA_TOTAL_BURNER_HOURS,
    DATA_TOTAL_BURNER_STARTS,
    OTGW,
    OTGW_ABOUT,
    OTGW_BUILD,
    OTGW_DHW_OVRD,
    OTGW_MODE,
    OTGW_SB_TEMP,
    OTGW_SETP_OVRD_MODE,
    OTGW_SMART_PWR,
    OTGW_THRM_DETECT,
    OTGW_VREF,
    THERMOSTAT,
)

from ..const import (
    CONF_NAME,
)
from ..entity import SatEntity
from . import (
    DATA_FAN_SPEED,
    DATA_FAN_SPEED_SETPOINT,
    DATA_HEAT_EXCHANGER_TEMP,
    TRANSLATE_SOURCE,
)
from .id_scan import INVALID, NO_ANSWER, SUPPORTED, UNKNOWN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .. import SatConfigEntry
    from . import SatSerialCoordinator

_LOGGER = logging.getLogger(__name__)


class SatSensorInfo:
    def __init__(
        self,
        device_class: sensor.SensorDeviceClass | None,
        unit: str | None,
        status_sources: list[str],
    ) -> None:
        self.unit = unit
        self.device_class = device_class
        self.status_sources = status_sources


SENSOR_INFO: dict[str, SatSensorInfo] = {
    DATA_CONTROL_SETPOINT: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_MASTER_MEMBERID: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_SLAVE_MEMBERID: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_SLAVE_OEM_FAULT: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_COOLING_CONTROL: SatSensorInfo(None, UnitOfRatio.PERCENTAGE, [BOILER, THERMOSTAT]),
    DATA_CONTROL_SETPOINT_2: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_ROOM_SETPOINT_OVRD: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_SLAVE_MAX_RELATIVE_MOD: SatSensorInfo(None, UnitOfRatio.PERCENTAGE, [BOILER, THERMOSTAT]),
    DATA_SLAVE_MAX_CAPACITY: SatSensorInfo(
        sensor.SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
        [BOILER, THERMOSTAT],
    ),
    DATA_SLAVE_MIN_MOD_LEVEL: SatSensorInfo(None, UnitOfRatio.PERCENTAGE, [BOILER, THERMOSTAT]),
    DATA_ROOM_SETPOINT: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_REL_MOD_LEVEL: SatSensorInfo(
        None,
        UnitOfRatio.PERCENTAGE,
        [BOILER, THERMOSTAT],
    ),
    DATA_CH_WATER_PRESS: SatSensorInfo(
        sensor.SensorDeviceClass.PRESSURE,
        UnitOfPressure.BAR,
        [BOILER, THERMOSTAT],
    ),
    DATA_DHW_FLOW_RATE: SatSensorInfo(
        None,
        f"{UnitOfVolume.LITERS}/{UnitOfTime.MINUTES}",
        [BOILER, THERMOSTAT],
    ),
    DATA_ROOM_SETPOINT_2: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_ROOM_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_CH_WATER_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_DHW_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_OUTSIDE_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_RETURN_WATER_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_SOLAR_STORAGE_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_SOLAR_COLL_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_CH_WATER_TEMP_2: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_DHW_TEMP_2: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_EXHAUST_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_FAN_SPEED_SETPOINT: SatSensorInfo(
        sensor.SensorDeviceClass.FREQUENCY,
        UnitOfFrequency.HERTZ,
        [BOILER],
    ),
    DATA_FAN_SPEED: SatSensorInfo(
        sensor.SensorDeviceClass.FREQUENCY,
        UnitOfFrequency.HERTZ,
        [BOILER],
    ),
    DATA_HEAT_EXCHANGER_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER],
    ),
    DATA_SLAVE_DHW_MAX_SETP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_SLAVE_DHW_MIN_SETP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_SLAVE_CH_MAX_SETP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_SLAVE_CH_MIN_SETP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_MAX_CH_SETPOINT: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [BOILER, THERMOSTAT],
    ),
    DATA_OEM_DIAG: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_TOTAL_BURNER_STARTS: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_CH_PUMP_STARTS: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_DHW_PUMP_STARTS: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_DHW_BURNER_STARTS: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_TOTAL_BURNER_HOURS: SatSensorInfo(
        sensor.SensorDeviceClass.DURATION,
        UnitOfTime.HOURS,
        [BOILER, THERMOSTAT],
    ),
    DATA_CH_PUMP_HOURS: SatSensorInfo(
        sensor.SensorDeviceClass.DURATION,
        UnitOfTime.HOURS,
        [BOILER, THERMOSTAT],
    ),
    DATA_DHW_PUMP_HOURS: SatSensorInfo(
        sensor.SensorDeviceClass.DURATION,
        UnitOfTime.HOURS,
        [BOILER, THERMOSTAT],
    ),
    DATA_DHW_BURNER_HOURS: SatSensorInfo(
        sensor.SensorDeviceClass.DURATION,
        UnitOfTime.HOURS,
        [BOILER, THERMOSTAT],
    ),
    DATA_MASTER_OT_VERSION: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_SLAVE_OT_VERSION: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_MASTER_PRODUCT_TYPE: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_MASTER_PRODUCT_VERSION: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_SLAVE_PRODUCT_TYPE: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    DATA_SLAVE_PRODUCT_VERSION: SatSensorInfo(None, None, [BOILER, THERMOSTAT]),
    OTGW_MODE: SatSensorInfo(None, None, [OTGW]),
    OTGW_DHW_OVRD: SatSensorInfo(None, None, [OTGW]),
    OTGW_ABOUT: SatSensorInfo(None, None, [OTGW]),
    OTGW_BUILD: SatSensorInfo(None, None, [OTGW]),
    OTGW_SB_TEMP: SatSensorInfo(
        sensor.SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        [OTGW],
    ),
    OTGW_SETP_OVRD_MODE: SatSensorInfo(None, None, [OTGW]),
    OTGW_SMART_PWR: SatSensorInfo(None, None, [OTGW]),
    OTGW_THRM_DETECT: SatSensorInfo(None, None, [OTGW]),
    OTGW_VREF: SatSensorInfo(None, None, [OTGW]),
}


async def async_setup_entry(
    coordinator: SatSerialCoordinator,
    config_entry: SatConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    has_thermostat = coordinator.data[OTGW].get(OTGW_THRM_DETECT) != "D"
    added: set[tuple[str, str]] = set()

    @callback
    def _add_reported_sensors() -> None:
        """Add a sensor once the gateway reports its value; some only come after a while."""
        entities = []
        for key, info in SENSOR_INFO.items():
            for source in info.status_sources:
                if source == THERMOSTAT and has_thermostat is False:
                    continue
                if (key, source) in added or coordinator.data[source].get(key) is None:
                    continue

                added.add((key, source))
                entities.append(SatSensor(coordinator, config_entry, info, key, source))

        if entities:
            async_add_entities(entities)

    _add_reported_sensors()
    config_entry.async_on_unload(coordinator.async_add_listener(_add_reported_sensors))

    if not coordinator.simulation:
        async_add_entities([SatOpenThermIdsSensor(coordinator, config_entry)])


class SatOpenThermIdsSensor(SatEntity, sensor.SensorEntity):
    """The OpenTherm data IDs the boiler answered in the scan after a start."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "opentherm_ids"
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator: SatSerialCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._scan = coordinator.id_scan
        self.entity_id = async_generate_entity_id(
            sensor.DOMAIN + ".{}",
            f"{config_entry.data[CONF_NAME].lower()}_opentherm_ids",
            hass=coordinator.hass,
        )
        self._attr_unique_id = f"{config_entry.entry_id}-opentherm-ids"

    @override
    def _update_attrs(self) -> None:
        scan = self._scan
        self._attr_native_value = (
            len(scan.ids(SUPPORTED)) if scan.finished and not scan.running else None
        )
        self._attr_extra_state_attributes = {
            "scan": "running" if scan.running else ("done" if scan.finished else "not_run"),
            "scanned_at": scan.scanned_at,
            "supported": scan.supported(),
            "data_invalid": scan.ids(INVALID),
            "unknown": scan.ids(UNKNOWN),
            "no_answer": scan.ids(NO_ANSWER),
            "parameter_count": scan.parameter_count,
            "parameters": {str(index): value for index, value in sorted(scan.parameters.items())},
            "fault_events": scan.fault_events,
        }


class SatSensor(SatEntity, sensor.SensorEntity):
    def __init__(
        self,
        coordinator: SatSerialCoordinator,
        config_entry: ConfigEntry,
        info: SatSensorInfo,
        key: str,
        source: str,
    ) -> None:
        super().__init__(coordinator, config_entry)

        self.entity_id = async_generate_entity_id(
            sensor.DOMAIN + ".{}",
            f"{config_entry.data[CONF_NAME].lower()}_{source}_{key}",
            hass=coordinator.hass,
        )

        self._key = key
        self._source = source
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}-{source}-{key}"
        self._attr_device_class = info.device_class
        self._attr_native_unit_of_measurement = info.unit
        self._attr_translation_key = key

        if (source_name := TRANSLATE_SOURCE[source]) is not None:
            self._attr_translation_placeholders = {"source": source_name}

    @override
    @property
    def available(self) -> bool:
        """Return availability of the sensor."""
        return self._coordinator.data[self._source].get(self._key) is not None

    @override
    def _update_attrs(self) -> None:
        value = self._coordinator.data[self._source].get(self._key)
        if isinstance(value, float):
            value = f"{value:2.1f}"

        self._attr_native_value = value
