from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.db import db, utc_now


def run_step(step: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    now = utc_now()
    with db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO pipeline_runs (step, status, progress, total, message, created_at, updated_at)
            VALUES (?, 'running', 0, 1, '', ?, ?)
            """,
            (step, now, now),
        )
        run_id = cursor.lastrowid
    try:
        result = fn()
        with db() as conn:
            conn.execute(
                "UPDATE pipeline_runs SET status='done', progress=1, total=1, message=?, updated_at=? WHERE id=?",
                (str(result), utc_now(), run_id),
            )
        return {"run_id": run_id, "step": step, "status": "done", "result": result}
    except Exception as exc:
        with db() as conn:
            conn.execute(
                "UPDATE pipeline_runs SET status='error', message=?, updated_at=? WHERE id=?",
                (str(exc), utc_now(), run_id),
            )
        raise
