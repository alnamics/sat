"""Tests for working out the burner power from the reported modulation."""

from custom_components.sat.modulation_scale import ModulationScale


def test_the_opentherm_reading_is_a_share_of_the_range() -> None:
    scale = ModulationScale()

    assert scale.share(0) == 0.0
    assert scale.share(50) == 0.5
    assert scale.share(100) == 1.0


def test_a_boiler_that_reports_a_share_of_its_maximum_is_rescaled() -> None:
    scale = ModulationScale()

    # Capped at minimum power this boiler still reads 16 %, its minimum level
    for _ in range(10):
        scale.observe_minimum(16.0, 16.0)

    assert scale.reading_at_minimum == 16.0
    assert scale.share(16) == 0.0
    assert scale.share(100) == 1.0
    # 33 kW boiler with a 5.28 kW minimum: 50 % of the maximum is 16.5 kW
    assert abs(5.28 + (33 - 5.28) * scale.share(50) - 16.5) < 0.01


def test_a_boiler_that_ignores_the_cap_teaches_nothing() -> None:
    scale = ModulationScale()

    for _ in range(10):
        scale.observe_minimum(60.0, 16.0)

    assert scale.reading_at_minimum == 0.0
    assert scale.share(60) == 0.6


def test_a_few_readings_are_not_enough() -> None:
    scale = ModulationScale()
    scale.observe_minimum(16.0, 16.0)

    assert scale.reading_at_minimum == 0.0


def test_a_lowest_reading_at_the_minimum_level_is_a_share_of_the_maximum() -> None:
    scale = ModulationScale()

    # This boiler is never capped by SAT; it idles at 16 %, its own minimum level
    for index in range(80):
        scale.observe(16.0 + index % 7, 16.0)

    assert scale.reading_at_minimum == 16.0


def test_a_reading_below_the_minimum_level_is_a_share_of_the_range() -> None:
    scale = ModulationScale()

    for index in range(80):
        scale.observe(float(index % 30), 16.0)

    assert scale.reading_at_minimum == 0.0
