# Example: an 87 m² flat with screed underfloor heating and a 33 kW boiler

🇵🇱 [Polska wersja](pl/example.md)

> [!WARNING]
> The description and numbers come from the first weeks of this fork on one installation
> (November 2026). The code was written by Claude, an AI model; it has not been reviewed by a
> person. Another house will give other numbers. Before and after: [Field test](mpx.md#field-test).

This page follows one flat to show what SAT does with the boiler: when and how long it burns, what it does in between, how it deals with hot water and flame losses and what it learns about the house. The general description is in [How SAT works](how-it-works.md) and [MPX additions](mpx.md).

- [The installation](#the-installation)
- [The problem: a boiler too big for the house](#the-problem-a-boiler-too-big-for-the-house)
- [Heat budget: how much and when](#heat-budget-how-much-and-when)
- [One block up close](#one-block-up-close)
- [Between blocks](#between-blocks)
- [Hot water and the cylinder](#hot-water-and-the-cylinder)
- [Flame losses](#flame-losses)
- [Loops and room thermostats](#loops-and-room-thermostats)
- [Humidity](#humidity)
- [Windows, an outage, the screed](#windows-an-outage-the-screed)
- [What the sensors show](#what-the-sensors-show)
- [Settings of this installation](#settings-of-this-installation)

## The installation

| | |
|---|---|
| Flat | 87 m² on two storeys, in a multi-unit house finished in 2021: a neighbour beside it and one below |
| Boiler | De Dietrich Lumea MPX 28/33 BIC, condensing, 40 l cylinder (a board of the Baxi Luna Duo-Tec family) |
| Boiler power | 33 kW, minimum **4.7–5.1 kW** per the data sheet; SAT counts 33 kW × 16% = 5.3 kW |
| Heating | screed underfloor heating, 8 loops |
| Loops | 2 always open (hallway and bathroom), the rest with Afriso actuators (5–6 minutes) under 4 Heatit Z-Temp2 thermostats |
| Connection | OpenTherm Gateway (OTGW) with an Ethernet module, as serial |
| Thermostat | De Dietrich AD289 iSense on OpenTherm, through the gateway; its temperature (tenths of a degree) is SAT's main sensor |

Boiler parameters (numbered as on the iSense; one higher on the boiler panel). SAT reads them over OpenTherm (*OpenTherm IDs* sensor):

| P | Meaning | Value |
|---|---|---|
| P09 | heating setpoint from the thermostat (OpenTherm) | 00 |
| P12 | maximum heating power | 0 (about 5 kW, factory 80) |
| P13 | maximum hot water power | 39% (about 16 kW, factory 100) |
| P15 | maximum heating temperature | 01 = 45 °C |
| P16 | pump overrun after heating | 1 min |
| P17 | wait before relighting for heating | 10 min |
| P30 | lowest setpoint from the thermostat | 25 °C |

## The problem: a boiler too big for the house

At 5 °C outside the flat needs about **37 kWh a day** for heating, 1.5 kW on average, at −2 °C about **52 kWh**, 2.2 kW. The boiler cannot go below 5.3 kW, so it always has to burn in bursts. The 33 kW were chosen for hot water.

SAT learns the **effective** heat loss, the heat the house really needs from the boiler per kelvin: here **about 90 W/K**, with a heat capacity of about 4.5 kWh/K (a time constant of about 50 hours). Heat from the neighbours, people and appliances is already taken off. In the first week SAT learned only 45–55 W/K, because its capacity took up the rest; the flat then ran 0.5–1 °C below its target until that was fixed ([field test](mpx.md#field-test)).

SAT's aim: **few starts, long burns at minimum power, the coolest water possible.**

## Heat budget: how much and when

The heating curve and the PID are still worked out, but while the budget is ready they do not drive the burner.

1. **Need.** *H × (22 °C − outside) − sun + a correction for the room error.* Every 0.1 °C too warm or too cold moves the need by about 40 W; an integral slowly takes up what the model misses.
2. **Credit.** Each hour the need goes into the credit, and heat from the burner (not hot water) takes it out.
3. **Block.** Once credit and an hour of need make at least the minimum burn (15 minutes here) at minimum power, a block starts. At 1.5–2.4 kW that is 17–27 minutes every hour; on a mild day with sun the budget skips an hour now and then.
4. **Learning.** Each hour SAT records the heat, the temperature difference, the sun and the change of the room temperature. It learns the heat loss from the hours without sun and the solar gain separately from the sunny ones.

A room 0.5 °C or more too warm gets nothing; after the target is lowered the budget waits until the room is within 0.2 °C of it.

## One block up close

| Time | What happens |
|---|---|
| 0:00 | SAT sends 45 °C (overshoot protection) and a maximum modulation of 0% |
| 0:05 | ignition: modulation 41%, fan 58 Hz (about 3500 rpm) |
| 0:30–1:30 | the boiler turns itself down: fan 40 → 33 → 24 → **19 Hz** (minimum, about 1150 rpm) |
| 3:00 | flow 35–40 °C, return 30–35 °C, flue gas a few K above the return: full condensing |
| 17:00–27:00 | the block delivered its heat, SAT sends 10 °C; the boiler turns down and the flame goes out about 3 minutes later (SAT counts that heat too) |

With enough water flowing the water stays below 45 °C, so the boiler does not cut the burn out. For the first 4 minutes SAT asks the boiler for its fault code every 10 seconds.

## Between blocks

- SAT sends 10 °C and the boiler raises it to its own minimum of **25 °C** (P30).
- **Heating stays enabled** (*Keep heating between PWM phases*): the pump circulates and the diverter valve does not swing to the cylinder after each block. Without it the cylinder lost 2–3 K every cycle and was reheated several times a night.
- The water cools from about 35 to 26 °C. **At 26 °C SAT disables heating until the next block**, because at 25 °C the boiler would light for a dozen seconds.
- If the boiler still lights in the pause (for example when its 10 minute wait runs out), a short burn disables heating until the next block as well.

## Hot water and the cylinder

- The boiler gives hot water priority and decides on reheats itself (to 45 °C, up to about 16 kW from P13). There were 51 reheats in 4 days, mostly 1.5–4 minutes.
- **Unflagged reheats:** the Lumea does not always report heating hot water. SAT tells them by the water rising more than 10 °C above the setpoint within 20 seconds.
- **Takeover:** when the cylinder needs heat during a block the boiler stops the heating burn and reheats it. SAT does not count that as a cut-out or a flame loss, and the block goes on afterwards.
- **Relight after a reheat:** lit for heating within half a minute of a reheat, the still hot exchanger lifted the flow from 40 to 50 °C in 15 seconds and the boiler cut out, then waited 10 minutes. SAT now holds the heating setpoint at 10 °C during the reheat and for at least a minute after it, with the pump running, until the flow is below 35 °C (*Relight margin after hot water*, 10 K under the 45 °C on-phase setpoint).
- **A reheat as a starting point:** when the cylinder is reheated late in a period, the next block starts right after it, on a warm boiler (`hot_water_piggybacks`).
- **Morning showers:** the cylinder sensor drops to 28–34 °C, as 16 kW cannot keep up with the draw. If the water turns lukewarm at the end of a shower, a higher P13 (60–70%) or a 50 °C setpoint helps.

## Flame losses

In the first 4 days the flame went out in **10 of 39 heating starts** (26%); from 25 November on it did not happen once. The boiler lights again after about 23 seconds, sometimes 3–4 times in a row. It happened with a cold and with a warm boiler, mostly in the evening and early morning, and more in the rain (36% against 20%). That points at the combustion: gas pressure at peak times, flue gas drawn back in, or the ionisation electrode.

SAT:
- tells a flame loss (flow more than 3 K below the setpoint) from a cut-out at the temperature limit;
- ends a block only after 4 losses and carries the heat not delivered into the next block;
- counts them in `flame_losses_24h` and raises a repair issue at 6 a day.

The Lumea does not report these losses as a fault code over OpenTherm. Its fault history is only on the boiler panel (P32–P41).

## Loops and room thermostats

The Z-Temp2 thermostats act as limiters (bedroom 22 °C, the rest 23 °C), SAT controls on the iSense. It uses the room thermostats for:

- whether any loop can take heat: with all closed the boiler does not burn and the budget builds no credit;
- the *Open loops* and *Loops to rebalance* sensors and the rotameter hints;
- the [ignition protection](mpx.md#ignition-protection): which sets of open loops let too little water through;
- the loop measurement (`sat.measure_loops`).

**Too little water.** On 27 November the living room and the bedroom sat at their thermostats' targets all day and only the children's room loop stayed open besides the hallway and bathroom. The boiler moved 10–11 l/min instead of 13–18, the flow jumped from 31 to 50 °C within 15 seconds of each ignition, and 25 of 27 ignitions cut out at the 45 °C ceiling (P15), each followed by a 10 minute wait. The room still held 21.8–22.1 °C, because the budget made the heat up in long burns once a loop opened, but the boiler made twice the starts. SAT now learns such valve sets and lets a block wait up to 45 minutes for another loop. Thermostats that switch every minute when their room sits at the target (as two of these did) do not open their loop at all, as the actuators need 5–6 minutes; a wider hysteresis on the Z-Temp2, setting the limiters a degree higher, or a faster pump or a bypass are the real cures.

## Humidity

The Z-Temp2 thermostats report humidity, so SAT works out the mould risk at the outside wall corners. With laundry drying indoors, the bedroom and the children's room ran at a dew point of 13–16 °C, which put the corners at 93–100 % (the *Mould risk* repair issue). At that humidity even 23 °C would not keep the corners below 80 %; a dew point of 9–10 °C (45–50 % at 21 °C) would, at 20–21 °C. A dehumidifier in the room where the laundry dries and airing when *Worth airing* is on are what helps; lowering the room temperature before the air is drier makes it worse.

## Windows, an outage, the screed

- **Window:** a drop of 0.3 °C in 30 minutes or 0.8 °C in 10 minutes pauses heating (Activity preset) until 30 minutes after the last drop, 2 hours at most. Not in the first 10 minutes after a start, and not for a reading that jumps more than 1.5 °C.
- **Home Assistant down:** after a few minutes the gateway hands the boiler back to the iSense, which holds its own setpoint, so keep it at a fixed 20–21 °C rather than 16 °C.
- **Screed:** the boiler is limited to 45 °C (P15), and SAT warns when the flow stays above 55 °C for 3 minutes.

## What the sensors show

Values from 27 November (−2 °C outside, wind 18 km/h):

| Sensor / attribute | Value | Meaning |
|---|---|---|
| `heat_loss_w_per_k` | 91 | effective heat loss |
| `heat_capacity_kwh_per_k` | 4.7 | heat stored per kelvin |
| `heat_need_kw` | 2.4 | the need right now |
| `heat_block_minutes` | 24 | length of the next block |
| `wind_heat_loss_percent_per_10kmh` | 0.3–2.3 | the wind barely matters here |
| `flame_losses_24h` | 0 | flame losses in the last day |
| `flue_return_gap` | 2.8 K | clean heat exchanger, full condensing |
| *Estimated boiler efficiency* | about 96 % | return at 28–32 °C |
| *Fan speed* | 19–58 Hz | 19 Hz is the minimum, 58 Hz ignition |
| *Estimated water flow* | 10–18 l/min | 10–11 with one room loop open, 13–18 with more |
| *Boiler power* | 5.28 kW | 33 kW × 16 % minimum modulation, as the boiler reports |
| *OpenTherm IDs* | 28 | the data IDs the boiler answers; attributes hold its parameters and fault codes |

The Lumea does not report start and hour counters (IDs 116–123 unknown), the heat exchanger temperature (34) or the flame current (36). SAT counts starts, hours, heat and gas itself.

## Settings of this installation

| Menu → setting | Value | Why |
|---|---|---|
| Heating system | Underfloor heating | screed |
| Heating curve and PID → Heating mode | Eco | control on the iSense |
| Heating curve and PID → Overshoot protection value | 45 °C | the ignition peak does not cut the burn out |
| Boiler and service → Boiler anti-cycling time | 10 min | same as P17 in the boiler |
| Boiler and service → Valve opening time | 6 min | Afriso actuators |
| Boiler and service → Keep heating enabled between PWM on-phases | on | one cylinder reheat a night instead of five |
| Heat budget → Heat budget | On | blocks of 17–27 minutes about every hour |
| Heat budget → Minimum burn | 15 min | fewer, longer blocks |
| Heat budget → Heat loss of the house | 0 (learned) | a fixed value only as a fallback, then about 90 W/K |
| Heat budget → Heat capacity of the house | 0 (learned) | about 4.5 kWh/K |
| Heat budget → Weather forecast | Met.no | trend, sun and wind |
| Heat budget → Warm weather shutdown | on | heating stops on a warm daily mean |
| Boiler and service → Wait for an open loop | 45 min | default |
| Boiler and service → Relight margin after hot water | 10 K | default |
| Hot water → Water meter | the flat's water meter | tells reheats after a tap from those without |
| Presence and windows → Detect open windows from the temperature | off | turned off by the owner; hours with a fast room drop are still left out of the learning |
| Boiler and service → Last boiler service | due 1 October 2027 | reminder in Repairs |

Recommended Z-Temp2 settings: report every 300 s (parameter 1) and on a 0.5 °C change (parameter 2), hysteresis 0.5 °C (parameter 10).
