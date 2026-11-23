# MPX additions

🇵🇱 [Polska wersja](pl/mpx.md)

> [!WARNING]
> Everything on this page was written by Claude, an AI model, and has not been reviewed by a
> person. It passes the automated tests and has run since mid-November 2026 on one real boiler
> (see [Field test](#field-test)); nothing else has been tried. Use it at your own risk, turn
> features on one at a time and watch the boiler.

This page lists what this fork (versions with a fourth number, such as 5.2.0.5) adds to [SAT v2](https://github.com/bellini666/SAT). The settings themselves are in [Options](options.md) (the Control and PWM, Heat budget, Hot water, Presence and windows, and Boiler and service menus); this page explains what they do and how they fit together.

**Defaults.** With every new option at its default SAT controls the boiler exactly as upstream SAT v2, except for the frost protection, which only heats a room at 6 °C while SAT is off. What runs regardless are the totals, the efficiency and flow estimates, the loop monitor and the repair issues: they read the boiler and raise issues, but do not control anything. A failure in any of them is logged once and the heating control carries on without it.

- [Why](#why)
- [Boiler settings](#boiler-settings)
- [Heat budget](#heat-budget)
- [Schedules and presence](#schedules-and-presence)
- [Hot water](#hot-water)
- [Monitoring](#monitoring)
- [Repair issues](#repair-issues)
- [Loop measurement](#loop-measurement)
- [After a restart](#after-a-restart)
- [Field test](#field-test)
- [Limits and what is not verified](#limits-and-what-is-not-verified)

## Why

A condensing combi boiler of 25–35 kW has a lowest power of about 4–6 kW. A well-insulated flat on screed underfloor heating needs 1–4 kW for most of the season, so the boiler cannot run continuously: it heats the water, cuts out, waits its anti-cycling time and lights again. Every start costs a purge of the combustion chamber and minutes of warming up, and wears the boiler.

Screed is slow: it stores hours of heat. It does not matter to the room whether the heat of an hour arrives in four 7-minute burns or in one 28-minute burn, but the boiler does three fewer starts. That is what the heat budget does. The rest of the additions follow from the same setup: measuring what the boiler does, catching problems early and not heating when nobody needs it.

## Boiler settings

| Option | Default | What it does |
|---|---|---|
| Boiler anti-cycling time | 0 | The boiler's own wait before it relights (installer setting, for example P17 on De Dietrich). SAT waits this plus a minute before calling the flame stuck off, calibration waits this plus two minutes for the burner to light, and the heat budget never plans a pause shorter than it. With 0 the heat budget learns it: the boiler's relight after a heating burn it held off under demand for at least a minute, the median of the last ten once three are seen (2–30 minutes, attribute `minimum_pause_minutes`); until then 10 minutes. |
| Valve opening time | 0 | How long the actuators of your room thermostats take to open (thermal actuators: 3–6 minutes). When a room starts asking for heat and none asked before, SAT waits this long before lighting the boiler. A boiler that is already burning is not affected. |
| Cut-short burns before a PWM on-phase ends | 2 | How many burns the boiler may stop by overheating in one PWM on-phase. 1 suits an oversized boiler on underfloor heating. |
| Learn the overshoot protection value | off | Adjusts the overshoot protection value from how PWM burns end: up 1 °C when the boiler cuts a burn out or the burner does not light because the water is already warmer than the setpoint, down 0.5 °C when a burn of at least 10 minutes levels off 2 °C or more below it. It stays between 30 °C and the maximum setpoint minus 3 °C; calibrating again or changing the value starts over. |
| Keep heating enabled between PWM on-phases | off | Leaves central heating enabled at the minimum setpoint in PWM off-phases, so a combi boiler does not swing its diverter valve to the hot water cylinder, where a long pump overrun would cool the cylinder. Many boilers raise a low setpoint to their own minimum (the Lumea and other Baxi boards to 25 °C, reported as ID 49 and as the setpoint the boiler accepted) and light once the water cools to it. SAT disables heating for the rest of the off-phase when the water comes within 1 K of that minimum; if the burner still lights more than 90 seconds into an off-phase, a short burn (the boiler's anti-cycling ran out) disables heating for the rest of that off-phase, and a longer one for an hour, with a warning. When the on-phase burn goes on into the off-phase (the boiler lowers its setpoint gradually and stops a few kelvin above it, a minute or three later), it is left to go out by itself and not taken for an ignition; switching heating off to end it would swing a combi boiler's valve to the cylinder. A burn still running after 10 minutes is ended by disabling heating. A short pump overrun on the boiler solves the same problem more simply. |
| PWM cycles per hour (underfloor) | 1–4 | Underfloor heating may go down to one cycle per hour. |
| Heat per cubic metre of gas | 10.2 | kWh/m³ for the gas, heat and efficiency estimates; about 24 for propane. |
| Condensing boiler | on | For the efficiency estimate of a boiler without a flue gas sensor. |

### Burner power

The heat and gas totals, the water flow and the heat budget need the burner's heat output. SAT takes it from the boiler's maximum capacity and minimum modulation level when it reports them (OpenTherm), otherwise from the **Gas use at minimum and maximum power** settings. When neither is known, the heat and gas totals stay at zero rather than being made up; the heat budget still works, counting in units of the minimum power.

OpenTherm defines the relative modulation as a share of the range between minimum and maximum power, but many boilers report a share of the maximum and read, say, 16 % at their minimum. Taken as a share of the range that would nearly double the power at the minimum. So SAT learns what the boiler reads while it is held at minimum modulation in settled burns and counts from there. A boiler whose lowest reading over many burns equals its own minimum modulation level is recognised too. Until it has seen such burns it assumes the OpenTherm meaning.

## Heat budget

Off, Learn only or On. For slow emitters (screed underfloor heating) with a boiler whose minimum power is above what the house usually needs. On only drives underfloor heating; with radiators or a heat pump it learns as in Learn only mode, because hour-long blocks would make fast emitters swing.

**The model.** Each hour SAT records the heat burned for space heating, the indoor-outdoor temperature difference, the sun and the change of the indoor temperature. Over a running day of such hours it fits *heat + S × sun = H × (indoor − outdoor) × hours + stored heat* in two steps, each with recursive least squares: H, the heat loss of the house (W/K), from the dark hours (at least 8 of them), then S, the heat the sun brings in full sun, from the clearly sunny hours on top of H, once per new such hour and only with at least an hour of full sun in the day. On a grey day a trace of sun would otherwise take all the free heat of cooking and people; the sun learned before 5.2.0.35 starts over for that reason. Learned together from one day, where the sun shines on the mildest hours, the two traded off against each other (S climbed to its limit while H fell). H is an effective value: heat from neighbours, people, appliances and a warm cylinder lowers it, which is what the budget needs. A day evens out the heat the screed stores and gives back. The heat stored per kelvin, C, starts at 4 kWh/K and is learned with H from the days the room temperature changed, a new target or a setback; on steady days it keeps its value (`heat_capacity_kwh_per_k`, 1–20 kWh/K). A masonry home with screed floors typically lands at 5–8. An hour measured at least half is scaled to the whole hour, a shorter one is left out, and the window survives restarts; the hour being measured is saved every 5 minutes and continues after a restart of up to 15 minutes. The first fit comes after 20 hours of data and the budget counts as ready after twelve fits, so about a day and a half after it is switched on (`heat_budget_ready`). With a fixed **Heat loss of the house** it is ready at once.

**The dispatch.** The heat the next period needs is *H × (target − outdoor) − S × sun*, plus a PI correction on the room error, counted as a shift of the outside temperature: 8 K per kelvin of room error, and an integral of 1 K per 1.5 kelvin-hours (at most ±8 K) that takes up what the model gets wrong. The integral only works within 0.5 °C of the target and once the budget is ready, so a change of target does not wind it up. In the simulation a target moved by 1 °C is reached in about 6 to 8 hours. With a weather forecast, the outdoor temperature is the measured one plus the forecast's trend over the next 3 hours (at most ±5 K), so a forecast that runs warmer or colder than your sensor does not bias the heat. That heat is burned in one block at minimum power:

- credit every **Period** (60 minutes: about one ignition an hour);
- a need smaller than the **Minimum burn** is carried into the next period (`heat_credit_kwh`), as is what a block could not deliver, up to one period at minimum power;
- a hot water request does not shorten a block: it runs on until its heat is delivered;
- two burns the boiler cuts out by overheating end a block; four flame losses (burns that end far below the setpoint, see Monitoring) end it too, with the heat not delivered carried over;
- a hot water reheat in the last third of a period starts the next block right away, while the boiler is warm (`hot_water_piggybacks`);
- a pause shorter than the anti-cycling time is not worth an ignition, so the block runs on;
- a room more than 0.5 °C above its target gets no heat: the running block ends and nothing is carried over (`heat_budget_room_too_warm`);
- after the target is lowered by 0.2 °C or more the house coasts: nothing burns until the room is within 0.2 °C of the new target (`heat_budget_coasting`);
- while all room valves are closed no heat is owed, so reopened valves do not start a block for the time they were closed.

Until the budget is ready the normal control runs, with its own Always use PWM setting. Once ready, SAT always uses low-load cycles, as Always use PWM does.

**Wind.** With a weather forecast entity that reports the wind speed, SAT also learns how much more heat the house loses in wind: from the dark hours, what H does not explain against the wind above its usual level (averaged over about four days). The learned share per 10 km/h is the `wind_heat_loss_percent_per_10kmh` attribute, with `wind_speed_kmh`. The need uses it (`wind_correction_active`) only after two days of fits, with the hourly wind varying by at least 4 km/h, and at 3 % per 10 km/h or more; the correction stays between −20 % and +50 %. A tight home with neighbours on some sides will often stay below that, and the integral takes up the rest anyway. SAT version 5 only measures the wind; here it is used once its effect is clear.

**Overload.** The budget only burns at minimum power. When the need stays 10 % above it for two hours while the room is at least 0.2 °C below target, as on a cold day in a larger or less insulated house, SAT hands control back to the heating curve with the boiler's own modulation, and takes it again once the need has stayed below 85 % of the minimum power for an hour (`heat_budget_overloaded`).

**Comfort schedule and setback.** With a schedule helper that is on in comfort hours, the heat budget lowers its target by the **Setback outside the schedule**. The recovery starts early by a learned time (Seem et al.: *hours = a × temperature rise + b × recent demand*), and comfort ends an hour early because the screed keeps heating. The setback only acts while the heat budget controls.

**Learn only** learns and shows the plan while the normal control runs. Two sensors carry the history: **Heat need** (kW, with the heat credit and the block length as attributes) and **Heat loss of the house** (W/K). `next_block_start` and `next_block_end` say when the next block is planned, if the need stays as it is (a hot water reheat late in a period can bring it forward). The climate's attributes show the rest (`heat_budget_ready`, `solar_gain_kw`, `heat_block_active`, `heat_budget_target`, `learning_samples`). Use it for a few days before `On`.

In a simulation of an 87 m² flat (H = 0.12 kW/K, 5.3 kW minimum power) the budget cut the burner starts from about 60–75 to about 26 a day at the same gas use, with the room mostly within about ±0.5 °C of the target. A simulation is not a house.

## Schedules and presence

- **Frost protection** (default 6 °C, in Control and PWM): while SAT is off, a room at or below this temperature is heated with 30 °C water until it is 1 °C warmer; then the boiler is handed back to the gateway and the thermostat on it. The climate shows *heating* and the attribute `frost_protection_active` meanwhile. 0 turns it off.
- **Warm weather shutdown**: central heating switches off while the outside temperature averaged over about a day (after at least 6 hours of readings) is at or above the threshold, and comes back once the average is 2 °C below it. A forecast keeps it off when the next 12 hours are warm, and keeps the heating on when they are cold; as in the heat budget only the forecast's trend counts. The average also runs while SAT is off, and starts over after an hour without readings. Hot water keeps working. Attributes `warm_weather_shutdown` and `outside_temperature_mean`.
- **Presence**: people, device trackers, zones (number of people) or groups. When nobody has been home for 30 minutes SAT switches from no preset, Home or Comfort to Away, and back to the previous preset when someone returns. With a Proximity distance sensor and a **Return distance**, the heating comes back as soon as someone is that close. Attribute `occupancy`. Set the Away preset mild for screed (for example 19 °C): a floor takes hours to recover from the default 10 °C.
- **Open window detection**: a drop of the main room temperature of 0.8 °C within 10 minutes, or of 0.3 °C within 30 minutes, switches to the Activity preset, as a contact sensor does. Each further drop of 0.1 °C within 25 minutes keeps the pause going; it ends 30 minutes after the last drop and after 2 hours at most. A floor heated room cools slower than 0.3 °C an hour on its own, so only outside air coming in drops it this fast. The room sensor needs to report tenths of a degree. For 10 minutes after a start the readings only settle, and a reading 1.5 °C or more off the previous one counts as a sensor glitch, not a drop. Attribute `window_open_detected`.

## Hot water

For boilers that accept a hot water setpoint over OpenTherm.

- **Hot water temperature** (0 = leave hot water to the boiler) and **Eco temperature**: with a **Hot water schedule** helper, the eco temperature applies outside its hours. A cooler cylinder loses less heat through its jacket, and the boiler condenses better while reheating it.
- **Legionella boost**: on the chosen day and time the cylinder is heated to 60 °C (or the boiler's own maximum when that is lower) and held there for an hour, or the boost gives up after 4 hours. One boost per week.
- SAT writes the setpoint when its value changes and once after each start, so a temperature set by hand stays until the next change. It does not check that the boiler accepted it. Attributes `hot_water_setpoint_sent`, `hot_water_legionella_boost` and `hot_water_last_boost_week`.
- **Reheats the boiler does not flag**: some boilers, the De Dietrich Lumea among them, reheat the cylinder without setting the hot water flag. A burn whose water rises more than 10 °C since ignition and above both its setpoint and the boiler's lowest heating setpoint (ID 49, otherwise 25 °C) by more than 10 °C counts as hot water after 20 seconds. Keep heating between PWM phases, the heat budget, the totals, the efficiency and the loop measurement all use this, and a heating burn the boiler stopped for such a reheat up to 5 minutes later is not counted as cut short.

## Monitoring

These run for every entry, also while SAT is off, so summer hot water counts too. They pause while the gateway is offline.

- **Totals** that only grow, for statistics and the Energy dashboard: Burner starts, Burner hours, Heat for space heating, Heat for hot water (kWh), Estimated gas use (m³), Heating degree days (base 18 °C), and with a **Gas price** an Estimated gas cost sensor. Heat and gas need a known [burner power](#burner-power).
  For boilers that leave their own counters (OpenTherm IDs 116–123) at 0 there are also Burner starts for hot water and Burner hours for hot water (a burn counts once it heats hot water, also when the boiler does not flag it), Hot water mode starts and hours, and with the OpenTherm Gateway over serial Heating mode starts and hours. The pump runs in both modes, so the mode counters stand in for the pump counters, without the pump overrun. Each heating mode start is also a diverter valve swing to heating.
- **Flame starts in the last hour.**
- **Estimated boiler efficiency**: an energy balance of the combustion on the gross calorific value (what the gas meter bills). The heat leaving with the flue gas and the latent heat of the vapour that does not condense are lost; below the dew point (about 55 °C for natural gas) part of the vapour condenses and gives its heat to the water. About 97 % at a 30 °C flue, 91 % at 50 °C, 88 % or less without condensing. The flue temperature comes from the boiler when reported; otherwise a condensing boiler is taken to run its flue 4 K above the return water, which is right near minimum power and too optimistic at high power. Excess air 1.3, combustion air 20 °C, casing and standby losses not included; propane is assumed when the heat per cubic metre of gas is 18 kWh or more. Attributes `heating_average`, `hot_water_average` (burn-time averages over a day) and `source`.
- **Estimated water flow**: the heat output divided by the flow/return spread in settled space heating burns (at least 3 minutes, at least 1.5 K spread); a drop shows loops closing.
- **Cylinder cooling by heating**: cylinder temperature drops of the last day that began within 10 minutes of a heating demand starting or ending, the sign of the diverter valve letting heating water through the cylinder coil. The attributes split the count into `after_heating_start` and `after_heating_stop` and give `all_drops_24h` to compare with. A count that grows with every heating cycle, also at night, points at the boiler; try **Keep heating enabled between PWM phases**.
- With room or radiator thermostats: **Open loops**, and **Loops to rebalance** with per room the share of the day its valve was open, how much warmer or colder it ran than the mean of the rooms, its loop's flow (learned once the loop was seen open and closed) and a rotameter hint (`reduce`, `increase`, `ok`). The hint assumes the rooms should be equally warm. `base_flow_lpm` is the flow of everything that was never seen closed: the loops without an actuator and the rooms whose valve never closed cannot be told apart.
- **Heat exchanger temperature** (OpenTherm Gateway over serial only): the temperature of the boiler's primary heat exchanger, OpenTherm data ID 34 (on the Lumea the panel's info item 08). Thermostats rarely ask for it, so SAT has the gateway ask the boiler once a minute with a priority message (`PM=34`). The sensor appears with the first answer. A boiler that does not know the ID answers Unknown-DataId: after 5 requests without a value SAT logs it and asks once an hour.
- **Flame losses**: a heating burn that ends while PWM is on with the flow more than 3 K below the setpoint lost its flame (the boiler relights by itself); it is not a cut-out, so it neither shortens the PWM cycle nor raises the overshoot advice. The heat budget ends a block after 4 flame losses and keeps the heat not delivered for the next block. `flame_losses_24h` on the climate counts them; many a day point at the ionisation electrode, flue gas recirculation or the gas supply.
- **Boiler faults around a burn start** (OpenTherm Gateway over serial only): a flame lost soon after ignition may leave a fault code for only seconds, and room thermostats ask for it about every 45 s. From each ignition until four minutes into the burn (or a minute after the flame went out) SAT asks for the fault code (ID 5) every 10 seconds. Every fault the boiler reports, also between those windows, is logged as a warning and kept on the OpenTherm IDs sensor as `fault_events` (time, code as on the boiler panel, flags; the last 20).
- **Fan speed** and **Fan speed setpoint** (OpenTherm Gateway over serial only, Hz): OpenTherm data ID 35, which many gateways ask for on their own. The sensors appear with the first answer. The setpoint the boiler accepted is on the *Control setpoint (Boiler)* sensor; a boiler raises a setpoint below its minimum (ID 49) to that minimum.
- **OpenTherm IDs** (diagnostic, OpenTherm Gateway over serial only), filled by the **Scan OpenTherm IDs** button: SAT asks the boiler once for every readable data ID (PM=<id>, one at a time, about 10 minutes in all) and lists the answers: `supported` with the raw value shown as an unsigned number, f8.8 and two bytes (which one applies depends on the ID), `data_invalid` (the ID is known but has no value now), `unknown` (Unknown-DataId) and `no_answer`. IDs whose read would carry the thermostat's own flags (0, 70, 101) and write-only IDs are never asked. `parameters` lists the boiler's transparent parameters as index: value (on Remeha and De Dietrich boilers these are the installer parameters; the index does not always match the P number on the panel). SAT hears them whenever they pass the gateway, also outside a scan: open the parameter menu of the room thermostat and it reads them all; a change made there is logged as `Boiler parameter 12 (OpenTherm TSP) changed: 7 -> 10`. Some gateways also read them all after the scan asks for their number (ID 10). The state is the number of supported IDs. The last scan is kept across restarts; an Unknown-DataId for ID 34 stops the heat exchanger requests. SAT does not use the other values yet.
- **Mould risk**, with room thermostats that report humidity (`current_humidity`, as the Heatit Z-Temp2 does) or a humidity sensor on the main room: SAT works out the relative humidity at the coldest surface of each room (outside wall corners, window reveals) from the room temperature and humidity and the outside temperature, with the temperature factor fRsi 0.72 that EN ISO 13788 rates such a spot by (the minimum for new buildings in Poland since 2021). The climate attribute `mould_risk` gives per room `surface_humidity`, its daily mean `surface_humidity_24h` (after 12 hours) and the `dew_point`. In frost a room above about 45 % is already near the limit.
- `suggested_heating_curve_coefficient` on the climate, once the heat budget is ready: from H and the floor's heat transfer learned in settled burns (`floor_heat_transfer_w_per_k`), the flow temperature the house needs at −15, −5 and 5 °C and the curve coefficient that matches it. The transfer is measured against the room, not the screed, so it is a rough guide. SAT does not change the curve itself.

Values that change with every reading (the heat need, the heat credit, the daily mean outside temperature, the flue gap) are kept out of the recorder as climate attributes, so they do not bloat the database.

## Repair issues

They appear under **Settings → System → Repairs** (and as a banner at the top of Settings) and clear themselves when the condition is gone.

| Issue | When |
|---|---|
| Low water pressure | below 0.8 bar for 10 minutes; clears at 0.9 bar |
| Water pressure keeps falling | the daily mean pressure, corrected for the water temperature, falls 0.05 bar a week or more over at least four days, with 0.1 bar lost |
| Boiler fault | the boiler reports a fault for a minute (with its OEM code) |
| Boiler often loses its flame | 6 or more heating burns lost their flame in the last day; clears at 2 |
| Heating cools the hot water cylinder | with no tap open the cylinder falls 2 K or more in the first 10 minutes of a heating burn (median of the last 10 burns, at least 5); clears at 1 K. Usually a diverter valve that lets heating water into the cylinder coil. Attribute `cylinder_drop_at_heating_start`. With a **Water meter** (Hot water menu) starts with a tap open are left out, and `cylinder_reheats_24h` / `cylinder_reheats_without_draw_24h` count the reheats and those no water use explains |
| Dirty heat exchanger | flue gas more than 12 K above the return in settled burns near minimum power, averaged over a day of burning |
| Flow too hot for the floor | underfloor only: flow above **Maximum flow for the screed** (55 °C) for 3 minutes in space heating; stays a day |
| Too little water flow | underfloor only: flow more than 20 K above the return for 5 minutes in settled burns |
| Boiler service due | **Last boiler service** plus the **Service interval** |
| Gas use went up | the heating gas of the last week is 30 % above what the four weeks before predict for its weather |
| Mould risk | the daily mean humidity at the coldest surface of a room reaches 80 % (after 12 hours of readings); clears below 75 % |

Three of them deserve a word on how they avoid false alarms:

- **Falling pressure.** The pressure of a sealed system follows the water temperature, so the end of the heating season alone lowers it. SAT learns how much the pressure moves per kelvin from how the two swing together within the last days, and compares the days at one temperature. A rise of 0.15 bar from one day to the next is a top-up and starts a new history. Hot water burns and the five minutes after them are left out.
- **Dirty heat exchanger.** At higher power the flue gas runs further above the return by design. Only burns in the lowest 15 % of the modulation range count, and only with flue gas below 90 °C (condensing). A boiler that does not report its modulation is not judged.
- **Gas use.** Heating gas per day rises in a straight line with the indoor-outdoor difference, but not from zero: sun, people and appliances heat for free. Gas per degree day therefore rises in every cold snap. SAT fits that line to the four weeks before and compares the last week with what the line predicts for its weather; hot water gas is left out, and a week whose weather lies more than 3 K outside those weeks is not judged.

## Loop measurement

The `sat.measure_loops` action (Developer tools → Actions) measures the water flow of each heating loop. It turns all room thermostats off and runs the burner at minimum power (up to your maximum setpoint) to measure the base flow of the loops without an actuator. Then it opens one room at a time (target 30 °C) and measures the rise. Each step waits the valve opening time (6 minutes when none is set) plus 5 minutes and takes 10 settled samples, so it takes about 15 minutes per room. The thermostats are put back as they were, and the result arrives as a notification and in the `loop_measurement` attribute. SAT must be in heat mode; turning it off stops the measurement. Avoid using hot water while it runs.

How the thermostats were set is saved before anything is changed. If Home Assistant stops in the middle, the thermostats are left as they are and put back from that record after the next start, as soon as each one is available again (Z-Wave thermostats can take minutes). A new measurement waits until that is done.

## After a restart

Kept across a restart of Home Assistant or a change of options: the totals, the learned heat loss with its day window, the learned recovery time, the pressure history, the gas history, the warm weather average (when the restart took less than 6 hours), an Away preset set by presence, an Activity preset set by the window detection (its 30 minutes start again), the week of the last legionella boost, the thermostat settings of a running loop measurement, the estimated water flow, the flue/return gap and the floor heat transfer.

Learned again: what the boiler reads at minimum modulation, the loop monitor's averages and flows, the floor's heat transfer, the efficiency averages, the heat credit and the current block of the heat budget.

## Field test

Since mid-November 2026 the additions have run on one installation: an 87 m² two-storey flat from 2021 in a multi-unit house (a neighbour beside it and one below), screed underfloor heating with 8 loops, a De Dietrich Lumea MPX 28/33 BIC (33 kW, minimum about 5 kW, 40 l cylinder) behind a serial OpenTherm Gateway, with a De Dietrich iSense as the room sensor. The [Example](example.md) describes it in full. The numbers below come from the boiler's history in Home Assistant, at 3–8 °C outside.

| | Before: PWM, no heat budget (16–17 Nov) | With the heat budget (20–22 Nov) |
|---|---|---|
| Heating burner starts | about 27 a day | 8–10 a day |
| Typical heating burn | 2–3 minutes, two thirds under 5 | 12–23 minutes, about one block every 2 hours |
| Flow temperature | up to the 45 °C limit | 35–44 °C; flue gas 2–3 K above the return (full condensing) |
| Burns under 5 minutes | about 18 a day | 1–2 a day, mostly flame losses; on 19 Nov, before the 25 °C fix, 16 |
| Room temperature at a 22 °C target | | 21.6–22.3 °C |

Hot water reheats are the boiler's own decision and stayed at 11–16 a day, 2–3 minutes each.

What only the real boiler showed, and what changed because of it:

- **The boiler raises a low setpoint to its own minimum.** With heating kept on between blocks, the Lumea turned the 10 °C off setpoint into 25 °C and lit for a few seconds whenever the water cooled to it. SAT now reads that minimum (ID 49, and the setpoint the boiler confirms) and disables heating at 1 K above it (5.2.0.27–28).
- **Hot water reheats without the hot water flag.** The Lumea often heats the cylinder without reporting it. SAT tells such burns by the water and does not count them as heating or as cut-outs.
- **Flame losses.** About a quarter of the heating starts lost the flame within minutes and the boiler relit by itself; at first SAT took them for cut-outs and ended the blocks. They are now told apart, counted (`flame_losses_24h`), end a block only after 4, and raise a repair issue at 6 a day (5.2.0.29–30). The cause is still open; a service visit is due.
- **Learning heat loss and sun together did not work.** With one day of data the sun rose to its 3 kW limit and H fell; they are now learned from separate hours (5.2.0.30). The house's effective heat loss came out at 45–55 W/K, lower than its walls alone because of the neighbours' heat.
- **A restart looked like an open window**, because the first readings jump; there is now a 10 minute start guard (5.2.0.30).
- **Warm-up modulation did nothing**: OpenTherm only caps the maximum modulation, and the Lumea turns itself down within 90 seconds anyway. It was removed, together with the dynamic minimum setpoint, which the budget made pointless (5.2.0.30–31).
- **Heating cools the hot water cylinder.** In the night logs the cylinder dropped 3–4 K within minutes of every heating start, with no tap open, and the boiler reheated it straight after. SAT now measures this and raises a repair issue (5.2.0.31); a diverter valve that does not switch cleanly is the likely cause.
- **Reading the boiler.** Over OpenTherm the Lumea answers 28 data IDs, gives its installer parameters (ID 10/11), fan speed (ID 35) and fault codes, but not its exchanger temperature (ID 34), counters or flame current.

## Limits and what is not verified

- Verified: unit and integration tests in CI (ruff with all rules, ty, pytest, hassfest), simulations of the heat budget on a two-node screed and room model, and about a week on one real boiler ([Field test](#field-test)): the heat budget with its learning, keep heating between blocks, the flame, hot water and fault tracking, the OpenTherm scan and parameters, the window detection and the repair issues, with a Met.no weather forecast.
- Not verified: other boilers and brands; MQTT, ESPHome and EMS connections; a heating season (frost, a whole winter, the overload hand-over); the comfort schedule, presence, hot water schedule and legionella boost, frost protection and the wind learning, which the test installation does not use yet or added last; the loop measurement on real actuators; the accuracy of the efficiency, gas and flow estimates (there is no gas meter in the test home).
- The estimates are estimates: they rest on the burner power, the boiler's own sensors and textbook combustion values.
- No config entry migration: going back to upstream SAT v2 is a matter of replacing the files.

---

Back: [README](../README.md) · See also: [Options](options.md) · [How SAT works](how-it-works.md)
