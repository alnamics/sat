"""Estimate the boiler efficiency from the flue gas temperature.

An energy balance of the combustion, on the gross calorific value of the gas (the energy the gas
bill counts): the heat that leaves with the flue gas is lost, as is the latent heat of the water
vapour that does not condense. Below the dew point (about 55 °C for natural gas) the flue gas
holds only as much vapour as saturation allows, and the rest condenses in the heat exchanger and
gives its heat to the water. That is where a condensing boiler gains, and why a cooler flue (and
so a cooler return) means a higher efficiency.

The flue gas temperature comes from the boiler when it reports one. Otherwise a condensing boiler
is assumed to run its flue a few kelvin above the return water, as a premix condensing heat
exchanger does; without either no estimate is given. Casing and standby losses are not included.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SECONDS_PER_HOUR = 3600.0
MAXIMUM_STEP_SECONDS = 300.0
ATMOSPHERE_KPA = 101.325
# Combustion air of a room sealed boiler, preheated in the concentric flue
AIR_TEMPERATURE = 20.0
# Typical excess air of a modulating premix burner
EXCESS_AIR = 1.3
# A premix condensing heat exchanger brings the flue gas this close to the return water
FLUE_ABOVE_RETURN = 4.0
# Molar heat capacities of the flue gas components near 50 °C, J/(mol·K)
CP_CO2 = 37.4
CP_H2O = 33.6
CP_O2 = 29.4
CP_N2 = 29.1
NITROGEN_PER_OXYGEN = 3.76
# Natural gas above this many kWh/m³ is taken as propane
PROPANE_ENERGY_CONTENT = 18.0
AVERAGING_HOURS = 24.0


@dataclass(frozen=True, slots=True)
class Fuel:
    """Combustion of one mole of fuel: CxHy + (x + y/4) O2 -> x CO2 + y/2 H2O."""

    carbon: int
    hydrogen: int
    gross_kj_per_mol: float

    @property
    def oxygen(self) -> float:
        return self.carbon + self.hydrogen / 4

    @property
    def water(self) -> float:
        return self.hydrogen / 2


METHANE = Fuel(carbon=1, hydrogen=4, gross_kj_per_mol=890.4)
PROPANE = Fuel(carbon=3, hydrogen=8, gross_kj_per_mol=2219.2)


def fuel_for(energy_content_kwh_per_m3: float) -> Fuel:
    return PROPANE if energy_content_kwh_per_m3 >= PROPANE_ENERGY_CONTENT else METHANE


def saturation_pressure_kpa(temperature: float) -> float:
    """Water vapour saturation pressure (Magnus formula)."""
    return 0.61094 * math.exp(17.625 * temperature / (temperature + 243.04))


def latent_heat_kj_per_mol(temperature: float) -> float:
    """Heat of vaporisation of water, 44.0 kJ/mol at 25 °C, falling slowly with temperature."""
    return 45.05 - 0.0425 * temperature


def gross_efficiency(
    flue: float,
    fuel: Fuel = METHANE,
    *,
    air: float = AIR_TEMPERATURE,
    excess_air: float = EXCESS_AIR,
) -> float:
    """Return the efficiency on the gross calorific value, as a fraction."""
    oxygen = fuel.oxygen * excess_air
    dry = fuel.carbon + oxygen - fuel.oxygen + oxygen * NITROGEN_PER_OXYGEN

    # Vapour left in the flue gas: all of it above the dew point, saturation below it
    saturation = saturation_pressure_kpa(flue)
    vapour = fuel.water
    if saturation < ATMOSPHERE_KPA:
        vapour = min(vapour, dry * saturation / (ATMOSPHERE_KPA - saturation))

    heat_capacity = (
        fuel.carbon * CP_CO2
        + (oxygen - fuel.oxygen) * CP_O2
        + oxygen * NITROGEN_PER_OXYGEN * CP_N2
        + vapour * CP_H2O
    ) / 1000
    sensible = heat_capacity * max(0.0, flue - air)
    latent = vapour * latent_heat_kj_per_mol(flue)
    return max(0.0, 1 - (sensible + latent) / fuel.gross_kj_per_mol)


def flue_temperature(
    *, exhaust: float | None, return_temperature: float | None, condensing: bool
) -> tuple[float | None, str | None]:
    """Return the flue gas temperature to use, and where it came from."""
    if exhaust is not None:
        return exhaust, "exhaust"
    if condensing and return_temperature is not None:
        return return_temperature + FLUE_ABOVE_RETURN, "return"
    return None, None


class EfficiencyTracker:
    """Keep the current estimate and burn-time averages for heating and hot water."""

    def __init__(self, fuel: Fuel = METHANE, *, condensing: bool = True) -> None:
        self._fuel = fuel
        self._condensing = condensing
        self._last_update: float | None = None
        self.current: float | None = None
        self.source: str | None = None
        self.heating_average: float | None = None
        self.hot_water_average: float | None = None

    @property
    def attributes(self) -> dict[str, object]:
        def percent(value: float | None) -> float | None:
            return None if value is None else round(value * 100, 1)

        return {
            "source": self.source,
            "heating_average": percent(self.heating_average),
            "hot_water_average": percent(self.hot_water_average),
        }

    def update(
        self,
        now: float,
        *,
        flame: bool,
        hot_water: bool,
        exhaust: float | None,
        return_temperature: float | None,
    ) -> None:
        dt = (
            0.0 if self._last_update is None else min(now - self._last_update, MAXIMUM_STEP_SECONDS)
        )
        self._last_update = now
        if not flame:
            return

        flue, source = flue_temperature(
            exhaust=exhaust, return_temperature=return_temperature, condensing=self._condensing
        )
        if flue is None:
            return

        efficiency = gross_efficiency(flue, self._fuel)
        self.current, self.source = efficiency, source

        weight = min(1.0, dt / (AVERAGING_HOURS * SECONDS_PER_HOUR))
        if hot_water:
            self.hot_water_average = (
                efficiency
                if self.hot_water_average is None
                else self.hot_water_average + (efficiency - self.hot_water_average) * weight
            )
        else:
            self.heating_average = (
                efficiency
                if self.heating_average is None
                else self.heating_average + (efficiency - self.heating_average) * weight
            )
