from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter

from backend.db import db, rows_to_dicts
from backend.services.citations import format_citation
from backend.services.entity_display import entity_display_text
from backend.services.taxonomy import (
    display_settings_from_conn,
    entity_color,
    entity_label,
    event_label,
    matching_entity_types,
    matching_event_codes,
)

router = APIRouter()


@router.get("/timeline")
def timeline(
    q: str | None = None,
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
    with db() as conn:
        settings = display_settings_from_conn(conn)
        if q:
            q_like = f"%{q}%"
            matching_events = matching_event_codes(q, settings)
            matching_entity_labels = matching_entity_types(q, settings)
            search_parts = [
                "d.raw_text LIKE ?",
                "d.volume LIKE ?",
                "tm.text LIKE ?",
                "ep.event_type LIKE ?",
                "EXISTS (SELECT 1 FROM entities sqe WHERE sqe.document_id=d.id AND (sqe.text LIKE ? OR sqe.entity_type LIKE ?))",
            ]
            params.extend([q_like, q_like, q_like, q_like, q_like, q_like])
            if matching_events:
                search_parts.append(f"ep.event_type IN ({','.join('?' for _ in matching_events)})")
                params.extend(matching_events)
            if matching_entity_labels:
                search_parts.append(
                    f"EXISTS (SELECT 1 FROM entities lqe WHERE lqe.document_id=d.id AND lqe.entity_type IN ({','.join('?' for _ in matching_entity_labels)}))"
                )
                params.extend(matching_entity_labels)
            conditions.append(f"({' OR '.join(search_parts)})")
        if event_type:
            matching_events = matching_event_codes(event_type, settings)
            if matching_events:
                conditions.append(f"ep.event_type IN ({','.join('?' for _ in matching_events)})")
                params.extend(matching_events)
            else:
                conditions.append("ep.event_type LIKE ?")
                params.append(f"%{event_type}%")
        if entity:
            matching_types = matching_entity_types(entity, settings)
            parts = ["e.text LIKE ?", "e.entity_type LIKE ?"]
            entity_params: list[Any] = [f"%{entity}%", f"%{entity}%"]
            if matching_types:
                parts.append(f"e.entity_type IN ({','.join('?' for _ in matching_types)})")
                entity_params.extend(matching_types)
            conditions.append(f"EXISTS (SELECT 1 FROM entities e WHERE e.document_id=d.id AND ({' OR '.join(parts)}))")
            params.extend(entity_params)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"""
            SELECT printf('T%04d', ep.id) AS timeline_id,
                   ep.id AS event_id,
                   d.id AS document_id, d.source_name, d.volume, d.seq, d.raw_text,
                   ep.event_type, ep.probability,
                   MIN(tm.ce_year) AS ce_year,
                   GROUP_CONCAT(DISTINCT tm.text) AS historical_dates,
                   GROUP_CONCAT(DISTINCT tm.calendar_date) AS calendar_dates,
                   GROUP_CONCAT(DISTINCT tm.date_precision) AS date_precisions,
                   GROUP_CONCAT(DISTINCT e.id || ':' || e.start || ':' || e.end || ':' || e.text || ':' || e.entity_type) AS entity_refs
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
        items = rows_to_dicts(rows)
        _enrich_timeline_items(conn, items, settings)
        facets = _timeline_facets(conn, settings)
    return {"items": items, "facets": facets, "display": settings}


def _enrich_timeline_items(conn: Any, items: list[dict[str, Any]], settings: dict[str, Any]) -> None:
    for item in items:
        item["event_type_label"] = event_label(item.get("event_type"), settings)
        item["citation"] = format_citation(item, item.get("ce_year"))
        annotations = conn.execute(
            """
            SELECT id, annotation_type, action, text, entity_type, event_type, note
            FROM user_annotations
            WHERE document_id = ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (item["document_id"],),
        ).fetchall()
        ai_rows = conn.execute(
            """
            SELECT id, target_kind, target_value, model, summary, updated_at
            FROM ai_analysis_results
            WHERE timeline_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 5
            """,
            (item["timeline_id"],),
        ).fetchall()
        chat_rows = conn.execute(
            """
            SELECT id, role, content, model, usage_json, created_at
            FROM ai_chat_messages
            WHERE timeline_id = ?
            ORDER BY id
            """,
            (item["timeline_id"],),
        ).fetchall()
        item["annotations"] = rows_to_dicts(annotations)
        item["annotation_count"] = len(item["annotations"])
        item["ai_analysis_results"] = rows_to_dicts(ai_rows)
        item["ai_chat_messages"] = rows_to_dicts(chat_rows)
        item["entities"] = _parse_entity_refs(item.get("entity_refs"), settings)


