"""Heat budget control for slow emitters such as underfloor heating.

A boiler that cannot modulate below the heat the house needs has to burn in blocks. Instead of
deriving the block length from flow temperatures, the heat budget works in energy:

* a grey-box energy balance, learned online with recursive least squares, gives the heat loss
  coefficient H (kW/K) and, when a weather forecast with cloud cover is available, a solar gain S;
* with the forecast's wind speed it also learns how much more the house loses in wind, and uses
  that once the wind has varied enough to show a clear effect;
* the heat the house needs over the next period follows from H, the forecast outdoor temperature
  and a slow PI correction on the room error;
* the burner delivers that heat in one block per period at its minimum power, and heat that a hot
  water request or a boiler cut-out kept from being delivered is carried into the next period;
* with a comfort schedule it starts the recovery from a setback early enough to be on time, using
  the return-time model of Seem et al. (tau = a * dT + b * u, with u the recent heating demand).
"""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN, PWMStatus

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SECONDS_PER_HOUR = 3600.0

# Heat stored per kelvin in the rooms and the screed of a flat; only corrects the 24 h balance
BUILDING_CAPACITY_KWH_PER_K = 4.0
# Learning: one record per hour, a balance over the last day, about four days of memory
LEARNING_WINDOW_HOURS = 24
LEARNING_FORGETTING = 0.99
LEARNING_MINIMUM_UPDATES = 12
# Covariance is kept below this many times its starting value
COVARIANCE_LIMIT_FACTOR = 10.0
# An hour with a gap in the data says nothing reliable about the balance
MAXIMUM_STEP_SECONDS = 300.0
# An hour with at least this share measured is scaled up to the full hour; a shorter one is
# left out of the window, which keeps the other hours
MINIMUM_HOUR_COVERAGE = 0.5
# The day window learns once it holds this many hours, and drops hours older than a day
LEARNING_MINIMUM_HOURS = 20
LEARNING_WINDOW_SPAN_HOURS = 26.0
# The forecast adds its trend to the measured outside temperature, within this much
FORECAST_TREND_LIMIT = 5.0
HEAT_LOSS_BOUNDS = (0.02, 0.6)
# An hour with less sun than this (sun height times clear sky, summed over the hour) is dark
DARK_SUN_HOURS = 0.02
LEARNING_MINIMUM_DARK_HOURS = 8
LEARNING_MINIMUM_SUN_HOURS = 0.5
SOLAR_GAIN_BOUNDS = (0.0, 3.0)
# Wind: the heat loss rises by this share per km/h above the usual wind. It is learned from the
# dark hours on top of H and used only once the wind has varied and the effect is clear
WIND_SENSITIVITY_BOUNDS = (0.0, 0.02)
WIND_MEAN_HOURS = 96.0
WIND_MINIMUM_UPDATES = 48
WIND_MINIMUM_SPREAD = 4.0
WIND_MINIMUM_SENSITIVITY = 0.003
WIND_FACTOR_BOUNDS = (0.8, 1.5)
# Before anything is learned an 87 m² flat loses roughly this much per kelvin
DEFAULT_HEAT_LOSS_KW_PER_K = 0.12

# Room error correction, in kelvin of outside temperature per kelvin of room error. The
# proportional part brings the room back in hours rather than days; the integral takes up what
# the model gets wrong (free heat, a heat loss that is off) and only works close to the target,
# so a change of target does not wind it up
PROPORTIONAL_GAIN = 8.0
INTEGRAL_HOURS = 1.5
INTEGRAL_LIMIT_K = 8.0
INTEGRAL_BAND_K = 0.5
# A room this far above its target gets no heat at all
SURPLUS_STOP_K = 0.5
# After the target is lowered the house coasts down to it; heating resumes this close to it,
# early enough for the screed to hold the room there
COAST_TARGET_DROP = 0.2
COAST_END_K = 0.2
# The hour being measured is saved this often, so a restart loses little of it
PARTIAL_HOUR_SAVE_SECONDS = 300.0
# A saved hour is continued when the restart took no longer than this
PARTIAL_HOUR_MAXIMUM_GAP_SECONDS = 900.0

# The heat released now reaches the rooms over the next hours, so that is the outdoor
# temperature that matters
FORECAST_HORIZON_HOURS = 3.0

# Boiler cut-outs in one block that end it, because the water cannot take the heat
CUT_SHORT_BURNS_TO_END_BLOCK = 2
# A boiler relights a lost flame by itself; this many in one block end it well before the
# boiler locks out (a Baxi board after about 12), and the heat stays owed for the next block
FLAME_LOSSES_TO_END_BLOCK = 4

