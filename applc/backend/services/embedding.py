from __future__ import annotations

import hashlib
import math
from typing import Any

from backend.db import db, json_dumps, utc_now
from backend.services.artifacts import artifact_path

MODEL_NAME = "research-hybrid-embedding-v2"
HASH_BACKEND = "char-entity-hash-dbow-v1"
NEURAL_BACKEND = "shibing624/text2vec-base-chinese"
VECTOR_SIZE = 128
_SENTENCE_MODEL: Any | None = None


def run_embeddings() -> dict[str, Any]:
    with db() as conn:
        documents = conn.execute("SELECT id, raw_text FROM documents").fetchall()
        entities = conn.execute("SELECT document_id, start, end, entity_type FROM entities").fetchall()
        by_doc: dict[int, list[dict[str, Any]]] = {}
        for entity in entities:
            by_doc.setdefault(entity["document_id"], []).append(dict(entity))
        now = utc_now()
        count = 0
        backend_name = HASH_BACKEND
        for doc in documents:
            vector, backend_name = embed_paragraph_research(doc["raw_text"], by_doc.get(doc["id"], []))
            conn.execute(
                """
                INSERT INTO paragraph_vectors (document_id, model_name, vector_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id, model_name)
                DO UPDATE SET vector_json=excluded.vector_json, created_at=excluded.created_at
                """,
                (doc["id"], MODEL_NAME, json_dumps(vector), now),
            )
            count += 1
        return {"documents": len(documents), "vectors": count, "model_name": MODEL_NAME, "backend": backend_name}


def embed_paragraph_research(text: str, entities: list[dict[str, Any]] | None = None) -> tuple[list[float], str]:
    neural = _embed_with_sentence_transformer(text)
    if neural:
        return neural, NEURAL_BACKEND
    return embed_paragraph(text, entities), HASH_BACKEND


def embed_paragraph(text: str, entities: list[dict[str, Any]] | None = None) -> list[float]:
    vector = [0.0] * VECTOR_SIZE
    tokens = list(text)
    tokens.extend(_bigrams(text))
    if entities:
        for entity in entities:
            tokens.append(f"<{entity['entity_type']}>")
            tokens.append(f"<{entity['entity_type']}:{text[entity['start']:entity['end']]}>")
    for token in tokens:
        index = _hash(token) % VECTOR_SIZE
        sign = 1.0 if (_hash("sign:" + token) % 2 == 0) else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def _bigrams(text: str) -> list[str]:
    return [text[index : index + 2] for index in range(max(0, len(text) - 1))]


def _hash(value: str) -> int:
    return int(hashlib.blake2b(value.encode("utf-8"), digest_size=8).hexdigest(), 16)


def _embed_with_sentence_transformer(text: str) -> list[float] | None:
    model = _load_sentence_model()
    if model is None:
        return None
    try:
        vector = model.encode([text], normalize_embeddings=True)[0]
    except Exception:
        return None
    return [round(float(value), 6) for value in vector]


def _load_sentence_model() -> Any | None:
    global _SENTENCE_MODEL
    if _SENTENCE_MODEL is not None:
        return _SENTENCE_MODEL
    path = artifact_path("text2vec-base-chinese")
    if not path.exists() or not any(path.iterdir()):
        return None
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        return None
    try:
        _SENTENCE_MODEL = SentenceTransformer(str(path))
    except Exception:
        _SENTENCE_MODEL = None
    return _SENTENCE_MODEL
