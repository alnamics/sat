# Options

🇵🇱 [Polska wersja](pl/options.md)

Open the integration page and click **Configure**. Settings are in three menus: [General](#general), [Presets](#presets) and [System Configuration](#system-configuration). Some settings only appear when they apply to your setup.

The defaults suit most homes.

The settings this fork adds are listed under [Advanced: MPX additions](#advanced-mpx-additions) and explained in [MPX additions](mpx.md).

## General

- **PID Controller Version**: Classic, Improved or Adaptive (default). Adaptive tunes itself. Classic and Improved use the Automatic Gains Value below.
- **Heating Mode**: only with rooms added. *Comfort* heats for whichever room is furthest from its target. *Eco* heats only for the main room.
- **Maximum Setpoint**: the hottest water SAT may ask for. 55-75 °C suits radiators, 50 °C underfloor heating. A higher value warms the house up faster. It can't be below the overshoot protection value.
- **Overshoot protection value**: the lowest water temperature your boiler can hold. Set by [calibration](how-it-works.md#calibration), or enter it yourself.
- **Heating Curve Coefficient**: how steep the [heating curve](how-it-works.md#heating-curve) is (default 2.0). Raise it if the house stays cold on cold days, lower it if it overheats.
- **Automatic Gains Value**: how strongly the Classic and Improved controllers react (default 2.0). Setting it equal to the heating curve coefficient works well.
- **Derivative Time Weight**: fine-tunes how SAT damps fast changes (default 2.5).
- **Proportional, Integral, Derivative**: your own PID values, shown when Automatic Gains is off.
- **Minimum Setpoint Controller Version** and **Adjustment Factor for Return Temperature**: settings of [Dynamic Minimum Setpoint](#advanced), shown when it's on. The version picks whether it follows the return or the boiler temperature. Start the factor between 0.1 and 0.5 (default 0.2).
- **Maximum Duty Cycle for Pulse Width Modulation**: the length of a [low-load cycle](how-it-works.md#low-load-control) when Automatic duty cycle is off (default 13 minutes).
- **Contact Sensors**: door and window sensors. When one stays open longer than the minimum open time, SAT switches to the Activity preset, then restores the previous target once it closes.

## Presets

Target temperatures from 5 to 35 °C:

| Preset | Default |
|---|---|
| Activity (also used while a window is open) | 10 °C |
| Away | 10 °C |
| Sleep | 15 °C |
| Home | 18 °C |
| Comfort | 20 °C |

- **Synchronize climates with preset**: applies the Sleep, Away and Activity presets to your room thermostats too.
- **Synchronize with thermostat attached to the boiler**: sends SAT's target to your wall thermostat.

## System Configuration

- **Automatic duty cycle**: SAT picks the [low-load cycle](how-it-works.md#low-load-control) length from the cycles per hour. When off, the length comes from the General menu.
- **Duty Cycles per hour**: the most boiler cycles per hour. 3 or 4 for radiators, 2 or 3 for heat pumps, 1 to 4 for underfloor heating (2 suits an oversized boiler).
- **Synchronize climates with mode**: turning SAT on or off does the same to every attached thermostat.
- **Temperature Sensor maximum value age**: how long a sensor reading counts as fresh (default 6 hours).
- **Mode when nothing can be restored**: whether SAT starts in heat or off when it has no saved state, such as on first start.
- **Minimum time for window to be open**: how long a contact sensor must stay open before SAT reacts (default 15 seconds).

### Advanced

This section is collapsed by default.

- **Thermal Comfort**: controls on the "feels like" temperature (Summer Simmer Index), from temperature and humidity. Needs the humidity sensor.
- **Dynamic Minimum Setpoint (Experimental)**: with some valves closed, the water can come back hotter than expected during low-load control. This watches the return temperature and adjusts the setpoint to match.
- **Force Pulse Width Modulation**: always use [low-load cycles](how-it-works.md#low-load-control), even when the boiler could hold the temperature itself. OTGW only.
- **Minimum Consumption** and **Maximum Consumption**: your boiler's gas use at its lowest and highest power, from its manual. SAT uses them to estimate gas consumption, and the burner power when the boiler does not report its capacity.
- **Climate valve offset**: for room thermostats that don't report whether they're heating. A room counts as wanting heat while it's at least this much below its target (default 0).
- **Target Temperature Step**: the step for SAT's target temperature (default 0.5 °C).
- **Maximum Relative Modulation**: caps the boiler's power, in percent (default 100).
- **Sample Time**: the shortest time between two PID updates (default 1 minute).
- **Calibration flame timeout** and **Calibration plateau timeout**: how long [calibration](how-it-works.md#calibration) waits for the burner to light (default 10 minutes) and for the water temperature to settle (default 40 minutes, at least 5).

### Advanced: MPX additions

> [!WARNING]
> AI-written and unverified, see [MPX additions](mpx.md). At their defaults SAT controls the boiler as upstream SAT v2 does.

What each setting is; [MPX additions](mpx.md) explains how the features behave.

**Boiler** ([details](mpx.md#boiler-settings))

- **Heat per cubic metre of gas**: kWh one cubic metre of gas gives the boiler (default 10.2 for natural gas; about 24 for propane).
- **Condensing boiler** (default on): for the efficiency estimate of a boiler that does not report its flue gas temperature. Turn off for a non-condensing boiler.
- **Cut-short burns before ending the PWM on-phase**: how many burns the boiler may stop by itself in one low-load cycle before SAT ends the on-phase (default 2; 1 for an oversized boiler on underfloor heating).
- **Boiler anti-cycling time**: the boiler's own wait before it relights, from its installer settings (default 0: not set).
- **Learn overshoot protection value** (default off): adjusts the calibrated value from how low-load burns end, between 30 °C and the maximum setpoint minus 3 °C. The `minimum_setpoint` attribute shows the current value.
- **Valve opening time**: how long the actuators of your room thermostats take to open (default 0: light the boiler at once).
- **Warm-up modulation** (default 0, off): lets a cold burn modulate up to this share for its first minutes, for a flame that goes out at minimum power. Not in switch mode.
- **Keep heating enabled between PWM on-phases** (default off): for combi boilers whose pump overrun cools the hot water cylinder. Not in switch mode.
- **Duty Cycles per hour**: underfloor heating can go down to 1.

**Heat budget** ([details](mpx.md#heat-budget))

- **Heat budget**: `Off` (default), `Learn only (shadow)` or `On`. `On` only drives underfloor heating.
- **Heat budget period**: one heating block per period (default 60 minutes).
- **Heat budget minimum burn**: the shortest block worth an ignition (default 10 minutes).
- **Heat loss of the house**: in W/K; 0 learns it (default).
- **Weather forecast**: a weather entity with an hourly forecast (for example Met.no or Open-Meteo). Also used by the warm weather shutdown. A sensor that only gives current values, such as Airly, cannot be used here.
- **Comfort schedule** and **Setback**: a schedule helper that is on in comfort hours, and how far the target drops outside them (default 0: no setback).

**Schedules and presence** ([details](mpx.md#schedules-and-presence))

- **Warm weather shutdown**: the daily mean outside temperature at which central heating switches off (default 0: never).
- **Presence**, **Distance to home** and **Return distance**: who counts as home, an optional Proximity distance sensor, and how close someone must be for the heating to come back.
- **Detect open windows from the temperature** (default off).

**Hot water** ([details](mpx.md#hot-water))

- **Hot water temperature** (default 0: leave hot water to the boiler), **Hot water eco temperature** and **Hot water schedule**.
- **Legionella boost day** (default off) and **start**.

**Monitoring** ([details](mpx.md#monitoring))

- **Maximum flow for the screed**: underfloor heating only (default 55 °C; 0 turns the check off).
- **Last boiler service** and **Service interval**: for the service reminder.
- **Gas price per cubic metre**: adds the gas cost sensor (default 0: off).

---

Back: [Setup](setup.md) · Next: [How SAT works](how-it-works.md)
