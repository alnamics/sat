"""Tests for the report for the service technician."""

from datetime import UTC, datetime

from custom_components.sat.service_report import build_service_report


def test_the_report_lists_the_counts_faults_and_parameters_in_polish() -> None:
    report = build_service_report(
        language="pl",
        title="Lumea",
        boiler="Serial",
        now=datetime(2026, 11, 23, 10, 0, tzinfo=UTC),
        totals={"starts": 1500.0, "burn_hours": 210.5, "heating_mode_starts": 320.0},
        attributes={
            "flame_losses_24h": 0,
            "cylinder_drop_at_heating_start": 3.7,
            "cylinder_reheats_24h": 8,
            "cylinder_reheats_without_draw_24h": 3,
            "active_issues": ["cylinder_cools_in_heating"],
        },
        yesterday={"date": "2026-11-22", "burner_starts": 14, "heating_starts": 12},
        pressure=1.4,
        faults=[{"time": "2026-11-20T06:00:00+00:00", "code": 128, "flags": "0x01"}],
        parameters={12: 0, 15: 1},
        parameter_changes=[{"time": "t", "index": 16, "old": 240, "new": 1}],
        settings={"minimum_setpoint": 45.0, "maximum_setpoint": 45.0},
    )

    assert "Raport dla serwisu: Lumea" in report
    assert "Starty palnika: 1500\n" in report
    assert "3.7 K" in report
    assert "8 / 3" in report
    assert "cylinder_cools_in_heating" in report
    assert "128 (0x01)" in report
    assert "12: 0, 15: 1" in report
    assert "16 240 → 1" in report


def test_a_boiler_without_a_gateway_scan_leaves_the_faults_out() -> None:
    report = build_service_report(
        language="en",
        title="SAT",
        boiler="Switch",
        now=datetime(2026, 11, 23, 10, 0, tzinfo=UTC),
        totals={},
        attributes={},
        yesterday={},
        pressure=None,
        faults=None,
        parameters=None,
        parameter_changes=None,
        settings={},
    )

    assert "Fault codes" not in report
    assert "Burner starts: —" in report
