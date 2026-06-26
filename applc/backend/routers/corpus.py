from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.db import DATA_DIR, db, json_dumps, rows_to_dicts, utc_now
from backend.services.preprocess import ParsedDocument, preprocess_text

router = APIRouter()


class ImportTextRequest(BaseModel):
    source_name: str = Field(default="manual.txt")
    text: str
    clear_existing: bool = False
    convert_traditional: bool = True


@router.post("/import-text")
def import_text(payload: ImportTextRequest) -> dict[str, Any]:
    docs = preprocess_text(payload.source_name, payload.text, payload.convert_traditional)
    inserted = _insert_documents(docs, payload.clear_existing)
    return {"source_name": payload.source_name, "documents": inserted}


@router.post("/upload")
async def upload_corpus(
    file: UploadFile = File(...),
    clear_existing: bool = False,
    convert_traditional: bool = True,
) -> dict[str, Any]:
    raw = await file.read()
    text, encoding = _decode_uploaded_text(raw)
    source_name = Path(file.filename or "upload.txt").name
    raw_path = DATA_DIR / "corpus" / "raw" / source_name
    raw_path.write_text(text, encoding="utf-8")
    docs = preprocess_text(source_name, text, convert_traditional)
    inserted = _insert_documents(docs, clear_existing)
    return {"source_name": source_name, "encoding": encoding, "raw_path": str(raw_path), "documents": inserted}


@router.get("/documents")
def list_documents(limit: int = 50, offset: int = 0, q: str | None = None) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if q:
        conditions.append("raw_text LIKE ?")
        params.append(f"%{q}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM documents {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, source_name, volume, seq, raw_text, meta_json, created_at
            FROM documents
            {where}
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return {"total": total, "items": rows_to_dicts(rows)}


@router.get("/stats")
def corpus_stats() -> dict[str, Any]:
    with db() as conn:
        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        volumes = conn.execute("SELECT COUNT(DISTINCT volume) FROM documents").fetchone()[0]
        chars = conn.execute("SELECT COALESCE(SUM(LENGTH(raw_text)), 0) FROM documents").fetchone()[0]
        by_volume = conn.execute(
            "SELECT volume, COUNT(*) AS count FROM documents GROUP BY volume ORDER BY volume LIMIT 50"
        ).fetchall()
    return {
        "documents": docs,
        "volumes": volumes,
        "characters": chars,
        "by_volume": rows_to_dicts(by_volume),
    }


@router.delete("/documents")
def clear_corpus() -> dict[str, int]:
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        conn.execute("DELETE FROM documents")
    return {"deleted": count}


def _insert_documents(docs: list[ParsedDocument], clear_existing: bool) -> int:
    if not docs:
        raise HTTPException(status_code=400, detail="No corpus documents were parsed from the input.")
    with db() as conn:
        if clear_existing:
            conn.execute("DELETE FROM documents")
        now = utc_now()
        conn.executemany(
            """
            INSERT INTO documents (source_name, volume, seq, raw_text, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(doc.source_name, doc.volume, doc.seq, doc.raw_text, json_dumps(doc.meta), now) for doc in docs],
        )
    return len(docs)


def _decode_uploaded_text(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "cp950"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"
