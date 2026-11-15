# Smart Autotune Thermostat v2 — MPX edition

[![hacs][hacs-badge]][hacs-url]
[![release][release-badge]][release-url]
![build][build-badge]

> [!WARNING]
> **Experimental, AI-written, unverified code. Use at your own risk.**
>
> The additions in this fork (versions with a fourth number, such as `5.2.0.5`) were written by
> [Claude](https://claude.ai), an AI model by Anthropic, in a conversation with the fork's owner.
> They pass the automated test suite (unit tests, ruff, ty, hassfest), but **they have not been
> reviewed by a person or run on a real boiler for any length of time**. They control a gas
> boiler: a mistake can mean a cold house, wasted gas, an overheated floor or a boiler lockout.
> Read the code before you use it, keep a backup, watch your boiler closely after installing, and
> keep the original [SAT v2](https://github.com/bellini666/SAT) at hand to go back to. Nothing
> here is endorsed by the authors of SAT.
>
> **Kod eksperymentalny, napisany przez AI i niesprawdzony. Używasz na własne ryzyko.**
> Zmiany w tym forku napisał Claude (model AI firmy Anthropic). Przechodzą testy automatyczne,
> ale nikt ich nie sprawdził ręcznie ani nie testował długo na prawdziwym kotle. Sterują kotłem
> gazowym: zrób kopię zapasową, obserwuj kocioł po instalacji i miej pod ręką oryginał.

SAT is a smart thermostat for Home Assistant that controls your boiler.

A regular thermostat turns the boiler on and off, and the boiler heats its water to a fixed, often high, temperature. SAT works out the lowest water temperature that keeps your home at the target, from the outside temperature and how far each room is from its target, and sends that to the boiler. Cooler water means less gas and fewer on/off cycles.

This fork builds on [SAT v2 by Thiago Bellini Ribeiro](https://github.com/bellini666/SAT), itself a fork of the original [Smart Autotune Thermostat](https://github.com/Alexwijn/SAT) by [Alex Wijnholds](https://github.com/Alexwijn). It was written for an oversized condensing combi boiler (De Dietrich Lumea, 33 kW, minimum about 5 kW) on screed underfloor heating behind an OpenTherm Gateway, and adds what such a setup needs to stop short cycling and save gas. Everything new is off, or only informs, until you turn it on.

## What this fork adds

All of it is described in [MPX additions][mpx].

**Control** (off by default)
- 🔋 **Heat budget**: learns the heat loss of the house and burns the heat each hour needs in one long block at minimum power, instead of several short PWM cycles. Hands back to normal modulation when the house needs more than the minimum power.
- 🌤️ **Weather forecast and sun**: the forecast trend and the sun's height and cloud cover enter the heat budget.
- ⏰ **Comfort schedule** with learned early recovery (optimum start) and an early stop.
- ☀️ **Warm weather shutdown** on the daily mean outside temperature.
- 🚿 **Hot water schedule** with an eco temperature and a weekly legionella boost.
- 🏃 **Presence**: Away preset when nobody is home, back early within a return distance.
- 🪟 **Open window detection** from fast temperature drops, without contact sensors.
- ⚙️ Boiler-specific settings: anti-cycling time, valve opening time, cut-short burns per PWM phase, keep heating enabled between PWM phases, learned overshoot protection value.

**Monitoring** (on, only informs)
- 📈 Running totals for the Energy dashboard: burner starts and hours, heat for heating and hot water, gas, heating degree days, gas cost.
- 🍃 **Estimated boiler efficiency** from the flue gas or return temperature.
- 💧 **Estimated water flow**, open loops and a per-room rotameter hint; `sat.measure_loops` measures each loop's flow.
- 🚨 Repair issues: low or falling water pressure, boiler fault, dirty heat exchanger, screed overheat, too little water flow, service due, gas use up.
- 📐 A suggested heating curve coefficient from what was learned.

## What you need

- **Home Assistant 2026.11 or newer.**
- A boiler that Home Assistant can talk to through one of:
  - [OpenTherm Gateway (OTGW)](https://otgw.tclcode.com/), over MQTT or serial
  - [ESPHome OpenTherm](https://esphome.io/components/opentherm.html)
  - [EMS-ESP](https://emsesp.org/), over MQTT
  - OpenTherm adapters such as the [DIYLess](https://diyless.com/) Master OpenTherm Shield, [Ihor Melnyk's](http://ihormelnyk.com/opentherm_adapter) adapter or [Jiří Praus'](https://www.tindie.com/products/jiripraus/opentherm-gateway-arduino-shield/) Arduino shield
- Or any `switch`, `valve` or `input_boolean` that turns your heating on and off. SAT then works as a smart on/off thermostat (most additions need a boiler that takes a setpoint).
- A room temperature sensor and an outside temperature sensor or weather entity.

The additions were developed against an OTGW in serial mode. The other connections share the same code paths but have had even less testing.

## Installation

**Make a backup** of Home Assistant first, and note your current SAT settings.

### With HACS

1. If SAT or SAT v2 is already installed through HACS, open it in HACS and choose **⋮ → Remove**. This removes the files, not your SAT entry and its settings. Do not restart yet.
2. In HACS choose **⋮ → Custom repositories**, add `https://github.com/alnamics/sat` with the type **Integration**.
3. Open **Smart Autotune Thermostat v2 (MPX)** in HACS and choose **Download**.
4. Restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alnamics&repository=sat&category=integration)

The integration domain is still `sat`, so an existing entry keeps its settings and the MPX edition takes the place of the SAT you had. HACS can hold only one of them at a time.

### By hand

Copy `custom_components/sat` from the [latest release][release-url] (the `sat.zip` file holds its contents) into your `custom_components` folder, replacing an existing SAT, and restart Home Assistant.

A new install is then added under **Settings → Devices & services → Add integration → Smart Autotune Thermostat**; the [setup guide][setup] walks through each step.

### Rolling it out safely

1. Run a day or two with all new options off. SAT then controls the boiler as upstream SAT v2 does; only the new sensors and repair issues are added. Check the logs for `sat` and your boiler's graphs.
2. Turn on the boiler settings you know (anti-cycling time, valve opening time).
3. Set the heat budget to **Learn only (shadow)** for two or three days. Once `heat_budget_ready` is true and `heat_loss_w_per_k` has settled, switch it to **On**.
4. Add the other features one at a time, so you can tell what each one does.

### Going back

In HACS remove the MPX edition and download SAT v2 again (or copy the original over `custom_components/sat` by hand), then restart. There is no config entry migration in this fork; the extra options are ignored and the extra entities become orphaned (remove them under **Settings → Entities**).

## Documentation

- [MPX additions][mpx]: every addition of this fork, what it does, its defaults and limits
- [Setup][setup]: what each setup step asks for
- [Options][options]: every setting, tab by tab
- [How SAT works][how-it-works]: heating curve, room feedback, low-load control, heat budget and calibration
- [Differences from the original SAT][differences]

## Credits

SAT is the work of [Alex Wijnholds](https://github.com/Alexwijn) and [Thiago Bellini Ribeiro](https://github.com/bellini666) and contributors. The MPX additions were written by Claude for [alnamics](https://github.com/alnamics); report problems with them here, not upstream.

<!-- Badges -->

[hacs-url]: https://hacs.xyz/docs/faq/custom_repositories/
[hacs-badge]: https://img.shields.io/badge/hacs-custom-orange.svg?style=for-the-badge
[release-badge]: https://img.shields.io/github/v/release/alnamics/sat?style=for-the-badge
[build-badge]: https://img.shields.io/github/actions/workflow/status/alnamics/sat/pytest.yml?branch=main&style=for-the-badge

<!-- References -->

[release-url]: https://github.com/alnamics/sat/releases
[mpx]: docs/mpx.md
[setup]: docs/setup.md
[options]: docs/options.md
[how-it-works]: docs/how-it-works.md
[differences]: docs/differences.md
