from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.db import db, json_dumps, utc_now
from backend.services.taxonomy import SETTING_KEYS, display_settings_from_conn

router = APIRouter()


class DisplaySettingsUpdate(BaseModel):
    event_labels: dict[str, str] = Field(default_factory=dict)
    entity_labels: dict[str, str] = Field(default_factory=dict)
    entity_colors: dict[str, str] = Field(default_factory=dict)


@router.get("/settings")
def get_display_settings() -> dict[str, Any]:
    with db() as conn:
        return display_settings_from_conn(conn)


@router.put("/settings")
def save_display_settings(payload: DisplaySettingsUpdate) -> dict[str, Any]:
    now = utc_now()
    rows = [
        (SETTING_KEYS["event_labels"], json_dumps(payload.event_labels), now),
        (SETTING_KEYS["entity_labels"], json_dumps(payload.entity_labels), now),
        (SETTING_KEYS["entity_colors"], json_dumps(payload.entity_colors), now),
    ]
    with db() as conn:
        conn.executemany(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            rows,
        )
        return display_settings_from_conn(conn)
