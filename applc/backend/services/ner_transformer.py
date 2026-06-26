from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.services.artifacts import artifact_path

_PIPELINE: Any | None = None
_PIPELINE_PATH: Path | None = None

LABEL_MAP = {
    "PER": "PER",
    "PERSON": "PER",
    "LOC": "LOC",
    "GPE": "LOC",
    "ORG": "TARGET",
    "OFF": "OFF",
    "TITLE": "OFF",
}


def predict_transformer_entities(text: str) -> list[dict[str, Any]]:
    pipe = _load_pipeline()
    if pipe is None:
        return []
    try:
        raw_items = pipe(text)
    except Exception:
        return []
    return [_convert_item(text, item) for item in raw_items if _convert_item(text, item) is not None]


def _load_pipeline() -> Any | None:
    global _PIPELINE, _PIPELINE_PATH
    path = artifact_path("ckip-bert-base-chinese-ner")
    if not path.exists() or not any(path.iterdir()):
        return None
    if _PIPELINE is not None and _PIPELINE_PATH == path:
        return _PIPELINE
    try:
        from transformers import pipeline  # type: ignore
    except Exception:
        return None
    try:
        _PIPELINE = pipeline("ner", model=str(path), tokenizer=str(path), aggregation_strategy="simple")
        _PIPELINE_PATH = path
    except Exception:
        _PIPELINE = None
    return _PIPELINE


def _convert_item(text: str, item: dict[str, Any]) -> dict[str, Any] | None:
    label = str(item.get("entity_group") or item.get("entity") or "").replace("B-", "").replace("I-", "")
    entity_type = LABEL_MAP.get(label.upper())
    if entity_type is None:
        return None
    start = item.get("start")
    end = item.get("end")
    word = str(item.get("word") or item.get("text") or "").replace(" ", "")
    if not isinstance(start, int) or not isinstance(end, int):
        if not word:
            return None
        start = text.find(word)
        if start < 0:
            return None
        end = start + len(word)
    if start < 0 or end <= start:
        return None
    mention = text[start:end]
    return {
        "start": start,
        "end": end,
        "text": mention,
        "entity_type": entity_type,
        "method": "transformer_bert",
        "confidence": round(float(item.get("score") or 0.78), 4),
    }
