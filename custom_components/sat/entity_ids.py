"""Keep the entity IDs English when Home Assistant names new entities in another language.

Home Assistant builds the entity ID of a new entity from its name in the language set up at that
moment, so on a Polish system a new sensor gets an ID like ..._warto_wietrzyc. Dashboards,
automations and the documentation use the English IDs, so an entity whose ID is exactly the one
generated from its translated name gets the English one instead, with the same part in front.
An ID the user changed is left alone.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

TRANSLATIONS = Path(__file__).parent / "translations"


def entity_names(language: str) -> dict[tuple[str, str], str]:
    """Return the entity names of a language by platform and translation key."""
    path = TRANSLATIONS / f"{language}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        (platform, key): value["name"]
        for platform, entities in (data.get("entity") or {}).items()
        for key, value in entities.items()
        if isinstance(value, dict) and isinstance(value.get("name"), str)
    }


async def async_keep_english_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rename the entities of this entry whose IDs came from their translated names."""
    language = hass.config.language.split("-")[0]
    if language == "en":
        return

    english, local = await hass.async_add_executor_job(
        lambda: (entity_names("en"), entity_names(language))
    )
    if not local:
        return

    registry = er.async_get(hass)
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        key = (item.domain, item.translation_key or "")
        translated, name = local.get(key), english.get(key)
        if translated is None or name is None or translated == name or "{" in name:
            continue

        # The device part in front is kept as it is, whatever it came from
        object_id = item.entity_id.split(".", 1)[1]
        suffix = slugify(translated)
        if object_id == suffix:
            prefix = ""
        elif object_id.endswith(f"_{suffix}"):
            prefix = object_id.removesuffix(suffix)
        else:
            continue
        target = f"{item.domain}.{prefix}{slugify(name)}"
        if registry.async_get(target) is not None or hass.states.get(target) is not None:
            continue

        _LOGGER.info("Renaming %s to %s, the English entity ID", item.entity_id, target)
        registry.async_update_entity(item.entity_id, new_entity_id=target)
