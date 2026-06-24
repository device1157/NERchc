from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Dataset, TrainRun, get_db, json_dumps, json_loads, row_to_dict
from ..models import TrainStartIn
from ..services.task_runner import create_task, start_thread
from ..services.trainer import run_training_simulation

router = APIRouter(tags=["train"])


@router.post("/train/start")
def start_train(payload: TrainStartIn, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, payload.dataset_id) if payload.dataset_id else db.query(Dataset).order_by(Dataset.id.desc()).first()
    if dataset is None:
        raise HTTPException(status_code=400, detail="请先构建训练数据集")
    run = TrainRun(
        project_id=1,
        dataset_id=dataset.id,
        config_json=json_dumps(payload.model_dump()),
        status="pending",
        progress_json="{}",
        metrics_json="{}",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    task = create_task(db, "train", total=payload.epochs * 12, ref_id=run.id, message="训练待启动")
    start_thread(task.id, lambda task_id: run_training_simulation(task_id, run.id, payload.model_dump()))
    return {"task_id": task.id, "train_run": row_to_dict(run)}


@router.get("/train/runs")
def list_train_runs(db: Session = Depends(get_db)):
    rows = db.query(TrainRun).order_by(TrainRun.id.desc()).all()
    result = []
    for row in rows:
        data = row_to_dict(row)
        data["progress"] = json_loads(row.progress_json, {})
        data["metrics"] = json_loads(row.metrics_json, {})
        result.append(data)
    return result


@router.get("/train/runs/{run_id}")
def get_train_run(run_id: int, db: Session = Depends(get_db)):
    row = db.get(TrainRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="train run not found")
    data = row_to_dict(row)
    data["config"] = json_loads(row.config_json, {})
    data["progress"] = json_loads(row.progress_json, {})
    data["metrics"] = json_loads(row.metrics_json, {})
    return data

