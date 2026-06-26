from __future__ import annotations

import re
from typing import Any

from backend.db import db, json_loads, utc_now
from backend.services.entity_display import normalize_entity_type
from backend.services.normalization import normalize_for_match
from backend.services.ner_transformer import predict_transformer_entities

TERM_TYPE_TO_ENTITY = {
    "location": "LOC",
    "office": "OFF",
    "target_entity": "TARGET",
    "person_name": "PER",
}
PERSON_TITLES = ("王", "侯", "公", "伯", "使", "將軍", "将军", "尚書", "侍郎", "都督", "指揮使")
OFFICE_INSTITUTIONS = (
    "中書省",
    "中书省",
    "戶部",
    "户部",
    "兵部",
    "吏部",
    "禮部",
    "礼部",
    "刑部",
    "工部",
    "都察院",
    "翰林院",
    "通政司",
    "大理寺",
    "國子監",
    "国子监",
)
OFFICE_TITLES = (
    "都指揮使",
    "都指挥使",
    "指揮使",
    "指挥使",
    "布政使",
    "按察使",
    "參政",
    "参政",
    "尚書",
    "尚书",
    "侍郎",
    "郎中",
    "員外郎",
    "员外郎",
    "都督",
    "知府",
    "知縣",
    "知县",
    "御史",
    "丞相",
    "府尹",
)
OFFICE_PREFIX_CHARS = "左右前後后副行署守兼攝摄同"
OFFICE_TRIM_CHARS = "命為为以授拜除陞升擢封遷迁調调改任召詔诏遣令其及與与、，。；;：:"


def run_ner() -> dict[str, Any]:
    with db() as conn:
        documents = conn.execute("SELECT id, raw_text FROM documents").fetchall()
        terms = conn.execute("SELECT * FROM knowledge_terms").fetchall()
        annotation_rows = conn.execute(
            "SELECT * FROM user_annotations WHERE annotation_type = 'entity' ORDER BY id"
        ).fetchall()
        annotations_by_doc: dict[int, list[dict[str, Any]]] = {}
        for row in annotation_rows:
            annotations_by_doc.setdefault(row["document_id"], []).append(dict(row))
        conn.execute("DELETE FROM entities")
        now = utc_now()
        count = 0
        for doc in documents:
            entities = extract_entities(doc["raw_text"], [dict(term) for term in terms])
            entities = apply_entity_annotations(
                doc["id"],
                entities,
                annotations_by_doc.get(doc["id"], []),
                doc["raw_text"],
            )
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
    candidates.extend(predict_transformer_entities(text))
    candidates = _trim_offices_around_people(candidates)
    return _resolve_overlaps(candidates)