def _parse_entity_refs(refs: str | None, settings: dict[str, Any]) -> list[dict[str, Any]]:
    entities = []
    for ref in (refs or "").split(","):
        if not ref:
            continue
        parts = ref.split(":")
        if len(parts) < 3:
            continue
        entity_id = parts[0]
        start = None
        end = None
        if len(parts) >= 5 and parts[1].isdigit() and parts[2].isdigit():
            start = int(parts[1])
            end = int(parts[2])
            text = ":".join(parts[3:-1])
        else:
            text = ":".join(parts[1:-1])
        entity_type = parts[-1]
        entities.append(
            {
                "id": entity_id,
                "start": start,
                "end": end,
                "text": text,
                "entity_type": entity_type,
                "entity_type_label": entity_label(entity_type, settings),
                "display_text": entity_display_text(text, entity_type),
                "color": entity_color(entity_type, settings),
            }
        )
    return entities


def _timeline_facets(conn: Any, settings: dict[str, Any]) -> dict[str, Any]:
    events = conn.execute(
        """
        SELECT event_type, COUNT(*) AS count
        FROM event_predictions
        GROUP BY event_type
        ORDER BY count DESC, event_type
        """
    ).fetchall()
    entities = conn.execute(
        """
        SELECT entity_type, text, COUNT(*) AS count
        FROM entities
        GROUP BY entity_type, text
        ORDER BY count DESC, text
        LIMIT 200
        """
    ).fetchall()
    return {
        "events": [
            {
                **dict(row),
                "event_type_label": event_label(row["event_type"], settings),
            }
            for row in events
        ],
        "entities": [
            {
                **dict(row),
                "entity_type_label": entity_label(row["entity_type"], settings),
                "display_text": entity_display_text(row["text"], row["entity_type"]),
                "color": entity_color(row["entity_type"], settings),
            }
            for row in entities
        ],
    }


def _timeline_id_to_event_id(timeline_id: str) -> int:
    match = re.match(r"^T?0*(\d+)$", timeline_id.strip(), flags=re.IGNORECASE)
    if not match:
        return -1
    return int(match.group(1))


@router.get("/charts")
def charts() -> dict[str, Any]:
    with db() as conn:
        settings = display_settings_from_conn(conn)
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
    by_event_items = _chart_items(rows_to_dicts(by_event), "event_type", settings)
    by_entity_items = _chart_items(rows_to_dicts(by_entity_type), "entity_type", settings)
    by_year_items = _chart_items(rows_to_dicts(by_year), "ce_year", settings)
    by_volume_items = _chart_items(rows_to_dicts(by_volume), "volume", settings)
    return {
        "by_event": by_event_items,
        "by_volume": by_volume_items,
        "by_year": by_year_items,
        "by_entity_type": by_entity_items,
        "display": settings,
    }


def _chart_items(rows: list[dict[str, Any]], key: str, settings: dict[str, Any]) -> list[dict[str, Any]]:
    for row in rows:
        ids = [item for item in str(row.get("timeline_ids") or "").split(",") if item]
        row["timeline_id_count"] = len(ids)
        row["timeline_id_preview"] = ids[:8]
        row["timeline_id_has_more"] = len(ids) > 8
        if key == "event_type":
            row["label"] = event_label(row.get("event_type"), settings)
        elif key == "entity_type":
            row["label"] = entity_label(row.get("entity_type"), settings)
            row["color"] = entity_color(row.get("entity_type"), settings)
        else:
            row["label"] = str(row.get(key) or "未知")
    return rows
