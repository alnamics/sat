# Options

🇵🇱 [Polska wersja](pl/options.md)

Open the integration page and click **Configure**. The settings are split into menus:

- [Heating curve and PID](#heating-curve-and-pid)
- [Presets](#presets)
- [Control and PWM](#control-and-pwm)
- [Heat budget](#heat-budget)
- [Hot water](#hot-water)
- [Presence and windows](#presence-and-windows)
- [Boiler and service](#boiler-and-service)

The heat budget, hot water and presence menus are not offered in switch mode (PID thermostat on/off). Some fields only appear when they apply to your setup. The defaults suit most homes.

Settings this fork adds are marked ⓜ and explained in [MPX additions](mpx.md).

## Heating curve and PID

- **PID controller**: Classic, Improved or Adaptive (default). Adaptive tunes itself; Classic and Improved use the automatic gains value.
- **Heating mode**: only with rooms added. *Comfort* heats for whichever room is furthest from its target, *Eco* only for the main room.
- **Maximum flow temperature**: the hottest water SAT may ask for. 55–75 °C suits radiators, 50 °C underfloor heating. It can't be below the overshoot protection value.
- **Overshoot protection value**: the lowest flow temperature the boiler holds at minimum power. Set by [calibration](how-it-works.md#calibration), or enter it yourself. SAT sends it in PWM on-phases.
- **Heating curve coefficient**: how steep the [heating curve](how-it-works.md#heating-curve) is (default 2.0). Raise it if the house stays cold in frosty weather, lower it if it overheats.
- **Automatic gains value**: how strongly the Classic and Improved controllers react (default 2.0). Setting it equal to the heating curve coefficient works well.
- **Derivative time weight**: how SAT damps fast changes (default 2.5).
- **Proportional, Integral, Derivative** (kP, kI, kD): your own PID values, shown when automatic gains are off.
- **Maximum PWM duty cycle**: the length of a [low-load cycle](how-it-works.md#low-load-control) when the automatic duty cycle is off (default 13 minutes).
- **Window and door sensors**: when one stays open longer than the minimum open time, SAT switches to the Activity preset, then restores the previous target once it closes.

## Presets

Target temperatures from 5 to 35 °C:

| Preset | Default |
|---|---|
| Activity (also used while a window is open) | 10 °C |
| Away | 10 °C |
| Sleep | 15 °C |
| Home | 18 °C |
| Comfort | 20 °C |

- **Pass the preset to the room thermostats**: the Sleep, Away and Activity presets go to your room thermostats too.
- **Pass the target to the boiler's thermostat**: the thermostat attached to the boiler keeps SAT's target, as a backup if Home Assistant fails.

## Control and PWM

- **Automatic PWM duty cycle**: SAT picks the [low-load cycle](how-it-works.md#low-load-control) length. When off, the length comes from the Heating curve and PID menu.
- **PWM cycles per hour**: the most burner starts per hour. 3 or 4 for radiators, 2 or 3 for heat pumps, ⓜ 1 to 4 for underfloor heating (2 suits an oversized boiler). The heat budget makes fewer.
- **Pass the mode to the room thermostats**: turning SAT on or off does the same to every attached thermostat.
- **Mode after a start without saved state**: heat or off, such as on first start.
- ⓜ **Frost protection while off**: while SAT is off, a room this cold is heated with 30 °C water until it is 1 °C warmer (default 6 °C; 0 turns it off). Not in switch mode.
- **Maximum age of a temperature reading**: an older reading counts as a stalled sensor (default 6 hours).
- **Minimum time a window is open**: how long a window sensor must stay open before heating pauses (default 15 seconds).

### Advanced

This section is collapsed by default.

- **Always use PWM**: low-load cycles even when the boiler could modulate down far enough. OpenTherm only.
- ⓜ **Learn the overshoot protection value** (default off): [details](mpx.md#boiler-settings). The current value is the `minimum_setpoint` attribute. OpenTherm only.
- ⓜ **Cut-short burns before a PWM on-phase ends**: how many burns the boiler may cut short in one on-phase (default 2; 1 suits an oversized boiler on underfloor heating).
- **Maximum modulation**: caps the boiler's power, in percent (default 100).
- **Room thermostat valve offset**: for room thermostats that don't report whether they heat. A room counts as wanting heat while it is at least this much below its target (default 0).
- **Target temperature step**: default 0.5 °C.
- **PID sample time**: the shortest time between two PID updates (default 1 minute).
- **Calibration: wait for the flame** and **wait for a steady flow**: how long [calibration](how-it-works.md#calibration) waits for the burner to light (default 10 minutes) and for the water temperature to settle (default 40 minutes, at least 5).
- **Felt temperature**: controls on the "feels like" temperature (Summer Simmer Index), from temperature and humidity. Needs the humidity sensor.
- **Simulation**: SAT calculates everything but sends nothing to the boiler.

## Heat budget

ⓜ For slow emitters such as screed underfloor heating. [Details](mpx.md#heat-budget).

> [!WARNING]
> AI-written code, field-tested on one boiler only, see [MPX additions](mpx.md#field-test). With the defaults SAT drives the boiler as the original SAT v2 does.

- **Heat budget**: Off (default), Learn only or On. On controls underfloor heating only.
- **Heat loss of the house**: in W/K; 0 learns it (default, recommended).
- **Period**: how often heat credit is added (default 60 minutes).
- **Minimum burn**: the shortest block worth lighting the burner for (default 10 minutes).
- **Weather forecast**: a weather entity with an hourly forecast; its wind speed is used to learn the wind effect (Met.no or Open-Meteo, for example). A sensor with current values only, such as Airly, doesn't work here.
- **Comfort schedule** and **Setback outside the schedule**: a schedule helper that is on in the comfort hours, and how much cooler it is outside them (default 0).
- **Warm weather shutdown**: the daily mean outside temperature at which central heating switches off (default 0: never).

## Hot water

ⓜ For boilers that take a hot water setpoint over OpenTherm. [Details](mpx.md#hot-water).

- **Hot water temperature**: default 0, which leaves the hot water to the boiler.
- **Eco temperature** and **Hot water schedule**: outside the schedule's hours the eco temperature applies.
- **Water meter**: a total water meter (litres or m³), for the cylinder check: it leaves out heating starts with a tap open and counts the reheats no water use explains.
- **Legionella boost day** and **start**: default off.

## Presence and windows

ⓜ [Details](mpx.md#schedules-and-presence).

- **Presence**: who counts as being home. After 30 minutes with nobody home SAT switches to Away.
- **Distance to home** and **Return distance**: an optional Proximity sensor and how close someone must be for the heating to come back.
- **Detect open windows from the temperature**: default off.

## Boiler and service

ⓜ [Details](mpx.md#boiler-settings) and [Monitoring](mpx.md#monitoring).

- **Keep heating enabled between PWM on-phases** (default off): for combi boilers whose pump overrun cools the hot water cylinder. Not in switch mode.
- **Boiler anti-cycling time**: the boiler's own wait before relighting, from its installer settings (default 0: not set).
- **Valve opening time**: how long the room thermostats' actuators take to open (default 0: light at once).
- **Maximum flow for the screed**: underfloor heating only (default 55 °C; 0 turns it off).
- **Condensing boiler** (default on): for the efficiency estimate without a flue gas sensor.
- **Gas use at minimum and maximum power**: from the boiler's manual, in m³/h. SAT uses them to estimate gas use, and the burner power when the boiler does not report its capacity. OpenTherm only.
- **Heat per cubic metre of gas**: default 10.2 kWh/m³ for natural gas, about 24 for propane. OpenTherm only.
- **Gas price per cubic metre**: adds a gas cost sensor (default 0: off).
- **Last boiler service** and **Service interval**: for the service reminder in Repairs.

---

Back: [Setup](setup.md) · Next: [How SAT works](how-it-works.md)
