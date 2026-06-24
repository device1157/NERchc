from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import DATA_DIR, Annotation, Dataset, Document, EntityType, Sentence, get_db, json_dumps, json_loads, row_to_dict
from ..models import DatasetBuildIn
from ..services.bioes import entities_to_bioes
from ..services.negatives import sample_negative_types

router = APIRouter(tags=["dataset"])


def _eligible_statuses(include_llm_only: bool) -> list[str]:
    return ["confirmed", "added", "unconfirmed"] if include_llm_only else ["confirmed", "added"]


@router.post("/dataset/build")
def build_dataset(payload: DatasetBuildIn, db: Session = Depends(get_db)):
    statuses = _eligible_statuses(payload.include_llm_only)
    sentence_rows = db.query(Sentence).order_by(Sentence.id).all()
    if not sentence_rows:
        raise HTTPException(status_code=400, detail="没有句子，无法构建数据集")
    type_tags = [row.tag for row in db.query(EntityType).order_by(EntityType.id).all()]
    output_dir = DATA_DIR / "datasets" / payload.name
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "annotations.jsonl"
    bioes_path = output_dir / "bioes.jsonl"
    stats = {"sentences": 0, "entities": 0, "by_type": {}, "negative_samples": 0, "train": 0, "test": 0, "warnings": []}
    with jsonl_path.open("w", encoding="utf-8") as ann_out, bioes_path.open("w", encoding="utf-8") as bioes_out:
        for sentence in sentence_rows:
            annotations = (
                db.query(Annotation)
                .filter(Annotation.sentence_id == sentence.id, Annotation.status.in_(statuses))
                .order_by(Annotation.start)
                .all()
            )
            entities = []
            for ann in annotations:
                item = {
                    "start": ann.start,
                    "end": ann.end,
                    "type": ann.entity_type_tag,
                    "text": ann.text,
                    "source": ann.source,
                    "score": ann.score,
                    "linked": None,
                }
                entities.append(item)
                stats["entities"] += 1
                stats["by_type"][ann.entity_type_tag] = stats["by_type"].get(ann.entity_type_tag, 0) + 1
            doc = db.get(Document, sentence.document_id)
            record = {
                "sentence_id": sentence.id,
                "volume": doc.volume if doc else None,
                "text": sentence.text,
                "split": sentence.split,
                "entities": entities,
            }
            ann_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            labels = entities_to_bioes(sentence.text, entities)
            bioes_out.write(
                json.dumps(
                    {
                        "sentence_id": sentence.id,
                        "tokens": list(sentence.text),
                        "labels": labels,
                        "split": sentence.split or "train",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            present = {entity["type"] for entity in entities}
            stats["negative_samples"] += len(sample_negative_types(type_tags, present, payload.positive_negative_ratio))
            stats["sentences"] += 1
            if sentence.split == "test":
                stats["test"] += 1
            else:
                stats["train"] += 1
    if stats["entities"] == 0:
        stats["warnings"].append("当前数据集中没有 confirmed/added 实体；如需调试可开启 include_llm_only。")
    row = Dataset(
        project_id=1,
        name=payload.name,
        config_json=json_dumps(payload.model_dump()),
        stats_json=json_dumps(stats),
        path=str(output_dir),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"dataset": row_to_dict(row), "stats": stats, "files": {"jsonl": str(jsonl_path), "bioes": str(bioes_path)}}


@router.get("/dataset/stats")
def dataset_stats(dataset_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Dataset)
    row = query.filter(Dataset.id == dataset_id).first() if dataset_id else query.order_by(Dataset.id.desc()).first()
    if row is None:
        return {"datasets": [], "stats": {}}
    return {"dataset": row_to_dict(row), "stats": json_loads(row.stats_json, {})}


@router.get("/dataset/sample")
def dataset_sample(dataset_id: int | None = None, limit: int = 5, db: Session = Depends(get_db)):
    row = db.query(Dataset).filter(Dataset.id == dataset_id).first() if dataset_id else db.query(Dataset).order_by(Dataset.id.desc()).first()
    if row is None:
        return {"items": []}
    path = Path(row.path) / "bioes.jsonl"
    if not path.exists():
        return {"items": []}
    items = []
    for line in path.read_text(encoding="utf-8").splitlines()[:limit]:
        items.append(json.loads(line))
    return {"items": items}


@router.get("/dataset/export")
def dataset_export(dataset_id: int | None = None, db: Session = Depends(get_db)):
    row = db.query(Dataset).filter(Dataset.id == dataset_id).first() if dataset_id else db.query(Dataset).order_by(Dataset.id.desc()).first()
    if row is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {"path": str(Path(row.path) / "annotations.jsonl")}

