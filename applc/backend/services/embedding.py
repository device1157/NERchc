from __future__ import annotations

import hashlib
import math
from typing import Any

from backend.db import db, json_dumps, utc_now

MODEL_NAME = "char-entity-hash-dbow-v1"
VECTOR_SIZE = 128


def run_embeddings() -> dict[str, Any]:
    with db() as conn:
        documents = conn.execute("SELECT id, raw_text FROM documents").fetchall()
        entities = conn.execute("SELECT document_id, start, end, entity_type FROM entities").fetchall()
        by_doc: dict[int, list[dict[str, Any]]] = {}
        for entity in entities:
            by_doc.setdefault(entity["document_id"], []).append(dict(entity))
        now = utc_now()
        count = 0
        for doc in documents:
            vector = embed_paragraph(doc["raw_text"], by_doc.get(doc["id"], []))
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
        return {"documents": len(documents), "vectors": count, "model_name": MODEL_NAME}


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
