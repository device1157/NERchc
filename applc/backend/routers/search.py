from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.db import db, rows_to_dicts

router = APIRouter()


@router.get("/entities")
def search_entities(q: str | None = None, type: str | None = None, limit: int = 100) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if q:
        conditions.append("(e.text LIKE ? OR l.canonical_text LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if type:
        conditions.append("e.entity_type = ?")
        params.append(type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT e.id, e.document_id, e.text, e.entity_type, e.start, e.end, e.method, e.confidence,
                   l.canonical_id, l.canonical_text, l.match_score,
                   d.volume, d.seq, d.raw_text
            FROM entities e
            JOIN documents d ON d.id = e.document_id
            LEFT JOIN entity_links l ON l.entity_id = e.id
            {where}
            ORDER BY e.id DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return {"items": rows_to_dicts(rows)}


@router.get("/events")
def search_events(event_type: str | None = None, start_year: int | None = None, end_year: int | None = None, limit: int = 100) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if event_type:
        conditions.append("ep.event_type = ?")
        params.append(event_type)
    if start_year is not None:
        conditions.append("(tm.ce_year IS NULL OR tm.ce_year >= ?)")
        params.append(start_year)
    if end_year is not None:
        conditions.append("(tm.ce_year IS NULL OR tm.ce_year <= ?)")
        params.append(end_year)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT ep.id, ep.document_id, ep.event_type, ep.probability, ep.source,
                   d.volume, d.seq, d.raw_text,
                   MIN(tm.ce_year) AS ce_year
            FROM event_predictions ep
            JOIN documents d ON d.id = ep.document_id
            LEFT JOIN time_mentions tm ON tm.document_id = d.id
            {where}
            GROUP BY ep.id
            ORDER BY COALESCE(ce_year, 9999), ep.probability DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return {"items": rows_to_dicts(rows)}


@router.get("/paragraphs")
def search_paragraphs(
    q: str | None = None,
    entity: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if q:
        conditions.append("d.raw_text LIKE ?")
        params.append(f"%{q}%")
    if entity:
        conditions.append("EXISTS (SELECT 1 FROM entities e WHERE e.document_id=d.id AND e.text LIKE ?)")
        params.append(f"%{entity}%")
    if event_type:
        conditions.append("EXISTS (SELECT 1 FROM event_predictions ep WHERE ep.document_id=d.id AND ep.event_type=?)")
        params.append(event_type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT d.id, d.source_name, d.volume, d.seq, d.raw_text,
                   GROUP_CONCAT(DISTINCT ep.event_type) AS event_types,
                   GROUP_CONCAT(DISTINCT e.text) AS entities,
                   MIN(tm.ce_year) AS ce_year
            FROM documents d
            LEFT JOIN event_predictions ep ON ep.document_id=d.id
            LEFT JOIN entities e ON e.document_id=d.id
            LEFT JOIN time_mentions tm ON tm.document_id=d.id
            {where}
            GROUP BY d.id
            ORDER BY d.id
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return {"items": rows_to_dicts(rows)}
