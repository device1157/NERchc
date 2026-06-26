from __future__ import annotations

from typing import Any


ENTITY_TYPE_ALIASES = {
    "人名": "PER",
    "人物": "PER",
    "PER": "PER",
    "地點": "LOC",
    "地点": "LOC",
    "LOC": "LOC",
    "官位": "OFF",
    "官職": "OFF",
    "职官": "OFF",
    "職官": "OFF",
    "OFF": "OFF",
    "研究對象": "TARGET",
    "研究对象": "TARGET",
    "TARGET": "TARGET",
}


def normalize_entity_type(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return ENTITY_TYPE_ALIASES.get(text, ENTITY_TYPE_ALIASES.get(text.upper(), text.upper() if text.isascii() else text))


def entity_display_text(text: str | None, entity_type: str | None) -> str:
    value = text or ""
    if normalize_entity_type(entity_type) == "PER":
        return f'人名|"{value}"'
    return value


def enrich_entity_display(entity: dict[str, Any]) -> dict[str, Any]:
    entity_type = normalize_entity_type(entity.get("entity_type"))
    return {
        **entity,
        "entity_type": entity_type or entity.get("entity_type"),
        "display_text": entity_display_text(entity.get("text"), entity_type),
    }
