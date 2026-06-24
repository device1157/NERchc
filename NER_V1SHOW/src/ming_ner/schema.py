"""Shared data structures for the Ming Shilu NER pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Document:
    """A cleaned text document with source metadata."""

    doc_id: str
    title: str
    source_path: str
    text: str


@dataclass
class Entity:
    """A single extracted entity span over the concatenated export text."""

    start: int
    end: int
    type: str
    text: str
    score: float
    source: str
    method: str
    doc_id: str | None = None
    linked: dict[str, Any] | None = None
    status: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "start": self.start,
            "end": self.end,
            "type": self.type,
            "text": self.text,
            "score": round(float(self.score), 4),
            "source": self.source,
            "method": self.method,
            "linked": self.linked,
        }
        if self.doc_id:
            data["doc_id"] = self.doc_id
        if self.status:
            data["status"] = self.status
        if self.meta:
            data["meta"] = self.meta
        return data
