from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.db import db, json_loads, utc_now

DEFAULT_EVENTS = {
    "military": ["征", "討", "兵", "軍", "都督", "衛", "边", "邊"],
    "tribute": ["貢", "贡", "來朝", "来朝", "遣使", "朝"],
    "appointment": ["授", "陞", "升", "拜", "除", "命", "官"],
    "punishment": ["誅", "诛", "斬", "斩", "罰", "罚", "罪", "獄", "狱"],
    "disaster": ["旱", "水", "蝗", "震", "災", "灾"],
    "finance": ["稅", "税", "糧", "粮", "鈔", "钞", "戶部", "户部"],
}


def run_classification(threshold: float = 0.2) -> dict[str, Any]:
    with db() as conn:
        documents = conn.execute("SELECT id, raw_text FROM documents").fetchall()
        terms = conn.execute("SELECT * FROM knowledge_terms WHERE type='event_keyword'").fetchall()
        event_keywords = _load_event_keywords([dict(term) for term in terms])
        conn.execute("DELETE FROM event_predictions")
        now = utc_now()
        count = 0
        for doc in documents:
            predictions = classify_text(doc["raw_text"], event_keywords, threshold)
            for event_type, probability in predictions:
                conn.execute(
                    """
                    INSERT INTO event_predictions
                    (document_id, event_type, probability, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (doc["id"], event_type, probability, "keyword_svm_fallback", now),
                )
                count += 1
        return {"documents": len(documents), "predictions": count}


def classify_text(text: str, event_keywords: dict[str, list[str]], threshold: float) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for event_type, keywords in event_keywords.items():
        score = 0.0
        for keyword in keywords:
            if not keyword:
                continue
            score += text.count(keyword) * (1.0 + min(len(keyword), 4) / 4.0)
        if score > 0:
            scores[event_type] = score
    if not scores:
        return [("uncategorized", 1.0)]
    total = sum(scores.values())
    predictions = [(event_type, round(score / total, 4)) for event_type, score in scores.items() if score / total >= threshold]
    return sorted(predictions or [(max(scores, key=scores.get), 1.0)], key=lambda item: item[1], reverse=True)


def _load_event_keywords(terms: list[dict[str, Any]]) -> dict[str, list[str]]:
    events: dict[str, list[str]] = defaultdict(list)
    for term in terms:
        metadata = json_loads(term.get("metadata_json"), {})
        event_type = metadata.get("event_type") or term.get("canonical_id") or term["text"]
        events[event_type].append(term["text"])
        events[event_type].extend(json_loads(term.get("aliases_json"), []))
    for event_type, keywords in DEFAULT_EVENTS.items():
        events[event_type].extend(keywords)
    return {event_type: sorted(set(keywords), key=len, reverse=True) for event_type, keywords in events.items()}
