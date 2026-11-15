from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)

from .const import (
    CONF_GAS_ENERGY_CONTENT,
    CONF_GAS_PRICE,
    CONF_MAXIMUM_CONSUMPTION,
    CONF_MINIMUM_CONSUMPTION,
    CONF_MODE,
    MODE_MQTT_OPENTHERM,
    OPTIONS_DEFAULTS,
)
from .entity import SatClimateEntity, SatEntity
from .helpers import float_value
from .serial import SatSerialCoordinator
from .serial import sensor as serial_sensor
from .simulator import SatSimulatorCoordinator
from .simulator import sensor as simulator_sensor

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import SatConfigEntry
    from .climate import SatClimate
    from .coordinator import SatDataUpdateCoordinator

_LOGGER: logging.Logger = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Specific heat of water in kJ/(kg·K), with 1 kg per litre
WATER_SPECIFIC_HEAT = 4.186
# The flow only settles a few minutes into a burn, and a small spread is mostly sensor noise
MINIMUM_SETTLED_BURN_SECONDS = 180
MINIMUM_FLOW_RETURN_DIFFERENCE = 1.5


async def async_setup_entry(
    _hass: HomeAssistant,
    _config_entry: SatConfigEntry,
    _async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors for the serial protocol if the integration is set to use it."""
    climate = _config_entry.runtime_data.climate
    coordinator = _config_entry.runtime_data.coordinator

    if isinstance(coordinator, SatSerialCoordinator):
        await serial_sensor.async_setup_entry(coordinator, _config_entry, _async_add_entities)

    if isinstance(coordinator, SatSimulatorCoordinator):
        await simulator_sensor.async_setup_entry(coordinator, _config_entry, _async_add_entities)

    if _config_entry.data.get(CONF_MODE) == MODE_MQTT_OPENTHERM:
        _async_add_entities([SatBoilerFaultCodeSensor(coordinator, _config_entry)])

    _async_add_entities(
        [
            SatFlameSensor(coordinator, _config_entry),
            SatFlameStartsSensor(coordinator, _config_entry),
            SatBoilerSensor(coordinator, _config_entry),
            SatManufacturerSensor(coordinator, _config_entry),
            SatErrorValueSensor(coordinator, _config_entry, climate),
            SatHeatingCurveSensor(coordinator, _config_entry, climate),
        ]
    )

    # Running totals that statistics and the Energy dashboard turn into daily values
    _async_add_entities(
        [
            SatTotalSensor(coordinator, _config_entry, climate, key)
            for key in ("starts", "burn_hours", "heating_kwh", "hot_water_kwh", "degree_days")
        ]
        + [SatHotWaterCoolingSensor(coordinator, _config_entry, climate)]
    )
    if (
        float(_config_entry.options.get(CONF_MINIMUM_CONSUMPTION) or 0) > 0
        or coordinator.supports_relative_modulation_management
    ):
        _async_add_entities([SatTotalSensor(coordinator, _config_entry, climate, "gas_m3")])
        if float(_config_entry.options.get(CONF_GAS_PRICE) or 0) > 0:
            _async_add_entities([SatGasCostSensor(coordinator, _config_entry, climate)])

    if climate.loop_monitor is not None:
        _async_add_entities(
            [
                SatOpenLoopsSensor(coordinator, _config_entry, climate),
                SatLoopBalanceSensor(coordinator, _config_entry, climate),
            ]
        )

    if coordinator.supports_relative_modulation_management:
        _async_add_entities([SatCurrentPowerSensor(coordinator, _config_entry)])

        if (
            float(_config_entry.options.get(CONF_MINIMUM_CONSUMPTION) or 0) > 0
            and float(_config_entry.options.get(CONF_MAXIMUM_CONSUMPTION) or 0) > 0
        ):
            _async_add_entities(
                [
                    SatCurrentConsumptionSensor(coordinator, _config_entry),
                    SatEstimatedWaterFlowSensor(coordinator, _config_entry),
                ]
            )


class SatCurrentPowerSensor(SatEntity, SensorEntity):
    _attr_translation_key = "boiler_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._attr_unique_id = f"{config_entry.entry_id}-boiler-current-power"

    @override
    @property
    def available(self) -> bool:
        """Return availability of the sensor."""
        return self._coordinator.boiler_power is not None

    @override
    def _update_attrs(self) -> None:
        self._attr_native_value = self._coordinator.boiler_power


class SatCurrentConsumptionSensor(SatEntity, SensorEntity):
    _attr_translation_key = "boiler_consumption"
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR

    def __init__(self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._attr_unique_id = f"{config_entry.entry_id}-boiler-current-consumption"
        self._minimum_consumption = self._config_entry.options[CONF_MINIMUM_CONSUMPTION]
        self._maximum_consumption = self._config_entry.options[CONF_MAXIMUM_CONSUMPTION]

    @override
    @property
    def available(self) -> bool:
        """Return availability of the sensor."""
        return self._coordinator.relative_modulation_value is not None

    @override
    def _update_attrs(self) -> None:
        relative_modulation_value = self._coordinator.relative_modulation_value
        if relative_modulation_value is None:
            return

        if not self._coordinator.device_active or not self._coordinator.flame_active:
            self._attr_native_value = 0
            return

        differential_gas_consumption = self._maximum_consumption - self._minimum_consumption

        self._attr_native_value = round(
            self._minimum_consumption
            + ((relative_modulation_value / 100) * differential_gas_consumption),
            3,
        )


class SatHeatingCurveSensor(SatClimateEntity, SensorEntity):
    _attr_translation_key = "heating_curve"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry, climate: SatClimate
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._attr_unique_id = f"{config_entry.entry_id}-heating-curve"

    @override
    @property
    def available(self) -> bool:
        """Return availability of the sensor."""
        return self.climate_added and self._climate.heating_curve.value is not None

    @override
    def _update_attrs(self) -> None:
        self._attr_native_value = self._climate.heating_curve.value


class SatErrorValueSensor(SatClimateEntity, SensorEntity):
    _attr_translation_key = "error_value"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE_DELTA
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry, climate: SatClimate
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._attr_unique_id = f"{config_entry.entry_id}-error-value"

    @override
    @property
    def available(self) -> bool:
        """Return availability of the sensor."""
        return self.climate_added

    @override
    def _update_attrs(self) -> None:
        if self.available:
            self._attr_native_value = self._climate.max_error.value


class SatManufacturerSensor(SatEntity, SensorEntity):
    _attr_translation_key = "boiler_manufacturer"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._attr_unique_id = f"{config_entry.entry_id}-manufacturer"

    @override
    def _update_attrs(self) -> None:
        manufacturer = self._coordinator.manufacturer
        self._attr_native_value = manufacturer.friendly_name if manufacturer is not None else None

    @override
    @property
    def available(self) -> bool:
        return self._coordinator.manufacturer is not None


class SatFlameSensor(SatEntity, SensorEntity):
    _attr_translation_key = "flame_status"

    def __init__(self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._attr_unique_id = f"{config_entry.entry_id}-flame-status"

    @override
    def _update_attrs(self) -> None:
        if self.available:
            self._attr_native_value = self._coordinator.flame.health_status.name

    @override
    @property
    def available(self) -> bool:
        return self._coordinator.flame.health_status is not None


class SatBoilerSensor(SatEntity, SensorEntity):
    _attr_translation_key = "boiler_status"

    def __init__(self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._attr_unique_id = f"{config_entry.entry_id}-boiler-status"

    @override
    def _update_attrs(self) -> None:
        if self.available:
            self._attr_native_value = self._coordinator.device_status.name

    @override
    @property
    def available(self) -> bool:
        return self._coordinator.device_status is not None


class SatBoilerFaultCodeSensor(SatEntity, SensorEntity):
    _attr_translation_key = "boiler_fault_code"

    def __init__(self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._attr_unique_id = f"{config_entry.entry_id}-boiler-fault-code"

    @override
    def _update_attrs(self) -> None:
        self._attr_native_value = self._coordinator.fault_code

    @override
    @property
    def available(self) -> bool:
        return self._coordinator.fault_code is not None


class SatFlameStartsSensor(SatEntity, SensorEntity):
    """How many times the burner lit in the last hour."""

    _attr_translation_key = "flame_starts_last_hour"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fire-circle"

    def __init__(self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._attr_unique_id = f"{config_entry.entry_id}-flame-starts-last-hour"

    @override
    def _update_attrs(self) -> None:
        self._attr_native_value = int(self._coordinator.flame.cycles_last_hour)


class SatEstimatedWaterFlowSensor(SatEntity, SensorEntity):
    """Water flow through the heating system, from the burner power and the flow/return spread.

    It is measured during settled space heating burns only and holds the last value between them.
    """

    _attr_translation_key = "estimated_water_flow"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._attr_unique_id = f"{config_entry.entry_id}-estimated-water-flow"
        self._minimum_consumption = float(self._config_entry.options[CONF_MINIMUM_CONSUMPTION])
        self._maximum_consumption = float(self._config_entry.options[CONF_MAXIMUM_CONSUMPTION])
        self._gas_energy_content = float(
            self._config_entry.options.get(CONF_GAS_ENERGY_CONTENT)
            or OPTIONS_DEFAULTS[CONF_GAS_ENERGY_CONTENT]
        )
        self._attr_extra_state_attributes = {"heat_output_kw": None, "flow_return_difference": None}

    def _heat_output(self) -> float | None:
        """Return the heat the burner delivers in kW, from the gas use the modulation implies."""
        if (modulation := float_value(self._coordinator.relative_modulation_value)) is None:
            return None

        consumption = self._minimum_consumption + (
            (modulation / 100) * (self._maximum_consumption - self._minimum_consumption)
        )
        return consumption * self._gas_energy_content

    @override
    def _update_attrs(self) -> None:
        coordinator = self._coordinator
        flow = coordinator.boiler_temperature
        return_temperature = coordinator.return_temperature
        on_time = coordinator.flame.latest_on_time_seconds

        if (
            not coordinator.flame_active
            or coordinator.hot_water_active
            or flow is None
            or return_temperature is None
            or on_time is None
            or on_time < MINIMUM_SETTLED_BURN_SECONDS
            or (difference := flow - return_temperature) < MINIMUM_FLOW_RETURN_DIFFERENCE
            or (heat_output := self._heat_output()) is None
        ):
            return

        # P = m · c · ΔT, so m = P / (c · ΔT), in kg/s and then l/min
        self._attr_native_value = round(heat_output / (WATER_SPECIFIC_HEAT * difference) * 60, 1)
        self._attr_extra_state_attributes = {
            "heat_output_kw": round(heat_output, 2),
            "flow_return_difference": round(difference, 1),
        }


TOTAL_SENSORS: dict[str, tuple[SensorDeviceClass | None, str | None, int]] = {
    "starts": (None, None, 0),
    "burn_hours": (SensorDeviceClass.DURATION, UnitOfTime.HOURS, 2),
    "heating_kwh": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 2),
    "hot_water_kwh": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 2),
    "gas_m3": (SensorDeviceClass.GAS, UnitOfVolume.CUBIC_METERS, 3),
    "degree_days": (None, "°C·d", 2),
}


class SatTotalSensor(SatClimateEntity, SensorEntity):
    """A running total of the boiler's work that only grows."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: SatDataUpdateCoordinator,
        config_entry: ConfigEntry,
        climate: SatClimate,
        key: str,
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._key = key
        device_class, unit, precision = TOTAL_SENSORS[key]
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_suggested_display_precision = precision
        self._attr_translation_key = f"total_{key}"
        self._attr_unique_id = f"{config_entry.entry_id}-total-{key.replace('_', '-')}"

    @override
    def _update_attrs(self) -> None:
        value = self._climate.boiler_stats.totals[self._key]
        self._attr_native_value = int(value) if self._key == "starts" else round(value, 4)


class SatGasCostSensor(SatClimateEntity, SensorEntity):
    """The estimated gas cost so far, at the configured price."""

    _attr_translation_key = "total_gas_cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry, climate: SatClimate
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._attr_unique_id = f"{config_entry.entry_id}-total-gas-cost"

    @override
    async def async_added_to_hass(self) -> None:
        self._attr_native_unit_of_measurement = self.hass.config.currency
        await super().async_added_to_hass()

    @override
    def _update_attrs(self) -> None:
        self._attr_native_value = round(self._climate.boiler_stats.totals["gas_cost"], 2)


class SatHotWaterCoolingSensor(SatClimateEntity, SensorEntity):
    """Cylinder temperature drops in the last day that started right after heating stopped."""

    _attr_translation_key = "hot_water_cooling"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-thermometer-outline"

    def __init__(
        self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry, climate: SatClimate
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._attr_unique_id = f"{config_entry.entry_id}-hot-water-cooling"

    @override
    def _update_attrs(self) -> None:
        stats = self._climate.boiler_stats
        self._attr_native_value = stats.hot_water_drops_after_heating
        self._attr_extra_state_attributes = {"all_drops_24h": stats.hot_water_drops}


class SatOpenLoopsSensor(SatClimateEntity, SensorEntity):
    """How many of the thermostat-controlled loops are open now."""

    _attr_translation_key = "open_loops"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:valve-open"

    def __init__(
        self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry, climate: SatClimate
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._attr_unique_id = f"{config_entry.entry_id}-open-loops"

    @override
    def _update_attrs(self) -> None:
        if (monitor := self._climate.loop_monitor) is None:
            return
        self._attr_native_value = len(monitor.open_rooms)
        self._attr_extra_state_attributes = {
            "open": monitor.open_rooms,
            "monitored": monitor.rooms,
            "base_flow_lpm": monitor.base_flow,
        }


class SatLoopBalanceSensor(SatClimateEntity, SensorEntity):
    """How many room loops would be better with their rotameter moved, with advice per room."""

    _attr_translation_key = "loop_balance"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:tune-variant"

    def __init__(
        self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry, climate: SatClimate
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._attr_unique_id = f"{config_entry.entry_id}-loop-balance"

    @override
    def _update_attrs(self) -> None:
        if (monitor := self._climate.loop_monitor) is None:
            return
        self._attr_native_value = monitor.rooms_to_adjust
        self._attr_extra_state_attributes = monitor.attributes
