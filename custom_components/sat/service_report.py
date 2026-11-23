"""A report for the service technician: what SAT saw of the boiler, in numbers.

The boiler's own fault history and counters often stay on its panel or are not reported over
OpenTherm at all. The report puts what SAT counted and noticed into one text that can be shown
or copied at a service visit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Service report",
        "made": "Made on",
        "boiler": "Boiler",
        "totals": "Counted by SAT",
        "starts": "Burner starts",
        "hours": "Burner hours",
        "hot_water_starts": "Burner starts for hot water",
        "hot_water_hours": "Burner hours for hot water",
        "heating_starts": "Heating mode starts (diverter valve to heating)",
        "gas": "Estimated gas use",
        "heat": "Heat for space heating / hot water",
        "last_day": "Last 24 hours",
        "flame_losses": "Flame losses in heating burns",
        "cylinder_drop": "Cylinder drop at heating start (median, no tap open)",
        "reheats": "Cylinder reheats / without water use",
        "pressure": "Water pressure",
        "pressure_trend": "Pressure trend",
        "flue_gap": "Flue gas above return (near minimum power)",
        "issues": "Open repair issues",
        "none": "none",
        "yesterday": "Yesterday",
        "faults": "Fault codes the boiler reported",
        "no_faults": "No fault codes reported over OpenTherm.",
        "parameters": "Boiler parameters (OpenTherm TSP index: value)",
        "changes": "Parameter changes",
        "settings": "SAT settings",
        "overshoot": "Setpoint of a heat block (overshoot protection value)",
        "maximum": "Maximum flow temperature",
        "unknown": "not known",
    },
    "pl": {
        "title": "Raport dla serwisu",
        "made": "Sporządzono",
        "boiler": "Kocioł",
        "totals": "Zliczone przez SAT",
        "starts": "Starty palnika",
        "hours": "Godziny pracy palnika",
        "hot_water_starts": "Starty palnika na c.w.u.",
        "hot_water_hours": "Godziny palnika na c.w.u.",
        "heating_starts": "Włączenia trybu c.o. (przełączenia zaworu na c.o.)",
        "gas": "Szacowane zużycie gazu",
        "heat": "Ciepło na ogrzewanie / c.w.u.",
        "last_day": "Ostatnie 24 godziny",
        "flame_losses": "Zaniki płomienia przy ogrzewaniu",
        "cylinder_drop": "Spadek zasobnika przy starcie c.o. (mediana, bez poboru)",
        "reheats": "Dogrzania zasobnika / bez poboru wody",
        "pressure": "Ciśnienie wody",
        "pressure_trend": "Trend ciśnienia",
        "flue_gap": "Spaliny ponad powrotem (blisko mocy minimalnej)",
        "issues": "Otwarte komunikaty w Naprawach",
        "none": "brak",
        "yesterday": "Wczoraj",
        "faults": "Kody usterek zgłoszone przez kocioł",
        "no_faults": "Kocioł nie zgłosił kodów usterek przez OpenTherm.",
        "parameters": "Parametry kotła (indeks OpenTherm TSP: wartość)",
        "changes": "Zmiany parametrów",
        "settings": "Ustawienia SAT",
        "overshoot": "Nastawa bloku grzania (ochrona przed przegrzaniem)",
        "maximum": "Maksymalna temperatura zasilania",
        "unknown": "nieznane",
    },
}


def _value(value: Any, unit: str = "", digits: int = 1) -> str:  # noqa: ANN401
    if value is None:
        return "—"
    if isinstance(value, float):
        value = round(value) if digits == 0 else round(value, digits)
    return f"{value} {unit}".strip()


def build_service_report(
    *,
    language: str,
    title: str,
    boiler: str,
    now: datetime,
    totals: Mapping[str, float],
    attributes: Mapping[str, Any],
    yesterday: Mapping[str, Any],
    pressure: float | None,
    faults: list[dict[str, Any]] | None,
    parameters: Mapping[int, int] | None,
    parameter_changes: list[dict[str, Any]] | None,
    settings: Mapping[str, Any],
) -> str:
    """Return the report as Markdown."""
    text = LABELS["pl" if language.startswith("pl") else "en"]
    total, attribute = totals.get, attributes.get
    heat = f"{_value(total('heating_kwh'), 'kWh', 0)} / {_value(total('hot_water_kwh'), 'kWh', 0)}"
    reheats = (
        f"{_value(attribute('cylinder_reheats_24h'))} / "
        f"{_value(attribute('cylinder_reheats_without_draw_24h'))}"
    )
    drop = _value(attribute("cylinder_drop_at_heating_start"), "K")
    trend = _value(attribute("pressure_trend_bar_per_week"), "bar/7d", 2)
    issues = ", ".join(attribute("active_issues") or []) or text["none"]
    lines = [
        f"## {text['title']}: {title}",
        f"{text['made']}: {now.strftime('%Y-%m-%d %H:%M')}. {text['boiler']}: {boiler}.",
        "",
        f"**{text['totals']}**",
        f"- {text['starts']}: {_value(total('starts'), digits=0)}",
        f"- {text['hours']}: {_value(total('burn_hours'), 'h')}",
        f"- {text['hot_water_starts']}: {_value(total('hot_water_starts'), digits=0)}",
        f"- {text['hot_water_hours']}: {_value(total('hot_water_burn_hours'), 'h')}",
        f"- {text['heating_starts']}: {_value(total('heating_mode_starts'), digits=0)}",
        f"- {text['gas']}: {_value(total('gas_m3'), 'm³')}",
        f"- {text['heat']}: {heat}",
        "",
        f"**{text['last_day']}**",
        f"- {text['flame_losses']}: {_value(attribute('flame_losses_24h'))}",
        f"- {text['cylinder_drop']}: {drop}",
        f"- {text['reheats']}: {reheats}",
        f"- {text['pressure']}: {_value(pressure, 'bar')}",
        f"- {text['pressure_trend']}: {trend}",
        f"- {text['flue_gap']}: {_value(attribute('flue_return_gap'), 'K')}",
        f"- {text['issues']}: {issues}",
    ]

    if yesterday:
        counts = ", ".join(
            f"{text[label]}: {yesterday.get(key)}"
            for label, key in (
                ("starts", "burner_starts"),
                ("heating_starts", "heating_starts"),
                ("hot_water_starts", "hot_water_starts"),
            )
        )
        lines += ["", f"**{text['yesterday']} ({yesterday.get('date')})**", f"- {counts}"]

    if faults is not None:
        lines += ["", f"**{text['faults']}**"]
        lines += [
            f"- {fault.get('time')}: {fault.get('code')} ({fault.get('flags')})"
            for fault in faults[-10:]
        ] or [text["no_faults"]]

    if parameters:
        listed = ", ".join(f"{index}: {value}" for index, value in sorted(parameters.items()))
        lines += ["", f"**{text['parameters']}**", listed]
    if parameter_changes:
        lines += ["", f"**{text['changes']}**"]
        lines += [
            f"- {change.get('time')}: {change.get('index')} "
            f"{change.get('old')} → {change.get('new')}"
            for change in parameter_changes[-10:]
        ]

    lines += [
        "",
        f"**{text['settings']}**",
        f"- {text['overshoot']}: {_value(settings.get('minimum_setpoint'), '°C')}",
        f"- {text['maximum']}: {_value(settings.get('maximum_setpoint'), '°C')}",
    ]
    return "\n".join(lines)
