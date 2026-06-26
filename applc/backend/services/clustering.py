from __future__ import annotations

import math
from collections import Counter
from typing import Any

from backend.db import db, json_loads, json_dumps, utc_now
from backend.services.embedding import MODEL_NAME


def run_clustering(k: int | None = None) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.raw_text, pv.vector_json
            FROM documents d
            JOIN paragraph_vectors pv ON pv.document_id = d.id
            WHERE pv.model_name = ?
            ORDER BY d.id
            """,
            (MODEL_NAME,),
        ).fetchall()
        if not rows:
            return {"documents": 0, "clusters": 0}
        vectors = [json_loads(row["vector_json"], []) for row in rows]
        cluster_count = k or _auto_k(len(rows))
        assignments, centroids = _kmeans(vectors, cluster_count)
        conn.execute("DELETE FROM clusters")
        conn.execute("DELETE FROM cluster_summaries")
        now = utc_now()
        for row, assignment, vector in zip(rows, assignments, vectors):
            similarity = cosine(vector, centroids[assignment])
            conn.execute(
                """
                INSERT INTO clusters (document_id, cluster_id, similarity, label, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (row["id"], assignment, round(similarity, 4), f"Cluster {assignment + 1}", now),
            )
        for cluster_id in sorted(set(assignments)):
            docs = [rows[index]["raw_text"] for index, item in enumerate(assignments) if item == cluster_id]
            keywords = _keywords(docs)
            template_text = min(docs, key=len)[:180] if docs else ""
            conn.execute(
                """
                INSERT INTO cluster_summaries (cluster_id, label, size, keywords_json, template_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cluster_id, f"Cluster {cluster_id + 1}", len(docs), json_dumps(keywords), template_text, now),
            )
        return {"documents": len(rows), "clusters": len(set(assignments))}


def _auto_k(n: int) -> int:
    if n <= 1:
        return 1
    return max(2, min(8, int(math.sqrt(n)) or 2))


def _kmeans(vectors: list[list[float]], k: int, iterations: int = 25) -> tuple[list[int], list[list[float]]]:
    k = max(1, min(k, len(vectors)))
    centroids = [vectors[index][:] for index in range(k)]
    assignments = [0] * len(vectors)
    for _ in range(iterations):
        changed = False
        for index, vector in enumerate(vectors):
            best = max(range(k), key=lambda cluster: cosine(vector, centroids[cluster]))
            if best != assignments[index]:
                assignments[index] = best
                changed = True
        centroids = [_mean([vectors[index] for index, cluster in enumerate(assignments) if cluster == cluster_id], len(vectors[0])) for cluster_id in range(k)]
        if not changed:
            break
    return assignments, centroids


def _mean(items: list[list[float]], size: int) -> list[float]:
    if not items:
        return [0.0] * size
    values = [0.0] * size
    for item in items:
        for index, value in enumerate(item):
            values[index] += value
    norm = math.sqrt(sum((value / len(items)) ** 2 for value in values)) or 1.0
    return [(value / len(items)) / norm for value in values]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _keywords(docs: list[str]) -> list[str]:
    counter: Counter[str] = Counter()
    stop = set("年月日之其以於于也者詔命")
    for doc in docs:
        for index in range(max(0, len(doc) - 1)):
            token = doc[index : index + 2]
            if any(char in stop for char in token):
                continue
            counter[token] += 1
    return [token for token, _ in counter.most_common(8)]
