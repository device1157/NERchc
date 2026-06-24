from __future__ import annotations

import threading
from collections.abc import Callable

from sqlalchemy.orm import Session

from ..db import SessionLocal, Task

RUNNING_THREADS: dict[int, threading.Thread] = {}
TASK_FLAGS: dict[int, dict[str, bool]] = {}


def create_task(db: Session, task_type: str, total: int = 0, ref_id: int | None = None, message: str = "") -> Task:
    task = Task(type=task_type, total=total, ref_id=ref_id, status="pending", message=message)
    db.add(task)
    db.commit()
    db.refresh(task)
    TASK_FLAGS[task.id] = {"cancel": False, "pause": False}
    return task


def update_task(task_id: int, **kwargs) -> None:
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if task is None:
            return
        for key, value in kwargs.items():
            setattr(task, key, value)
        db.commit()


def get_flags(task_id: int) -> dict[str, bool]:
    return TASK_FLAGS.setdefault(task_id, {"cancel": False, "pause": False})


def start_thread(task_id: int, target: Callable[[int], None]) -> None:
    def run() -> None:
        update_task(task_id, status="running")
        try:
            target(task_id)
        except Exception as exc:
            update_task(task_id, status="error", message=str(exc))

    thread = threading.Thread(target=run, daemon=True)
    RUNNING_THREADS[task_id] = thread
    thread.start()


def set_task_flag(task_id: int, flag: str, value: bool) -> bool:
    flags = get_flags(task_id)
    if flag not in flags:
        return False
    flags[flag] = value
    return True

