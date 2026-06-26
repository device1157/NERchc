from __future__ import annotations

import re
from typing import Any

from backend.db import json_loads


EVENT_LABELS = {
    "military": "軍事",
    "appointment": "任官任命",
    "tribute": "朝貢外交",
    "punishment": "刑罰司法",
    "disaster": "災異",
    "finance": "財政賦役",
    "uncategorized": "未分類",
}

ENTITY_LABELS = {
    "PER": "人物",
    "LOC": "地點",
    "OFF": "官位職官",
    "TARGET": "研究對象",
}

ENTITY_COLORS = {
    "PER": "#ad3f28",
    "LOC": "#2f7d55",
    "OFF": "#246b9f",
    "TARGET": "#bc8b38",
}

EVENT_LABELS.update(
    {
        "military": "軍事",
        "appointment": "任官任命",
        "tribute": "朝貢外交",
        "punishment": "刑罰司法",
        "disaster": "災異",
        "finance": "財政賦役",
        "uncategorized": "未分類",
    }
)
ENTITY_LABELS.update({"PER": "人名", "person_name": "人名"})

SETTING_KEYS = {
    "event_labels": "display.event_labels",
    "entity_labels": "display.entity_labels",
    "entity_colors": "display.entity_colors",
}


def display_settings_from_conn(conn: Any) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT key, value FROM app_settings WHERE key IN (?, ?, ?)",
        tuple(SETTING_KEYS.values()),
    ).fetchall()
    stored = {row["key"]: row["value"] for row in rows}
    return {
        "event_labels": {**EVENT_LABELS, **_json_dict(stored.get(SETTING_KEYS["event_labels"]))},
        "entity_labels": {**ENTITY_LABELS, **_json_dict(stored.get(SETTING_KEYS["entity_labels"]))},
        "entity_colors": {
            **ENTITY_COLORS,
            **_sanitize_colors(_json_dict(stored.get(SETTING_KEYS["entity_colors"]))),
        },
    }


def event_label(event_type: str | None, settings: dict[str, Any] | None = None) -> str:
    if not event_type:
        return "未分類"
    labels = (settings or {}).get("event_labels") or EVENT_LABELS
    return labels.get(event_type, event_type)


def entity_label(entity_type: str | None, settings: dict[str, Any] | None = None) -> str:
    if not entity_type:
        return "未知類別"
    labels = (settings or {}).get("entity_labels") or ENTITY_LABELS
    return labels.get(entity_type, entity_type)


def entity_color(entity_type: str | None, settings: dict[str, Any] | None = None) -> str:
    colors = (settings or {}).get("entity_colors") or ENTITY_COLORS
    return colors.get(entity_type or "", "#756653")


def matching_event_codes(query: str | None, settings: dict[str, Any]) -> list[str]:
    if not query:
        return []
    value = query.strip().lower()
    labels = settings.get("event_labels") or EVENT_LABELS
    return [
        code
        for code, label in labels.items()
        if value in code.lower() or value in str(label).lower()
    ]


def matching_entity_types(query: str | None, settings: dict[str, Any]) -> list[str]:
    if not query:
        return []
    value = query.strip().lower()
    labels = settings.get("entity_labels") or ENTITY_LABELS
    return [
        code
        for code, label in labels.items()
        if value in code.lower() or value in str(label).lower()
    ]


def _json_dict(value: str | None) -> dict[str, str]:
    data = json_loads(value, {})
    if not isinstance(data, dict):
        return {}
    return {str(key): str(item) for key, item in data.items() if str(key)}


def _sanitize_colors(colors: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in colors.items()
        if re.match(r"^#[0-9a-fA-F]{6}$", value)
    }
