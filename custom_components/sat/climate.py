"""Climate platform for SAT."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING, Any, override

from homeassistant.components import persistent_notification, sensor, weather
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    PRESET_ACTIVITY,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_HOME,
    PRESET_NONE,
    PRESET_SLEEP,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CoreState,
    Event,
    EventStateChangedData,
    HassJob,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityPlatformState
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .area import SENSOR_TEMPERATURE_ID, Areas, is_heating_blocked
from .boiler_diagnostics import BoilerDiagnostics
from .boiler_stats import BoilerStats
from .const import (
    COLD_SETPOINT,
    CONF_BOILER_ANTI_CYCLING_TIME,
    CONF_CLIMATE_VALVE_OFFSET,
    CONF_COMFORT_SCHEDULE_ENTITY_ID,
    CONF_CONDENSING_BOILER,
    CONF_DEFAULT_HVAC_MODE,
    CONF_DYNAMIC_MINIMUM_SETPOINT,
    CONF_DYNAMIC_MINIMUM_SETPOINT_VERSION,
    CONF_FORCE_PULSE_WIDTH_MODULATION,
    CONF_GAS_ENERGY_CONTENT,
    CONF_GAS_PRICE,
    CONF_HEAT_BUDGET_MINIMUM_BURN,
    CONF_HEAT_BUDGET_MODE,
    CONF_HEAT_BUDGET_PERIOD,
    CONF_HEAT_LOSS_COEFFICIENT,
    CONF_HEATING_MODE,
    CONF_HEATING_SYSTEM,
    CONF_HOT_WATER_COMFORT_TEMPERATURE,
    CONF_HOT_WATER_ECO_TEMPERATURE,
    CONF_HOT_WATER_SCHEDULE_ENTITY_ID,
    CONF_HUMIDITY_SENSOR_ENTITY_ID,
    CONF_INSIDE_SENSOR_ENTITY_ID,
    CONF_KEEP_HEATING_IN_PWM_OFF,
    CONF_LAST_SERVICE_DATE,
    CONF_LEGIONELLA_DAY,
    CONF_LEGIONELLA_TIME,
    CONF_MAXIMUM_CONSUMPTION,
    CONF_MAXIMUM_RELATIVE_MODULATION,
    CONF_MINIMUM_CONSUMPTION,
    CONF_OUTSIDE_SENSOR_ENTITY_ID,
    CONF_OVERSHOOT_PROTECTION,
    CONF_PRESENCE_ENTITY_IDS,
    CONF_PROXIMITY_ENTITY_ID,
    CONF_PUSH_SETPOINT_TO_THERMOSTAT,
    CONF_RADIATORS,
    CONF_RETURN_DISTANCE,
    CONF_SCREED_MAXIMUM_TEMPERATURE,
    CONF_SENSOR_MAX_VALUE_AGE,
    CONF_SERVICE_INTERVAL,
    CONF_SETBACK_TEMPERATURE,
    CONF_SIMULATION,
    CONF_SYNC_CLIMATES_WITH_MODE,
    CONF_SYNC_CLIMATES_WITH_PRESET,
    CONF_TARGET_TEMPERATURE_STEP,
    CONF_THERMAL_COMFORT,
    CONF_THERMOSTAT,
    CONF_VALVE_OPENING_TIME,
    CONF_WARM_WEATHER_SHUTDOWN,
    CONF_WEATHER_FORECAST_ENTITY_ID,
    CONF_WINDOW_DETECTION,
    CONF_WINDOW_MINIMUM_OPEN_TIME,
    CONTROL_LOOP_STALL_TIME,
    DEADBAND,
    DOMAIN,
    DYNAMIC_MINIMUM_SETPOINT_VERSION_1,
    DYNAMIC_MINIMUM_SETPOINT_VERSION_2,
    HEAT_BUDGET_OFF,
    HEAT_BUDGET_ON,
    HEAT_BUDGET_SHADOW,
    HEATING_MODE_ECO,
    HEATING_SYSTEM_UNDERFLOOR,
    LEGIONELLA_OFF,
    MINIMUM_RELATIVE_MODULATION,
    MINIMUM_SETPOINT,
    OPTIONS_DEFAULTS,
    PWM_HYSTERESIS,
    BoilerStatus,
    PWMStatus,
)
from .coordinator import DeviceState, SatDataUpdateCoordinator
from .curve_advisor import CurveAdvisor
from .efficiency import EfficiencyTracker, fuel_for
from .entity import SatEntity
from .errors import Error, Errors
from .heat_budget import (
    FORECAST_HORIZON_HOURS,
    HeatBudget,
    HeatBudgetInputs,
    sun_factor,
)
from .helpers import convert_time_str_to_seconds, float_value, is_state_stale, state_age_seconds
from .hot_water_schedule import HotWaterPlan, HotWaterSchedule
from .loop_measurement import LoopMeasurement
from .loop_monitor import LoopMonitor, RoomReading, estimate_water_flow
from .manufacturers.geminox import Geminox
from .presence import Occupancy, PresenceTracker, is_home
from .relative_modulation import RelativeModulation, RelativeModulationState
from .summer_simmer import SummerSimmer
from .util import (
    create_heating_curve_controller,
    create_minimum_setpoint_controller,
    create_pid_controller,
    create_pwm_controller,
)
from .warm_weather import WarmWeatherShutdown
from .window_detection import TemperatureDropDetector

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Coroutine

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import State
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import SatConfigEntry
    from .pwm import PWMState

ATTR_ROOMS = "rooms"
ATTR_SETPOINT = "setpoint"
ATTR_OPTIMAL_COEFFICIENT = "optimal_coefficient"
ATTR_COEFFICIENT_DERIVATIVE = "coefficient_derivative"
ATTR_PRE_CUSTOM_TEMPERATURE = "pre_custom_temperature"
ATTR_PRE_ACTIVITY_TEMPERATURE = "pre_activity_temperature"

# How long the last control setpoint is refreshed while inputs are missing,
# before the boiler goes back to the room thermostat
INPUTS_MISSING_GRACE_PERIOD = timedelta(minutes=10)
# The on-phase flame goes out within seconds of the off-phase setpoint reaching the boiler
KEEP_HEATING_FLAME_GRACE_SECONDS = 90
# A boiler that lit against the off-phase setpoint gets heating disabled between on-phases again
KEEP_HEATING_SUSPEND_SECONDS = 3600
# The flow and return only settle a few minutes into a burn, the flue gas a few more
SETTLED_BURN_SECONDS = 180
DIAGNOSTIC_BURN_SECONDS = 600
# After hot water the flow sensor still reads the hot water temperature for a while
AFTER_HOT_WATER_SECONDS = 300
DISTANCE_TO_KM = {"m": 0.001, "km": 1.0, "mi": 1.609344, "ft": 0.0003048, "yd": 0.0009144}

_LOGGER = logging.getLogger(__name__)


PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    _config_entry: SatConfigEntry,
    _async_add_devices: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the SatClimate device."""
    _async_add_devices([_config_entry.runtime_data.climate])


@dataclass
class SatClimateExtraStoredData(ExtraStoredData):
    hvac_mode: str | None
    target_temperature: float | None
    preset_mode: str | None
    pre_custom_temperature: float | None

    @override
    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SatClimateExtraStoredData:
        return cls(
            data.get("hvac_mode"),
            data.get("target_temperature"),
            data.get("preset_mode"),
            data.get("pre_custom_temperature"),
        )


