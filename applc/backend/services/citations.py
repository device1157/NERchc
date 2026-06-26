from __future__ import annotations

from typing import Any


def format_citation(doc: dict[str, Any], ce_year: int | None = None) -> str:
    source = doc.get("source_name") or "Ming Shilu"
    volume = doc.get("volume") or "unknown volume"
    seq = doc.get("seq") or doc.get("document_id") or doc.get("id") or "unknown entry"
    year = f", CE {ce_year}" if ce_year else ""
    return f"{source}, Vol. {volume}, Entry {seq}{year}"


def timeline_id(event_id: int | None) -> str | None:
    if event_id is None:
        return None
    return f"T{event_id:04d}"
