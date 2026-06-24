from __future__ import annotations

import json
import re
from typing import Any


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def parse_llm_entities(response_text: str, sentence: str, entity_type_tag: str) -> list[dict[str, Any]]:
    payload = strip_code_fence(response_text)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", payload)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []

    entities = []
    for item in data:
        if isinstance(item, str):
            text = item.strip()
            score = None
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("entity") or "").strip()
            score = item.get("score")
        else:
            continue
        if not text:
            continue
        for start in find_all_occurrences(sentence, text):
            entities.append(
                {
                    "start": start,
                    "end": start + len(text),
                    "text": text,
                    "type": entity_type_tag,
                    "score": _safe_float(score),
                }
            )
    return resolve_overlaps(deduplicate_entities(entities))


def find_all_occurrences(sentence: str, text: str) -> list[int]:
    starts = []
    pos = sentence.find(text)
    while pos >= 0:
        starts.append(pos)
        pos = sentence.find(text, pos + 1)
    return starts


def deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for entity in entities:
        key = (entity["start"], entity["end"], entity["type"])
        if key in seen:
            continue
        seen.add(key)
        result.append(entity)
    return result


def resolve_overlaps(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_entities = sorted(entities, key=lambda x: (x["start"], -(x["end"] - x["start"])))
    kept: list[dict[str, Any]] = []
    for entity in sorted_entities:
        overlaps = [old for old in kept if not (entity["end"] <= old["start"] or entity["start"] >= old["end"])]
        if not overlaps:
            kept.append(entity)
            continue
        longest = max(overlaps + [entity], key=lambda x: x["end"] - x["start"])
        if longest is entity:
            kept = [old for old in kept if old not in overlaps]
            kept.append(entity)
    return sorted(kept, key=lambda x: (x["start"], x["end"]))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

