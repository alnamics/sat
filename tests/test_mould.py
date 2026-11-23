"""Tests for the mould risk at the coldest surfaces of the rooms."""

import pytest

from custom_components.sat.mould import (
    MINIMUM_HOURS,
    MouldRisk,
    airing_advice,
    dew_point,
    saturation_pressure,
    surface_humidity,
)

HOUR = 3600.0


def test_the_vapour_pressure_and_dew_point_match_the_tables() -> None:
    assert saturation_pressure(20.0) == pytest.approx(2339, rel=0.01)
    assert dew_point(20.0, 50.0) == pytest.approx(9.3, abs=0.1)


def test_a_cold_corner_is_more_humid_than_the_room() -> None:
    # 22 °C and 50 % with 0 °C outside: the corner is at about 15.8 °C
    assert surface_humidity(22.0, 50.0, 0.0) == pytest.approx(73, abs=1)
    # Warm outside, the corner is as warm as the room
    assert surface_humidity(22.0, 50.0, 25.0) == pytest.approx(50)


def run(risk: MouldRisk, humidity: float, hours: float, start: float = 0.0) -> float:
    now = start
    while now <= start + hours * HOUR:
        risk.update(now, now, rooms={"climate.bedroom": (21.0, humidity)}, outdoor=0.0)
        now += 300
    return now


def test_a_humid_room_raises_the_risk_once_a_day_is_known() -> None:
    risk = MouldRisk()

    now = run(risk, 62.0, MINIMUM_HOURS - 1)
    assert risk.rooms_at_risk == []
    assert risk.attributes["climate.bedroom"]["surface_humidity_24h"] is None

    now = run(risk, 62.0, 2, now)
    assert risk.rooms_at_risk == ["climate.bedroom"]
    assert risk.highest_mean is not None
    assert risk.highest_mean >= 80

    # Airing brings the mean down; it clears below 75 %
    run(risk, 40.0, 24, now)
    assert risk.rooms_at_risk == []


def test_a_dry_room_is_no_risk() -> None:
    risk = MouldRisk()

    run(risk, 45.0, 30)
    assert risk.rooms_at_risk == []
    assert risk.attributes["climate.bedroom"]["dew_point"] == pytest.approx(8.6, abs=0.2)


def test_no_outside_temperature_judges_nothing() -> None:
    risk = MouldRisk()

    risk.update(0.0, 0.0, rooms={"climate.bedroom": (21.0, 70.0)}, outdoor=None)
    assert risk.attributes == {}


def test_cold_outside_air_dries_a_humid_flat() -> None:
    rooms = {"climate.bathroom": (22.0, 65.0), "climate.bedroom": (21.0, 55.0)}

    # 2 °C at 90 %: about 5 g/m³ of water, against about 11 g/m³ inside
    advice = airing_advice(rooms, outdoor=2.0, outdoor_humidity=90.0)
    assert advice is not None
    assert advice["worth_airing"]
    assert advice["humidity_after_airing"] < 35


def test_damp_summer_air_does_not_dry_the_flat() -> None:
    advice = airing_advice({"climate.room": (23.0, 62.0)}, outdoor=26.0, outdoor_humidity=70.0)
    assert advice is not None
    assert advice["airing_needed"]
    assert not advice["worth_airing"]


def test_a_dry_flat_needs_no_airing() -> None:
    advice = airing_advice({"climate.room": (22.0, 40.0)}, outdoor=2.0, outdoor_humidity=90.0)
    assert advice is not None
    assert not advice["worth_airing"]
    assert airing_advice({}, outdoor=2.0, outdoor_humidity=90.0) is None