# Recovery from a setback: hours per kelvin and hours at full demand, bounded
PREHEAT_DEFAULT_HOURS_PER_K = 2.0
PREHEAT_DEFAULT_DEMAND_HOURS = 1.0
PREHEAT_MAXIMUM_HOURS = 8.0
PREHEAT_REACHED_MARGIN = 0.1
PREHEAT_MINIMUM_RISE = 0.3
DEMAND_SMOOTHING_HOURS = 24.0
# The screed keeps heating after the burner stops, so comfort can end this much earlier
OPTIMUM_STOP_SECONDS = 3600.0
# A house that needs more than the minimum power is handed back to modulation
OVERLOAD_SMOOTHING_HOURS = 1.0
OVERLOAD_ENTER = 1.1
OVERLOAD_EXIT = 0.85
OVERLOAD_ENTER_SECONDS = 2 * 3600.0
OVERLOAD_EXIT_SECONDS = 3600.0
OVERLOAD_ROOM_DEFICIT = 0.2
# A hot water reheat this close to the next period starts that period's block at once,
# while the boiler is still warm, instead of lighting it again a little later
PIGGYBACK_SHARE = 1 / 3
# A target this much higher starts a new period at once; this much lower ends a recovery
TARGET_RAISE_RESTART = 0.5
RECOVERY_CANCEL_DROP = 0.2


def solar_elevation(when: datetime, latitude: float, longitude: float) -> float:
    """Return the solar elevation in degrees (NOAA approximation, about 1 degree)."""
    utc = when.astimezone(UTC) if when.tzinfo is not None else when
    hours = utc.hour + utc.minute / 60 + utc.second / 3600
    gamma = 2 * math.pi / 365 * (utc.timetuple().tm_yday - 1 + (hours - 12) / 24)
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    solar_minutes = hours * 60 + equation_of_time + 4 * longitude
    hour_angle = math.radians(solar_minutes / 4 - 180)
    phi = math.radians(latitude)
    cos_zenith = math.sin(phi) * math.sin(declination) + math.cos(phi) * math.cos(
        declination
    ) * math.cos(hour_angle)
    return math.degrees(math.asin(min(max(cos_zenith, -1.0), 1.0)))


def sun_factor(when: datetime, latitude: float, longitude: float, cloud_coverage: float) -> float:
    """Return 0..1 for how much sun can reach the windows: sun height times clear sky."""
    height = math.sin(math.radians(solar_elevation(when, latitude, longitude)))
    return max(0.0, height) * (1 - min(max(cloud_coverage, 0.0), 100.0) / 100)


def heat_budget_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.heat_budget")


@dataclass(slots=True)
class HeatBudgetInputs:
    """What the heat budget needs from one control step."""

    now: float
    wall_time: datetime
    indoor: float | None
    target: float | None
    outdoor: float | None
    heating_power_kw: float
    minimum_power_kw: float
    flame_active: bool
    hot_water_active: bool
    outdoor_forecast: float | None = None
    outdoor_forecast_now: float | None = None
    solar: float | None = None
    solar_forecast: float | None = None
    # km/h
    wind: float | None = None
    cut_short_burn_ends: tuple[float, ...] = ()
    flame_loss_ends: tuple[float, ...] = ()
    comfort: bool | None = None
    next_comfort_change: datetime | None = None
    setback: float = 0.0
    # False while no loop can take heat (all valves closed); nothing is owed then
    heating_allowed: bool = True


@dataclass(slots=True)
class _Hour:
    heat_kwh: float = 0.0
    kelvin_hours: float = 0.0
    sun_hours: float = 0.0
    seconds: float = 0.0
    indoor_start: float | None = None
    indoor_end: float | None = None
    wall_end: float | None = None
    # Wind speed times the temperature difference, the wind speed, and the seconds it was known
    wind_kelvin_hours: float = 0.0
    wind_hours: float = 0.0
    wind_seconds: float = 0.0

    def to_list(self) -> list[float | None]:
        return [
            self.heat_kwh,
            self.kelvin_hours,
            self.sun_hours,
            self.seconds,
            self.indoor_start,
            self.indoor_end,
            self.wall_end,
            self.wind_kelvin_hours,
            self.wind_hours,
            self.wind_seconds,
        ]

    @property
    def has_wind(self) -> bool:
        return self.seconds > 0 and self.wind_seconds >= MINIMUM_HOUR_COVERAGE * self.seconds

    @classmethod
    def from_list(cls, values: object) -> _Hour | None:
        # Hours saved before the wind was recorded have seven values
        if not isinstance(values, list) or len(values) not in (7, len(cls.__slots__)):
            return None
        numbers = [float(value) for value in values if isinstance(value, int | float)]
        if len(numbers) != len(values):
            return None
        return cls(*numbers)


