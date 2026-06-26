from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.db import db, json_dumps, row_to_dict, rows_to_dicts, utc_now
from backend.services.cbdb import update_cbdb_people
from backend.services.normalization import compact_text, to_traditional

router = APIRouter()


class TermPayload(BaseModel):
    type: str = Field(min_length=1)
    text: str = Field(min_length=1)
    canonical_id: str | None = None
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportSummary(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


class CbdbUpdatePayload(BaseModel):
    names: list[str] = Field(default_factory=list)
    include_extracted: bool = False
    include_terms: bool = False


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


@router.post("/import")
async def import_terms(file: UploadFile = File(...), skip_duplicates: bool = True) -> dict[str, Any]:
    raw = await file.read()
    text = _decode_text(raw)
    name = (file.filename or "").lower()
    if name.endswith(".json") or text.lstrip().startswith(("[", "{")):
        records = _parse_json_terms(text)
    else:
        records = _parse_csv_terms(text)
    summary = _insert_imported_terms(records, skip_duplicates)
    return summary.model_dump()


@router.post("/cbdb/update")
def update_from_cbdb(payload: CbdbUpdatePayload) -> dict[str, Any]:
    return update_cbdb_people(
        names=payload.names,
        include_extracted=payload.include_extracted,
        include_terms=payload.include_terms,
    )


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


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "cp950"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_json_terms(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON import: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("items") or payload.get("terms") or [payload]
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="JSON import must be an object, list, or {items: [...]}.")
    return [_normalize_import_record(item) for item in payload if isinstance(item, dict)]


def _parse_csv_terms(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV import requires a header row.")
    return [_normalize_import_record(row) for row in reader]


def _normalize_import_record(record: dict[str, Any]) -> dict[str, Any]:
    metadata = _parse_jsonish(record.get("metadata") or record.get("metadata_json"), {})
    event_type = record.get("event_type")
    canonical = record.get("canonical")
    if event_type:
        metadata["event_type"] = str(event_type).strip()
    if canonical:
        metadata["canonical"] = str(canonical).strip()
    aliases = record.get("aliases") or record.get("aliases_json") or []
    return {
        "type": str(record.get("type") or record.get("term_type") or "").strip(),
        "text": str(record.get("text") or record.get("name") or "").strip(),
        "canonical_id": (str(record.get("canonical_id") or record.get("id") or "").strip() or None),
        "aliases": _parse_aliases(aliases),
        "metadata": metadata,
    }


def _parse_aliases(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    parsed = _parse_jsonish(value, None)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in str(value).replace(";", ",").split(",") if item.strip()]


def _parse_jsonish(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None or value == "":
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _insert_imported_terms(records: list[dict[str, Any]], skip_duplicates: bool) -> ImportSummary:
    imported = 0
    skipped = 0
    errors: list[str] = []
    with db() as conn:
        existing = {
            (row["type"], row["normalized_text"], row["canonical_id"])
            for row in conn.execute("SELECT type, normalized_text, canonical_id FROM knowledge_terms").fetchall()
        }
        now = utc_now()
        for index, record in enumerate(records, start=1):
            term_type = record["type"]
            text = record["text"]
            if not term_type or not text:
                errors.append(f"Row {index}: type and text are required.")
                skipped += 1
                continue
            normalized = to_traditional(compact_text(text))
            key = (term_type, normalized, record.get("canonical_id"))
            if skip_duplicates and key in existing:
                skipped += 1
                continue
            conn.execute(
                """
                INSERT INTO knowledge_terms
                (type, canonical_id, text, normalized_text, aliases_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    term_type,
                    record.get("canonical_id"),
                    text,
                    normalized,
                    json_dumps(record["aliases"]),
                    json_dumps(record["metadata"]),
                    now,
                ),
            )
            existing.add(key)
            imported += 1
    return ImportSummary(imported=imported, skipped=skipped, errors=errors)
