"""The translations stay complete and match the options flow."""

import json
import re
from pathlib import Path
from typing import Any

TRANSLATIONS = Path(__file__).parent.parent / "custom_components" / "sat" / "translations"
PLACEHOLDER = re.compile(r"\{\w+\}")


def flatten(tree: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            flat.update(flatten(value, f"{prefix}/{key}"))
        else:
            flat[f"{prefix}/{key}"] = value
    return flat


def load(language: str) -> dict[str, str]:
    return flatten(json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")))


def test_polish_has_every_english_string_with_the_same_placeholders() -> None:
    english, polish = load("en"), load("pl")

    assert sorted(set(english) - set(polish)) == []
    assert sorted(set(polish) - set(english)) == []
    for key, text in english.items():
        assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(polish[key])), key


def test_every_drop_down_has_its_labels() -> None:
    source = (TRANSLATIONS.parent / "config_flow.py").read_text(encoding="utf-8")
    english = json.loads((TRANSLATIONS / "en.json").read_text(encoding="utf-8"))

    keys = set(re.findall(r'_choice\(\s*"(\w+)"', source))
    assert keys
    assert keys <= set(english["selector"])
