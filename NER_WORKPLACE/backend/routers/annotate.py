from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Annotation, EntityType, LLMCall, PromptTemplate, Sentence, SessionLocal, get_db, json_dumps
from ..services.llm_client import LLMClient
from ..services.ner_parse import parse_llm_entities
from ..services.task_runner import create_task, get_flags, start_thread, update_task
from ..settings_store import load_llm_settings
from .prompt import render_messages
from ..models import PromptPreviewIn

router = APIRouter(tags=["annotate"])


@router.get("/annotate/estimate")
def estimate_annotation(db: Session = Depends(get_db)):
    sentence_count = db.query(Sentence).filter(Sentence.sampled == True).count()
    type_count = db.query(EntityType).count()
    done = db.query(LLMCall).filter(LLMCall.status == "done").count()
    total = sentence_count * type_count
    return {"sentences": sentence_count, "entity_types": type_count, "total_calls": total, "remaining": max(0, total - done)}


@router.post("/annotate/start")
def start_annotation(db: Session = Depends(get_db)):
    estimate = estimate_annotation(db)
    if estimate["total_calls"] == 0:
        raise HTTPException(status_code=400, detail="没有 sampled 句子或实体类型")
    task = create_task(db, "annotate", total=estimate["total_calls"], message="LLM 批量标注待启动")
    start_thread(task.id, _run_annotation_task)
    return {"task_id": task.id, **estimate}


def _run_annotation_task(task_id: int) -> None:
    asyncio.run(_run_annotation_async(task_id))


async def _run_annotation_async(task_id: int) -> None:
    settings = load_llm_settings(mask_key=False)
    client = LLMClient(settings)
    with SessionLocal() as db:
        template = db.query(PromptTemplate).filter(PromptTemplate.is_active == True).first()
        if template is None:
            update_task(task_id, status="error", message="没有 active prompt")
            return
        sentence_ids = [row.id for row in db.query(Sentence.id).filter(Sentence.sampled == True).order_by(Sentence.id).all()]
        entity_types = db.query(EntityType).order_by(EntityType.id).all()
        total = len(sentence_ids) * len(entity_types)
        update_task(task_id, total=total, message="开始批量标注")

    progress = 0
    for sentence_id in sentence_ids:
        for entity_type in entity_types:
            flags = get_flags(task_id)
            if flags.get("cancel"):
                update_task(task_id, status="cancelled", message="标注已取消")
                return
            while flags.get("pause"):
                update_task(task_id, status="paused", message="标注已暂停")
                await asyncio.sleep(0.5)
            with SessionLocal() as db:
                sentence = db.get(Sentence, sentence_id)
                if sentence is None:
                    progress += 1
                    continue
                existing = (
                    db.query(LLMCall)
                    .filter(
                        LLMCall.sentence_id == sentence.id,
                        LLMCall.entity_type_tag == entity_type.tag,
                        LLMCall.is_negative == False,
                        LLMCall.status == "done",
                    )
                    .first()
                )
                if existing:
                    progress += 1
                    update_task(task_id, progress=progress, status="running", message="跳过已完成调用")
                    continue
                prompt_payload = PromptPreviewIn(sentence=sentence.text, type_tag=entity_type.tag, type_label=entity_type.label)
                messages = render_messages(template, db, prompt_payload)
                call = LLMCall(
                    sentence_id=sentence.id,
                    entity_type_tag=entity_type.tag,
                    is_negative=False,
                    request_json=json_dumps({"messages": messages}),
                    status="pending",
                )
                db.add(call)
                db.commit()
                db.refresh(call)

            result = await client.chat(messages)
            with SessionLocal() as db:
                call = db.get(LLMCall, call.id)
                sentence = db.get(Sentence, sentence_id)
                if call is None or sentence is None:
                    continue
                call.response_text = result.content
                if result.ok:
                    parsed = parse_llm_entities(result.content, sentence.text, entity_type.tag)
                    call.parsed_json = json.dumps(parsed, ensure_ascii=False)
                    call.status = "done"
                    for item in parsed:
                        exists = (
                            db.query(Annotation)
                            .filter(
                                Annotation.sentence_id == sentence.id,
                                Annotation.entity_type_tag == item["type"],
                                Annotation.start == item["start"],
                                Annotation.end == item["end"],
                                Annotation.status != "rejected",
                            )
                            .first()
                        )
                        if exists is None:
                            db.add(
                                Annotation(
                                    sentence_id=sentence.id,
                                    entity_type_tag=item["type"],
                                    start=item["start"],
                                    end=item["end"],
                                    text=item["text"],
                                    source="llm",
                                    score=item.get("score"),
                                    status="unconfirmed",
                                )
                            )
                    sentence.status = "llm_done"
                else:
                    call.status = "error"
                    call.error_msg = result.error_message
                db.commit()
            progress += 1
            update_task(task_id, progress=progress, total=total, status="running", message=f"已完成 {progress}/{total}")
    update_task(task_id, progress=progress, total=progress, status="done", message="批量标注完成")