def _balance(hours: list[_Hour]) -> tuple[float, float, float]:
    """Return the heat, the kelvin hours and the heat stored in the house over these hours."""
    heat = sum(h.heat_kwh for h in hours)
    kelvin_hours = sum(h.kelvin_hours for h in hours)
    # Each hour's own temperature change, so a missing hour leaves no false jump
    stored = BUILDING_CAPACITY_KWH_PER_K * sum(
        (h.indoor_end or 0.0) - (h.indoor_start or 0.0) for h in hours
    )
    return heat, kelvin_hours, stored


class _RecursiveLeastSquares:
    """Recursive least squares with forgetting for a small parameter vector."""

    def __init__(self, theta: list[float], variance: list[float], forgetting: float) -> None:
        self.theta: list[float] = [float(value) for value in theta]
        size = len(theta)
        self.p: list[list[float]] = [
            [variance[i] if i == j else 0.0 for j in range(size)] for i in range(size)
        ]
        self.forgetting = forgetting
        self.limit = max(variance) * COVARIANCE_LIMIT_FACTOR
        self.updates = 0

    def update(self, x: list[float], y: float) -> None:
        size = len(self.theta)
        px = [sum(self.p[i][j] * x[j] for j in range(size)) for i in range(size)]
        denominator = self.forgetting + sum(x[i] * px[i] for i in range(size))
        if denominator <= 0:
            return

        gain = [value / denominator for value in px]
        error = y - sum(self.theta[i] * x[i] for i in range(size))
        self.theta = [self.theta[i] + gain[i] * error for i in range(size)]
        self.p = [
            [(self.p[i][j] - gain[i] * px[j]) / self.forgetting for j in range(size)]
            for i in range(size)
        ]
        # A parameter that is never excited (no sun without a forecast) would see its
        # covariance grow without bound under forgetting
        largest = max(self.p[i][i] for i in range(size))
        if largest > self.limit:
            factor = self.limit / largest
            self.p = [[value * factor for value in row] for row in self.p]
        self.updates += 1

    def to_dict(self) -> dict[str, Any]:
        return {"theta": self.theta, "p": self.p, "updates": self.updates}

    def load(self, data: dict[str, Any]) -> None:
        theta, p = data.get("theta"), data.get("p")
        if (
            isinstance(theta, list)
            and len(theta) == len(self.theta)
            and isinstance(p, list)
            and len(p) == len(self.theta)
        ):
            self.theta = [float(value) for value in theta]
            self.p = [[float(value) for value in row] for row in p]
            self.updates = int(data.get("updates", 0))


