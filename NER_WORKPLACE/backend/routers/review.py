from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Annotation, Document, Sentence, get_db, row_to_dict
from ..models import AnnotationIn, AnnotationUpdateIn, ReviewConfirmIn, SplitAssignIn

router = APIRouter(tags=["review"])


def sentence_payload(sentence: Sentence | None, db: Session) -> dict | None:
    if sentence is None:
        return None
    annotations = db.query(Annotation).filter(Annotation.sentence_id == sentence.id, Annotation.status != "rejected").all()
    payload = row_to_dict(sentence)
    payload["annotations"] = [row_to_dict(row) for row in annotations]
    return payload


@router.get("/review/next")
def review_next(status: str = "pending", db: Session = Depends(get_db)):
    sentence = (
        db.query(Sentence)
        .filter(Sentence.sampled == True, Sentence.status != "reviewed")
        .order_by(Sentence.id)
        .first()
    )
    if sentence is None and status:
        sentence = db.query(Sentence).filter(Sentence.status == status).order_by(Sentence.id).first()
    return sentence_payload(sentence, db)


@router.post("/annotations")
def create_annotation(payload: AnnotationIn, db: Session = Depends(get_db)):
    sentence = db.get(Sentence, payload.sentence_id)
    if sentence is None:
        raise HTTPException(status_code=404, detail="sentence not found")
    text = payload.text if payload.text is not None else sentence.text[payload.start : payload.end]
    row = Annotation(
        sentence_id=payload.sentence_id,
        entity_type_tag=payload.entity_type_tag,
        start=payload.start,
        end=payload.end,
        text=text,
        source=payload.source,
        score=payload.score,
        status=payload.status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row_to_dict(row)


@router.put("/annotations/{annotation_id}")
def update_annotation(annotation_id: int, payload: AnnotationUpdateIn, db: Session = Depends(get_db)):
    row = db.get(Annotation, annotation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key != "id" and value is not None:
            setattr(row, key, value)
    db.commit()
    return row_to_dict(row)


@router.delete("/annotations/{annotation_id}")
def delete_annotation(annotation_id: int, db: Session = Depends(get_db)):
    row = db.get(Annotation, annotation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    row.status = "rejected"
    db.commit()
    return {"ok": True}


@router.post("/review/confirm")
def confirm_review(payload: ReviewConfirmIn, db: Session = Depends(get_db)):
    sentence = db.get(Sentence, payload.sentence_id)
    if sentence is None:
        raise HTTPException(status_code=404, detail="sentence not found")
    for annotation in db.query(Annotation).filter(Annotation.sentence_id == sentence.id, Annotation.status == "unconfirmed").all():
        annotation.status = "confirmed"
    sentence.status = "reviewed"
    db.commit()
    return sentence_payload(sentence, db)


@router.post("/split/assign")
def assign_split(payload: SplitAssignIn, db: Session = Depends(get_db)):
    if payload.train_volumes or payload.test_volumes:
        train_ids = [
            row.id
            for row in (
                db.query(Sentence.id)
                .join(Document, Sentence.document_id == Document.id)
                .filter(Document.volume.in_(payload.train_volumes))
                .all()
            )
        ]
        test_ids = [
            row.id
            for row in (
                db.query(Sentence.id)
                .join(Document, Sentence.document_id == Document.id)
                .filter(Document.volume.in_(payload.test_volumes))
                .all()
            )
        ]
        train_count = 0
        test_count = 0
        if train_ids:
            train_count = (
                db.query(Sentence)
                .filter(Sentence.id.in_(train_ids))
                .update({Sentence.split: "train"}, synchronize_session=False)
            )
        if test_ids:
            test_count = (
                db.query(Sentence)
                .filter(Sentence.id.in_(test_ids))
                .update({Sentence.split: "test"}, synchronize_session=False)
            )
        db.commit()
        return {"train": train_count, "test": test_count}
    rows = db.query(Sentence).order_by(Sentence.id).all()
    cutoff = round(len(rows) * (1 - payload.test_ratio))
    for i, row in enumerate(rows):
        row.split = "train" if i < cutoff else "test"
    db.commit()
    return {"train": cutoff, "test": max(0, len(rows) - cutoff)}
