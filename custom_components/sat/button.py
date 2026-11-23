from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .const import (
    CONF_HEATING_SYSTEM,
    CONF_MINIMUM_SETPOINT,
    CONF_OVERSHOOT_PROTECTION,
    DOMAIN,
    HEATING_SYSTEM_UNKNOWN,
)
from .entity import SatClimateEntity, SatEntity
from .helpers import configured_maximum_setpoint
from .overshoot_protection import CalibrationError, create_overshoot_protection
from .serial import SatSerialCoordinator
from .service_report import build_service_report

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import SatConfigEntry
    from .climate import SatClimate
    from .coordinator import SatDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: SatConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data.coordinator

    if coordinator.supports_setpoint_management:
        async_add_entities(
            [SatCalibrateButton(coordinator, config_entry, config_entry.runtime_data.climate)]
        )

    if isinstance(coordinator, SatSerialCoordinator) and not coordinator.simulation:
        async_add_entities([SatScanOpenThermIdsButton(coordinator, config_entry)])

    async_add_entities(
        [SatServiceReportButton(coordinator, config_entry, config_entry.runtime_data.climate)]
    )


class SatServiceReportButton(SatClimateEntity, ButtonEntity):
    """Show what SAT saw of the boiler as a report for the service technician."""

    _attr_translation_key = "service_report"
    _attr_icon = "mdi:clipboard-text-outline"

    def __init__(
        self,
        coordinator: SatDataUpdateCoordinator,
        config_entry: SatConfigEntry,
        climate: SatClimate,
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._attr_unique_id = f"{config_entry.entry_id}-service-report"

    @override
    async def async_press(self) -> None:
        coordinator = self._coordinator
        scan = coordinator.id_scan if isinstance(coordinator, SatSerialCoordinator) else None
        report = build_service_report(
            language=self.hass.config.language,
            title=self._config_entry.title,
            boiler=coordinator.device_type,
            now=dt_util.now(),
            totals=self._climate.boiler_stats.totals,
            attributes=self._climate.extra_state_attributes or {},
            yesterday=self._climate.boiler_stats.yesterday,
            pressure=coordinator.water_pressure,
            faults=scan.fault_events if scan is not None else None,
            parameters=scan.parameters if scan is not None else None,
            parameter_changes=scan.parameter_changes if scan is not None else None,
            settings={
                "minimum_setpoint": coordinator.minimum_setpoint,
                "maximum_setpoint": coordinator.maximum_setpoint,
            },
        )
        persistent_notification.async_create(
            self.hass,
            report,
            title=self._config_entry.title,
            notification_id=f"{DOMAIN}_{self._config_entry.entry_id}_service_report",
        )


class SatScanOpenThermIdsButton(SatEntity, ButtonEntity):
    """Ask the boiler for every OpenTherm ID once; the answers show on the OpenTherm IDs sensor."""

    _attr_translation_key = "scan_opentherm_ids"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:magnify-scan"

    def __init__(self, coordinator: SatSerialCoordinator, config_entry: SatConfigEntry) -> None:
        super().__init__(coordinator, config_entry)

        self._serial = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}-scan-opentherm-ids"

    @override
    @property
    def available(self) -> bool:
        return not self._serial.id_scan.running

    @override
    async def async_press(self) -> None:
        if self._serial.async_start_id_scan():
            self.async_write_ha_state()


class SatCalibrateButton(SatClimateEntity, ButtonEntity):
    _attr_translation_key = "calibrate_overshoot_protection"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: SatDataUpdateCoordinator,
        config_entry: SatConfigEntry,
        climate: SatClimate,
    ) -> None:
        super().__init__(coordinator, config_entry, climate)

        self._attr_unique_id = f"{config_entry.entry_id}-calibrate-overshoot-protection"

    @override
    @property
    def available(self) -> bool:
        return self._climate.calibration is None

    @override
    async def async_press(self) -> None:
        if not self._climate.valves_open:
            _LOGGER.warning(
                "Calibrating while no valves report open, the measured value may come out too high"
            )

        self._config_entry.async_create_background_task(
            self.hass, self._async_calibrate(), "sat_overshoot_protection_calibration"
        )

    async def _async_calibrate(self) -> None:
        entry = self._config_entry
        heating_system = entry.data.get(CONF_HEATING_SYSTEM, HEATING_SYSTEM_UNKNOWN)
        maximum_setpoint = configured_maximum_setpoint(entry.options, heating_system)

        try:
            async with self._climate.async_calibrating():
                result = await create_overshoot_protection(
                    self._coordinator, heating_system, maximum_setpoint, entry.options
                ).calculate()
        except CalibrationError as error:
            message = (
                f"Calibrating the overshoot protection value failed ({error.reason}). "
                "The current value stays in use."
            )
            if error.value is not None:
                message += (
                    f" The boiler reached {error.value} °C at minimum modulation, "
                    "a starting point for setting it by hand."
                )
        except Exception as error:
            _LOGGER.exception("Overshoot protection calibration failed")
            message = (
                f"Calibrating the overshoot protection value failed ({error}). "
                "The current value stays in use."
            )
        else:
            message = (
                f"Overshoot protection value calibrated at {result.value} °C ({result.method})."
            )
            self.hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_OVERSHOOT_PROTECTION: True},
                options={**entry.options, CONF_MINIMUM_SETPOINT: result.value},
            )
            self.hass.config_entries.async_schedule_reload(entry.entry_id)

        persistent_notification.async_create(
            self.hass,
            message,
            title=entry.title,
            notification_id=f"sat_calibration_{entry.entry_id}",
        )
