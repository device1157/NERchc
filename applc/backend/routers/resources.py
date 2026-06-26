from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import db, json_dumps, row_to_dict, rows_to_dicts, utc_now
from backend.services.normalization import compact_text, to_traditional

router = APIRouter()


class TermPayload(BaseModel):
    type: str = Field(min_length=1)
    text: str = Field(min_length=1)
    canonical_id: str | None = None
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/terms")
def list_terms(type: str | None = None, q: str | None = None, limit: int = 500) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if type:
        conditions.append("type = ?")
        params.append(type)
    if q:
        conditions.append("(text LIKE ? OR canonical_id LIKE ? OR aliases_json LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, type, canonical_id, text, normalized_text, aliases_json, metadata_json, created_at
            FROM knowledge_terms
            {where}
            ORDER BY type, text
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return {"items": rows_to_dicts(rows)}


@router.get("/types")
def list_types() -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT type, COUNT(*) AS count FROM knowledge_terms GROUP BY type ORDER BY type").fetchall()
    return {"items": rows_to_dicts(rows)}


@router.post("/terms")
def create_term(payload: TermPayload) -> dict[str, Any]:
    normalized = to_traditional(compact_text(payload.text))
    with db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO knowledge_terms
            (type, canonical_id, text, normalized_text, aliases_json, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.type,
                payload.canonical_id,
                payload.text,
                normalized,
                json_dumps(payload.aliases),
                json_dumps(payload.metadata),
                utc_now(),
            ),
        )
        row = conn.execute("SELECT * FROM knowledge_terms WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row) or {}


@router.put("/terms/{term_id}")
def update_term(term_id: int, payload: TermPayload) -> dict[str, Any]:
    normalized = to_traditional(compact_text(payload.text))
    with db() as conn:
        conn.execute(
            """
            UPDATE knowledge_terms
            SET type=?, canonical_id=?, text=?, normalized_text=?, aliases_json=?, metadata_json=?
            WHERE id=?
            """,
            (
                payload.type,
                payload.canonical_id,
                payload.text,
                normalized,
                json_dumps(payload.aliases),
                json_dumps(payload.metadata),
                term_id,
            ),
        )
        row = conn.execute("SELECT * FROM knowledge_terms WHERE id = ?", (term_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Term not found.")
    return row_to_dict(row) or {}


@router.delete("/terms/{term_id}")
def delete_term(term_id: int) -> dict[str, int]:
    with db() as conn:
        cursor = conn.execute("DELETE FROM knowledge_terms WHERE id = ?", (term_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Term not found.")
    return {"deleted": term_id}