class HeatBudget:
    """Learn the heat loss of the house and dose the burner in blocks of one period."""

    def __init__(
        self,
        *,
        period_seconds: float = SECONDS_PER_HOUR,
        minimum_burn_seconds: float = 600.0,
        minimum_off_seconds: float = 600.0,
        heat_loss_kw_per_k: float | None = None,
    ) -> None:
        self._period = max(900.0, float(period_seconds))
        self._minimum_burn = max(180.0, float(minimum_burn_seconds))
        self._minimum_off = max(0.0, float(minimum_off_seconds))
        self._fixed_heat_loss = heat_loss_kw_per_k or None

        # The heat loss is learned from the hours without sun, the solar gain from the sunny
        # ones on top of it: learned together from one day, where the sun and the mild hours
        # come at the same time, the two traded off against each other
        self._learner = _RecursiveLeastSquares(
            [DEFAULT_HEAT_LOSS_KW_PER_K], [0.01], LEARNING_FORGETTING
        )
        self._solar_learner = _RecursiveLeastSquares([0.0], [0.25], LEARNING_FORGETTING)
        self._wind_learner = _RecursiveLeastSquares([0.0], [1e-4], LEARNING_FORGETTING)
        self._wind_mean: float | None = None
        self._wind_square = 0.0
        self._wind: float | None = None
        self._hours: deque[_Hour] = deque(maxlen=LEARNING_WINDOW_HOURS)
        self._hour = _Hour()
        self._hour_started: float | None = None
        # Wall time the running hour began, and how far a restored hour already was
        self._hour_started_wall: float | None = None
        self._restored_hour_seconds: float | None = None
        self._last_partial_save: float | None = None

        self._preheat = _RecursiveLeastSquares(
            [PREHEAT_DEFAULT_HOURS_PER_K, PREHEAT_DEFAULT_DEMAND_HOURS], [1.0, 1.0], 0.95
        )
        self._recovery: tuple[float, float, float] | None = None
        self._demand = 0.5
        self._load = 0.0
        self._overloaded = False
        self._overload_change_since: float | None = None

        self._store: Store[dict[str, Any]] | None = None
        self._last_update: float | None = None
        self._integral = 0.0
        self._surplus = False
        self._coasting = False
        self._credit = 0.0
        self._need = 0.0

        self._period_end: float | None = None
        self._block_target = 0.0
        self._block_delivered = 0.0
        self._block_started: float | None = None
        self._block_active = False
        self._last_block_end: float | None = None
        self._hot_water_seen = False
        self._piggybacks = 0
        self._planned_on = 0.0
        self._effective_target: float | None = None
        self._target_seen: float | None = None
        self._minimum_power = 5.0

    # ---------------------------------------------------------------- storage

    async def async_initialize(self, hass: HomeAssistant, entry_id: str) -> None:
        if self._store is not None:
            return

        self._store = heat_budget_store(hass, entry_id)
        if (data := await self._store.async_load()) is None:
            return

        self._load_learners(data)
        self._preheat.load(data.get("preheat", {}))
        self._integral = float(data.get("integral", 0.0))
        self._demand = float(data.get("demand", self._demand))
        self._clamp_parameters()

        # The day window survives a restart, so the learning picks up where it was
        now = datetime.now(UTC).timestamp()
        for values in data.get("hours", []):
            hour = _Hour.from_list(values)
            if (
                hour is not None
                and hour.wall_end is not None
                and now - hour.wall_end <= LEARNING_WINDOW_SPAN_HOURS * SECONDS_PER_HOUR
            ):
                self._hours.append(hour)

        # The hour that was being measured continues after a short restart
        current = _Hour.from_list(data.get("current"))
        started = data.get("current_started")
        if (
            current is not None
            and current.wall_end is not None
            and isinstance(started, int | float)
            and 0 <= now - current.wall_end <= PARTIAL_HOUR_MAXIMUM_GAP_SECONDS
            and 0 <= now - started < SECONDS_PER_HOUR
        ):
            self._hour = current
            self._hour_started_wall = float(started)
            self._restored_hour_seconds = now - started
        _LOGGER.debug("Loaded heat budget: H=%.3f kW/K.", self.heat_loss)

    def _load_learners(self, data: dict[str, Any]) -> None:
        heat_loss = data.get("heat_loss") or {}
        theta = heat_loss.get("theta") if isinstance(heat_loss, dict) else None
        if isinstance(theta, list) and len(theta) == 2:  # noqa: PLR2004 - learned together before
            # Keep what was learned; the variances start over for the separate learners
            self._learner.theta = [float(theta[0])]
            self._learner.updates = int(heat_loss.get("updates", 0))
            self._solar_learner.theta = [float(theta[1])]
        else:
            self._learner.load(heat_loss)
            self._solar_learner.load(data.get("solar_gain") or {})
        wind = data.get("wind") or {}
        if isinstance(wind, dict):
            self._wind_learner.load(wind)
            mean, square = wind.get("mean"), wind.get("square")
            if isinstance(mean, int | float) and isinstance(square, int | float):
                self._wind_mean, self._wind_square = float(mean), float(square)
        self._clamp_parameters()

    async def async_save(self) -> None:
        """Write the learning state now, before the entry unloads."""
        if self._store is not None:
            await self._store.async_save(self._data_to_save())

    def _save(self) -> None:
        if self._store is not None:
            self._store.async_delay_save(self._data_to_save, 120)

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "heat_loss": self._learner.to_dict(),
            "solar_gain": self._solar_learner.to_dict(),
            "wind": {
                **self._wind_learner.to_dict(),
                "mean": self._wind_mean,
                "square": self._wind_square,
            },
            "preheat": self._preheat.to_dict(),
            "integral": self._integral,
            "demand": self._demand,
            "hours": [hour.to_list() for hour in self._hours],
            "current": self._hour.to_list(),
            "current_started": self._hour_started_wall,
        }

    # ------------------------------------------------------------- properties

    @property
    def heat_loss(self) -> float:
        """Heat loss coefficient in kW/K."""
        if self._fixed_heat_loss is not None:
            return self._fixed_heat_loss
        return self._learner.theta[0]

    @property
    def solar_gain(self) -> float:
        """Heat gained in full sun in kW."""
        return self._solar_learner.theta[0]

    @property
    def wind_sensitivity(self) -> float:
        """Learned rise of the heat loss per km/h above the usual wind."""
        return self._wind_learner.theta[0]

    @property
    def wind_spread(self) -> float | None:
        """Standard deviation of the hourly wind speed over the last days, in km/h."""
        if self._wind_mean is None:
            return None
        return math.sqrt(max(0.0, self._wind_square - self._wind_mean**2))

    @property
    def wind_correction_active(self) -> bool:
        spread = self.wind_spread
        return (
            self._fixed_heat_loss is None
            and self._wind_learner.updates >= WIND_MINIMUM_UPDATES
            and spread is not None
            and spread >= WIND_MINIMUM_SPREAD
            and self.wind_sensitivity >= WIND_MINIMUM_SENSITIVITY
        )

    def _wind_factor(self, wind: float | None) -> float:
        if wind is None or self._wind_mean is None or not self.wind_correction_active:
            return 1.0
        factor = 1.0 + self.wind_sensitivity * (wind - self._wind_mean)
        return min(max(factor, WIND_FACTOR_BOUNDS[0]), WIND_FACTOR_BOUNDS[1])

    @property
    def ready(self) -> bool:
        """Return True once the heat loss is known well enough to control with."""
        return (
            self._fixed_heat_loss is not None or self._learner.updates >= LEARNING_MINIMUM_UPDATES
        )

    @property
    def status(self) -> PWMStatus:
        return PWMStatus.ON if self._block_active else PWMStatus.OFF

    @property
    def duty_cycle(self) -> tuple[int, int]:
        on_time = round(self._planned_on)
        return on_time, max(0, round(self._period) - on_time)

    @property
    def effective_target(self) -> float | None:
        return self._effective_target

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            "heat_budget_ready": self.ready,
            "heat_loss_w_per_k": round(self.heat_loss * 1000),
            "solar_gain_kw": round(self.solar_gain, 2),
            "wind_speed_kmh": None if self._wind is None else round(self._wind),
            "wind_heat_loss_percent_per_10kmh": round(self.wind_sensitivity * 1000, 1),
            "wind_correction_active": self.wind_correction_active,
            "heat_need_kw": round(self._need, 2),
            "heat_credit_kwh": round(self._credit, 2),
            "heat_block_minutes": round(self._planned_on / 60),
            "heat_block_active": self._block_active,
            "heat_budget_target": self._effective_target,
            "preheat_hours_per_k": round(self._preheat.theta[0], 2),
            "learning_samples": self._learner.updates,
            "heat_budget_overloaded": self._overloaded,
            "heat_budget_room_too_warm": self._surplus,
            "heat_budget_coasting": self._coasting,
            "hot_water_piggybacks": self._piggybacks,
        }

    # ------------------------------------------------------------- the update

    def update(self, inputs: HeatBudgetInputs) -> None:
        """Learn from the last step and decide whether the burner should run."""
        now = inputs.now
        dt = 0.0 if self._last_update is None else now - self._last_update
        self._last_update = now
        self._minimum_power = max(1.0, inputs.minimum_power_kw)
        self._wind = inputs.wind

        delivered = 0.0
        if inputs.flame_active and not inputs.hot_water_active:
            delivered = inputs.heating_power_kw * min(dt, MAXIMUM_STEP_SECONDS) / SECONDS_PER_HOUR

        self._learn(inputs, dt, delivered)

        indoor, outdoor = inputs.indoor, inputs.outdoor
        if indoor is None or inputs.target is None or outdoor is None:
            self._end_block(now)
            return

        if not inputs.heating_allowed:
            # Closed valves: the rooms are warm enough, so no debt builds up for later
            self._credit = min(self._credit, 0.0)
            self._need = 0.0
            self._block_target = 0.0
            self._period_end = None
            self._end_block(now)
            return

        target = self._comfort_target(inputs, inputs.target, indoor)
        self._effective_target = round(target, 2)
        self._track_recovery(inputs, target, indoor)
        self._track_coasting(target, indoor)

        self._need = self._heat_need(inputs, target, indoor, outdoor, dt)
        step = min(dt, MAXIMUM_STEP_SECONDS) / SECONDS_PER_HOUR
        limit = self._minimum_power * self._period / SECONDS_PER_HOUR
        self._credit = min(max(self._credit + self._need * step - delivered, -limit), limit)
        self._demand += (min(self._need / self._minimum_power, 1.0) - self._demand) * min(
            1.0, step / DEMAND_SMOOTHING_HOURS
        )

        self._track_overload(now, step, target - indoor)

        # A room that is too warm is owed nothing, and a running block has done enough
        if self._surplus:
            self._credit = min(self._credit, 0.0)
            self._block_target = 0.0
            self._end_block(now)

        if self._block_active:
            self._block_delivered += delivered
            self._continue_block(inputs)

        # A target raised by hand or by the schedule starts a new period at once
        raised = (
            self._target_seen is not None and target - self._target_seen >= TARGET_RAISE_RESTART
        )
        self._target_seen = target
        if raised and not self._block_active:
            self._period_end = None

        # Right after a hot water reheat the boiler is warm: bring the next block forward
        hot_water_ended = self._hot_water_seen and not inputs.hot_water_active
        self._hot_water_seen = inputs.hot_water_active
        if (
            hot_water_ended
            and not self._block_active
            and self._period_end is not None
            and self._period_end - now <= self._period * PIGGYBACK_SHARE
            and self._may_start(now)
        ):
            self._period_end = None
            piggyback = True
        else:
            piggyback = False

        if self._period_end is None or now >= self._period_end:
            self._plan_period(now)

        if not self._block_active and self._block_target > 0 and self._may_start(now):
            self._block_active = True
            self._block_started = now
            self._block_delivered = 0.0
            if piggyback:
                self._piggybacks += 1

    @property
    def overloaded(self) -> bool:
        """Return True while the house needs more heat than the boiler gives at minimum power."""
        return self._overloaded

    def _track_overload(self, now: float, step: float, error: float) -> None:
        load = self._need / self._minimum_power
        self._load += (load - self._load) * min(1.0, step / OVERLOAD_SMOOTHING_HOURS)

        if self._overloaded:
            changing = self._load <= OVERLOAD_EXIT
            hold = OVERLOAD_EXIT_SECONDS
        else:
            changing = (
                self.ready and self._load >= OVERLOAD_ENTER and error >= OVERLOAD_ROOM_DEFICIT
            )
            hold = OVERLOAD_ENTER_SECONDS

        if not changing:
            self._overload_change_since = None
            return

        if self._overload_change_since is None:
            self._overload_change_since = now
        if now - self._overload_change_since >= hold:
            self._overloaded = not self._overloaded
            self._overload_change_since = None

    def _heat_need(
        self,
        inputs: HeatBudgetInputs,
        target: float,
        indoor: float,
        outdoor: float,
        dt: float,
    ) -> float:
        # The forecast's trend over the next hours, on top of the measured temperature:
        # a forecast that runs warmer or colder than the local sensor does not bias the need
        if inputs.outdoor_forecast is not None and inputs.outdoor_forecast_now is not None:
            trend = inputs.outdoor_forecast - inputs.outdoor_forecast_now
            outdoor += min(max(trend, -FORECAST_TREND_LIMIT), FORECAST_TREND_LIMIT)
        solar = inputs.solar_forecast if inputs.solar_forecast is not None else inputs.solar
        error = target - indoor

        base = self.heat_loss * (target - outdoor) * self._wind_factor(
            inputs.wind
        ) - self.solar_gain * (solar or 0.0)
        need = base + self.heat_loss * (PROPORTIONAL_GAIN * error + self._integral)

        # The integral only winds further while the burner can still follow it
        # (and only once the heat loss is known, or it soaks up the learning error)
        saturated_high = need >= self._minimum_power and error > 0
        saturated_low = need <= 0 and error < 0
        if (
            self.ready
            and not self._coasting
            and not saturated_high
            and not saturated_low
            and abs(error) <= INTEGRAL_BAND_K
        ):
            self._integral += (
                error * min(dt, MAXIMUM_STEP_SECONDS) / (INTEGRAL_HOURS * SECONDS_PER_HOUR)
            )
            self._integral = min(max(self._integral, -INTEGRAL_LIMIT_K), INTEGRAL_LIMIT_K)

        self._surplus = self._coasting or error <= -SURPLUS_STOP_K
        if self._surplus:
            return 0.0
        return max(0.0, need)

    # -------------------------------------------------------------- dispatch

    def _plan_period(self, now: float) -> None:
        period_hours = self._period / SECONDS_PER_HOUR
        energy = self._credit + self._need * period_hours
        on_time = min(max(energy / self._minimum_power * SECONDS_PER_HOUR, 0.0), self._period)

        # A pause shorter than the boiler's own wait is not worth an extra ignition
        if on_time >= self._period - max(self._minimum_off, self._minimum_burn):
            on_time = self._period
        elif on_time < self._minimum_burn:
            on_time = 0.0

        self._period_end = now + self._period
        self._planned_on = on_time
        self._block_target = on_time / SECONDS_PER_HOUR * self._minimum_power

        if self._block_active:
            # Burning straight on into the next period needs no new ignition
            if on_time > 0:
                self._block_started = now
                self._block_delivered = 0.0
            else:
                self._end_block(now)

    def _may_start(self, now: float) -> bool:
        return self._last_block_end is None or now - self._last_block_end >= self._minimum_off

    def _continue_block(self, inputs: HeatBudgetInputs) -> None:
        now = inputs.now
        started = now if self._block_started is None else self._block_started
        cut_short = sum(1 for ended in inputs.cut_short_burn_ends if ended >= started)
        if cut_short >= CUT_SHORT_BURNS_TO_END_BLOCK:
            _LOGGER.info("The boiler cut out %d burns; ending the heat block.", cut_short)
            # The water could not take the heat, so do not push the rest straight after
            self._credit = min(self._credit, self._minimum_power * self._period / 7200)
            self._block_target = 0.0
            self._end_block(now)
            return

        losses = sum(1 for ended in inputs.flame_loss_ends if ended >= started)
        if losses >= FLAME_LOSSES_TO_END_BLOCK:
            _LOGGER.warning(
                "The boiler lost its flame %d times in this heat block; ending it, "
                "the heat not delivered carries over to the next block.",
                losses,
            )
            self._block_target = 0.0
            self._end_block(now)
            return

        if self._planned_on < self._period and self._block_delivered >= self._block_target:
            self._block_target = 0.0
            self._end_block(now)

    def _end_block(self, now: float) -> None:
        if self._block_active:
            self._last_block_end = now
        self._block_active = False
        self._block_started = None

    # -------------------------------------------------------------- learning

    def _learn(self, inputs: HeatBudgetInputs, dt: float, delivered: float) -> None:
        now = inputs.now
        wall = inputs.wall_time.timestamp()
        if self._hour_started is None:
            if self._restored_hour_seconds is not None:
                # Pick the saved hour up where the restart interrupted it
                self._hour_started = now - self._restored_hour_seconds
                self._restored_hour_seconds = None
            else:
                self._hour_started = now
                self._hour_started_wall = wall
                self._hour = _Hour(indoor_start=inputs.indoor)
            self._last_partial_save = now
            return

        if dt <= MAXIMUM_STEP_SECONDS and inputs.indoor is not None and inputs.outdoor is not None:
            hours = dt / SECONDS_PER_HOUR
            self._hour.heat_kwh += delivered
            self._hour.kelvin_hours += (inputs.indoor - inputs.outdoor) * hours
            self._hour.sun_hours += (inputs.solar or 0.0) * hours
            if inputs.wind is not None:
                self._hour.wind_kelvin_hours += (
                    (inputs.indoor - inputs.outdoor) * inputs.wind * hours
                )
                self._hour.wind_hours += inputs.wind * hours
                self._hour.wind_seconds += dt
            self._hour.seconds += dt
            self._hour.indoor_end = inputs.indoor
            self._hour.wall_end = wall

        if now - self._hour_started < SECONDS_PER_HOUR:
            if (
                self._last_partial_save is None
                or now - self._last_partial_save >= PARTIAL_HOUR_SAVE_SECONDS
            ):
                self._last_partial_save = now
                self._save()
            return

        hour, self._hour = self._hour, _Hour(indoor_start=inputs.indoor)
        self._hour_started = now
        self._hour_started_wall = wall
        self._last_partial_save = now

        # Drop the hours that fell out of the day
        while (
            self._hours
            and self._hours[0].wall_end is not None
            and wall - self._hours[0].wall_end > LEARNING_WINDOW_SPAN_HOURS * SECONDS_PER_HOUR
        ):
            self._hours.popleft()

        if (
            hour.seconds < MINIMUM_HOUR_COVERAGE * SECONDS_PER_HOUR
            or hour.indoor_start is None
            or hour.indoor_end is None
            or hour.wall_end is None
        ):
            # Too little of this hour was measured; the rest of the day stays
            return

        # A partly measured hour stands for the whole hour
        scale = SECONDS_PER_HOUR / hour.seconds if hour.seconds < SECONDS_PER_HOUR else 1.0
        hour.heat_kwh *= scale
        hour.kelvin_hours *= scale
        hour.sun_hours *= scale
        hour.wind_kelvin_hours *= scale
        hour.wind_hours *= scale
        hour.wind_seconds *= scale
        self._track_wind(hour)
        self._hours.append(hour)
        self._save()
        if len(self._hours) < LEARNING_MINIMUM_HOURS:
            return

        self._fit()
        self._save()

    def _fit(self) -> None:
        """Fit the heat loss to the dark hours of the last day and the solar gain to the rest."""
        # heat + S * sun = H * kelvin_hours + stored
        dark = [h for h in self._hours if h.sun_hours <= DARK_SUN_HOURS]
        sunny = [h for h in self._hours if h.sun_hours > DARK_SUN_HOURS]
        if len(dark) >= LEARNING_MINIMUM_DARK_HOURS:
            heat, kelvin_hours, stored = _balance(dark)
            if kelvin_hours > 0:
                self._learner.update([kelvin_hours], heat - stored)
        if self._learner.updates > 0 and sunny:
            heat, kelvin_hours, stored = _balance(sunny)
            sun_hours = sum(h.sun_hours for h in sunny)
            if sun_hours >= LEARNING_MINIMUM_SUN_HOURS:
                self._solar_learner.update(
                    [sun_hours], self.heat_loss * kelvin_hours + stored - heat
                )
        if self._learner.updates > 0 and self._wind_mean is not None:
            self._fit_wind([h for h in dark if h.has_wind])
        self._clamp_parameters()

    def _track_wind(self, hour: _Hour) -> None:
        """Average the hourly wind over the last days: the wind effect is measured from there."""
        if not hour.has_wind:
            return
        speed = hour.wind_hours / (hour.wind_seconds / SECONDS_PER_HOUR)
        if self._wind_mean is None:
            self._wind_mean, self._wind_square = speed, speed**2
            return
        weight = 1 / WIND_MEAN_HOURS
        self._wind_mean += (speed - self._wind_mean) * weight
        self._wind_square += (speed**2 - self._wind_square) * weight

    def _fit_wind(self, hours: list[_Hour]) -> None:
        # What H does not explain in the dark hours, against the wind above its usual level:
        # heat - stored - H * kelvin_hours = H * w * (wind_kelvin_hours - mean * kelvin_hours)
        if len(hours) < LEARNING_MINIMUM_DARK_HOURS or self._wind_mean is None:
            return
        heat, kelvin_hours, stored = _balance(hours)
        wind_kelvin_hours = sum(h.wind_kelvin_hours * h.seconds / h.wind_seconds for h in hours)
        x = self.heat_loss * (wind_kelvin_hours - self._wind_mean * kelvin_hours)
        if abs(x) < 1e-6:  # noqa: PLR2004
            return
        self._wind_learner.update([x], heat - stored - self.heat_loss * kelvin_hours)

    def _clamp_parameters(self) -> None:
        theta = self._learner.theta
        theta[0] = min(max(theta[0], HEAT_LOSS_BOUNDS[0]), HEAT_LOSS_BOUNDS[1])
        solar = self._solar_learner.theta
        solar[0] = min(max(solar[0], SOLAR_GAIN_BOUNDS[0]), SOLAR_GAIN_BOUNDS[1])
        wind = self._wind_learner.theta
        wind[0] = min(max(wind[0], WIND_SENSITIVITY_BOUNDS[0]), WIND_SENSITIVITY_BOUNDS[1])
        a, b = self._preheat.theta
        self._preheat.theta = [min(max(a, 0.1), PREHEAT_MAXIMUM_HOURS), min(max(b, 0.0), 4.0)]

    # ------------------------------------------------------- comfort schedule

    def preheat_hours(self, rise: float) -> float:
        """Hours the house needs to rise by this many kelvin."""
        a, b = self._preheat.theta
        return min(max(a * rise + b * self._demand, 0.0), PREHEAT_MAXIMUM_HOURS)

    def _comfort_target(self, inputs: HeatBudgetInputs, target: float, indoor: float) -> float:
        if inputs.comfort is None or inputs.setback <= 0:
            return target

        setback_target = target - inputs.setback
        change = inputs.next_comfort_change
        seconds_to_change = (
            (change - inputs.wall_time).total_seconds() if change is not None else math.inf
        )

        if inputs.comfort:
            # Optimum stop: the screed carries the house through the last hour
            return setback_target if 0 <= seconds_to_change <= OPTIMUM_STOP_SECONDS else target

        # Optimum start: begin the recovery early enough to be warm at the change
        rise = max(0.0, target - indoor)
        if 0 <= seconds_to_change <= self.preheat_hours(rise) * SECONDS_PER_HOUR:
            return target
        return setback_target

    def _track_coasting(self, target: float, indoor: float) -> None:
        """After the target is lowered, heat nothing until the room has come down to it."""
        if (
            self._target_seen is not None
            and self._target_seen - target >= COAST_TARGET_DROP
            and indoor > target + COAST_END_K
        ):
            self._coasting = True
        elif self._coasting and (
            indoor <= target + COAST_END_K
            or (self._target_seen is not None and target > self._target_seen)
        ):
            self._coasting = False

    def _track_recovery(self, inputs: HeatBudgetInputs, target: float, indoor: float) -> None:
        if self._recovery is None:
            if (
                self._target_seen is not None
                and target - self._target_seen >= PREHEAT_MINIMUM_RISE
                and target - indoor >= PREHEAT_MINIMUM_RISE
            ):
                self._recovery = (inputs.now, target - indoor, self._demand)
            return

        started, rise, demand = self._recovery
        if target < indoor - 1.0 or target - (self._target_seen or target) < -RECOVERY_CANCEL_DROP:
            # The target went down again before the house got there
            self._recovery = None
            return

        if indoor >= target - PREHEAT_REACHED_MARGIN:
            hours = (inputs.now - started) / SECONDS_PER_HOUR
            self._preheat.update([rise, demand], min(hours, PREHEAT_MAXIMUM_HOURS))
            self._clamp_parameters()
            self._recovery = None
            _LOGGER.debug("Recovery of %.1f K took %.1f h.", rise, hours)
            self._save()
