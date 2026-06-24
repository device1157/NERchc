"""Annotation JSONL validation and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ENTITY_TYPES = ("PER", "LOC", "OFF")
DEFAULT_SETTINGS = {
    "weak_threshold": 0.8,
    "target_f1": 0.8,
    "entity_types": list(ENTITY_TYPES),
    "min_reviewed_segments": 300,
}


@dataclass(frozen=True)
class AnnotationValidationError(ValueError):
    message: str

    def __str__(self) -> str:
        return self.message


def validate_entities(text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    for entity in sorted(entities, key=lambda item: (int(item["start"]), int(item["end"]))):
        start = int(entity["start"])
        end = int(entity["end"])
        entity_type = str(entity["type"])
        if entity_type not in ENTITY_TYPES:
            raise AnnotationValidationError(f"Unsupported entity type: {entity_type}")
        if start < 0 or end <= start or end > len(text):
            raise AnnotationValidationError(f"Invalid span: [{start}, {end})")
        value = text[start:end]
        supplied = str(entity.get("text", value))
        if supplied != value:
            raise AnnotationValidationError(f"Span text mismatch: {supplied!r} != {value!r}")
        if any(start < kept_end and end > kept_start for kept_start, kept_end in spans):
            raise AnnotationValidationError(f"Overlapping span: [{start}, {end})")
        spans.append((start, end))
        cleaned.append(
            {
                "start": start,
                "end": end,
                "type": entity_type,
                "text": value,
                "status": str(entity.get("status") or "gold"),
            }
        )
    return cleaned


def validate_annotation(record: dict[str, Any]) -> dict[str, Any]:
    text = str(record.get("text", ""))
    if not text:
        raise AnnotationValidationError("Annotation text is required")
    entities = validate_entities(text, list(record.get("entities", [])))
    return {
        "id": str(record.get("id") or ""),
        "doc_id": str(record.get("doc_id") or ""),
        "file": str(record.get("file") or ""),
        "entry_start": int(record.get("entry_start") or 1),
        "entry_end": int(record.get("entry_end") or 1),
        "text": text,
        "entities": entities,
        "weak_threshold": float(record.get("weak_threshold") or DEFAULT_SETTINGS["weak_threshold"]),
    }


def annotation_id(file_name: str, entry_start: int, entry_end: int) -> str:
    stem = Path(file_name).stem
    return f"{stem}_{entry_start:06d}_{entry_end:06d}"


def append_annotation(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    validated = validate_annotation(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(validated, ensure_ascii=False) + "\n")
    return validated


def read_annotations(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(validate_annotation(json.loads(line)))
    return rows


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_settings(path: Path, settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
