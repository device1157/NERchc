from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import EntityType, get_db, json_dumps, json_loads, row_to_dict
from ..models import EntityTypeIn

router = APIRouter(tags=["schema"])


def serialize_entity_type(row: EntityType) -> dict:
    data = row_to_dict(row)
    data["positive_examples"] = json_loads(row.positive_examples, [])
    data["negative_examples"] = json_loads(row.negative_examples, [])
    return data


@router.get("/entity-types")
def list_entity_types(db: Session = Depends(get_db)):
    return [serialize_entity_type(row) for row in db.query(EntityType).order_by(EntityType.id).all()]


@router.post("/entity-types")
def create_entity_type(payload: EntityTypeIn, db: Session = Depends(get_db)):
    row = EntityType(
        project_id=1,
        tag=payload.tag.upper(),
        label=payload.label,
        definition=payload.definition,
        rules=payload.rules,
        positive_examples=json_dumps(payload.positive_examples),
        negative_examples=json_dumps(payload.negative_examples),
        color=payload.color,
        freq=payload.freq,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_entity_type(row)


@router.put("/entity-types/{entity_id}")
def update_entity_type(entity_id: int, payload: EntityTypeIn, db: Session = Depends(get_db)):
    row = db.get(EntityType, entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="entity type not found")
    row.tag = payload.tag.upper()
    row.label = payload.label
    row.definition = payload.definition
    row.rules = payload.rules
    row.positive_examples = json_dumps(payload.positive_examples)
    row.negative_examples = json_dumps(payload.negative_examples)
    row.color = payload.color
    row.freq = payload.freq
    db.commit()
    return serialize_entity_type(row)


@router.delete("/entity-types/{entity_id}")
def delete_entity_type(entity_id: int, db: Session = Depends(get_db)):
    row = db.get(EntityType, entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="entity type not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/entity-types/try")
def try_entity_type(payload: dict, db: Session = Depends(get_db)):
    sentence = payload.get("sentence", "")
    examples = []
    for entity_type in db.query(EntityType).all():
        for text in json_loads(entity_type.positive_examples, []):
            start = sentence.find(text)
            if start >= 0:
                examples.append({"start": start, "end": start + len(text), "type": entity_type.tag, "text": text})
    return {"sentence": sentence, "entities": examples}

