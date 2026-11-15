# Base component constants
from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Any

DOMAIN = "sat"

MODE_FAKE = "fake"
MODE_MQTT_EMS = "mqtt_ems"
MODE_MQTT_OPENTHERM = "mqtt_opentherm"
MODE_SWITCH = "switch"
MODE_SERIAL = "serial"
MODE_ESPHOME = "esphome"
MODE_SIMULATOR = "simulator"

DEADBAND = 0.1
BOILER_DEADBAND = 2
HEATER_STARTUP_TIMEFRAME = 180

COLD_SETPOINT = 28.2
MINIMUM_SETPOINT = 10
# One 0.1 °C sensor step moves the setpoint about 2 °C with automatic gains
PWM_HYSTERESIS = 2.0

# Four missed 30 second control intervals
CONTROL_LOOP_STALL_TIME = timedelta(minutes=2)
SETUP_FAILED_ISSUE_DELAY = timedelta(minutes=5)
MAXIMUM_SETPOINT = 65
MINIMUM_RELATIVE_MODULATION = 0

MAX_BOILER_TEMPERATURE_AGE = 60

# Configuration and options
CONF_MODE = "mode"
CONF_NAME = "name"
CONF_DEVICE = "device"
CONF_THERMOSTAT = "thermostat"
CONF_MANUFACTURER = "manufacturer"
CONF_CYCLES_PER_HOUR = "cycles_per_hour"
CONF_SIMULATED_HEATING = "simulated_heating"
CONF_SIMULATED_COOLING = "simulated_cooling"
CONF_SIMULATED_WARMING_UP = "simulated_warming_up"
CONF_MINIMUM_SETPOINT = "minimum_setpoint"
CONF_MAXIMUM_SETPOINT = "maximum_setpoint"
CONF_MAXIMUM_RELATIVE_MODULATION = "maximum_relative_modulation"
CONF_ROOMS = "secondary_climates"
CONF_MQTT_TOPIC = "mqtt_topic"
CONF_RADIATORS = "main_climates"
CONF_WINDOW_SENSORS = "window_sensors"
CONF_PUSH_SETPOINT_TO_THERMOSTAT = "push_setpoint_to_thermostat"
CONF_WINDOW_MINIMUM_OPEN_TIME = "window_minimum_open_time"
CONF_THERMAL_COMFORT = "thermal_comfort"
CONF_SIMULATION = "simulation"
CONF_INTEGRAL = "integral"
CONF_DERIVATIVE = "derivative"
CONF_PROPORTIONAL = "proportional"
CONF_DUTY_CYCLE = "duty_cycle"
CONF_SAMPLE_TIME = "sample_time"
CONF_AUTOMATIC_GAINS = "automatic_gains"
CONF_AUTOMATIC_DUTY_CYCLE = "automatic_duty_cycle"
CONF_AUTOMATIC_GAINS_VALUE = "automatic_gains_value"
CONF_DERIVATIVE_TIME_WEIGHT = "derivative_time_weight"
CONF_CLIMATE_VALVE_OFFSET = "climate_valve_offset"
CONF_SENSOR_MAX_VALUE_AGE = "sensor_max_value_age"
CONF_DEFAULT_HVAC_MODE = "default_hvac_mode"
CONF_CALIBRATION_FLAME_TIMEOUT = "calibration_flame_timeout"
CONF_CALIBRATION_PLATEAU_TIMEOUT = "calibration_plateau_timeout"
CONF_PWM_SHORT_BURNS_THRESHOLD = "pwm_short_burns_threshold"
CONF_BOILER_ANTI_CYCLING_TIME = "boiler_anti_cycling_time"
CONF_LEARN_OVERSHOOT_PROTECTION = "learn_overshoot_protection"
CONF_VALVE_OPENING_TIME = "valve_opening_time"
CONF_KEEP_HEATING_IN_PWM_OFF = "keep_heating_in_pwm_off"
CONF_HEAT_BUDGET_MODE = "heat_budget_mode"
CONF_HEAT_BUDGET_PERIOD = "heat_budget_period"
CONF_HEAT_BUDGET_MINIMUM_BURN = "heat_budget_minimum_burn"
CONF_HEAT_LOSS_COEFFICIENT = "heat_loss_coefficient"
CONF_WEATHER_FORECAST_ENTITY_ID = "weather_forecast_entity_id"
CONF_COMFORT_SCHEDULE_ENTITY_ID = "comfort_schedule_entity_id"
CONF_SETBACK_TEMPERATURE = "setback_temperature"
CONF_WARM_WEATHER_SHUTDOWN = "warm_weather_shutdown_temperature"
CONF_HOT_WATER_SCHEDULE_ENTITY_ID = "hot_water_schedule_entity_id"
CONF_HOT_WATER_COMFORT_TEMPERATURE = "hot_water_comfort_temperature"
CONF_HOT_WATER_ECO_TEMPERATURE = "hot_water_eco_temperature"
CONF_LEGIONELLA_DAY = "legionella_day"
CONF_LEGIONELLA_TIME = "legionella_time"
CONF_PRESENCE_ENTITY_IDS = "presence_entity_ids"
CONF_PROXIMITY_ENTITY_ID = "proximity_entity_id"
CONF_RETURN_DISTANCE = "return_distance"
CONF_WINDOW_DETECTION = "window_detection"
CONF_SCREED_MAXIMUM_TEMPERATURE = "screed_maximum_temperature"
CONF_LAST_SERVICE_DATE = "last_service_date"
CONF_SERVICE_INTERVAL = "service_interval"
CONF_GAS_PRICE = "gas_price"
LEGIONELLA_OFF = "off"

