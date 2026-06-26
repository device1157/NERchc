from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.db import db, json_loads

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
    writer = csv.DictWriter(output, fieldnames=["document_id", "volume", "seq", "ce_year", "events", "entities", "text"])
    writer.writeheader()
    for item in _export_items():
        writer.writerow(
            {
                "document_id": item["document_id"],
                "volume": item["volume"],
                "seq": item["seq"],
                "ce_year": ",".join(str(t["ce_year"]) for t in item["time_mentions"] if t.get("ce_year")),
                "events": ",".join(event["event_type"] for event in item["events"]),
                "entities": ",".join(entity["text"] for entity in item["entities"]),
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
                "SELECT event_type, probability, source FROM event_predictions WHERE document_id=? ORDER BY probability DESC",
                (doc["id"],),
            ).fetchall()
            items.append(
                {
                    "document_id": doc["id"],
                    "source_name": doc["source_name"],
                    "volume": doc["volume"],
                    "seq": doc["seq"],
                    "text": doc["raw_text"],
                    "meta": json_loads(doc["meta_json"], {}),
                    "time_mentions": [dict(row) for row in times],
                    "entities": [dict(row) for row in entities],
                    "events": [dict(row) for row in events],
                }
            )
    return items
