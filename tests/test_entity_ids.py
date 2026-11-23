"""Tests for keeping the entity IDs English on a non-English system."""

from typing import TYPE_CHECKING

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sat.const import DOMAIN
from custom_components.sat.entity_ids import async_keep_english_entity_ids, entity_names

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def test_the_translations_give_the_names() -> None:
    assert entity_names("pl")[("binary_sensor", "worth_airing")] == "Warto wietrzyć"
    assert entity_names("en")[("binary_sensor", "worth_airing")] == "Worth airing"
    assert entity_names("xx") == {}


async def test_a_polish_entity_id_becomes_english(hass: HomeAssistant) -> None:
    hass.config.language = "pl"
    entry = MockConfigEntry(domain=DOMAIN, title="Kotłownia")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)}, name="Kotłownia"
    )
    registry = er.async_get(hass)
    polish = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "airing",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="kotlownia_warto_wietrzyc",
        translation_key="worth_airing",
    )
    renamed = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "summary",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="my_own_name",
        translation_key="daily_summary",
    )

    await async_keep_english_entity_ids(hass, entry)

    assert registry.async_get(polish.entity_id) is None
    assert registry.async_get("binary_sensor.kotlownia_worth_airing") is not None
    assert registry.async_get(renamed.entity_id) is not None
