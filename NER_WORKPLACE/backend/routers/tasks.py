from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Task, get_db, row_to_dict
from ..services.task_runner import set_task_flag, update_task

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def list_tasks(db: Session = Depends(get_db)):
    return [row_to_dict(row) for row in db.query(Task).order_by(Task.id.desc()).limit(50).all()]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    row = db.get(Task, task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return row_to_dict(row)


@router.post("/tasks/{task_id}/pause")
def pause_task(task_id: int):
    set_task_flag(task_id, "pause", True)
    update_task(task_id, status="paused", message="已请求暂停")
    return {"ok": True}


@router.post("/tasks/{task_id}/resume")
def resume_task(task_id: int):
    set_task_flag(task_id, "pause", False)
    update_task(task_id, status="running", message="已恢复")
    return {"ok": True}


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int):
    set_task_flag(task_id, "cancel", True)
    update_task(task_id, message="已请求取消")
    return {"ok": True}

