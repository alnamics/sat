# Example: an 87 m² flat with screed underfloor heating and a 33 kW boiler

🇵🇱 [Polska wersja](pl/example.md)

> [!WARNING]
> The description and numbers come from the first weeks of this fork on one installation
> (November 2026). The code was written by Claude, an AI model; it has not been reviewed by a
> person. Another house will give other numbers.

This page follows one flat to show what SAT does with the boiler: when and how long it burns, what it does in between, how it deals with hot water and flame losses and what it learns about the house. The general description is in [How SAT works](how-it-works.md) and [MPX additions](mpx.md).

- [The installation](#the-installation)
- [The problem: a boiler too big for the house](#the-problem-a-boiler-too-big-for-the-house)
- [Heat budget: how much and when](#heat-budget-how-much-and-when)
- [One block up close](#one-block-up-close)
- [Between blocks](#between-blocks)
- [Hot water and the cylinder](#hot-water-and-the-cylinder)
- [Flame losses](#flame-losses)
- [Loops and room thermostats](#loops-and-room-thermostats)
- [Windows, an outage, the screed](#windows-an-outage-the-screed)
- [What the sensors show](#what-the-sensors-show)
- [Settings of this installation](#settings-of-this-installation)

## The installation

| | |
|---|---|
| Flat | 87 m² in a block of flats, finished in 2021 |
| Boiler | De Dietrich Lumea MPX 28/33 BIC, condensing, 40 l cylinder (a board of the Baxi Luna Duo-Tec family) |
| Boiler power | 33 kW, minimum **4.7–5.1 kW** per the data sheet; SAT counts 33 kW × 16% = 5.3 kW |
| Heating | screed underfloor heating, 8 loops |
| Loops | 4 with Afriso actuators (5–6 minutes) and Heatit Z-Temp2 thermostats, 4 always open |
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

At 5–12 °C outside the flat needs **7–20 kWh a day** for heating, 0.3–0.8 kW on average. The boiler cannot go below 5.3 kW, so it always has to burn in bursts. The 33 kW were chosen for hot water.

A flat in a block gets a lot of free heat: from the neighbours, people, appliances and the warm cylinder. It needs less than its walls and windows lose, and SAT learns the **effective** heat loss (here 45–55 W/K), the heat the house really needs from the boiler.

SAT's aim: **few starts, long burns at minimum power, the coolest water possible.**

## Heat budget: how much and when

The heating curve and the PID are still worked out, but while the budget is ready they do not drive the burner.

1. **Need.** *H × (22 °C − outside) − sun + a correction for the room error.* Every 0.1 °C too warm or too cold moves the need by about 40 W; an integral slowly takes up what the model misses.
2. **Credit.** Each hour the need goes into the credit, and heat from the burner (not hot water) takes it out.
3. **Block.** Once credit and an hour of need make at least 10 minutes at minimum power, a block starts. At 0.4–0.6 kW that is 12–15 minutes every 2–3 hours.
4. **Learning.** Each hour SAT records the heat, the temperature difference, the sun and the change of the room temperature. It learns the heat loss from the hours without sun and the solar gain separately from the sunny ones.

A room 0.5 °C or more too warm gets nothing; after the target is lowered the budget waits until the room is within 0.2 °C of it.

## One block up close

| Time | What happens |
|---|---|
| 0:00 | SAT sends 45 °C (overshoot protection) and a maximum modulation of 0% |
| 0:05 | ignition: modulation 41%, fan 58 Hz (about 3500 rpm) |
| 0:30–1:30 | the boiler turns itself down: fan 40 → 33 → 24 → **19 Hz** (minimum, about 1150 rpm) |
| 3:00 | flow 35–40 °C, return 30–35 °C, flue gas a few K above the return: full condensing |
| 12:00–15:00 | the block delivered its heat, SAT sends 10 °C, the flame goes out |

The water never reaches 45 °C, so the boiler does not cut the burn out. For the first 4 minutes SAT asks the boiler for its fault code every 10 seconds.

## Between blocks

- SAT sends 10 °C and the boiler raises it to its own minimum of **25 °C** (P30).
- **Heating stays enabled** (*Keep heating between PWM phases*): the pump circulates and the diverter valve does not swing to the cylinder after each block. Without it the cylinder lost 2–3 K every cycle and was reheated several times a night.
- The water cools from about 35 to 26 °C. **At 26 °C SAT disables heating until the next block**, because at 25 °C the boiler would light for a dozen seconds.
- If the boiler still lights in the pause (for example when its 10 minute wait runs out), a short burn disables heating until the next block as well.

## Hot water and the cylinder

- The boiler gives hot water priority and decides on reheats itself (to 45 °C, up to about 16 kW from P13). There were 51 reheats in 4 days, mostly 1.5–4 minutes.
- **Unflagged reheats:** the Lumea does not always report heating hot water. SAT tells them by the water rising more than 10 °C above the setpoint within 20 seconds.
- **Takeover:** when the cylinder needs heat during a block the boiler stops the heating burn and reheats it. SAT does not count that as a cut-out or a flame loss, and the block goes on afterwards.
- **Morning showers:** the cylinder sensor drops to 28–34 °C, as 16 kW cannot keep up with the draw. If the water turns lukewarm at the end of a shower, a higher P13 (60–70%) or a 50 °C setpoint helps.

## Flame losses

In 4 days the flame went out in **10 of 39 heating starts** (26%). The boiler lights again after about 23 seconds, sometimes 3–4 times in a row. It happened with a cold and with a warm boiler, mostly in the evening and early morning, and more in the rain (36% against 20%). That points at the combustion: gas pressure at peak times, flue gas drawn back in, or the ionisation electrode.

SAT:
- tells a flame loss (flow more than 3 K below the setpoint) from a cut-out at the temperature limit;
- ends a block only after 4 losses and carries the heat not delivered into the next block;
- counts them in `flame_losses_24h` and raises a repair issue at 6 a day.

The Lumea does not report these losses as a fault code over OpenTherm. Its fault history is only on the boiler panel (P32–P41).

## Loops and room thermostats

The Z-Temp2 thermostats act as limiters (bedroom 22 °C, the rest 23 °C), SAT controls on the iSense. It uses the room thermostats for:

- whether any loop can take heat: with all closed the boiler does not burn and the budget builds no credit;
- the *Open loops* and *Loops to rebalance* sensors and the rotameter hints;
- the loop measurement (`sat.measure_loops`).

## Windows, an outage, the screed

- **Window:** a drop of 0.3 °C in 30 minutes or 0.8 °C in 10 minutes pauses heating (Activity preset) until 30 minutes after the last drop, 2 hours at most. Not in the first 10 minutes after a start, and not for a reading that jumps more than 1.5 °C.
- **Home Assistant down:** after a few minutes the gateway hands the boiler back to the iSense, which holds its own setpoint, so keep it at a fixed 20–21 °C rather than 16 °C.
- **Screed:** the boiler is limited to 45 °C (P15), and SAT warns when the flow stays above 55 °C for 3 minutes.

## What the sensors show

Values from 21 November (+5 °C outside):

| Sensor / attribute | Value | Meaning |
|---|---|---|
| `heat_loss_w_per_k` | about 50 | effective heat loss |
| `heat_need_kw` | 0.76 | the need right now |
| `heat_block_minutes` | 13 | length of the next block |
| `flame_losses_24h` | 2–6 | flame losses in the last day |
| `flue_return_gap` | 2.7 K | clean heat exchanger, full condensing |
| *Fan speed* | 19–58 Hz | 19 Hz is the minimum, 58 Hz ignition |
| *Estimated water flow* | about 15 l/min | with the loops open |
| *OpenTherm IDs* | 28 | the data IDs the boiler answers; attributes hold its parameters and fault codes |

The Lumea does not report start and hour counters (IDs 116–123 unknown), the heat exchanger temperature (34) or the flame current (36). SAT counts starts, hours, heat and gas itself.

## Settings of this installation

| Setting | Value | Why |
|---|---|---|
| Heating system | Underfloor | screed |
| Heating mode | Eco | control on the iSense |
| Overshoot protection | on, 45 °C | the ignition peak does not cut the burn out |
| Anti-cycling time | 10 min | same as P17 in the boiler |
| Valve opening time | 6 min | Afriso actuators |
| Keep heating between PWM phases | on | one cylinder reheat a night instead of five |
| Heat budget | On | 12–15 minute blocks every 2–3 hours |
| Heat loss of the house | 0 (learned) | a fixed value only as a fallback, then about 45 W/K |
| Detect open windows | on | the iSense reports tenths of a degree |
| Warm weather shutdown | on | heating stops on a warm daily mean |
| Boiler service | due 1 October 2027 | reminder in Repairs |

Recommended Z-Temp2 settings: report every 300 s (parameter 1) and on a 0.5 °C change (parameter 2), hysteresis 0.5 °C (parameter 10).
