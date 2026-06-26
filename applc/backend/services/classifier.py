from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.db import db, json_loads, utc_now
from backend.services.embedding import MODEL_NAME

MIN_SUPERVISED_LABELS = 4

DEFAULT_EVENTS = {
    "military": ["征", "討", "讨", "伐", "兵", "軍", "军", "率軍", "都督", "衛", "卫", "边", "邊"],
    "tribute": ["朝貢", "朝贡", "入貢", "入贡", "貢", "贡", "來朝", "来朝", "遣使", "朝"],
    "appointment": ["冊立", "册立", "立為", "立为", "皇太子", "太子", "封", "授", "陞", "升", "拜", "除", "命", "官"],
    "punishment": ["誅", "诛", "斬", "斩", "罰", "罚", "罪", "獄", "狱"],
    "disaster": ["大水", "水災", "水灾", "旱", "蝗", "震", "災", "灾", "水"],
    "finance": ["稅", "税", "糧", "粮", "鈔", "钞", "戶部", "户部"],
}

PHRASE_BOOSTS = {
    "military": {
        "率軍": 2.4,
        "率军": 2.4,
        "討邊": 2.2,
        "讨边": 2.2,
        "征討": 2.2,
        "征讨": 2.2,
        "出師": 1.8,
        "出师": 1.8,
    },
    "tribute": {
        "遣使來朝": 3.0,
        "遣使来朝": 3.0,
        "朝貢": 2.8,
        "朝贡": 2.8,
        "入貢": 2.5,
        "入贡": 2.5,
        "貢方物": 2.2,
        "贡方物": 2.2,
    },
    "appointment": {
        "冊立": 3.0,
        "册立": 3.0,
        "皇太子": 2.8,
        "立為": 2.4,
        "立为": 2.4,
        "封": 1.8,
        "命": 0.8,
    },
    "punishment": {
        "下獄": 2.4,
        "下狱": 2.4,
        "論罪": 2.2,
        "论罪": 2.2,
        "斬首": 2.4,
        "斩首": 2.4,
    },
    "disaster": {
        "大水": 2.8,
        "水災": 2.8,
        "水灾": 2.8,
        "地震": 2.6,
        "蝗災": 2.6,
        "蝗灾": 2.6,
        "旱災": 2.6,
        "旱灾": 2.6,
    },
    "finance": {
        "戶部": 1.9,
        "户部": 1.9,
        "賦役": 2.2,
        "赋役": 2.2,
        "稅糧": 2.4,
        "税粮": 2.4,
        "鈔法": 2.2,
        "钞法": 2.2,
    },
}

AMBIGUOUS_SINGLE_CHAR_WEIGHTS = {
    ("appointment", "命"): 0.45,
    ("appointment", "官"): 0.55,
    ("tribute", "朝"): 0.15,
    ("military", "衛"): 0.25,
    ("military", "卫"): 0.25,
    ("disaster", "水"): 0.1,
}

DISASTER_WATER_CONTEXTS = ("大水", "水災", "水灾", "河決", "河决", "霖雨", "洪水", "水旱")
TRIBUTE_COURT_CONTEXTS = ("來朝", "来朝", "朝貢", "朝贡", "入朝", "遣使")