HEAT_BUDGET_OFF = "off"
HEAT_BUDGET_SHADOW = "shadow"
HEAT_BUDGET_ON = "on"
CONF_OVERSHOOT_PROTECTION = "overshoot_protection"
CONF_SYNC_CLIMATES_WITH_MODE = "sync_climates_with_mode"
CONF_SYNC_CLIMATES_WITH_PRESET = "sync_climates_with_preset"
CONF_FORCE_PULSE_WIDTH_MODULATION = "force_pulse_width_modulation"
CONF_TARGET_TEMPERATURE_STEP = "target_temperature_step"
CONF_INSIDE_SENSOR_ENTITY_ID = "inside_sensor_entity_id"
CONF_OUTSIDE_SENSOR_ENTITY_ID = "outside_sensor_entity_id"
CONF_HUMIDITY_SENSOR_ENTITY_ID = "humidity_sensor_entity_id"

CONF_HEATING_MODE = "heating_mode"
CONF_HEATING_SYSTEM = "heating_system"
CONF_HEATING_CURVE_COEFFICIENT = "heating_curve_coefficient"

CONF_PID_CONTROLLER_VERSION = "pid_controller_version"

CONF_DYNAMIC_MINIMUM_SETPOINT = "dynamic_minimum_setpoint"
CONF_DYNAMIC_MINIMUM_SETPOINT_VERSION = "dynamic_minimum_setpoint_version"
CONF_MINIMUM_SETPOINT_ADJUSTMENT_FACTOR = "minimum_setpoint_adjustment_factor"

CONF_MINIMUM_CONSUMPTION = "minimum_consumption"
CONF_MAXIMUM_CONSUMPTION = "maximum_consumption"
CONF_GAS_ENERGY_CONTENT = "gas_energy_content"

CONF_AWAY_TEMPERATURE = "away_temperature"
CONF_HOME_TEMPERATURE = "home_temperature"
CONF_SLEEP_TEMPERATURE = "sleep_temperature"
CONF_COMFORT_TEMPERATURE = "comfort_temperature"
CONF_ACTIVITY_TEMPERATURE = "activity_temperature"

HEATING_SYSTEM_UNKNOWN = "unknown"
HEATING_SYSTEM_HEAT_PUMP = "heat_pump"
HEATING_SYSTEM_RADIATORS = "radiators"
HEATING_SYSTEM_UNDERFLOOR = "underfloor"

