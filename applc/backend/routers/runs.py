from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.db import db, row_to_dict, rows_to_dicts

router = APIRouter()


@router.get("")
def list_runs(limit: int = 100) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, step, status, progress, total, message, created_at, updated_at
            FROM pipeline_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return {"items": rows_to_dicts(rows)}


@router.get("/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM pipeline_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found.")
    return row_to_dict(row) or {}
