from __future__ import annotations

import re
from typing import Any

from backend.db import db, json_loads, utc_now
from backend.services.normalization import normalize_for_match

TERM_TYPE_TO_ENTITY = {
    "location": "LOC",
    "office": "OFF",
    "target_entity": "TARGET",
}
PERSON_TITLES = ("王", "侯", "公", "伯", "使", "將軍", "将军", "尚書", "侍郎", "都督", "指揮使")


def run_ner() -> dict[str, Any]:
    with db() as conn:
        documents = conn.execute("SELECT id, raw_text FROM documents").fetchall()
        terms = conn.execute("SELECT * FROM knowledge_terms").fetchall()
        conn.execute("DELETE FROM entities")
        now = utc_now()
        count = 0
        for doc in documents:
            entities = extract_entities(doc["raw_text"], [dict(term) for term in terms])
            for entity in entities:
                conn.execute(
                    """
                    INSERT INTO entities
                    (document_id, start, end, text, entity_type, method, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc["id"],
                        entity["start"],
                        entity["end"],
                        entity["text"],
                        entity["entity_type"],
                        entity["method"],
                        entity["confidence"],
                        now,
                    ),
                )
                count += 1
        return {"documents": len(documents), "entities": count}


def extract_entities(text: str, terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variant_terms = [term for term in terms if term["type"] == "variant"]
    candidates: list[dict[str, Any]] = []
    for term in terms:
        entity_type = TERM_TYPE_TO_ENTITY.get(term["type"])
        if not entity_type:
            continue
        forms = [term["text"], *json_loads(term.get("aliases_json"), [])]
        for form in sorted({item for item in forms if item}, key=len, reverse=True):
            candidates.extend(_find_term_matches(text, form, entity_type, "dictionary", 0.96, variant_terms))
    candidates.extend(_extract_office_patterns(text))
    candidates.extend(_extract_person_candidates(text, terms))
    return _resolve_overlaps(candidates)


def _find_term_matches(
    text: str,
    form: str,
    entity_type: str,
    method: str,
    confidence: float,
    variant_terms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    start = 0
    while True:
        index = text.find(form, start)
        if index == -1:
            break
        matches.append(_entity(index, index + len(form), text[index : index + len(form)], entity_type, method, confidence))
        start = index + 1
    normalized_form = normalize_for_match(form, variant_terms)
    if normalized_form != form:
        start = 0
        while True:
            index = text.find(normalized_form, start)
            if index == -1:
                break
            matches.append(
                _entity(index, index + len(normalized_form), text[index : index + len(normalized_form)], entity_type, "variant_dictionary", confidence - 0.08)
            )
            start = index + 1
    return matches


def _extract_office_patterns(text: str) -> list[dict[str, Any]]:
    patterns = [
        r"[\u4e00-\u9fff]{1,8}(?:都督|指揮使|指挥使|知府|尚書|尚书|侍郎|御史|丞相)",
        r"(?:中書省|中书省|戶部|户部|兵部|吏部|禮部|礼部|刑部|工部)[\u4e00-\u9fff]{0,4}",
    ]
    matches: list[dict[str, Any]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            span_text = match.group(0)
            if 2 <= len(span_text) <= 14:
                matches.append(_entity(match.start(), match.end(), span_text, "OFF", "pattern", 0.72))
    return matches


def _extract_person_candidates(text: str, terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    surnames = {term["text"] for term in terms if term["type"] == "surname"}
    for term in terms:
        if term["type"] == "surname":
            surnames.update(json_loads(term.get("aliases_json"), []))
    matches: list[dict[str, Any]] = []
    if not surnames:
        return matches
    surname_class = "".join(re.escape(surname) for surname in surnames if len(surname) == 1)
    if not surname_class:
        return matches
    pattern = re.compile(rf"(?<![\u4e00-\u9fff])([{surname_class}][\u4e00-\u9fff]{{1,2}})(?=[\u4e00-\u9fff]{{0,3}}(?:{'|'.join(PERSON_TITLES)}))?")
    for match in pattern.finditer(text):
        name = match.group(1)
        if len(name) in (2, 3):
            matches.append(_entity(match.start(1), match.end(1), name, "PER", "surname_feature", 0.58))
    return matches


def _entity(start: int, end: int, text: str, entity_type: str, method: str, confidence: float) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "text": text,
        "entity_type": entity_type,
        "method": method,
        "confidence": round(confidence, 4),
    }


def _resolve_overlaps(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda item: (item["start"], -(item["end"] - item["start"]), -item["confidence"]))
    accepted: list[dict[str, Any]] = []
    for candidate in ordered:
        if any(not (candidate["end"] <= item["start"] or candidate["start"] >= item["end"]) for item in accepted):
            continue
        accepted.append(candidate)
    return sorted(accepted, key=lambda item: (item["start"], item["end"]))
