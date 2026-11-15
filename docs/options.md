# Options

Open the integration page and click **Configure**. Settings are in three menus: [General](#general), [Presets](#presets) and [System Configuration](#system-configuration). Some settings only appear when they apply to your setup.

The defaults suit most homes.

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
- **Heat budget** (`Off`, `Learn only (shadow)`, `On`): for slow emitters such as screed underfloor heating with a boiler whose minimum power is above what the house needs. SAT keeps an hourly energy balance of the house (heat burned for space heating, indoor and outdoor temperature, and sun when a forecast with cloud cover is set) and learns the heat loss coefficient H with recursive least squares over a running day. Once it has about 36 hours of data it works in energy instead of flow temperatures: the heat the next period needs is H × (target − forecast outdoor temperature), minus the sun, plus a slow PI correction on the room error. That heat is burned in one block per period at minimum power. A block a hot water request interrupts runs on until its heat is delivered, heat smaller than the minimum burn is carried into the next period, and two boiler cut-outs end the block. Shadow mode learns and shows the plan in the climate attributes (`heat_loss_w_per_k`, `heat_need_kw`, `heat_block_minutes`, `heat_credit_kwh`, …) while the normal PWM keeps control. With `On` and the heat budget ready, SAT always uses low-load cycles (as Force PWM does); until then the normal control and its own Force PWM setting apply. When the house needs more than the boiler gives at minimum power (the need stays 10 % above it for two hours while the room is at least 0.2 °C below target, as on a cold day in a larger or less insulated house), SAT hands the control back to the heating curve with the boiler's own modulation, and takes it again once the need has stayed below 85 % of the minimum power for an hour; the `heat_budget_overloaded` attribute shows it. `On` only drives underfloor heating: with radiators or a heat pump it learns as in shadow mode, because hour-long blocks would make fast emitters swing.
- **Heat budget period**: one block per period; 60 minutes gives about one ignition an hour.
- **Heat budget minimum burn**: the shortest block worth an ignition.
- **Heat loss of the house**: in W/K; 0 learns it.
- **Weather forecast**: a weather entity with an hourly forecast (for example Met.no or Open-Meteo). Sensors such as Airly only give current values and cannot be used here; they can be the outside sensor of SAT instead.
- **Comfort schedule** and **Setback**: a schedule helper that is on in comfort hours. Outside them the target is lowered by the setback; the recovery starts early by a learned return time (Seem et al.: hours = a × temperature rise + b × recent demand) and comfort ends an hour early because the screed keeps heating.
- **Calibration flame timeout** and **Calibration plateau timeout**: how long [calibration](how-it-works.md#calibration) waits for the burner to light (default 10 minutes) and for the water temperature to settle (default 40 minutes, at least 5).

---

Back: [Setup](setup.md) · Next: [How SAT works](how-it-works.md)
