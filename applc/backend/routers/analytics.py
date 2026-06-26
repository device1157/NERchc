from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter

from backend.db import db, rows_to_dicts

router = APIRouter()


@router.get("/timeline")
def timeline(
    event_type: str | None = None,
    entity: str | None = None,
    timeline_id: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if timeline_id:
        event_id = _timeline_id_to_event_id(timeline_id)
        conditions.append("ep.id = ?")
        params.append(event_id)
    if event_type:
        conditions.append("ep.event_type = ?")
        params.append(event_type)
    if entity:
        conditions.append("EXISTS (SELECT 1 FROM entities e WHERE e.document_id=d.id AND e.text LIKE ?)")
        params.append(f"%{entity}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT printf('T%04d', ep.id) AS timeline_id,
                   ep.id AS event_id,
                   d.id AS document_id, d.volume, d.seq, d.raw_text,
                   ep.event_type, ep.probability,
                   MIN(tm.ce_year) AS ce_year,
                   GROUP_CONCAT(DISTINCT tm.text) AS historical_dates,
                   GROUP_CONCAT(DISTINCT e.id || ':' || e.text || ':' || e.entity_type) AS entity_refs
            FROM documents d
            JOIN event_predictions ep ON ep.document_id=d.id
            LEFT JOIN time_mentions tm ON tm.document_id=d.id
            LEFT JOIN entities e ON e.document_id=d.id
            {where}
            GROUP BY d.id, ep.id
            ORDER BY COALESCE(ce_year, 9999), d.id
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return {"items": rows_to_dicts(rows)}


def _timeline_id_to_event_id(timeline_id: str) -> int:
    match = re.match(r"^T?0*(\d+)$", timeline_id.strip(), flags=re.IGNORECASE)
    if not match:
        return -1
    return int(match.group(1))


@router.get("/charts")
def charts() -> dict[str, Any]:
    with db() as conn:
        by_event = conn.execute(
            """
            SELECT event_type,
                   COUNT(*) AS count,
                   GROUP_CONCAT(DISTINCT printf('T%04d', id)) AS timeline_ids,
                   GROUP_CONCAT(DISTINCT document_id) AS document_ids
            FROM event_predictions
            GROUP BY event_type
            ORDER BY count DESC
            """
        ).fetchall()
        by_volume = conn.execute(
            """
            SELECT d.volume,
                   COUNT(DISTINCT d.id) AS count,
                   GROUP_CONCAT(DISTINCT CASE WHEN ep.id IS NOT NULL THEN printf('T%04d', ep.id) END) AS timeline_ids,
                   GROUP_CONCAT(DISTINCT d.id) AS document_ids
            FROM documents d
            LEFT JOIN event_predictions ep ON ep.document_id=d.id
            GROUP BY d.volume
            ORDER BY d.volume
            LIMIT 80
            """
        ).fetchall()
        by_year = conn.execute(
            """
            SELECT tm.ce_year,
                   COUNT(DISTINCT tm.document_id) AS count,
                   GROUP_CONCAT(DISTINCT CASE WHEN ep.id IS NOT NULL THEN printf('T%04d', ep.id) END) AS timeline_ids,
                   GROUP_CONCAT(DISTINCT tm.document_id) AS document_ids
            FROM time_mentions tm
            LEFT JOIN event_predictions ep ON ep.document_id=tm.document_id
            WHERE tm.ce_year IS NOT NULL
            GROUP BY tm.ce_year
            ORDER BY ce_year
            """
        ).fetchall()
        by_entity_type = conn.execute(
            """
            SELECT e.entity_type,
                   COUNT(DISTINCT e.id) AS count,
                   GROUP_CONCAT(DISTINCT CASE WHEN ep.id IS NOT NULL THEN printf('T%04d', ep.id) END) AS timeline_ids,
                   GROUP_CONCAT(DISTINCT e.text) AS entity_names,
                   GROUP_CONCAT(DISTINCT e.document_id) AS document_ids
            FROM entities e
            LEFT JOIN event_predictions ep ON ep.document_id=e.document_id
            GROUP BY e.entity_type
            ORDER BY count DESC
            """
        ).fetchall()
    return {
        "by_event": rows_to_dicts(by_event),
        "by_volume": rows_to_dicts(by_volume),
        "by_year": rows_to_dicts(by_year),
        "by_entity_type": rows_to_dicts(by_entity_type),
    }
