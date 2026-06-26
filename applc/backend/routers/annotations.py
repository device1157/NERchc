from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import db, json_dumps, row_to_dict, rows_to_dicts, utc_now
from backend.services.entity_display import normalize_entity_type

router = APIRouter()


class AnnotationPayload(BaseModel):
    document_id: int
    annotation_type: str = Field(pattern="^(entity|event|time|note)$")
    action: str = Field(default="add", pattern="^(add|delete|update|confirm)$")
    target_id: int | None = None
    start: int | None = None
    end: int | None = None
    text: str | None = None
    entity_type: str | None = None
    event_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


@router.get("")
def list_annotations(
    document_id: int | None = None,
    annotation_type: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if document_id is not None:
        conditions.append("document_id = ?")
        params.append(document_id)
    if annotation_type:
        conditions.append("annotation_type = ?")
        params.append(annotation_type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM user_annotations
            {where}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return {"items": rows_to_dicts(rows)}


@router.post("")
def create_annotation(payload: AnnotationPayload) -> dict[str, Any]:
    now = utc_now()
    entity_type = normalize_entity_type(payload.entity_type) if payload.annotation_type == "entity" else payload.entity_type
    with db() as conn:
        document = conn.execute("SELECT id FROM documents WHERE id = ?", (payload.document_id,)).fetchone()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")
        cursor = conn.execute(
            """
            INSERT INTO user_annotations
            (document_id, annotation_type, action, target_id, start, end, text,
             entity_type, event_type, payload_json, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.document_id,
                payload.annotation_type,
                payload.action,
                payload.target_id,
                payload.start,
                payload.end,
                payload.text,
                entity_type,
                payload.event_type,
                json_dumps(payload.payload),
                payload.note,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM user_annotations WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row) or {}


@router.delete("/{annotation_id}")
def delete_annotation(annotation_id: int) -> dict[str, int]:
    with db() as conn:
        cursor = conn.execute("DELETE FROM user_annotations WHERE id = ?", (annotation_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Annotation not found.")
    return {"deleted": annotation_id}
