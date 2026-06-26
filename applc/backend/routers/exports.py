from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.db import db, json_loads
from backend.services.citations import format_citation, timeline_id
from backend.services.entity_display import enrich_entity_display

router = APIRouter()


@router.get("/jsonl")
def export_jsonl() -> StreamingResponse:
    payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in _export_items()) + "\n"
    return StreamingResponse(
        iter([payload]),
        media_type="application/jsonl; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=mingshilu_events.jsonl"},
    )


@router.get("/csv")
def export_csv() -> StreamingResponse:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "document_id",
            "timeline_ids",
            "citation",
            "source_name",
            "volume",
            "seq",
            "ce_year",
            "calendar_dates",
            "date_precision",
            "events",
            "entities",
            "annotations",
            "ai_analysis",
            "text",
        ],
    )
    writer.writeheader()
    for item in _export_items():
        writer.writerow(
            {
                "document_id": item["document_id"],
                "timeline_ids": ",".join(event["timeline_id"] for event in item["events"] if event.get("timeline_id")),
                "citation": item["citation"],
                "source_name": item["source_name"],
                "volume": item["volume"],
                "seq": item["seq"],
                "ce_year": ",".join(str(t["ce_year"]) for t in item["time_mentions"] if t.get("ce_year")),
                "calendar_dates": ",".join(t["calendar_date"] for t in item["time_mentions"] if t.get("calendar_date")),
                "date_precision": ",".join(sorted({t.get("date_precision") or "" for t in item["time_mentions"] if t.get("date_precision")})),
                "events": ",".join(event["event_type"] for event in item["events"]),
                "entities": ",".join(entity.get("display_text") or entity["text"] for entity in item["entities"]),
                "annotations": "; ".join(_summarize_annotation(annotation) for annotation in item["annotations"]),
                "ai_analysis": " | ".join(result["summary"] for result in item["ai_analysis_results"]),
                "text": item["text"],
            }
        )
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=mingshilu_events.csv"},
    )


def _export_items() -> list[dict[str, Any]]:
    with db() as conn:
        docs = conn.execute("SELECT * FROM documents ORDER BY id").fetchall()
        items = []
        for doc in docs:
            entities = conn.execute(
                """
                SELECT e.*, l.canonical_id, l.canonical_text, l.match_score
                FROM entities e
                LEFT JOIN entity_links l ON l.entity_id=e.id
                WHERE e.document_id=?
                ORDER BY e.start
                """,
                (doc["id"],),
            ).fetchall()
            times = conn.execute("SELECT * FROM time_mentions WHERE document_id=? ORDER BY start", (doc["id"],)).fetchall()
            events = conn.execute(
                "SELECT id, event_type, probability, source FROM event_predictions WHERE document_id=? ORDER BY probability DESC",
                (doc["id"],),
            ).fetchall()
            annotations = conn.execute(
                "SELECT * FROM user_annotations WHERE document_id=? ORDER BY id",
                (doc["id"],),
            ).fetchall()
            ai_results = conn.execute(
                """
                SELECT timeline_id, target_kind, target_value, model, summary, usage_json, created_at
                FROM ai_analysis_results
                WHERE document_id=?
                ORDER BY updated_at DESC, id DESC
                """,
                (doc["id"],),
            ).fetchall()
            ce_year = next((row["ce_year"] for row in times if row["ce_year"] is not None), None)
            doc_dict = dict(doc)
            items.append(
                {
                    "document_id": doc["id"],
                    "source_name": doc["source_name"],
                    "volume": doc["volume"],
                    "seq": doc["seq"],
                    "text": doc["raw_text"],
                    "citation": format_citation(doc_dict, ce_year),
                    "meta": json_loads(doc["meta_json"], {}),
                    "time_mentions": [dict(row) for row in times],
                    "entities": [enrich_entity_display(dict(row)) for row in entities],
                    "events": [{**dict(row), "timeline_id": timeline_id(row["id"])} for row in events],
                    "annotations": [dict(row) for row in annotations],
                    "ai_analysis_results": [dict(row) for row in ai_results],
                }
            )
    return items


def _summarize_annotation(annotation: dict[str, Any]) -> str:
    if annotation.get("annotation_type") == "entity":
        return f"{annotation.get('action')} entity {annotation.get('text')}:{annotation.get('entity_type')}"
    if annotation.get("annotation_type") == "event":
        return f"{annotation.get('action')} event {annotation.get('event_type')}"
    return f"{annotation.get('action')} {annotation.get('annotation_type')}"