def apply_entity_annotations(
    document_id: int,
    entities: list[dict[str, Any]],
    annotation_rows: list[dict[str, Any]] | None = None,
    document_text: str | None = None,
) -> list[dict[str, Any]]:
    if annotation_rows is None:
        with db() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM user_annotations
                WHERE document_id = ? AND annotation_type = 'entity'
                ORDER BY id
                """,
                (document_id,),
            ).fetchall()
        annotation_rows = [dict(row) for row in rows]
    result = list(entities)
    for item in annotation_rows:
        if item["action"] == "delete" and item["target_id"]:
            result = [entity for entity in result if entity.get("id") != item["target_id"]]
            continue
        if item["action"] == "delete" and item["text"]:
            result = [entity for entity in result if entity.get("text") != item["text"]]
            continue
        if item["action"] in {"add", "update", "confirm"} and item["text"] and item["entity_type"]:
            entity_type = normalize_entity_type(item["entity_type"]) or item["entity_type"]
            start = item["start"]
            end = item["end"]
            if document_text and (start is None or end is None or document_text[int(start) : int(end)] != item["text"]):
                inferred = document_text.find(item["text"])
                if inferred >= 0:
                    start = inferred
                    end = inferred + len(item["text"])
            if start is None or end is None:
                continue
            result.append(
                _entity(
                    int(start),
                    int(end),
                    item["text"],
                    entity_type,
                    f"user_{item['action']}",
                    1.0,
                )
            )
    return _resolve_overlaps(result)


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
    title_pattern = "|".join(re.escape(title) for title in sorted(OFFICE_TITLES, key=len, reverse=True))
    institution_pattern = "|".join(re.escape(item) for item in sorted(OFFICE_INSTITUTIONS, key=len, reverse=True))
    patterns = [
        rf"[\u4e00-\u9fff]{{0,8}}(?:{title_pattern})",
        rf"(?:{institution_pattern})[\u4e00-\u9fff]{{0,4}}(?:{title_pattern})?",
    ]
    matches: list[dict[str, Any]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            entity = _clean_office_entity(match.start(), match.group(0), "pattern", 0.72)
            if entity:
                matches.append(entity)
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
    title_pattern = "|".join(re.escape(title) for title in sorted((*OFFICE_TITLES, *PERSON_TITLES), key=len, reverse=True))
    office_terms = sorted(
        {
            term["text"]
            for term in terms
            if term["type"] == "office" and term.get("text")
        },
        key=len,
        reverse=True,
    )
    context_terms = "|".join(re.escape(term) for term in [*office_terms, *OFFICE_TITLES, *PERSON_TITLES])
    if context_terms:
        after_context = re.compile(rf"(?:{context_terms})([{surname_class}][\u4e00-\u9fff]{{1,2}})")
        for match in after_context.finditer(text):
            name = match.group(1)
            if len(name) in (2, 3):
                matches.append(_entity(match.start(1), match.end(1), name, "PER", "surname_after_title", 0.74))
    pattern = re.compile(rf"(?<![\u4e00-\u9fff])([{surname_class}][\u4e00-\u9fff]{{1,2}})(?=[\u4e00-\u9fff]{{0,3}}(?:{title_pattern}))")
    for match in pattern.finditer(text):
        name = match.group(1)
        if len(name) in (2, 3):
            matches.append(_entity(match.start(1), match.end(1), name, "PER", "surname_feature", 0.58))
    return matches


def _clean_office_entity(start: int, span_text: str, method: str, confidence: float) -> dict[str, Any] | None:
    cleaned = span_text.strip(OFFICE_TRIM_CHARS)
    start += len(span_text) - len(span_text.lstrip(OFFICE_TRIM_CHARS))
    if not cleaned:
        return None
    best_start: int | None = None
    for institution in OFFICE_INSTITUTIONS:
        index = cleaned.find(institution)
        if index >= 0 and (best_start is None or index < best_start):
            best_start = index
    for title in OFFICE_TITLES:
        index = cleaned.find(title)
        if index < 0:
            continue
        prefix_start = index
        while prefix_start > 0 and cleaned[prefix_start - 1] in OFFICE_PREFIX_CHARS:
            prefix_start -= 1
        if best_start is None or prefix_start < best_start:
            best_start = prefix_start
    if best_start is None:
        return None
    start += best_start
    cleaned = cleaned[best_start:].strip(OFFICE_TRIM_CHARS)
    if not _looks_like_office(cleaned):
        return None
    return _entity(start, start + len(cleaned), cleaned, "OFF", method, confidence)


def _looks_like_office(text: str) -> bool:
    if not (2 <= len(text) <= 14):
        return False
    return any(title in text for title in OFFICE_TITLES) or any(text.startswith(item) for item in OFFICE_INSTITUTIONS)


def _trim_offices_around_people(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    people = [candidate for candidate in candidates if candidate["entity_type"] == "PER"]
    if not people:
        return candidates
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate["entity_type"] != "OFF":
            result.append(candidate)
            continue
        segments = [(candidate["start"], candidate["end"], candidate["text"])]
        for person in people:
            next_segments: list[tuple[int, int, str]] = []
            for start, end, text in segments:
                overlap_start = max(start, person["start"])
                overlap_end = min(end, person["end"])
                if overlap_start >= overlap_end:
                    next_segments.append((start, end, text))
                    continue
                left_len = overlap_start - start
                right_offset = overlap_end - start
                if left_len > 0:
                    next_segments.append((start, overlap_start, text[:left_len]))
                if overlap_end < end:
                    next_segments.append((overlap_end, end, text[right_offset:]))
            segments = next_segments
        for start, _end, text in segments:
            cleaned = _clean_office_entity(start, text, candidate["method"], candidate["confidence"])
            if cleaned:
                result.append(cleaned)
    return result


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
    type_priority = {"PER": 4, "OFF": 3, "TARGET": 2, "LOC": 1}
    ordered = sorted(
        candidates,
        key=lambda item: (
            item["start"],
            -type_priority.get(item["entity_type"], 0),
            -item["confidence"],
            -(item["end"] - item["start"]),
        ),
    )
    accepted: list[dict[str, Any]] = []
    for candidate in ordered:
        if any(not (candidate["end"] <= item["start"] or candidate["start"] >= item["end"]) for item in accepted):
            continue
        accepted.append(candidate)
    return sorted(accepted, key=lambda item: (item["start"], item["end"]))
