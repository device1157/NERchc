from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Annotation, Dataset, Document, EntityType, Sentence, TrainRun, get_db, json_loads, row_to_dict
from ..models import InferIn

router = APIRouter(tags=["results"])


@router.get("/results/annotations")
def browse_annotations(
    page: int = 1,
    page_size: int = 20,
    entity_type: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Sentence).order_by(Sentence.id)
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for sentence in rows:
        ann_query = db.query(Annotation).filter(Annotation.sentence_id == sentence.id, Annotation.status != "rejected")
        if entity_type:
            ann_query = ann_query.filter(Annotation.entity_type_tag == entity_type)
        if source:
            ann_query = ann_query.filter(Annotation.source == source)
        doc = db.get(Document, sentence.document_id)
        items.append(
            {
                **row_to_dict(sentence),
                "volume": doc.volume if doc else None,
                "annotations": [row_to_dict(row) for row in ann_query.order_by(Annotation.start).all()],
            }
        )
    return {"total": total, "items": items}


@router.post("/results/infer")
def infer(payload: InferIn, db: Session = Depends(get_db)):
    # MVP：无模型时用实体正例词表做可解释预览；真实模型可在 trainer 中替换。
    entities = []
    for entity_type in db.query(EntityType).all():
        examples = json_loads(entity_type.positive_examples, [])
        for example in examples:
            pos = payload.text.find(example)
            while pos >= 0:
                entities.append(
                    {
                        "start": pos,
                        "end": pos + len(example),
                        "type": entity_type.tag,
                        "text": example,
                        "source": "model",
                        "score": 0.5,
                    }
                )
                pos = payload.text.find(example, pos + 1)
    return {"text": payload.text, "checkpoint_path": payload.checkpoint_path, "entities": entities}


@router.get("/results/metrics/{run_id}")
def metrics(run_id: int, db: Session = Depends(get_db)):
    run = db.get(TrainRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="train run not found")
    return json_loads(run.metrics_json, {})


@router.get("/results/export")
def export_results(dataset_id: int | None = None, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first() if dataset_id else db.query(Dataset).order_by(Dataset.id.desc()).first()
    if dataset:
        return {"annotations_jsonl": f"{dataset.path}/annotations.jsonl", "dataset_dir": dataset.path}
    raise HTTPException(status_code=404, detail="请先构建数据集")

