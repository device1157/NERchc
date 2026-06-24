from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import DATA_DIR, Document, Sentence, get_db, json_dumps, row_to_dict
from ..models import PreprocessIn, SampleIn
from ..services.preprocess import (
    clean_text,
    convert_simplified_to_traditional,
    punctuate_document,
    read_text,
    split_documents,
    split_sentences,
    stratified_sample,
)

router = APIRouter(tags=["corpus"])
RAW_DIR = DATA_DIR / "corpus" / "raw"
PREVIEW_PATH = DATA_DIR / "corpus" / "last_preview.json"


@router.post("/corpus/upload")
async def upload_corpus(file: UploadFile = File(...)):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="只支持 .txt 文件")
    target = RAW_DIR / Path(file.filename).name
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"filename": target.name, "path": str(target), "size": target.stat().st_size}


@router.post("/corpus/preprocess")
def preprocess_corpus(payload: PreprocessIn, db: Session = Depends(get_db)):
    files = [RAW_DIR / payload.filename] if payload.filename else sorted(RAW_DIR.glob("*.txt"))
    files = [path for path in files if path.exists()]
    if not files:
        raise HTTPException(status_code=404, detail="未找到可处理的 txt 文件")

    if payload.reset_existing:
        db.query(Sentence).delete()
        db.query(Document).delete()
        db.commit()

    stats = {
        "files": len(files),
        "documents": 0,
        "sentences": 0,
        "conversion": "disabled",
        "punctuation": "fallback_rules",
        "samples": [],
    }
    for path in files:
        text = read_text(path)
        text = clean_text(text, payload.clean_regex)
        text, conversion = convert_simplified_to_traditional(text, payload.convert_s2t)
        stats["conversion"] = conversion
        for doc in split_documents(text):
            punctuated, punctuation = punctuate_document(doc.text)
            stats["punctuation"] = punctuation
            row = Document(project_id=1, volume=doc.volume, seq=doc.seq, raw_text=punctuated, meta_json=json_dumps(doc.meta))
            db.add(row)
            db.flush()
            stats["documents"] += 1
            for sentence in split_sentences(punctuated, payload.min_sentence_len, payload.max_sentence_len):
                db.add(
                    Sentence(
                        document_id=row.id,
                        idx=sentence.idx,
                        text=sentence.text,
                        char_offset=sentence.char_offset,
                        status="pending",
                    )
                )
                stats["sentences"] += 1
    db.commit()
    sample_payload = SampleIn(sample_size=payload.sample_size)
    sample_result = sample_sentences(sample_payload, db)
    stats["sampled"] = sample_result["sampled"]
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


@router.get("/corpus/preview")
def corpus_preview(db: Session = Depends(get_db), limit: int = 10):
    rows = db.query(Sentence).order_by(Sentence.id).limit(limit).all()
    stats = json.loads(PREVIEW_PATH.read_text(encoding="utf-8")) if PREVIEW_PATH.exists() else {}
    return {"stats": stats, "sentences": [row_to_dict(row) for row in rows]}


@router.post("/corpus/sample")
def sample_sentences(payload: SampleIn, db: Session = Depends(get_db)):
    rows = (
        db.query(Sentence.id, Document.volume, Sentence.text)
        .join(Document, Sentence.document_id == Document.id)
        .order_by(Sentence.id)
        .all()
    )
    selected = stratified_sample([(row.id, row.volume or "未分卷", row.text) for row in rows], payload.sample_size)
    db.query(Sentence).update({Sentence.sampled: False})
    if selected:
        db.query(Sentence).filter(Sentence.id.in_(selected)).update({Sentence.sampled: True}, synchronize_session=False)
    db.commit()
    return {"sampled": len(selected), "total": len(rows)}


@router.get("/corpus/stats")
def corpus_stats(db: Session = Depends(get_db)):
    volume_counts = (
        db.query(Document.volume, func.count(Sentence.id))
        .join(Sentence, Sentence.document_id == Document.id)
        .group_by(Document.volume)
        .all()
    )
    return {
        "documents": db.query(Document).count(),
        "sentences": db.query(Sentence).count(),
        "sampled": db.query(Sentence).filter(Sentence.sampled == True).count(),
        "reviewed": db.query(Sentence).filter(Sentence.status == "reviewed").count(),
        "volumes": [{"volume": volume, "sentences": count} for volume, count in volume_counts],
    }


@router.get("/sentences")
def list_sentences(
    page: int = 1,
    page_size: int = 30,
    sampled: bool | None = None,
    status: str | None = None,
    split: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Sentence)
    if sampled is not None:
        query = query.filter(Sentence.sampled == sampled)
    if status:
        query = query.filter(Sentence.status == status)
    if split:
        query = query.filter(Sentence.split == split)
    total = query.count()
    rows = query.order_by(Sentence.id).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [row_to_dict(row) for row in rows]}