def run_classification(threshold: float = 0.2) -> dict[str, Any]:
    with db() as conn:
        documents = conn.execute("SELECT id, raw_text FROM documents").fetchall()
        terms = conn.execute("SELECT * FROM knowledge_terms WHERE type='event_keyword'").fetchall()
        annotations = conn.execute(
            "SELECT * FROM user_annotations WHERE annotation_type = 'event' ORDER BY id"
        ).fetchall()
        vectors = conn.execute(
            "SELECT document_id, vector_json FROM paragraph_vectors WHERE model_name = ?",
            (MODEL_NAME,),
        ).fetchall()
        event_keywords = _load_event_keywords([dict(term) for term in terms])
        event_annotations, event_deletions = _load_event_annotation_rules([dict(row) for row in annotations])
        supervised = _try_supervised_predictions([dict(row) for row in documents], [dict(row) for row in vectors], event_annotations, threshold)
        conn.execute("DELETE FROM event_predictions")
        now = utc_now()
        count = 0
        for doc in documents:
            doc_id = doc["id"]
            if event_annotations.get(doc_id):
                predictions = [(event_type, 1.0, "user_annotation") for event_type in event_annotations[doc_id]]
            elif supervised:
                predictions = supervised.get(doc_id) or classify_text_with_source(doc["raw_text"], event_keywords, threshold)
            else:
                predictions = classify_text_with_source(doc["raw_text"], event_keywords, threshold)
            deleted = event_deletions.get(doc_id, set())
            if deleted:
                predictions = [prediction for prediction in predictions if prediction[0] not in deleted]
                if not predictions:
                    predictions = [("uncategorized", 1.0, "user_annotation_delete")]
            for event_type, probability, source in predictions:
                conn.execute(
                    """
                    INSERT INTO event_predictions
                    (document_id, event_type, probability, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (doc["id"], event_type, probability, source, now),
                )
                count += 1
        return {"documents": len(documents), "predictions": count, "supervised": bool(supervised)}


def classify_text(text: str, event_keywords: dict[str, list[str]], threshold: float) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for event_type, keywords in event_keywords.items():
        score = 0.0
        for keyword in keywords:
            if not keyword:
                continue
            score += _keyword_score(text, event_type, keyword)
        score += _phrase_boost(text, event_type)
        if score > 0:
            scores[event_type] = score
    if not scores:
        return [("uncategorized", 1.0)]
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_score = ranked[0][1]
    selected_scores = [
        (event_type, score)
        for event_type, score in ranked
        if score >= best_score * 0.68
    ]
    total = sum(score for _event_type, score in selected_scores)
    predictions = [
        (event_type, round(score / total, 4))
        for event_type, score in selected_scores
        if score / total >= threshold
    ]
    return sorted(predictions or [(ranked[0][0], 1.0)], key=lambda item: item[1], reverse=True)


def classify_text_with_source(text: str, event_keywords: dict[str, list[str]], threshold: float) -> list[tuple[str, float, str]]:
    return [(event_type, probability, "keyword_rules_v2") for event_type, probability in classify_text(text, event_keywords, threshold)]


def _keyword_score(text: str, event_type: str, keyword: str) -> float:
    count = text.count(keyword)
    if count <= 0:
        return 0.0
    if event_type == "disaster" and keyword == "水" and not any(phrase in text for phrase in DISASTER_WATER_CONTEXTS):
        return 0.0
    if event_type == "tribute" and keyword == "朝" and not any(phrase in text for phrase in TRIBUTE_COURT_CONTEXTS):
        return 0.0
    weight = AMBIGUOUS_SINGLE_CHAR_WEIGHTS.get((event_type, keyword))
    if weight is None:
        weight = 0.75 if len(keyword) == 1 else 1.0 + min(len(keyword), 4) / 3.0
    return count * weight


def _phrase_boost(text: str, event_type: str) -> float:
    boosts = PHRASE_BOOSTS.get(event_type, {})
    return sum(text.count(phrase) * weight for phrase, weight in boosts.items() if phrase in text)


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


def _load_event_annotation_rules(rows: list[dict[str, Any]]) -> tuple[dict[int, list[str]], dict[int, set[str]]]:
    labels: dict[int, list[str]] = defaultdict(list)
    deletions: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        event_type = row.get("event_type")
        if not event_type:
            continue
        doc_id = int(row["document_id"])
        if row.get("action") == "delete":
            deletions[doc_id].add(event_type)
            continue
        if event_type not in labels[doc_id]:
            labels[doc_id].append(event_type)
    return dict(labels), dict(deletions)


def _try_supervised_predictions(
    documents: list[dict[str, Any]],
    vectors: list[dict[str, Any]],
    labels_by_doc: dict[int, list[str]],
    threshold: float,
) -> dict[int, list[tuple[str, float, str]]] | None:
    if sum(len(labels) for labels in labels_by_doc.values()) < MIN_SUPERVISED_LABELS:
        return None
    vector_by_doc = {row["document_id"]: json_loads(row["vector_json"], []) for row in vectors}
    train_x = []
    train_y = []
    for doc_id, labels in labels_by_doc.items():
        vector = vector_by_doc.get(doc_id)
        if not vector:
            continue
        for label in labels:
            train_x.append(vector)
            train_y.append(label)
    if len(train_x) < MIN_SUPERVISED_LABELS or len(set(train_y)) < 2:
        return None
    try:
        from sklearn.linear_model import LogisticRegression  # type: ignore
    except Exception:
        return None
    try:
        classifier = LogisticRegression(max_iter=1000, class_weight="balanced")
        classifier.fit(train_x, train_y)
    except Exception:
        return None
    predictions: dict[int, list[tuple[str, float, str]]] = {}
    classes = list(classifier.classes_)
    for doc in documents:
        doc_id = doc["id"]
        vector = vector_by_doc.get(doc_id)
        if not vector:
            continue
        try:
            probabilities = classifier.predict_proba([vector])[0]
        except Exception:
            continue
        selected = [
            (classes[index], round(float(probability), 4), "logistic_regression_annotation_v1")
            for index, probability in enumerate(probabilities)
            if float(probability) >= threshold
        ]
        if not selected:
            best_index = max(range(len(probabilities)), key=lambda index: probabilities[index])
            selected = [(classes[best_index], round(float(probabilities[best_index]), 4), "logistic_regression_annotation_v1")]
        predictions[doc_id] = sorted(selected, key=lambda item: item[1], reverse=True)
    return predictions
