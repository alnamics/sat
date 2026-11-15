"""Tests for spotting heating gas use that the weather does not explain."""

from datetime import date, timedelta

from custom_components.sat.energy_signature import EnergySignature

HEAT_LOSS = 0.12  # kW/K
FREE_HEAT = 0.4  # kW from sun, people and appliances
GAS_ENERGY = 10.2  # kWh/m³


def feed(
    signature: EnergySignature,
    day: date,
    days: int,
    outdoor: float,
    *,
    extra: float = 1.0,
    swing: float = 3.0,
) -> date:
    """Feed whole days of a house that needs HEAT_LOSS per kelvin minus its free heat."""
    for index in range(days):
        # The weather varies from day to day around its mean
        temperature = outdoor + swing * ((index % 5) - 2) / 2
        gas_per_hour = max(0.0, HEAT_LOSS * (21 - temperature) - FREE_HEAT) / GAS_ENERGY * extra
        for _ in range(24 * 12):
            signature.update(
                300,
                day.isoformat(),
                heating_gas=gas_per_hour / 12,
                indoor=21.0,
                outdoor=temperature,
            )
        day += timedelta(days=1)
    return day


def test_a_cold_snap_is_not_an_anomaly() -> None:
    signature = EnergySignature()
    day = feed(signature, date(2026, 11, 1), 28, 8.0)
    assert signature.ratio is None or abs(signature.ratio - 1.0) < 0.05

    # Gas per degree day rises by a third here, but the house behaves exactly as before
    day = feed(signature, day, 8, 4.0)

    ratio = signature.ratio
    assert ratio is not None
    assert abs(ratio - 1.0) < 0.08


def test_more_gas_in_the_same_weather_stands_out() -> None:
    signature = EnergySignature()
    day = feed(signature, date(2026, 11, 1), 28, 5.0)
    feed(signature, day, 8, 5.0, extra=1.4)

    ratio = signature.ratio
    assert ratio is not None
    assert 1.3 <= ratio <= 1.5


def test_weather_far_outside_the_reference_is_not_judged() -> None:
    signature = EnergySignature()
    day = feed(signature, date(2026, 11, 1), 28, 12.0)
    feed(signature, day, 8, -10.0)

    assert signature.ratio is None


def test_the_history_survives_a_restart() -> None:
    signature = EnergySignature()
    day = feed(signature, date(2026, 11, 1), 28, 5.0)
    feed(signature, day, 8, 5.0, extra=1.4)

    restored = EnergySignature()
    restored.load(signature.to_dict())

    assert restored.ratio == signature.ratio
