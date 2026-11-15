# Options

Open the integration page and click **Configure**. Settings are in three menus: [General](#general), [Presets](#presets) and [System Configuration](#system-configuration). Some settings only appear when they apply to your setup.

The defaults suit most homes.

Many settings in [Advanced](#advanced) belong to this fork's AI-written, unverified additions: the boiler settings from *Cut-short burns* on, the heat budget, warm weather shutdown, hot water schedule, presence, window detection, the screed limit, service, gas price and energy content, and the condensing boiler setting. They are explained together in [MPX additions](mpx.md). At their defaults SAT behaves as upstream SAT v2.

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
- **Minimum Consumption** and **Maximum Consumption**: your boiler's gas use at its lowest and highest power, from its manual. SAT uses them to estimate gas consumption, and, when the boiler reports a return temperature, the water flow through the system: the **Estimated water flow** sensor divides the heat output (gas use × the heat per cubic metre) by the flow/return spread during space heating burns that have run for at least 3 minutes, and holds the last value between them. A drop in the flow shows loops closing. The **Flame starts in the last hour** sensor counts burner ignitions, hot water included.

Every SAT entry also keeps running totals that only grow, so Home Assistant's statistics (and the Energy dashboard for gas) turn them into daily, weekly and monthly values, also for boilers that do not report their own counters: **Burner starts**, **Burner hours**, **Heat for space heating** and **Heat for hot water** (kWh, from the burner power), **Estimated gas use** (m³) and **Heating degree days** (base 18 °C). Gas divided by degree days compares weeks with different weather. **Cylinder cooling after heating stops** counts the hot water cylinder drops of the last day that began within 10 minutes of a heating demand ending: on a combi boiler whose diverter valve rests on hot water, the pump overrun then cools the cylinder with heating water (see *Keep heating enabled between PWM on-phases*).

With room or radiator thermostats configured, **Open loops** shows which actuators are open, and **Loops to rebalance** gives per room the share of the last day its valve was open, how much warmer or colder than the other rooms it ran, the water flow of its loop (learned from the estimated system flow and the open/closed pattern, once the loop was seen both open and closed) and a rotameter hint: `reduce` for a room that runs warm or whose thermostat often closes, `increase` for a room that runs cold with its valve always open.

SAT raises repair issues in Home Assistant for water pressure below 0.8 bar for 10 minutes, a fault the boiler reports (with its manufacturer code) and, from settled heating burns, flue gas running more than 12 K above the return water over a day, a sign of a dirty heat exchanger. Burns with flue gas above 90 °C do not condense and are left out of that check, so older non-condensing boilers are not reported. They clear themselves when the condition is gone.
- **Heat per cubic metre of gas**: what one cubic metre of gas gives the boiler, in kWh (default 10.2 for natural gas; about 24 for propane). Used for the gas, heat and water flow estimates.
- **Climate valve offset**: for room thermostats that don't report whether they're heating. A room counts as wanting heat while it's at least this much below its target (default 0).
- **Target Temperature Step**: the step for SAT's target temperature (default 0.5 °C).
- **Maximum Relative Modulation**: caps the boiler's power, in percent (default 100).
- **Sample Time**: the shortest time between two PID updates (default 1 minute).
- **Cut-short burns before ending the PWM on-phase**: how many burns the boiler may stop by itself in one [low-load cycle](how-it-works.md#low-load-control) before SAT ends the on-phase early (default 2). Set 1 for an oversized boiler on underfloor heating, so each on-phase allows a single burn.
- **Boiler anti-cycling time**: the boiler's own wait before it relights, from its installer settings (for example 10 minutes). SAT then waits this long plus a minute before reporting the flame as stuck off, and calibration waits at least this long plus two minutes for the burner to light. 0 keeps the defaults.
- **Learn overshoot protection value**: starts from the calibrated (or entered) value and adjusts it during normal operation. It goes up 1 °C when the boiler stops a PWM burn by overheating the water, or when an on-phase passes without the burner lighting because the water is already warmer than the setpoint. It goes down 0.5 °C when a burn of at least 10 minutes levels off 2 °C or more below the setpoint. It stays between 30 °C and the maximum setpoint minus 3 °C. Calibrating again or changing the value starts over. The `minimum_setpoint` attribute of the climate shows the current value.
- **Valve opening time**: how long the valve actuators of your radiator and room thermostats take to open, for example 5 minutes for thermal actuators. When a thermostat starts asking for heat and none has been asking for longer, SAT waits this long before lighting the boiler, so the water has somewhere to go. A boiler that is already burning is not affected. 0 lights it at once (default).
- **Keep heating enabled between PWM on-phases**: in a PWM off-phase SAT normally sends the minimum setpoint and switches central heating off. With this option heating stays enabled at the minimum setpoint, so the boiler stays in heating mode without burning. Its pump keeps circulating through the system, and a combi boiler with a hot water cylinder does not swing its diverter valve to the cylinder, where the pump overrun would cool the cylinder with heating water and trigger extra reheats. Some boilers raise a low setpoint to their own minimum (often 25 °C) and would light when the system water is colder than that; if the burner lights more than 90 seconds into an off-phase, SAT switches heating off between on-phases again for an hour and logs a warning. The `heating_kept_on_in_pwm_off` attribute of the climate shows when heating is held on. Not available in switch mode.
- **Heat budget** (`Off`, `Learn only (shadow)`, `On`): for slow emitters such as screed underfloor heating with a boiler whose minimum power is above what the house needs. SAT keeps an hourly energy balance of the house (heat burned for space heating, indoor and outdoor temperature, and sun when a forecast with cloud cover is set) and learns the heat loss coefficient H with recursive least squares over a running day. Once it has about 36 hours of data it works in energy instead of flow temperatures: the heat the next period needs is H × (target − forecast outdoor temperature), minus the sun, plus a slow PI correction on the room error. With a forecast, only its trend over the next hours is added to the measured outside temperature, so a forecast that runs warmer or colder than your own sensor does not bias the heat. An hour that is partly missing (a restart, a sensor dropping out) stands in for the whole hour when at least half of it was measured, and is left out otherwise; the day window is kept across restarts. That heat is burned in one block per period at minimum power. A block a hot water request interrupts runs on until its heat is delivered, heat smaller than the minimum burn is carried into the next period, and two boiler cut-outs end the block. Shadow mode learns and shows the plan in the climate attributes (`heat_loss_w_per_k`, `heat_need_kw`, `heat_block_minutes`, `heat_credit_kwh`, …) while the normal PWM keeps control. With `On` and the heat budget ready, SAT always uses low-load cycles (as Force PWM does); until then the normal control and its own Force PWM setting apply. When the house needs more than the boiler gives at minimum power (the need stays 10 % above it for two hours while the room is at least 0.2 °C below target, as on a cold day in a larger or less insulated house), SAT hands the control back to the heating curve with the boiler's own modulation, and takes it again once the need has stayed below 85 % of the minimum power for an hour; the `heat_budget_overloaded` attribute shows it. `On` only drives underfloor heating: with radiators or a heat pump it learns as in shadow mode, because hour-long blocks would make fast emitters swing.
- **Heat budget period**: one block per period; 60 minutes gives about one ignition an hour.
- **Heat budget minimum burn**: the shortest block worth an ignition.
- **Heat loss of the house**: in W/K; 0 learns it.
- **Weather forecast**: a weather entity with an hourly forecast (for example Met.no or Open-Meteo). Sensors such as Airly only give current values and cannot be used here; they can be the outside sensor of SAT instead.
- **Comfort schedule** and **Setback**: a schedule helper that is on in comfort hours. Outside them the target is lowered by the setback; the recovery starts early by a learned return time (Seem et al.: hours = a × temperature rise + b × recent demand) and comfort ends an hour early because the screed keeps heating.
- **Warm weather shutdown**: central heating switches off while the outside temperature averaged over about a day (after at least 6 hours of readings) is at or above this, and comes back once the average is 2 °C below it. With a weather forecast set, heating stays off when the next 12 hours are warm again, and does not switch off when they are cold. Hot water keeps working; the `warm_weather_shutdown` and `outside_temperature_mean` attributes show the state. 0 keeps heating on.
- **Hot water temperature**, **Hot water eco temperature**, **Hot water schedule**: SAT sends the cylinder temperature to the boiler (OpenTherm, when the boiler accepts it). Outside the hours a schedule helper is on, the eco temperature applies, which cuts the standing losses of the cylinder. SAT only writes when its value changes, so a temperature set by hand stays until the next change. 0 leaves hot water to the boiler.
- **Legionella boost day** and **start**: once a week the cylinder is heated to 60 °C and held there for an hour (or the boost gives up after 4 hours).
- **Presence**, **Distance to home** and **Return distance**: when none of the people, trackers, zones or groups has been home for 30 minutes, SAT switches to the Away preset (from no preset, Home or Comfort), and back to the previous preset when someone returns. With a Proximity distance sensor, the heating comes back as soon as someone is within the return distance. Set the Away preset to a mild setback for screed floors, for example 19 °C.
- **Detect open windows from the temperature**: a drop of the room temperature of 0.8 °C within 10 minutes switches to the Activity preset for 30 minutes, as a contact sensor would.
- **Maximum flow for the screed**: underfloor heating only. Flow water above this for 3 minutes during space heating (not hot water, nor the 5 minutes after it) raises a repair issue that stays a day.
- **Last boiler service** and **Service interval**: a repair issue when the next service is due.
- **Gas price per cubic metre**: adds an **Estimated gas cost** sensor in your currency, counted at the price in force at the time.

More repair issues need no setting: **water pressure keeps falling** (daily lowest pressures falling 0.05 bar a week or more over at least four days, with 0.1 bar lost), **too little water through the heating** (flow more than 20 K above the return for 5 minutes in settled burns) and **gas use went up** (gas per degree day of the last week 30 % above the four weeks before, in weeks cold enough to compare).

The climate also shows `suggested_heating_curve_coefficient` once the heat budget knows the house: from the learned heat loss and the floor's heat transfer (`floor_heat_transfer_w_per_k`, learned from settled burns) it computes the flow temperature the house needs at -15, -5 and 5 °C outside and the curve coefficient that matches it. It is a suggestion; SAT does not change the curve.

With the heat budget on, a hot water reheat in the last third of a period starts the next heating block right away while the boiler is warm, instead of lighting it again a little later (`hot_water_piggybacks` counts them).

The **Measure loops** action (`sat.measure_loops`) measures the water flow of each loop: it turns all room thermostats off, burns at minimum power and measures the base flow of the loops without an actuator, then opens one room at a time (target 30 °C) and measures the rise. Each step waits the valve opening time plus 5 minutes and takes 10 settled samples, so it takes about 15 minutes per room. The thermostats are put back afterwards and the result arrives as a notification and in the `loop_measurement` attribute. Turning SAT off stops it.
- **Condensing boiler** (default on): see *Estimated boiler efficiency* below.

**Estimated boiler efficiency** is an energy balance of the combustion on the gross calorific value (what the gas meter bills): the heat leaving with the flue gas and the latent heat of the water vapour that does not condense are lost. Below the dew point (about 55 °C for natural gas) part of the vapour condenses and gives its heat to the water, which is why a cooler flue, and so a cooler return, means a higher efficiency: about 97 % at a 30 °C flue, 91 % at 50 °C and 88 % or less without condensing. The flue gas temperature comes from the boiler when it reports one; otherwise a condensing boiler is taken to run its flue 4 K above the return water, and a boiler with *Condensing boiler* off gets no estimate. Excess air is taken as 1.3 and combustion air as 20 °C; propane is assumed when the heat per cubic metre of gas is 18 kWh or more. Casing and standby losses are not included. The value updates while the burner runs and holds between burns; the `heating_average` and `hot_water_average` attributes give burn-time averages over about a day, and `source` says whether the flue (`exhaust`) or the return (`return`) was used.

- **Calibration flame timeout** and **Calibration plateau timeout**: how long [calibration](how-it-works.md#calibration) waits for the burner to light (default 10 minutes) and for the water temperature to settle (default 40 minutes, at least 5).

---

Back: [Setup](setup.md) · Next: [How SAT works](how-it-works.md)
