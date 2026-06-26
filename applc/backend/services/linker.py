from __future__ import annotations

from typing import Any

from backend.db import db, json_loads, utc_now
from backend.services.normalization import normalize_for_match

ENTITY_TO_TERM_TYPES = {
    "LOC": {"location", "target_entity"},
    "OFF": {"office"},
    "TARGET": {"target_entity", "location"},
    "PER": {"target_entity", "person_name"},
}


def run_entity_linking() -> dict[str, Any]:
    with db() as conn:
        entities = conn.execute("SELECT * FROM entities").fetchall()
        terms = [dict(row) for row in conn.execute("SELECT * FROM knowledge_terms").fetchall()]
        variant_terms = [term for term in terms if term["type"] == "variant"]
        conn.execute("DELETE FROM entity_links")
        now = utc_now()
        count = 0
        for entity_row in entities:
            entity = dict(entity_row)
            link = link_entity(entity, terms, variant_terms)
            if not link:
                continue
            conn.execute(
                """
                INSERT INTO entity_links
                (entity_id, canonical_id, canonical_text, match_score, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entity["id"],
                    link.get("canonical_id"),
                    link["canonical_text"],
                    link["match_score"],
                    link["metadata_json"],
                    now,
                ),
            )
            count += 1
        return {"entities": len(entities), "links": count}


def link_entity(entity: dict[str, Any], terms: list[dict[str, Any]], variant_terms: list[dict[str, Any]]) -> dict[str, Any] | None:
    allowed_types = ENTITY_TO_TERM_TYPES.get(entity["entity_type"], set())
    if not allowed_types:
        return None
    source = normalize_for_match(entity["text"], variant_terms)
    best: dict[str, Any] | None = None
    for term in terms:
        if term["type"] not in allowed_types:
            continue
        forms = [term["text"], *json_loads(term.get("aliases_json"), [])]
        for form in forms:
            target = normalize_for_match(form, variant_terms)
            score = similarity(source, target)
            if source[:1] and target[:1] and source[0] == target[0]:
                score += 0.06
            score = min(score, 1.0)
            if best is None or score > best["match_score"]:
                best = {
                    "canonical_id": term.get("canonical_id"),
                    "canonical_text": term["text"],
                    "match_score": round(score, 4),
                    "metadata_json": term.get("metadata_json") or "{}",
                }
    if best and best["match_score"] >= 0.58:
        return best
    return None


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    distance = weighted_edit_distance(a, b)
    return max(0.0, 1.0 - distance / max(len(a), len(b), 1))


def weighted_edit_distance(a: str, b: str) -> float:
    rows = len(a) + 1
    cols = len(b) + 1
    dp = [[0.0] * cols for _ in range(rows)]
    for i in range(1, rows):
        dp[i][0] = dp[i - 1][0] + (1.25 if i == 1 else 1.0)
    for j in range(1, cols):
        dp[0][j] = dp[0][j - 1] + (1.25 if j == 1 else 1.0)
    for i in range(1, rows):
        for j in range(1, cols):
            substitution = 0.0 if a[i - 1] == b[j - 1] else (1.25 if i == 1 or j == 1 else 1.0)
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,
                dp[i][j - 1] + 1.0,
                dp[i - 1][j - 1] + substitution,
            )
    return dp[-1][-1]