HEATING_MODE_ECO = "eco"
HEATING_MODE_COMFORT = "comfort"

OPTIONS_DEFAULTS: dict[str, Any] = {
    CONF_PROPORTIONAL: "45",
    CONF_INTEGRAL: "0",
    CONF_DERIVATIVE: "6000",
    CONF_CYCLES_PER_HOUR: 4,
    CONF_AUTOMATIC_GAINS: True,
    CONF_AUTOMATIC_DUTY_CYCLE: True,
    CONF_AUTOMATIC_GAINS_VALUE: 2.0,
    CONF_DERIVATIVE_TIME_WEIGHT: 2.5,
    CONF_OVERSHOOT_PROTECTION: False,
    CONF_DYNAMIC_MINIMUM_SETPOINT: False,
    CONF_MINIMUM_SETPOINT_ADJUSTMENT_FACTOR: 0.2,
    CONF_RADIATORS: [],
    CONF_ROOMS: [],
    CONF_SIMULATION: False,
    CONF_WINDOW_SENSORS: [],
    CONF_THERMAL_COMFORT: False,
    CONF_HUMIDITY_SENSOR_ENTITY_ID: None,
    CONF_PUSH_SETPOINT_TO_THERMOSTAT: False,
    CONF_SYNC_CLIMATES_WITH_MODE: True,
    CONF_SYNC_CLIMATES_WITH_PRESET: False,
    CONF_SIMULATED_HEATING: 20,
    CONF_SIMULATED_COOLING: 5,
    CONF_MINIMUM_SETPOINT: 10,
    CONF_MAXIMUM_RELATIVE_MODULATION: 100,
    CONF_FORCE_PULSE_WIDTH_MODULATION: False,
    CONF_MINIMUM_CONSUMPTION: 0,
    CONF_MAXIMUM_CONSUMPTION: 0,
    # Heat from one cubic metre of natural gas in a condensing boiler; propane gives about 24
    CONF_GAS_ENERGY_CONTENT: 10.2,
    CONF_DUTY_CYCLE: "00:13:00",
    CONF_SAMPLE_TIME: "00:01:00",
    CONF_CLIMATE_VALVE_OFFSET: 0,
    CONF_TARGET_TEMPERATURE_STEP: 0.5,
    CONF_SENSOR_MAX_VALUE_AGE: "06:00:00",
    CONF_DEFAULT_HVAC_MODE: "heat",
    CONF_CALIBRATION_FLAME_TIMEOUT: "00:10:00",
    CONF_CALIBRATION_PLATEAU_TIMEOUT: "00:40:00",
    # Burns the boiler may cut short in one PWM on-phase before SAT ends the on-phase
    CONF_PWM_SHORT_BURNS_THRESHOLD: 2,
    # The boiler's own wait before relighting; 0 keeps the default stuck-off timeout
    CONF_BOILER_ANTI_CYCLING_TIME: "00:00:00",
    # Adjust the overshoot protection value from how PWM burns end
    CONF_LEARN_OVERSHOOT_PROTECTION: False,
    # How long the valve actuators of the climates take to open; 0 lights the boiler at once
    CONF_VALVE_OPENING_TIME: "00:00:00",
    # Leave central heating enabled at the minimum setpoint between PWM on-phases
    CONF_KEEP_HEATING_IN_PWM_OFF: False,
    # Dose the burner from a learned heat balance instead of flow temperatures
    CONF_HEAT_BUDGET_MODE: "off",
    CONF_HEAT_BUDGET_PERIOD: "60",
    CONF_HEAT_BUDGET_MINIMUM_BURN: "00:10:00",
    # Heat loss of the house in W/K; 0 learns it
    CONF_HEAT_LOSS_COEFFICIENT: 0,
    CONF_WEATHER_FORECAST_ENTITY_ID: None,
    CONF_COMFORT_SCHEDULE_ENTITY_ID: None,
    CONF_SETBACK_TEMPERATURE: 0.0,
    # 0 keeps central heating on whatever the weather
    CONF_WARM_WEATHER_SHUTDOWN: 0.0,
    CONF_HOT_WATER_SCHEDULE_ENTITY_ID: None,
    # 0 leaves the hot water temperature to the boiler
    CONF_HOT_WATER_COMFORT_TEMPERATURE: 0.0,
    CONF_HOT_WATER_ECO_TEMPERATURE: 0.0,
    CONF_LEGIONELLA_DAY: LEGIONELLA_OFF,
    CONF_LEGIONELLA_TIME: "03:00:00",
    CONF_PRESENCE_ENTITY_IDS: [],
    CONF_PROXIMITY_ENTITY_ID: None,
    CONF_RETURN_DISTANCE: 0.0,
    CONF_WINDOW_DETECTION: False,
    # Flow water above this for 3 minutes raises a repair issue (underfloor only, 0 = off)
    CONF_SCREED_MAXIMUM_TEMPERATURE: 55.0,
    CONF_LAST_SERVICE_DATE: None,
    CONF_SERVICE_INTERVAL: 12,
    CONF_GAS_PRICE: 0.0,
    CONF_SIMULATED_WARMING_UP: "00:00:15",
    CONF_WINDOW_MINIMUM_OPEN_TIME: "00:00:15",
    CONF_ACTIVITY_TEMPERATURE: 10,
    CONF_AWAY_TEMPERATURE: 10,
    CONF_HOME_TEMPERATURE: 18,
    CONF_SLEEP_TEMPERATURE: 15,
    CONF_COMFORT_TEMPERATURE: 20,
    CONF_HEATING_CURVE_COEFFICIENT: 2.0,
    CONF_HEATING_MODE: HEATING_MODE_COMFORT,
    CONF_HEATING_SYSTEM: HEATING_SYSTEM_RADIATORS,
    CONF_PID_CONTROLLER_VERSION: 3,
    CONF_DYNAMIC_MINIMUM_SETPOINT_VERSION: 1,
}

