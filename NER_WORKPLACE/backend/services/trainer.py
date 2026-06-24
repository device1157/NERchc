from __future__ import annotations

import json
import time
from pathlib import Path

from ..db import SessionLocal, TrainRun, now
from .task_runner import get_flags, update_task

ROOT_DIR = Path(__file__).resolve().parents[2]


def run_training_simulation(task_id: int, train_run_id: int, config: dict) -> None:
    epochs = int(config.get("epochs") or 3)
    steps_per_epoch = 12
    total = epochs * steps_per_epoch
    progress = 0
    for epoch in range(1, epochs + 1):
        for step in range(1, steps_per_epoch + 1):
            flags = get_flags(task_id)
            if flags.get("cancel"):
                _finish_run(train_run_id, "cancelled", {}, None)
                update_task(task_id, status="cancelled", message="训练已取消")
                return
            while flags.get("pause"):
                update_task(task_id, status="paused", message="训练已暂停")
                time.sleep(0.5)
            progress += 1
            loss = max(0.05, 1.2 / (progress + 1))
            f1 = min(0.95, 0.35 + progress / total * 0.5)
            progress_json = {"stage": "domain", "epoch": epoch, "step": step, "loss": loss, "eval_f1": f1}
            with SessionLocal() as db:
                run = db.get(TrainRun, train_run_id)
                if run:
                    run.status = "running"
                    run.progress_json = json.dumps(progress_json, ensure_ascii=False)
                    db.commit()
            update_task(task_id, progress=progress, total=total, status="running", message=f"epoch {epoch}/{epochs}, step {step}")
            time.sleep(0.15)
    checkpoint = ROOT_DIR / "data" / "models" / f"train_run_{train_run_id}"
    checkpoint.mkdir(parents=True, exist_ok=True)
    (checkpoint / "README.txt").write_text("模拟训练产物。安装 transformers 后可替换为真实训练流程。", encoding="utf-8")
    metrics = {
        "overall": {"precision": 0.82, "recall": 0.78, "f1": 0.80},
        "by_type": {
            "PER": {"precision": 0.84, "recall": 0.80, "f1": 0.82},
            "LOC": {"precision": 0.80, "recall": 0.76, "f1": 0.78},
            "OFF": {"precision": 0.78, "recall": 0.72, "f1": 0.75},
        },
        "partial": {"exact": 42, "partial": 7, "missing": 9, "spurious": 6},
        "diagnosis": ["partial 较高时可尝试 CRF 或官职词典", "missing 较高时优先补充低频类型样本", "spurious 较高时增加负样本"],
    }
    _finish_run(train_run_id, "done", metrics, str(checkpoint))
    update_task(task_id, status="done", progress=total, total=total, message="训练完成")


def _finish_run(train_run_id: int, status: str, metrics: dict, checkpoint_path: str | None) -> None:
    with SessionLocal() as db:
        run = db.get(TrainRun, train_run_id)
        if run:
            run.status = status
            run.metrics_json = json.dumps(metrics, ensure_ascii=False)
            run.checkpoint_path = checkpoint_path
            run.finished_at = now()
            db.commit()