class SatClimate(SatEntity, ClimateEntity, RestoreEntity):
    # These change on nearly every write and would give each recorder row its own attributes
    _unrecorded_attributes = frozenset(
        {
            "boiler_flame_timing",
            "boiler_temperature_cold",
            "boiler_temperature_derivative",
            "current_kd",
            "current_ki",
            "current_kp",
            "derivative",
            "derivative_raw",
            "error",
            "integral",
            "proportional",
            "pulse_width_modulation_duty_cycle",
        }
    )

    def __init__(
        self, coordinator: SatDataUpdateCoordinator, config_entry: ConfigEntry, unit: str
    ) -> None:
        super().__init__(coordinator, config_entry)

        # Set up some public variables
        self.thermostat = config_entry.data.get(CONF_THERMOSTAT)

        # Get some sensor entity IDs
        self.inside_sensor_entity_id: str = config_entry.data[CONF_INSIDE_SENSOR_ENTITY_ID]
        self.humidity_sensor_entity_id = config_entry.data.get(CONF_HUMIDITY_SENSOR_ENTITY_ID)

        # Get outside sensor entity IDs
        outside_sensor_entities = config_entry.data[CONF_OUTSIDE_SENSOR_ENTITY_ID]

        # If outside sensor entity IDs is a string, make it a list
        self.outside_sensor_entities: list[str] = (
            [outside_sensor_entities]
            if isinstance(outside_sensor_entities, str)
            else outside_sensor_entities
        )

        # Create config options dictionary with defaults
        config_options = OPTIONS_DEFAULTS.copy()
        config_options.update(config_entry.options)

        # Create a dictionary mapping preset keys to temperature options
        conf_presets = {
            p: f"{p}_temperature"
            for p in (PRESET_ACTIVITY, PRESET_AWAY, PRESET_HOME, PRESET_SLEEP, PRESET_COMFORT)
        }

        # Create a dictionary mapping preset keys to temperature values
        self._presets = {
            key: config_options[value] for key, value in conf_presets.items() if key in conf_presets
        }

        self._alpha = 0.2
        self._sensors: list[str] = []
        self._rooms: dict[str, float] | None = None
        self._setpoint: float | None = None
        self._calculated_setpoint: float | None = None
        self._last_boiler_temperature: float | None = None

        self._window_sensor_handle: asyncio.Task[None] | None = None
        self._pre_custom_temperature: float | None = None
        self._pre_activity_temperature: float | None = None

        self._attr_native_temperature_unit = unit
        self._attr_hvac_mode = None
        self._attr_preset_mode = PRESET_NONE
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_preset_modes = [PRESET_NONE, *self._presets.keys()]

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

        self._control_heating_loop_unsub: Callable[[], None] | None = None
        self._sensor_stale_unsub: Callable[[], None] | None = None
        self._last_control_at = dt_util.utcnow()
        self._inputs_missing_since: datetime | None = None
        self._inputs_missing_released = False
        self._valves_open = True
        self.control_paused = False
        self.calibration: asyncio.Task[None] | None = None
        self._control_lock = asyncio.Lock()
        self._state_listeners: list[Callable[[], None]] = []

        # System Configuration
        self._attr_name = None
        self._attr_unique_id = config_entry.entry_id

        self._radiators = config_entry.data.get(CONF_RADIATORS) or []

        self._simulation = bool(config_entry.data.get(CONF_SIMULATION))
        self._heating_system = str(config_entry.data.get(CONF_HEATING_SYSTEM))
        self._overshoot_protection = bool(config_entry.data.get(CONF_OVERSHOOT_PROTECTION))

        # User Configuration
        self._heating_mode = str(config_entry.options.get(CONF_HEATING_MODE))
        self._thermal_comfort = bool(config_options.get(CONF_THERMAL_COMFORT))
        self._push_setpoint_to_thermostat = bool(
            config_options.get(CONF_PUSH_SETPOINT_TO_THERMOSTAT)
        )
        self._climate_valve_offset = float(config_options[CONF_CLIMATE_VALVE_OFFSET])
        self._attr_target_temperature_step = float(config_options[CONF_TARGET_TEMPERATURE_STEP])
        self._dynamic_minimum_setpoint = bool(config_options.get(CONF_DYNAMIC_MINIMUM_SETPOINT))
        self._sync_climates_with_mode = bool(config_options.get(CONF_SYNC_CLIMATES_WITH_MODE))
        self._sync_climates_with_preset = bool(config_options.get(CONF_SYNC_CLIMATES_WITH_PRESET))
        self._maximum_relative_modulation = int(config_options[CONF_MAXIMUM_RELATIVE_MODULATION])
        self._minimum_setpoint_version = int(config_options[CONF_DYNAMIC_MINIMUM_SETPOINT_VERSION])
        self._force_pulse_width_modulation = bool(
            config_options.get(CONF_FORCE_PULSE_WIDTH_MODULATION)
        )
        self._sensor_max_value_age = convert_time_str_to_seconds(
            config_options[CONF_SENSOR_MAX_VALUE_AGE]
        )
        self._default_hvac_mode = HVACMode(config_options[CONF_DEFAULT_HVAC_MODE])
        self._window_minimum_open_time = convert_time_str_to_seconds(
            config_options[CONF_WINDOW_MINIMUM_OPEN_TIME]
        )

        # Thermal actuators take minutes to open, so the boiler waits for them before lighting
        self._valve_opening_time = convert_time_str_to_seconds(
            config_options[CONF_VALVE_OPENING_TIME]
        )
        self._valves_opening_since: dict[str, float] = {}
        self._valve_wait_logged = False

        # Some combi boilers swing their diverter valve to hot water once heating is disabled,
        # so the pump overrun pulls the cylinder heat into the floor
        self._keep_heating_in_pwm_off = bool(config_options.get(CONF_KEEP_HEATING_IN_PWM_OFF))
        self._pwm_off_since: float | None = None
        self._keep_heating_suspended_until: float | None = None

        # Create a PID controller with given configuration options
        self.pid = create_pid_controller(config_entry.data, config_options)

        # Create Area controllers
        self.areas = Areas(config_entry.data, config_options)

        # Create Relative Modulation controller
        self.relative_modulation = RelativeModulation(coordinator, self._heating_system)

        # Create a Heating Curve controller with given configuration options
        self.heating_curve = create_heating_curve_controller(config_entry.data, config_options)

        # Create the Minimum Setpoint controller
        self.minimum_setpoint = create_minimum_setpoint_controller(
            coordinator.minimum_setpoint, config_options
        )

        # Learn the heat loss of the house and dose the burner in blocks of one period
        self._heat_budget_mode = str(config_options.get(CONF_HEAT_BUDGET_MODE) or HEAT_BUDGET_OFF)
        self.heat_budget: HeatBudget | None = None
        if self._heat_budget_mode != HEAT_BUDGET_OFF and coordinator.supports_setpoint_management:
            anti_cycling = convert_time_str_to_seconds(
                config_options.get(CONF_BOILER_ANTI_CYCLING_TIME) or "00:00:00"
            )
            heat_loss = float(config_options.get(CONF_HEAT_LOSS_COEFFICIENT) or 0) / 1000
            self.heat_budget = HeatBudget(
                period_seconds=int(config_options[CONF_HEAT_BUDGET_PERIOD]) * 60,
                minimum_burn_seconds=convert_time_str_to_seconds(
                    config_options[CONF_HEAT_BUDGET_MINIMUM_BURN]
                ),
                minimum_off_seconds=anti_cycling or 600,
                heat_loss_kw_per_k=heat_loss or None,
            )
        # Fast radiators would swing with hour-long blocks, so they only learn
        if (
            self._heat_budget_mode == HEAT_BUDGET_ON
            and self._heating_system != HEATING_SYSTEM_UNDERFLOOR
        ):
            _LOGGER.warning(
                "The heat budget only drives underfloor heating, it learns without control here."
            )
            self._heat_budget_mode = HEAT_BUDGET_SHADOW
        driving_budget = self.heat_budget if self._heat_budget_mode == HEAT_BUDGET_ON else None
        self._driving_budget: HeatBudget | None = driving_budget
        self._budget_overloaded = False

        self._weather_forecast_entity_id = config_options.get(CONF_WEATHER_FORECAST_ENTITY_ID)
        self._weather_forecast: list[tuple[datetime, float | None, float | None]] = []
        self._comfort_schedule_entity_id = config_options.get(CONF_COMFORT_SCHEDULE_ENTITY_ID)
        self._setback_temperature = float(config_options.get(CONF_SETBACK_TEMPERATURE) or 0)
        self._minimum_consumption = float(config_options.get(CONF_MINIMUM_CONSUMPTION) or 0)
        self._maximum_consumption = float(config_options.get(CONF_MAXIMUM_CONSUMPTION) or 0)
        self._gas_energy_content = float(
            config_options.get(CONF_GAS_ENERGY_CONTENT) or OPTIONS_DEFAULTS[CONF_GAS_ENERGY_CONTENT]
        )

        # Create a PWM controller with given configuration options
        self.pwm = create_pwm_controller(
            self.heating_curve, config_entry.data, config_options, driving_budget
        )

        # Running totals, loop watching and boiler diagnostics
        self.boiler_stats = BoilerStats()
        self.boiler_diagnostics: BoilerDiagnostics | None = None
        monitored = [*self._radiators, *self.areas.items()]
        self.loop_monitor = LoopMonitor(monitored) if monitored else None
        self._heating_stopped_at: float | None = None
        self._failed_monitors: set[str] = set()
        self._last_pwm_status: PWMStatus | None = None
        self._last_device_active: bool | None = None
        self._flow_sample: float | None = None
        self._last_water_flow: float | None = None
        self._hot_water_ended_at: float | None = None
        self._last_hot_water_active = False
        self._init_extras(coordinator, config_options)

        if self._simulation:
            _LOGGER.warning("Simulation mode!")

    def _init_extras(
        self, coordinator: SatDataUpdateCoordinator, config_options: dict[str, Any]
    ) -> None:
        """Set up warm weather shutdown, hot water, presence, window and service settings."""
        threshold = float(config_options.get(CONF_WARM_WEATHER_SHUTDOWN) or 0)
        self.warm_weather = (
            WarmWeatherShutdown(threshold)
            if threshold > 0 and coordinator.supports_setpoint_management
            else None
        )
        self._warm_weather_was_active = False

        self._hot_water_schedule_entity_id = config_options.get(CONF_HOT_WATER_SCHEDULE_ENTITY_ID)
        self.hot_water_schedule: HotWaterSchedule | None = None
        comfort = float(config_options.get(CONF_HOT_WATER_COMFORT_TEMPERATURE) or 0)
        if comfort > 0 and coordinator.supports_hot_water_setpoint_management:
            day = str(config_options.get(CONF_LEGIONELLA_DAY) or LEGIONELLA_OFF)
            eco = float(config_options.get(CONF_HOT_WATER_ECO_TEMPERATURE) or 0)
            self.hot_water_schedule = HotWaterSchedule(
                HotWaterPlan(
                    comfort_temperature=comfort,
                    eco_temperature=eco or None,
                    legionella_weekday=None if day == LEGIONELLA_OFF else int(day),
                    legionella_start_seconds=convert_time_str_to_seconds(
                        config_options.get(CONF_LEGIONELLA_TIME) or "03:00:00"
                    ),
                )
            )
        self._hot_water_setpoint_sent: float | None = None

        self._presence_entity_ids = list(config_options.get(CONF_PRESENCE_ENTITY_IDS) or [])
        self._proximity_entity_id = config_options.get(CONF_PROXIMITY_ENTITY_ID)
        self.presence = (
            PresenceTracker(float(config_options.get(CONF_RETURN_DISTANCE) or 0))
            if self._presence_entity_ids
            else None
        )
        self._presence_previous_preset: str | None = None

        self.window_detector = (
            TemperatureDropDetector() if config_options.get(CONF_WINDOW_DETECTION) else None
        )
        self._window_detected = False

        self.curve_advisor = CurveAdvisor()
        self.efficiency = EfficiencyTracker(
            fuel_for(self._gas_energy_content),
            condensing=bool(config_options.get(CONF_CONDENSING_BOILER, True)),
        )
        self._gas_price = float(config_options.get(CONF_GAS_PRICE) or 0)
        screed = float(config_options.get(CONF_SCREED_MAXIMUM_TEMPERATURE) or 0)
        self._screed_limit = (
            screed if screed > 0 and self._heating_system == HEATING_SYSTEM_UNDERFLOOR else None
        )
        service = config_options.get(CONF_LAST_SERVICE_DATE)
        self._last_service = dt_util.parse_date(str(service)) if service else None
        self._service_interval = int(config_options.get(CONF_SERVICE_INTERVAL) or 12)

        self.loop_measurement: LoopMeasurement | None = None
        self._loop_measurement_task: asyncio.Task[None] | None = None
        self._loop_measurement_result: dict[str, Any] | None = None

    def async_track_coordinator_data(self) -> None:
        """Track changes in the coordinator's boiler temperature and trigger the heating loop."""
        if (
            self._coordinator.boiler_temperature is not None
            and self._last_boiler_temperature == self._coordinator.boiler_temperature
        ):
            return

        self.schedule_control_heating_loop()
        self._last_boiler_temperature = self._coordinator.boiler_temperature

    @override
    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Restore the previous state if available, or set default values
        await self._restore_previous_state_or_set_defaults()

        # Update a heating curve if outside temperature is available
        outside_temperature = self.current_outside_temperature
        if outside_temperature is not None and self.native_target_temperature is not None:
            self.areas.heating_curves.update(outside_temperature)
            self.heating_curve.update(self.native_target_temperature, outside_temperature)

        self.async_on_remove(async_at_started(self.hass, self._async_started))

        await self.minimum_setpoint.async_initialize(self.hass, self._config_entry.entry_id)

        await self.boiler_stats.async_initialize(self.hass, self._config_entry.entry_id)
        self.boiler_diagnostics = BoilerDiagnostics(
            self.hass,
            self._config_entry.entry_id,
            self._config_entry.title,
            screed_limit=self._screed_limit,
            last_service=self._last_service,
            service_interval_months=self._service_interval,
        )
        await self.boiler_diagnostics.async_initialize()

        if self.heat_budget is not None:
            await self.heat_budget.async_initialize(self.hass, self._config_entry.entry_id)

        if self._weather_forecast_entity_id and (
            self.heat_budget is not None or self.warm_weather is not None
        ):
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._async_refresh_weather_forecast, timedelta(minutes=30)
                )
            )
            self.hass.async_create_task(
                self._async_refresh_weather_forecast(), "sat_weather_forecast"
            )
        await self._coordinator.async_initialize_flame(self._config_entry.entry_id)

        # Initialize the area system
        await self.areas.async_added_to_hass(self.hass)

        # Let the coordinator know we are ready
        await self._coordinator.async_added_to_hass()

        # A release sent while the gateway was unreachable is lost,
        # and the gateway keeps the override until told otherwise
        if self.hvac_mode != HVACMode.HEAT:
            await self._coordinator.async_release_control()

    @callback
    def async_add_state_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call the listener every time this entity writes its state."""
        self._state_listeners.append(listener)
        return lambda: self._state_listeners.remove(listener)

    @override
    @callback
    def _async_write_ha_state(self) -> None:
        self._async_update_sensor_values()

        if self.hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF
        elif not self._coordinator.device_active:
            self._attr_hvac_action = HVACAction.IDLE
        else:
            self._attr_hvac_action = HVACAction.HEATING

        self._attr_extra_state_attributes = self.compute_extra_state_attributes()
        super()._async_write_ha_state()

        for listener in list(self._state_listeners):
            listener()

        if self._sensor_stale_unsub is not None:
            self._sensor_stale_unsub()
            self._sensor_stale_unsub = None

        if self._platform_state is not EntityPlatformState.ADDED or self._sensor_max_value_age <= 0:
            return

        ages = [
            state_age_seconds(state)
            for entity_id in (
                self.inside_sensor_entity_id,
                self.humidity_sensor_entity_id,
                *self.outside_sensor_entities,
            )
            if entity_id is not None
            and (state := self.hass.states.get(entity_id)) is not None
            and not is_state_stale(state, self._sensor_max_value_age)
        ]
        if ages:
            self._sensor_stale_unsub = async_call_later(
                self.hass,
                self._sensor_max_value_age - max(ages) + 1,
                HassJob(callback(lambda _now: self.async_write_ha_state())),
            )

    @override
    async def async_will_remove_from_hass(self) -> None:
        if self._control_heating_loop_unsub is not None:
            self._control_heating_loop_unsub()
            self._control_heating_loop_unsub = None

        if self._sensor_stale_unsub is not None:
            self._sensor_stale_unsub()
            self._sensor_stale_unsub = None

        if self._window_sensor_handle is not None:
            self._window_sensor_handle.cancel()
            self._window_sensor_handle = None

        if self._loop_measurement_task is not None:
            self._loop_measurement_task.cancel()
            self._loop_measurement_task = None

    async def _async_started(self, _hass: HomeAssistant) -> None:
        await self._register_event_listeners()
        await self.async_control_heating_loop()

    async def _register_event_listeners(self) -> None:
        """Register event listeners."""
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self.schedule_control_heating_loop, timedelta(seconds=30)
            )
        )

        self.async_on_remove(self.coordinator.async_add_listener(self.async_track_coordinator_data))

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.inside_sensor_entity_id], self._async_inside_sensor_changed
            )
        )

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self.outside_sensor_entities, self._async_outside_entity_changed
            )
        )

        if self.thermostat is not None:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self.thermostat, self._async_thermostat_changed
                )
            )

        if self.humidity_sensor_entity_id is not None:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self.humidity_sensor_entity_id], self._async_inside_sensor_changed
                )
            )

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._radiators, self._async_main_climate_changed
            )
        )

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self.areas.items(), self._async_climate_changed
            )
        )

        if self._valve_opening_time > 0:
            # Valves already asking for heat at startup have had their time to open
            opened = monotonic() - self._valve_opening_time
            for entity_id in self._radiators + self.areas.items():
                if self._climate_wants_heat(self.hass.states.get(entity_id)):
                    self._valves_opening_since[entity_id] = opened

            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._radiators + self.areas.items(),
                    self._async_valve_climate_changed,
                )
            )

        for entity_id in self.areas.items():
            state = self.hass.states.get(entity_id)
            if state is not None and (
                sensor_temperature_id := state.attributes.get(SENSOR_TEMPERATURE_ID)
            ):
                self.async_track_sensor_temperature(sensor_temperature_id)

    async def _restore_previous_state_or_set_defaults(self) -> None:
        """Restore the previous state if available or set default values."""
        old_state = await self.async_get_last_state()
        extra_data = await self.async_get_last_extra_data()

        if extra_data is not None:
            restored = SatClimateExtraStoredData.from_dict(extra_data.as_dict())

            if restored.hvac_mode in self.hvac_modes:
                self._attr_hvac_mode = HVACMode(restored.hvac_mode)

            if restored.target_temperature is not None:
                self._attr_native_target_temperature = float(restored.target_temperature)

            if self.preset_modes is not None and restored.preset_mode in self.preset_modes:
                self._attr_preset_mode = restored.preset_mode

            if restored.pre_custom_temperature is not None:
                self._pre_custom_temperature = float(restored.pre_custom_temperature)

        # Unavailable or unknown placeholder states carry no attributes worth restoring
        if old_state is not None and old_state.state not in self.hvac_modes:
            old_state = None

        if old_state is not None:
            self.pwm.restore(old_state)
            self.pid.restore(old_state)

            if self.native_target_temperature is None:
                if old_state.attributes.get(ATTR_TEMPERATURE) is None:
                    self._attr_native_target_temperature = float(self._presets[PRESET_HOME])
                    _LOGGER.warning(
                        "Undefined target temperature, falling back to %s",
                        self.native_target_temperature,
                    )
                else:
                    self._attr_native_target_temperature = float(
                        old_state.attributes[ATTR_TEMPERATURE]
                    )

            if self.hvac_mode is None:
                self._attr_hvac_mode = HVACMode(old_state.state)

            if old_state.attributes.get(ATTR_SETPOINT):
                self._setpoint = old_state.attributes.get(ATTR_SETPOINT)

            if extra_data is None and old_state.attributes.get(ATTR_PRESET_MODE):
                self._attr_preset_mode = old_state.attributes.get(ATTR_PRESET_MODE)

            if old_state.attributes.get(ATTR_PRE_ACTIVITY_TEMPERATURE):
                self._pre_activity_temperature = old_state.attributes.get(
                    ATTR_PRE_ACTIVITY_TEMPERATURE
                )

            if old_state.attributes.get(ATTR_PRE_CUSTOM_TEMPERATURE):
                self._pre_custom_temperature = old_state.attributes.get(ATTR_PRE_CUSTOM_TEMPERATURE)

            if optimal_coefficient := old_state.attributes.get(ATTR_OPTIMAL_COEFFICIENT):
                self.heating_curve.restore_autotune(
                    optimal_coefficient,
                    old_state.attributes.get(ATTR_COEFFICIENT_DERIVATIVE),
                )

            if old_state.attributes.get(ATTR_ROOMS):
                self._rooms = old_state.attributes.get(ATTR_ROOMS)
            else:
                await self._async_update_rooms_from_climates()
        else:
            if self._rooms is None:
                await self._async_update_rooms_from_climates()

            if self.native_target_temperature is None:
                self._attr_native_target_temperature = float(self._presets[PRESET_HOME])
                _LOGGER.info(
                    "Nothing to restore, starting at the home temperature %s",
                    self.native_target_temperature,
                )

            if self.hvac_mode is None:
                self._attr_hvac_mode = self._default_hvac_mode

        if self._attr_preset_mode != PRESET_NONE and self._pre_custom_temperature is None:
            self._pre_custom_temperature = self.native_target_temperature

        self.async_write_ha_state()

    async def async_stop_control(self) -> None:
        """Wait for a running control loop and stop sending boiler commands."""
        async with self._control_lock:
            self.control_paused = True

    @contextlib.asynccontextmanager
    async def async_calibrating(self) -> AsyncGenerator[None]:
        """Pause control while the current task calibrates, so off, unload and stop cancel it."""
        self.calibration = asyncio.current_task()
        try:
            await self.async_stop_control()
            self.async_write_ha_state()
            yield
        finally:
            self.calibration = None
            self.control_paused = False
            self._last_control_at = dt_util.utcnow()
            self.async_write_ha_state()

    async def async_cancel_calibration(self) -> None:
        if (calibration := self.calibration) is not None:
            calibration.cancel()
            await asyncio.wait([calibration])

    async def async_reset_integral(self) -> None:
        """Reset the integral part of the PID controllers."""
        self.pid.reset()
        self.areas.pids.reset()

    async def async_set_pulse_width_modulation(self, *, enabled: bool) -> None:
        """Enable or disable Pulse Width Modulation."""
        if enabled:
            self.pwm.enable()
        else:
            self.pwm.disable()

    @override
    @property
    def extra_restore_state_data(self) -> SatClimateExtraStoredData:
        return SatClimateExtraStoredData(
            self.hvac_mode,
            self.native_target_temperature,
            self._attr_preset_mode,
            self._pre_custom_temperature,
        )

    def compute_extra_state_attributes(self) -> dict[str, Any]:
        inside_temperature = self._get_entity_state_float(self.inside_sensor_entity_id)

        return {
            "error": self.max_error.value,
            "error_pid": self.pid.last_error,
            "error_source": self.max_error.entity_id,
            "integral": self.pid.integral,
            "derivative": self.pid.derivative,
            "proportional": self.pid.proportional,
            "integral_enabled": self.pid.integral_enabled,
            "boiler_flame_timing": self._coordinator.flame.average_on_time_seconds,
            "boiler_temperature_cold": self._coordinator.boiler_temperature_cold,
            "boiler_temperature_tracking": self._coordinator.boiler_temperature_tracking,
            "boiler_temperature_derivative": round(derivative, 3)
            if (derivative := self._coordinator.boiler_temperature_derivative) is not None
            else None,
            "pre_custom_temperature": self._pre_custom_temperature,
            "pre_activity_temperature": self._pre_activity_temperature,
            "derivative_enabled": self.pid.derivative_enabled,
            "derivative_raw": self.pid.raw_derivative,
            "current_kp": self.pid.kp,
            "current_ki": self.pid.ki,
            "current_kd": self.pid.kd,
            "rooms": self._rooms,
            "setpoint": self._setpoint,
            "current_humidity": self.current_humidity,
            "summer_simmer_index": SummerSimmer.index(inside_temperature, self.current_humidity),
            "summer_simmer_perception": SummerSimmer.perception(
                inside_temperature, self.current_humidity
            ),
            "valves_open": self.valves_open,
            "heating_curve": self.heating_curve.value,
            "requested_setpoint": self.requested_setpoint,
            "minimum_setpoint": self.minimum_setpoint_value,
            "outside_temperature": self.current_outside_temperature,
            "optimal_coefficient": self.heating_curve.optimal_coefficient,
            "coefficient_derivative": self.heating_curve.coefficient_derivative,
            "relative_modulation_value": self.relative_modulation_value,
            "relative_modulation_enabled": self.relative_modulation.enabled,
            "relative_modulation_state": self.relative_modulation_state.name,
            "pulse_width_modulation_enabled": self.pulse_width_modulation_enabled,
            "pulse_width_modulation_state": self.pwm.status.name,
            "heating_kept_on_in_pwm_off": self._heating_is_kept_on,
            "pulse_width_modulation_duty_cycle": self.pwm.duty_cycle,
            **(
                {"heat_budget_mode": self._heat_budget_mode, **self.heat_budget.attributes}
                if self.heat_budget is not None
                else {}
            ),
            **(self.boiler_diagnostics.attributes if self.boiler_diagnostics is not None else {}),
            **self._extras_attributes(),
        }

    def _extras_attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        if self.warm_weather is not None:
            attributes.update(self.warm_weather.attributes)
        if self.hot_water_schedule is not None:
            attributes["hot_water_setpoint_sent"] = self._hot_water_setpoint_sent
            attributes.update(self.hot_water_schedule.attributes)
        if self.presence is not None:
            attributes["occupancy"] = self.presence.state.value
        if self.window_detector is not None:
            attributes["window_open_detected"] = self._window_detected
        if (transfer := self.curve_advisor.transfer_kw_per_k) is not None:
            attributes["floor_heat_transfer_w_per_k"] = round(transfer * 1000)
        attributes["suggested_heating_curve_coefficient"] = self._suggested_coefficient()
        if self.loop_measurement is not None and self.loop_measurement.running:
            attributes["loop_measurement_step"] = self.loop_measurement.step
        if self._loop_measurement_result is not None:
            attributes["loop_measurement"] = self._loop_measurement_result
        return attributes

    def _suggested_coefficient(self) -> float | None:
        budget = self.heat_budget
        target = self.native_target_temperature
        if budget is None or not budget.ready or target is None:
            return None
        return self.curve_advisor.suggest(
            self.heating_curve,
            heat_loss_kw_per_k=budget.heat_loss,
            target=target,
            water_flow_lpm=self._last_water_flow,
        )

    @callback
    def _async_update_sensor_values(self) -> None:
        """Read the inside temperature and humidity from their sensors.

        Sensors go stale by age without firing a state change, so readers refresh first.
        """
        if self.humidity_sensor_entity_id is None:
            self._attr_current_humidity = None
        else:
            self._attr_current_humidity = self._get_entity_state_float(
                self.humidity_sensor_entity_id
            )

        current_temperature = self._get_entity_state_float(self.inside_sensor_entity_id)
        if current_temperature is not None and self._thermal_comfort:
            current_temperature = SummerSimmer.index(current_temperature, self.current_humidity)

        self._attr_native_current_temperature = current_temperature

    @property
    def error(self) -> float:
        """Return the error value."""
        if self.native_target_temperature is None or self.native_current_temperature is None:
            return 0

        return round(self.native_target_temperature - self.native_current_temperature, 2)

    @property
    def current_outside_temperature(self) -> float | None:
        """Return the current outside temperature."""
        self.outside_sensor_entities.sort(key=lambda x: "sensor" not in x)
        for entity_id in self.outside_sensor_entities:
            state = self.hass.states.get(entity_id)
            if (
                state is None
                or state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]
                or is_state_stale(state, self._sensor_max_value_age)
            ):
                continue

            if sensor.DOMAIN in entity_id and (value := float_value(state.state)) is not None:
                return value

            if (
                weather.DOMAIN in entity_id
                and (value := float_value(state.attributes.get("temperature"))) is not None
            ):
                return value

        return None

    @property
    def errors(self) -> Errors:
        errors = Errors([Error(self.entity_id, self.error)])
        if self._heating_mode == HEATING_MODE_ECO:
            return errors

        return errors + self.areas.errors

    @property
    def max_error(self) -> Error:
        return max(self.errors, key=lambda error: error.value)

    @property
    def setpoint(self) -> float | None:
        return self._setpoint

    @property
    def requested_setpoint(self) -> float:
        """Get the requested setpoint based on the heating curve and PID output."""
        if self.heating_curve.value is None:
            return MINIMUM_SETPOINT

        return round(max(self.heating_curve.value + self.pid.output, MINIMUM_SETPOINT), 1)

    @property
    def valves_open(self) -> bool:
        """Determine if any of the controlled climates have open valves."""
        # Get the list of all controlled climates
        climates = self._radiators + self.areas.items()

        # If there are no radiators, we can safely assume the valves are open
        if len(self._radiators) == 0:
            return True

        # Iterate through each controlled thermostat
        for climate in climates:
            # Get the current state of the thermostat
            state = self.hass.states.get(climate)

            # If the thermostat is unavailable or has an unknown state, skip it
            if state is None or state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                continue

            # If the thermostat is turned off, skip it
            if state.state == HVACMode.OFF:
                continue

            if is_heating_blocked(state):
                continue

            # If the thermostat reports that it is heating, we can assume the valves are open
            if state.attributes.get("hvac_action") == HVACAction.HEATING:
                return True

            # If the thermostat does not support hvac action, we can assume the valves are
            # open if the current temperature is not at the target temperature
            if state.attributes.get("hvac_action") is None:
                target_temperature = float_value(state.attributes.get("temperature"))
                current_temperature = float_value(state.attributes.get("current_temperature"))

                # If there is a current temperature, and it is not at the target temperature,
                # we can assume the valves are open
                if (
                    current_temperature is not None
                    and target_temperature is not None
                    and target_temperature >= current_temperature + self._climate_valve_offset
                ):
                    return True

        # If none of the thermostats have open valves, return False
        return False

    @property
    def pulse_width_modulation_enabled(self) -> bool:
        """Return True if pulse width modulation is enabled, False otherwise."""
        if not self._coordinator.supports_setpoint_management:
            return True

        # A learned heat budget doses the burner in blocks, unless the house needs more than
        # the minimum power: then the curve and the boiler's own modulation take over
        budget = self._driving_budget
        if budget is not None and budget.ready:
            if not budget.overloaded:
                return True
        elif self._force_pulse_width_modulation:
            return True

        if not self._overshoot_protection or self._calculated_setpoint is None:
            return False

        if not self._dynamic_minimum_setpoint:
            hysteresis = PWM_HYSTERESIS if self.pwm.status != PWMStatus.IDLE else 0.0
            return self._coordinator.minimum_setpoint + hysteresis > self._calculated_setpoint

        if self._minimum_setpoint_version == DYNAMIC_MINIMUM_SETPOINT_VERSION_1:
            return self.minimum_setpoint_value > self._calculated_setpoint

        return self.pwm.enabled

    @property
    def control_problems(self) -> list[str]:
        """Return why SAT is not controlling the boiler while it should be."""
        if (
            self.hvac_mode != HVACMode.HEAT
            or self.control_paused
            or self.hass.state is not CoreState.running
        ):
            return []

        problems = []
        if not self._coordinator.online:
            problems.append("gateway_offline")

        if (
            self.native_current_temperature is None
            or self.native_target_temperature is None
            or self.current_outside_temperature is None
        ):
            problems.append("inputs_missing")

        if (
            self._coordinator.boiler_temperature is None
            and not self._coordinator.awaiting_boiler_data
        ):
            problems.append("boiler_data_missing")

        if not problems and dt_util.utcnow() - self._last_control_at > CONTROL_LOOP_STALL_TIME:
            problems.append("control_loop_stalled")

        return problems

    @property
    def relative_modulation_value(self) -> int:
        if (
            not self.relative_modulation.enabled
            and self._coordinator.supports_relative_modulation_management
        ):
            return MINIMUM_RELATIVE_MODULATION

        # Heating left enabled in an off-phase is not meant to burn, so any burn stays minimal
        if self._heating_is_kept_on and not self._coordinator.hot_water_active:
            return MINIMUM_RELATIVE_MODULATION

        # The loop measurement reads the flow from the minimum power
        if self._measuring_loops and not self._coordinator.hot_water_active:
            return MINIMUM_RELATIVE_MODULATION

        return self._maximum_relative_modulation

    @property
    def relative_modulation_state(self) -> RelativeModulationState:
        return self.relative_modulation.state

    @property
    def minimum_setpoint_value(self) -> float:
        """Get the minimum allowable setpoint temperature."""
        if self._dynamic_minimum_setpoint:
            # Version 1: Use MinimumSetpoint controller
            if self._minimum_setpoint_version == DYNAMIC_MINIMUM_SETPOINT_VERSION_1:
                return max(self.minimum_setpoint.current, self._coordinator.minimum_setpoint)

            # Version 2: Use Pulse Width Modulation controller
            if self._minimum_setpoint_version == DYNAMIC_MINIMUM_SETPOINT_VERSION_2:
                return max(self.pwm.setpoint, self._coordinator.minimum_setpoint)

        # Default to coordinator's minimum setpoint
        return self._coordinator.minimum_setpoint

    def _calculate_control_setpoint(self) -> float:
        """Calculate the control setpoint based on the heating curve and PID output."""
        if self.heating_curve.value is None:
            return MINIMUM_SETPOINT

        return self.requested_setpoint

    async def _async_thermostat_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle changes to the connected thermostat."""
        old_state = event.data.get("old_state")
        if old_state is None or old_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        # A thermostat in off or auto reports no setpoint
        if (temperature := new_state.attributes.get("temperature")) is None:
            return

        if (
            old_state.state != new_state.state
            or old_state.attributes.get("temperature") != temperature
        ):
            _LOGGER.debug("Thermostat State Changed.")
            await self.async_set_target_temperature(temperature, cascade=False)

    async def _async_inside_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle changes to the inside temperature or humidity sensor."""
        self._async_update_sensor_values()

        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        _LOGGER.debug("Inside Sensor Changed.")
        self.async_write_ha_state()

        self._async_control_pid()
        self.schedule_control_heating_loop()

    async def _async_outside_entity_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle changes to the outside entity."""
        if event.data.get("new_state") is None:
            return

        _LOGGER.debug("Outside Sensor Changed.")
        self.async_write_ha_state()

        self._async_control_pid()
        self.schedule_control_heating_loop()

    async def _async_main_climate_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle changes to the main climate entity."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        if old_state is None or new_state.state != old_state.state:
            _LOGGER.debug("Main Climate State Changed (%s).", new_state.entity_id)
            self.schedule_control_heating_loop()

    async def _async_climate_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle changes to the climate entity.

        If the state, target temperature, or current temperature of the climate
        entity has changed, update the PID controller and heating control.
        """
        # Get the new state of the climate entity
        new_state = event.data.get("new_state")

        # Return if the new state is not available
        if not new_state:
            return

        # Get the old state of the climate entity
        old_state = event.data.get("old_state")

        # Get the attributes of the new state
        new_attrs = new_state.attributes

        # Get the attributes of the old state, if available
        old_attrs = old_state.attributes if old_state else {}

        _LOGGER.debug("Climate State Changed (%s).", new_state.entity_id)

        # Check if the last state is None, so we can track the attached sensor if needed
        if old_state is None and (sensor_temperature_id := new_attrs.get(SENSOR_TEMPERATURE_ID)):
            self.async_track_sensor_temperature(sensor_temperature_id)

        # If the state has changed or the old state is not available, update the PID controller
        if (
            not old_state
            or new_state.state != old_state.state
            or new_attrs.get("temperature") != old_attrs.get("temperature")
            or is_heating_blocked(new_state) != is_heating_blocked(old_state)
        ):
            self._async_control_pid(reset=True)

        # If the current temperature has changed, update the PID controller
        elif SENSOR_TEMPERATURE_ID not in new_attrs and new_attrs.get(
            "current_temperature"
        ) != old_attrs.get("current_temperature"):
            self._async_control_pid()

        # A synced preset writes its own temperature to the rooms,
        # which must not replace the home targets
        if (
            self._rooms is not None
            and (
                new_state.entity_id not in self._rooms
                or not self._sync_climates_with_preset
                or self.preset_mode == PRESET_HOME
            )
            and (target_temperature := new_attrs.get("temperature"))
        ):
            self._rooms[new_state.entity_id] = float(target_temperature)

        # Update the heating control
        self.schedule_control_heating_loop()

    async def _async_temperature_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle changes to the climate sensor entity."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        _LOGGER.debug("Climate Sensor Changed (%s).", new_state.entity_id)
        self._async_control_pid()
        self.schedule_control_heating_loop()

    async def async_window_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle changes to the contact sensor entity."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        _LOGGER.debug("Window Sensor Changed to %s.", new_state.state)

        if new_state.state == STATE_ON:
            if self.preset_mode == PRESET_ACTIVITY or (
                self._window_sensor_handle is not None and not self._window_sensor_handle.done()
            ):
                return

            try:
                self._window_sensor_handle = asyncio.create_task(
                    asyncio.sleep(self._window_minimum_open_time)
                )
                self._pre_activity_temperature = self.native_target_temperature or self.min_temp

                await self._window_sensor_handle
                await self.async_set_preset_mode(PRESET_ACTIVITY)
            except asyncio.CancelledError:
                _LOGGER.debug("Window closed before minimum open time.")

            return

        if new_state.state == STATE_OFF:
            if self._window_sensor_handle is not None:
                self._window_sensor_handle.cancel()
                self._window_sensor_handle = None

            if self.preset_mode == PRESET_ACTIVITY:
                _LOGGER.debug("Restoring original target temperature.")
                await self.async_set_temperature(temperature=self._pre_activity_temperature)

            return

    def _async_control_pid(self, *, reset: bool = False) -> None:
        """Control the PID controller."""
        self._async_update_sensor_values()

        # We can't continue if we don't have a valid outside temperature
        outside_temperature = self.current_outside_temperature
        if outside_temperature is None:
            return

        # Reset the PID controller if the sensor data is too old
        if is_state_stale(
            self.hass.states.get(self.inside_sensor_entity_id), self._sensor_max_value_age
        ):
            self.pid.reset()
            self.areas.pids.reset()

        # Calculate the maximum error between the current temperature
        # and the target temperature of all climates
        max_error = self.max_error

        # Make sure we use the latest heating curve value
        if self.native_target_temperature is not None:
            self.areas.heating_curves.update(outside_temperature)
            self.heating_curve.update(self.native_target_temperature, outside_temperature)

        # Update the PID controller with the maximum error
        if not reset:
            _LOGGER.debug(
                "Updating error to %s from %s (Reset: False)", max_error.value, max_error.entity_id
            )

            # Calculate an optimal heating curve when we are in the deadband
            if (
                self.native_target_temperature is not None
                and -DEADBAND <= max_error.value <= DEADBAND
            ):
                self.heating_curve.autotune(
                    setpoint=self.requested_setpoint,
                    target_temperature=self.native_target_temperature,
                    outside_temperature=outside_temperature,
                )

            # Update our PID controllers if we have valid values
            if self._coordinator.boiler_temperature is not None:
                self.areas.pids.update()

                if self.heating_curve.value is not None:
                    self.pid.update(max_error, self.heating_curve.value)

        elif max_error.value != self.pid.last_error:
            _LOGGER.debug(
                "Updating error to %s from %s (Reset: True)", max_error.value, max_error.entity_id
            )

            self.pid.update_reset(error=max_error, heating_curve_value=self.heating_curve.value)
            self._calculated_setpoint = None

        self.async_write_ha_state()

    async def _async_control_setpoint(
        self, pwm_state: PWMState, calculated_setpoint: float
    ) -> None:
        """Control the setpoint of the heating system based on the current mode and PWM state."""
        if self._measuring_loops:
            # Keep the burner on at minimum power while the loops are measured
            self._setpoint = self._coordinator.maximum_setpoint
            await self._coordinator.async_set_control_setpoint(self._setpoint)
            return

        if not self.pulse_width_modulation_enabled or pwm_state.status == PWMStatus.IDLE:
            # Normal cycle without PWM
            self._setpoint = calculated_setpoint
            _LOGGER.debug(
                "Pulse Width Modulation is disabled or in IDLE state. Running normal heating cycle."
            )
            _LOGGER.debug("Calculated setpoint for normal cycle: %.1f°C", calculated_setpoint)

            # Some final checks to see if it's even warm, or if any heat can go anywhere
            if self._setpoint < COLD_SETPOINT or not self._valves_open:
                self._setpoint = MINIMUM_SETPOINT
                _LOGGER.debug(
                    "Calculated setpoint is too cold. Setting setpoint to minimum: %.1f°C",
                    MINIMUM_SETPOINT,
                )
        else:
            # PWM is enabled and actively controlling the cycle
            _LOGGER.debug("Running PWM cycle with state: %s", pwm_state.status)

            if pwm_state.status == PWMStatus.ON:
                self._setpoint = self.minimum_setpoint_value
                _LOGGER.debug("Setting setpoint to minimum: %.1f°C", self._setpoint)
            else:
                self._setpoint = MINIMUM_SETPOINT
                _LOGGER.debug("Setting setpoint to absolute minimum: %.1f°C", MINIMUM_SETPOINT)

        # Apply the setpoint using the coordinator
        self._setpoint = min(self._setpoint, self._coordinator.maximum_setpoint)
        await self._coordinator.async_set_control_setpoint(self._setpoint)
        _LOGGER.debug("Control setpoint has been updated to: %.1f°C", self._setpoint)

    async def _async_control_relative_modulation(self) -> None:
        """Control the relative modulation value based on the conditions."""
        if not self._coordinator.supports_relative_modulation_management:
            _LOGGER.debug("Relative modulation management is not supported. Skipping control.")
            return

        # Update relative modulation state
        await self.relative_modulation.update(
            pulse_width_modulation_enabled=self.pulse_width_modulation_enabled
        )

        # Retrieve the relative modulation
        relative_modulation_value = self.relative_modulation_value

        # Apply some filters based on the manufacturer
        if isinstance(self._coordinator.manufacturer, Geminox):
            relative_modulation_value = max(10, relative_modulation_value)

        # Determine if the value needs to be updated
        if (
            self._coordinator.control_max_relative_modulation
            == relative_modulation_value
            == self._coordinator.maximum_relative_modulation_value
        ):
            _LOGGER.debug(
                "Relative modulation value unchanged (%d%%). No update necessary.",
                relative_modulation_value,
            )
            return

        await self._coordinator.async_set_control_max_relative_modulation(relative_modulation_value)

    async def _async_update_rooms_from_climates(self) -> None:
        """Update the temperature setpoint for each room based on its climate entity."""
        self._rooms = {}

        # Iterate through each climate entity
        for entity_id in self.areas.items():
            state = self.hass.states.get(entity_id)

            # Skip any entities that are unavailable or have an unknown state
            if not state or state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
                continue

            # Retrieve the target temperature from the climate entity's attributes
            target_temperature = state.attributes.get("temperature")

            # If the target temperature exists, store it in the _rooms dictionary
            # with the climate entity as the key
            if target_temperature is not None:
                self._rooms[entity_id] = float(target_temperature)

    def reset_control_state(self) -> None:
        """Reset control state when major changes occur."""
        self.pwm.disable()
        self._calculated_setpoint = None

    def async_track_sensor_temperature(self, entity_id: str) -> None:
        """Track the temperature of the sensor specified by the given entity_id.

        If the sensor is already being tracked, the method will return without doing anything.
        Otherwise, it will register a callback for state changes on the specified sensor
        and start tracking its temperature.
        """
        if entity_id in self._sensors:
            return

        self.async_on_remove(
            async_track_state_change_event(self.hass, [entity_id], self._async_temperature_change)
        )

        self._sensors.append(entity_id)

    @callback
    def schedule_control_heating_loop(
        self,
        _time: datetime | None = None,
        *,
        force: bool = False,
    ) -> None:
        """Schedule a debounced execution of the heating control loop."""
        # Force immediate execution
        if force:
            # Cancel previous scheduled run, if any
            if self._control_heating_loop_unsub is not None:
                self._control_heating_loop_unsub()
                self._control_heating_loop_unsub = None

            self.hass.async_create_task(self.async_control_heating_loop())
            return

        # If a run is already scheduled, do nothing.
        if self._control_heating_loop_unsub is not None:
            return

        self._control_heating_loop_unsub = async_call_later(
            self.hass, 10, HassJob(self.async_control_heating_loop)
        )

    async def async_control_heating_loop(self, _time: datetime | None = None) -> None:
        """Control the heating from the current, target and outside temperatures."""
        if self._control_heating_loop_unsub is not None:
            self._control_heating_loop_unsub()
            self._control_heating_loop_unsub = None

        async with self._control_lock:
            self._async_update_sensor_values()

            # Totals and diagnostics also run while SAT is off, so summer hot water counts too
            self._run_guarded("monitors", self._update_monitors)
            await self._async_run_guarded("hot water", self._async_control_hot_water)

            # No need to do anything if we are not on, or while something else drives the boiler
            if (
                self.hvac_mode != HVACMode.HEAT
                or self.control_paused
                or not self._coordinator.online
            ):
                return

            await self._async_run_guarded("presence", self._async_update_presence)
            await self._async_run_guarded("window detection", self._async_detect_window)

            # A sensor that stops reporting fires no state change,
            # so the stale reset has to happen here
            if is_state_stale(
                self.hass.states.get(self.inside_sensor_entity_id), self._sensor_max_value_age
            ):
                self.pid.reset()
                self.areas.pids.reset()

            outside_temperature = self.current_outside_temperature
            if (
                self.native_current_temperature is None
                or self.native_target_temperature is None
                or outside_temperature is None
            ):
                if self._inputs_missing_since is None:
                    self._inputs_missing_since = dt_util.utcnow()

                # The gateway hands the boiler back to the room thermostat
                # when the override is not refreshed
                if (
                    self._setpoint is not None
                    and dt_util.utcnow() - self._inputs_missing_since < INPUTS_MISSING_GRACE_PERIOD
                ):
                    await self._coordinator.async_set_control_setpoint(
                        min(self._setpoint, self._coordinator.maximum_setpoint)
                    )
                elif (
                    dt_util.utcnow() - self._inputs_missing_since >= INPUTS_MISSING_GRACE_PERIOD
                    and not self._inputs_missing_released
                ):
                    _LOGGER.warning(
                        "Inputs missing for %s, handing the boiler back to the room thermostat.",
                        INPUTS_MISSING_GRACE_PERIOD,
                    )
                    self._setpoint = None
                    self._inputs_missing_released = True
                    await self._coordinator.async_release_control()
                    self.async_write_ha_state()

                return

            # The PID timers kept aging while the boiler was handed back,
            # and the integral would apply the current error to the whole outage
            if self._inputs_missing_released:
                self.pid.reset()
                self.areas.pids.reset()
                self._async_control_pid(reset=True)

            self._inputs_missing_since = None
            self._inputs_missing_released = False

            # An outside source that goes stale fires no state change
            self.areas.heating_curves.update(outside_temperature)
            self.heating_curve.update(self.native_target_temperature, outside_temperature)

            # Control the heating through the coordinator
            await self._coordinator.async_control_heating_loop(pwm_state=self.pwm.state)

            # Warm weather: central heating stays off, hot water keeps working
            if self._warm_weather_shutdown():
                self.pwm.reset()
                self._setpoint = MINIMUM_SETPOINT
                await self._coordinator.async_set_control_setpoint(MINIMUM_SETPOINT)
                await self.async_set_heater_state(DeviceState.OFF)
                self._last_control_at = dt_util.utcnow()
                self.async_write_ha_state()
                return

            if self._calculated_setpoint is None:
                # Default to the calculated setpoint
                self._calculated_setpoint = self._calculate_control_setpoint()
            else:
                # Apply low filter on the requested setpoint
                self._calculated_setpoint = round(
                    self._alpha * self._calculate_control_setpoint()
                    + (1 - self._alpha) * self._calculated_setpoint,
                    1,
                )

            # Check for overshoot
            if self._coordinator.device_status == BoilerStatus.OVERSHOOT_HANDLING:
                _LOGGER.info("Overshoot Handling detected, enabling Pulse Width Modulation.")
                self.pwm.enable()

            # Without open valves there is no demand,
            # so PWM stays idle and the boiler is held at the minimum setpoint
            if (valves_open := self.valves_open) != self._valves_open:
                if valves_open:
                    _LOGGER.info("Valves opened, resuming the heating cycle.")
                else:
                    _LOGGER.info("No valves are open, holding the boiler at the minimum setpoint.")

                self._valves_open = valves_open

            # The heat budget learns in every mode and decides the blocks when it drives
            self._run_guarded("heat budget", self._update_heat_budget)

            # Pulse Width Modulation
            if not self.pulse_width_modulation_enabled:
                self.pwm.reset()
            elif not valves_open:
                self.pwm.reset()
                self.pwm.enable()
            else:
                await self.pwm.update(
                    flame=self._coordinator.flame,
                    boiler=self._coordinator.boiler,
                    requested_setpoint=self._calculated_setpoint,
                )

            # The next flame-off must be judged against the PWM state after this step
            self._coordinator.update_flame(pwm_state=self.pwm.state)

            # Set the control setpoint to make sure we always stay in control
            await self._async_control_setpoint(self.pwm.state, self._calculated_setpoint)
            self._last_control_at = dt_util.utcnow()

            # Set the relative modulation value, if supported
            await self._async_control_relative_modulation()

            if (
                self._push_setpoint_to_thermostat
                and self._coordinator.control_thermostat_setpoint != self.native_target_temperature
            ):
                await self._coordinator.async_set_control_thermostat_setpoint(
                    self.native_target_temperature
                )

            # Apply an error change that arrived inside the sample time,
            # then control the integral (if exceeded the time limit)
            if self._coordinator.boiler_temperature is not None:
                self.areas.pids.update()

            if self.heating_curve.value is not None:
                if self._coordinator.boiler_temperature is not None:
                    self.pid.update(self.max_error, self.heating_curve.value)

                self.pid.update_integral(self.max_error, self.heating_curve.value)

            # Control our areas
            await self.areas.async_control_heating_loops()

            # Control our dynamic minimum setpoint (version 1)
            if not self._coordinator.hot_water_active and self._coordinator.flame_active:
                # Calculate the base return temperature
                if self._coordinator.device_status == BoilerStatus.HEATING_UP:
                    self.minimum_setpoint.warming_up(self._coordinator.boiler)

                # Calculate the dynamic minimum setpoint
                self.minimum_setpoint.calculate(self._coordinator.boiler, self.pwm.status)

            # If the setpoint is high, turn on the heater; the off-phase check runs every time
            # so it sees each off-phase start
            kept_on = self._heating_kept_on_in_pwm_off()
            await self.async_set_heater_state(
                DeviceState.ON
                if (self._setpoint is not None and self._setpoint > COLD_SETPOINT) or kept_on
                else DeviceState.OFF
            )

            self.async_write_ha_state()

    def _climate_wants_heat(self, state: State | None) -> bool:
        """Return whether a controlled climate asks for heat, the way valves_open judges it."""
        if state is None or state.state in [STATE_UNKNOWN, STATE_UNAVAILABLE, HVACMode.OFF]:
            return False

        if (hvac_action := state.attributes.get("hvac_action")) is not None:
            return bool(hvac_action == HVACAction.HEATING)

        target_temperature = float_value(state.attributes.get("temperature"))
        current_temperature = float_value(state.attributes.get("current_temperature"))
        return (
            current_temperature is not None
            and target_temperature is not None
            and target_temperature >= current_temperature + self._climate_valve_offset
        )

    async def _async_valve_climate_changed(self, event: Event[EventStateChangedData]) -> None:
        """Record when a controlled climate starts asking for heat, so its valve starts opening."""
        entity_id = event.data["entity_id"]
        if self._climate_wants_heat(event.data.get("new_state")):
            self._valves_opening_since.setdefault(entity_id, monotonic())
        else:
            self._valves_opening_since.pop(entity_id, None)

    def _valve_opening_remaining(self) -> float:
        """Return how long the boiler still waits for a valve that just started opening."""
        if self._valve_opening_time <= 0 or not self._valves_opening_since:
            return 0.0

        # One valve open long enough already gives the water somewhere to go
        opened_for = monotonic() - min(self._valves_opening_since.values())
        return max(0.0, self._valve_opening_time - opened_for)

    async def _async_refresh_weather_forecast(self, _time: datetime | None = None) -> None:
        """Fetch the hourly forecast the heat budget looks ahead with."""
        entity_id = self._weather_forecast_entity_id
        if not entity_id:
            return

        try:
            response = await self.hass.services.async_call(
                weather.DOMAIN,
                "get_forecasts",
                {"entity_id": entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, ValueError) as error:
            _LOGGER.debug("No hourly forecast from %s: %s", entity_id, error)
            return

        result = (response or {}).get(entity_id)
        entries = result.get("forecast") if isinstance(result, dict) else None
        forecast: list[tuple[datetime, float | None, float | None]] = []
        for entry in entries[:24] if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            if (when := dt_util.parse_datetime(str(entry.get("datetime")))) is None:
                continue
            temperature, cloud = entry.get("temperature"), entry.get("cloud_coverage")
            forecast.append(
                (
                    dt_util.as_utc(when),
                    float_value(temperature) if isinstance(temperature, int | float) else None,
                    float_value(cloud) if isinstance(cloud, int | float) else None,
                )
            )
        self._weather_forecast = forecast

    def _heat_budget_inputs(self) -> HeatBudgetInputs:
        """Collect what the heat budget needs for this control step."""
        coordinator = self._coordinator
        now_utc = dt_util.utcnow()
        minimum_power = self._minimum_power()
        heating_power = self._heating_power()

        # The heat released now reaches the rooms over the next hours
        horizon = now_utc + timedelta(hours=FORECAST_HORIZON_HOURS)
        upcoming = [
            entry
            for entry in self._weather_forecast
            if now_utc - timedelta(hours=1) < entry[0] <= horizon
        ]
        temperatures = [temperature for _, temperature, _ in upcoming if temperature is not None]
        latitude, longitude = self.hass.config.latitude, self.hass.config.longitude
        sunshine = [
            sun_factor(when, latitude, longitude, cloud)
            for when, _, cloud in upcoming
            if cloud is not None
        ]
        solar = sunshine[0] if sunshine else None

        comfort: bool | None = None
        next_change: datetime | None = None
        if self._comfort_schedule_entity_id and (
            schedule := self.hass.states.get(self._comfort_schedule_entity_id)
        ):
            if schedule.state in ("on", "off"):
                comfort = schedule.state == "on"
            next_event = schedule.attributes.get("next_event")
            if isinstance(next_event, datetime):
                next_change = next_event
            elif next_event is not None:
                next_change = dt_util.parse_datetime(str(next_event))
            if next_change is not None:
                next_change = dt_util.as_utc(next_change)

        return HeatBudgetInputs(
            now=monotonic(),
            wall_time=now_utc,
            indoor=self.native_current_temperature,
            target=self.native_target_temperature,
            outdoor=self.current_outside_temperature,
            heating_power_kw=float(heating_power),
            minimum_power_kw=float(minimum_power),
            flame_active=coordinator.flame_active,
            hot_water_active=coordinator.hot_water_active,
            outdoor_forecast=sum(temperatures) / len(temperatures) if temperatures else None,
            solar=solar,
            solar_forecast=sum(sunshine) / len(sunshine) if sunshine else None,
            cut_short_burn_ends=coordinator.flame.cut_short_burn_ends,
            comfort=comfort,
            next_comfort_change=next_change,
            setback=self._setback_temperature,
        )

    def _gas_use(self) -> float | None:
        """Gas the burner uses now in m³/h, from the consumption options and the modulation."""
        if self._minimum_consumption <= 0 or self._maximum_consumption <= 0:
            return None

        modulation = float_value(self._coordinator.relative_modulation_value) or 0.0
        return self._minimum_consumption + modulation / 100 * (
            self._maximum_consumption - self._minimum_consumption
        )

    def _minimum_power(self) -> float:
        """Return the burner's lowest heat output in kW."""
        capacity = self._coordinator.minimum_boiler_capacity
        if capacity is not None and capacity > 0:
            return float(capacity)
        if self._minimum_consumption > 0:
            return self._minimum_consumption * self._gas_energy_content
        return 5.0

    def _heating_power(self) -> float:
        """Return the burner's heat output in kW while it burns."""
        power = self._coordinator.boiler_power
        if power is not None and power > 0:
            return float(power)
        if (gas := self._gas_use()) is not None:
            return gas * self._gas_energy_content
        return self._minimum_power()

    def _run_guarded(self, name: str, update: Callable[[], None]) -> None:
        """Keep a failure in the totals, diagnostics or heat budget from stopping the control."""
        try:
            update()
        except Exception:
            if name not in self._failed_monitors:
                _LOGGER.exception("SAT %s failed, the heating control continues without it", name)
                self._failed_monitors.add(name)
        else:
            self._failed_monitors.discard(name)

    async def _async_run_guarded(
        self, name: str, update: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        """Like _run_guarded, for the extras that call services."""
        try:
            await update()
        except Exception:
            if name not in self._failed_monitors:
                _LOGGER.exception("SAT %s failed, the heating control continues without it", name)
                self._failed_monitors.add(name)
        else:
            self._failed_monitors.discard(name)

    @property
    def _measuring_loops(self) -> bool:
        return self.loop_measurement is not None and self.loop_measurement.running

    def _forecast_mean(self, hours: float) -> float | None:
        now = dt_util.utcnow()
        values = [
            temperature
            for moment, temperature, _ in self._weather_forecast
            if temperature is not None and now <= moment <= now + timedelta(hours=hours)
        ]
        return sum(values) / len(values) if values else None

    def _warm_weather_shutdown(self) -> bool:
        if self.warm_weather is None or self._measuring_loops:
            return False

        active = self.warm_weather.update(
            monotonic(), self.current_outside_temperature, self._forecast_mean(12)
        )
        if active != self._warm_weather_was_active:
            _LOGGER.info(
                "Warm weather: central heating %s (daily mean %s °C).",
                "off" if active else "back on",
                self.warm_weather.mean,
            )
            if not active:
                # The integral aged through the whole pause
                self.pid.reset()
                self.areas.pids.reset()
            self._warm_weather_was_active = active
        return active

    async def _async_control_hot_water(self) -> None:
        schedule = self.hot_water_schedule
        if schedule is None:
            return

        comfort: bool | None = None
        if self._hot_water_schedule_entity_id and (
            state := self.hass.states.get(self._hot_water_schedule_entity_id)
        ):
            comfort = {STATE_ON: True, STATE_OFF: False}.get(state.state)

        target = schedule.target(
            dt_util.now(), comfort=comfort, temperature=self._coordinator.hot_water_temperature
        )
        target = min(
            max(target, self._coordinator.minimum_hot_water_setpoint),
            self._coordinator.maximum_hot_water_setpoint,
        )
        if target != self._hot_water_setpoint_sent:
            _LOGGER.info("Hot water schedule sets the cylinder to %.0f °C.", target)
            await self._coordinator.async_set_control_hot_water_setpoint(target)
            self._hot_water_setpoint_sent = target

    def _someone_home(self) -> bool | None:
        readings = [
            is_home(state.state if (state := self.hass.states.get(entity_id)) else None)
            for entity_id in self._presence_entity_ids
        ]
        known = [reading for reading in readings if reading is not None]
        if not known:
            return None
        return any(known)

    def _return_distance_km(self) -> float | None:
        if not self._proximity_entity_id:
            return None
        state = self.hass.states.get(self._proximity_entity_id)
        if state is None or (value := float_value(state.state)) is None:
            return None
        unit = state.attributes.get("unit_of_measurement")
        return value * DISTANCE_TO_KM.get(str(unit), 1.0)

    async def _async_update_presence(self) -> None:
        if self.presence is None:
            return

        previous = self.presence.state
        occupancy = self.presence.update(
            monotonic(), home=self._someone_home(), distance_km=self._return_distance_km()
        )
        if occupancy == previous:
            return

        if occupancy == Occupancy.AWAY:
            if self.preset_mode in (PRESET_NONE, PRESET_HOME, PRESET_COMFORT):
                _LOGGER.info("Nobody is home, switching to the away preset.")
                self._presence_previous_preset = self.preset_mode
                await self.async_set_preset_mode(PRESET_AWAY)
        elif self._presence_previous_preset is not None:
            if self.preset_mode == PRESET_AWAY:
                _LOGGER.info("Someone is %s, restoring the preset.", occupancy.value)
                await self.async_set_preset_mode(self._presence_previous_preset)
            self._presence_previous_preset = None

    async def _async_detect_window(self) -> None:
        if self.window_detector is None:
            return

        detected = self.window_detector.update(monotonic(), self.native_current_temperature)
        if detected == self._window_detected:
            return

        if detected:
            # A contact sensor that already set the activity preset stays in charge
            if self.preset_mode == PRESET_ACTIVITY:
                return
            _LOGGER.info("The room temperature drops fast, pausing the heating for a window.")
            self._pre_activity_temperature = self.native_target_temperature or self.min_temp
            await self.async_set_preset_mode(PRESET_ACTIVITY)
        elif self.preset_mode == PRESET_ACTIVITY:
            _LOGGER.info("No more fast drop, restoring the target.")
            await self.async_set_temperature(temperature=self._pre_activity_temperature)
        self._window_detected = detected

    async def async_measure_loops(self) -> None:
        """Measure the water flow of each loop, one room at a time."""
        if self._measuring_loops:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="loop_measurement_running"
            )
        rooms = self.loop_monitor.rooms if self.loop_monitor is not None else []
        if (
            not rooms
            or self.hvac_mode != HVACMode.HEAT
            or not self._coordinator.supports_setpoint_management
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="loop_measurement_unavailable"
            )

        self.loop_measurement = LoopMeasurement(
            self.hass,
            list(rooms),
            valve_seconds=self._valve_opening_time or 360,
            sample=lambda: self._flow_sample,
        )
        self._loop_measurement_task = self.hass.async_create_background_task(
            self._async_run_loop_measurement(self.loop_measurement), "sat_measure_loops"
        )

    async def _async_run_loop_measurement(self, measurement: LoopMeasurement) -> None:
        _LOGGER.info("Measuring the heating loops; this takes about 15 minutes per room.")
        self.schedule_control_heating_loop(force=True)
        try:
            result = await measurement.async_run()
        finally:
            self.schedule_control_heating_loop(force=True)

        self._loop_measurement_result = result.as_dict()
        lines = [f"- base (loops without actuator): {result.as_dict()['base_lpm']} l/min"]
        lines += [
            f"- {entity_id}: {flow} l/min"
            for entity_id, flow in result.as_dict()["loops_lpm"].items()
        ]
        persistent_notification.async_create(
            self.hass,
            "\n".join(lines),
            title=f"{self._config_entry.title}: loop flows",
            notification_id=f"{DOMAIN}_{self._config_entry.entry_id}_loop_measurement",
        )
        self.async_write_ha_state()

    def _update_monitors(self) -> None:
        """Feed the running totals, the loop monitor and the boiler diagnostics."""
        coordinator = self._coordinator
        now = monotonic()
        flame = coordinator.flame_active
        hot_water = coordinator.hot_water_active

        # Heating demand ends when PWM switches off or the boiler is no longer asked to heat
        device_active = coordinator.device_active
        if (self._last_pwm_status == PWMStatus.ON and self.pwm.status != PWMStatus.ON) or (
            self._last_device_active is True and not device_active
        ):
            self._heating_stopped_at = now
        self._last_pwm_status = self.pwm.status
        self._last_device_active = device_active

        if self._last_hot_water_active and not hot_water:
            self._hot_water_ended_at = now

        self.efficiency.update(
            now,
            flame=flame,
            hot_water=hot_water,
            exhaust=coordinator.exhaust_temperature,
            return_temperature=coordinator.return_temperature,
        )
        self._last_hot_water_active = hot_water

        heat = self._heating_power() if flame else None
        today = dt_util.now().date()
        self.boiler_stats.update(
            now=now,
            flame=flame,
            hot_water=hot_water,
            heat_kw=heat,
            gas_m3_per_hour=(
                (self._gas_use() or (heat or 0.0) / self._gas_energy_content) if flame else None
            ),
            outdoor=self.current_outside_temperature,
            hot_water_temperature=coordinator.hot_water_temperature,
            heating_stopped_at=self._heating_stopped_at,
            day=today.isoformat(),
            gas_price=self._gas_price,
        )

        on_time = coordinator.flame.latest_on_time_seconds
        settled = (
            flame and not hot_water and on_time is not None and on_time >= SETTLED_BURN_SECONDS
        )
        flow_sample = None
        if (
            settled
            and heat is not None
            and coordinator.boiler_temperature is not None
            and coordinator.return_temperature is not None
        ):
            flow_sample = estimate_water_flow(
                heat, coordinator.boiler_temperature, coordinator.return_temperature
            )
            if flow_sample is not None:
                self._last_water_flow = flow_sample
            indoor = self.native_current_temperature
            if on_time >= DIAGNOSTIC_BURN_SECONDS and indoor is not None:
                self.curve_advisor.update(
                    heat_kw=heat,
                    flow=coordinator.boiler_temperature,
                    return_temperature=coordinator.return_temperature,
                    indoor=indoor,
                )
        self._flow_sample = flow_sample

        if self.loop_monitor is not None:
            readings: dict[str, RoomReading] = {}
            for entity_id in self.loop_monitor.rooms:
                state = self.hass.states.get(entity_id)
                if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                    continue
                readings[entity_id] = RoomReading(
                    open=self._climate_wants_heat(state),
                    temperature=float_value(state.attributes.get("current_temperature")),
                )
            self.loop_monitor.update(now, readings, flow_sample)

        if self.boiler_diagnostics is not None:
            self.boiler_diagnostics.update(
                now,
                pressure=coordinator.water_pressure,
                fault=coordinator.boiler_fault_reported,
                fault_code=coordinator.boiler_fault_code_reported,
                exhaust=coordinator.exhaust_temperature,
                return_temperature=coordinator.return_temperature,
                settled_heating_burn=settled
                and on_time is not None
                and on_time >= DIAGNOSTIC_BURN_SECONDS,
                today=today,
                flow=coordinator.boiler_temperature,
                heating_burn=flame
                and not hot_water
                and (
                    self._hot_water_ended_at is None
                    or now - self._hot_water_ended_at > AFTER_HOT_WATER_SECONDS
                ),
                gas_use_ratio=self.boiler_stats.gas_per_degree_day_ratio,
            )

    def _update_heat_budget(self) -> None:
        if self.heat_budget is None:
            return

        self.heat_budget.update(self._heat_budget_inputs())
        overloaded = self._driving_budget is not None and self.heat_budget.overloaded
        if overloaded != self._budget_overloaded:
            if overloaded:
                _LOGGER.info(
                    "The house needs more than the minimum power, "
                    "handing the heat budget over to boiler modulation."
                )
            else:
                _LOGGER.info("The house needs less than the minimum power, heat budget resumes.")
            self._budget_overloaded = overloaded

    @property
    def _heating_is_kept_on(self) -> bool:
        """Return True if the last control step left heating enabled in a PWM off-phase."""
        return self._pwm_off_since is not None and self._keep_heating_suspended_until is None

    def _heating_kept_on_in_pwm_off(self) -> bool:
        """Return True if central heating stays enabled through this PWM off-phase."""
        if (
            not self._keep_heating_in_pwm_off
            or not self._coordinator.supports_setpoint_management
            or not self.pulse_width_modulation_enabled
            or self.pwm.status != PWMStatus.OFF
        ):
            self._pwm_off_since = None
            return False

        now = monotonic()
        if self._pwm_off_since is None:
            self._pwm_off_since = now

        if self._keep_heating_suspended_until is not None:
            if now < self._keep_heating_suspended_until:
                return False
            self._keep_heating_suspended_until = None

        # A boiler that raises the off-phase setpoint to its own minimum lights against it;
        # the on-phase flame is given time to go out first
        if (
            self._coordinator.flame_active
            and not self._coordinator.hot_water_active
            and now - self._pwm_off_since > KEEP_HEATING_FLAME_GRACE_SECONDS
        ):
            self._keep_heating_suspended_until = now + KEEP_HEATING_SUSPEND_SECONDS
            _LOGGER.warning(
                "The boiler lit during a PWM off-phase with heating left enabled; "
                "disabling heating between on-phases for the next %d minutes.",
                KEEP_HEATING_SUSPEND_SECONDS // 60,
            )
            return False

        return True

    async def async_set_heater_state(self, state: DeviceState) -> None:
        """Set the heater state, ensuring proper conditions are met."""
        _LOGGER.debug("Attempting to set heater state to: %s", state)

        if state == DeviceState.ON:
            if not self.valves_open:
                if self._coordinator.device_active:
                    _LOGGER.info("Valves closed while heater active. Turning off.")
                    await self._coordinator.async_set_heater_state(DeviceState.OFF)
                else:
                    _LOGGER.warning("Cannot turn on heater: no valves are open.")
                return

            if self._coordinator.device_active:
                _LOGGER.debug("Heater is already active. No action taken.")
                return

            if (remaining := self._valve_opening_remaining()) > 0:
                if not self._valve_wait_logged:
                    _LOGGER.info(
                        "Waiting %.0fs for the valves to open before lighting the boiler.",
                        remaining,
                    )
                    self._valve_wait_logged = True
                return

            self._valve_wait_logged = False

        elif not self._coordinator.device_active:
            _LOGGER.debug("Heater is already off. No action taken.")
            return

        await self._coordinator.async_set_heater_state(state)

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return None

        # Automatically select the preset
        for preset in self._presets:
            if float(self._presets[preset]) == float(temperature):
                return await self.async_set_preset_mode(preset)

        self._attr_preset_mode = PRESET_NONE
        return await self.async_set_target_temperature(temperature)

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode, cascade: bool = True) -> None:
        """Set the heating/cooling mode for the devices and update the state."""
        # Only allow the hvac mode to be set to heat or off
        if hvac_mode == HVACMode.HEAT:
            if self.hvac_mode != HVACMode.HEAT:
                self._last_control_at = dt_util.utcnow()

            self._attr_hvac_mode = HVACMode.HEAT
        elif hvac_mode == HVACMode.OFF:
            await self.async_cancel_calibration()
            if self._loop_measurement_task is not None:
                self._loop_measurement_task.cancel()
                self._loop_measurement_task = None
            async with self._control_lock:
                self._attr_hvac_mode = HVACMode.OFF
                await self.async_set_heater_state(DeviceState.OFF)
                await self._coordinator.async_release_control()
        else:
            # If an unsupported mode is passed, log an error message
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return

        # Reset the PID controller
        self._async_control_pid(reset=True)

        # Reset the climate
        self.reset_control_state()

        # Collect which climates to control
        climates = self._radiators[:]
        if self._sync_climates_with_mode:
            climates += self.areas.items()

        if cascade:
            # Set the hvac mode for those climate devices
            for entity_id in climates:
                state = self.hass.states.get(entity_id)
                if state is None or hvac_mode not in state.attributes.get("hvac_modes", []):
                    continue

                data = {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: hvac_mode}
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, data, blocking=True
                )

        # Update the state and control the heating
        self.async_write_ha_state()
        self.schedule_control_heating_loop()

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode for the thermostat."""
        if self.preset_modes is None or preset_mode not in self.preset_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_preset_mode",
                translation_placeholders={
                    "preset_mode": preset_mode,
                    "preset_modes": ", ".join(self.preset_modes or []),
                },
            )

        # Return if the given preset mode is already set
        if preset_mode == self._attr_preset_mode:
            return

        # Reset the preset mode if `PRESET_NONE` is given
        if preset_mode == PRESET_NONE:
            self._attr_preset_mode = PRESET_NONE
            if self._pre_custom_temperature is None:
                self.async_write_ha_state()
            else:
                await self.async_set_target_temperature(self._pre_custom_temperature)

        else:
            # Save the current target temperature if the preset mode is being set for the first time
            if self._attr_preset_mode == PRESET_NONE:
                self._pre_custom_temperature = self.native_target_temperature

            # Set the preset mode and target temperature
            self._attr_preset_mode = preset_mode
            await self.async_set_target_temperature(self._presets[preset_mode])

            # Set the temperature for each room, when enabled
            if self._sync_climates_with_preset:
                for entity_id in self.areas.items():
                    state = self.hass.states.get(entity_id)
                    if state is None or state.state == HVACMode.OFF:
                        continue

                    if preset_mode != PRESET_HOME or self._rooms is None:
                        target_temperature = self._presets[preset_mode]
                    else:
                        target_temperature = self._rooms.get(entity_id, self._presets[preset_mode])

                    data = {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: target_temperature}
                    await self.hass.services.async_call(
                        CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE, data, blocking=True
                    )

    async def async_set_target_temperature(
        self, temperature: float, *, cascade: bool = True
    ) -> None:
        """Set the temperature setpoint for all main climates."""
        if self.native_target_temperature == temperature:
            return

        # Set the new target temperature
        self._attr_native_target_temperature = temperature

        if cascade:
            # Set the target temperature for each main climate
            for entity_id in self._radiators:
                data = {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: temperature}
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE, data, blocking=True
                )

            # Set the target temperature for the connected boiler
            if self._push_setpoint_to_thermostat:
                await self._coordinator.async_set_control_thermostat_setpoint(temperature)

        # Reset the PID controller
        self._async_control_pid(reset=True)

        # Reset the climate
        self.reset_control_state()

        # Write the state to Home Assistant
        self.async_write_ha_state()

        # Control the heating based on the new temperature setpoint
        self.schedule_control_heating_loop(force=True)

    def _get_entity_state_float(self, entity_id: str) -> float | None:
        """Return state if available and valid."""
        if (entity := self.hass.states.get(entity_id)) is None:
            return None

        sensor_max_value_age = self._sensor_max_value_age

        if is_state_stale(entity, sensor_max_value_age):
            _LOGGER.debug(
                "Sensor %s stale for %s (age=%.1fs > %.1fs)",
                entity_id,
                self.entity_id,
                state_age_seconds(entity),
                sensor_max_value_age,
            )
            return None

        if entity.state in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            return None

        return float_value(entity.state)