# Overshoot protection
OVERSHOOT_PROTECTION_SETPOINT = {
    HEATING_SYSTEM_HEAT_PUMP: 40,
    HEATING_SYSTEM_RADIATORS: 62,
    HEATING_SYSTEM_UNDERFLOOR: 45,
}

# Services
SERVICE_RESET_INTEGRAL = "reset_integral"
SERVICE_MEASURE_LOOPS = "measure_loops"
SERVICE_PULSE_WIDTH_MODULATION = "pulse_width_modulation"


# Enumerations
class FlameStatus(StrEnum):
    HEALTHY = "healthy"
    IDLE_OK = "idle_ok"
    STUCK_ON = "stuck_on"
    STUCK_OFF = "stuck_off"
    PWM_SHORT = "pwm_short"
    SHORT_CYCLING = "short_cycling"
    INSUFFICIENT_DATA = "insufficient_data"


class BoilerStatus(StrEnum):
    HOT_WATER = "hot_water"
    PREHEATING = "preheating"
    HEATING_UP = "heating_up"
    AT_SETPOINT = "at_setpoint"
    COOLING_DOWN = "cooling_down"
    ANTI_CYCLING = "anti_cycling"
    NEAR_SETPOINT = "near_setpoint"
    PUMP_STARTING = "pump_starting"
    WAITING_FOR_FLAME = "waiting_for_flame"
    BELOW_SETPOINT = "below_setpoint"
    OVERSHOOT_HANDLING = "overshoot_handling"
    OVERSHOOT_STABILIZED = "overshoot_stabilized"

    IDLE = "idle"
    INSUFFICIENT_DATA = "insufficient_data"


class PWMStatus(StrEnum):
    """The current state of Pulse Width Modulation."""

    ON = "on"
    OFF = "off"
    IDLE = "idle"


# Dynamic minimum setpoint versions
DYNAMIC_MINIMUM_SETPOINT_VERSION_1 = 1
DYNAMIC_MINIMUM_SETPOINT_VERSION_2 = 2
