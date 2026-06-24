from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import EntityType, PromptTemplate, get_db, json_loads, row_to_dict
from ..models import PromptIn, PromptPreviewIn
from ..services.llm_client import LLMClient
from ..services.ner_parse import parse_llm_entities
from ..settings_store import load_llm_settings

router = APIRouter(tags=["prompt"])


def render_schema(db: Session) -> str:
    lines = []
    for row in db.query(EntityType).order_by(EntityType.id).all():
        pos = "、".join(json_loads(row.positive_examples, []))
        neg = "、".join(json_loads(row.negative_examples, []))
        lines.append(f"- {row.tag}（{row.label}）：{row.definition}\n  边界规则：{row.rules}\n  正例：{pos}\n  反例：{neg}")
    return "\n".join(lines)


def render_messages(template: PromptTemplate, db: Session, payload: PromptPreviewIn) -> list[dict[str, str]]:
    entity_type = db.query(EntityType).filter(EntityType.tag == payload.type_tag).first()
    type_label = payload.type_label or (entity_type.label if entity_type else payload.type_tag)
    schema = render_schema(db)
    system_prompt = template.system_prompt.replace("{schema}", schema)
    user = template.user_template.format(
        sentence=payload.sentence,
        type_label=type_label,
        type_tag=payload.type_tag,
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}]


@router.get("/prompts")
def list_prompts(db: Session = Depends(get_db)):
    return [row_to_dict(row) for row in db.query(PromptTemplate).order_by(PromptTemplate.id).all()]


@router.post("/prompts")
def create_prompt(payload: PromptIn, db: Session = Depends(get_db)):
    if payload.is_active:
        db.query(PromptTemplate).update({PromptTemplate.is_active: False})
    row = PromptTemplate(project_id=1, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row_to_dict(row)


@router.put("/prompts/{prompt_id}")
def update_prompt(prompt_id: int, payload: PromptIn, db: Session = Depends(get_db)):
    row = db.get(PromptTemplate, prompt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="prompt not found")
    if payload.is_active:
        db.query(PromptTemplate).update({PromptTemplate.is_active: False})
    row.name = payload.name
    row.system_prompt = payload.system_prompt
    row.user_template = payload.user_template
    row.is_active = payload.is_active
    db.commit()
    return row_to_dict(row)


@router.delete("/prompts/{prompt_id}")
def delete_prompt(prompt_id: int, db: Session = Depends(get_db)):
    row = db.get(PromptTemplate, prompt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="prompt not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/prompts/sync-schema")
def sync_schema(db: Session = Depends(get_db)):
    template = db.query(PromptTemplate).filter(PromptTemplate.is_active == True).first()
    if template is None:
        raise HTTPException(status_code=404, detail="active prompt not found")
    schema = render_schema(db)
    if "{schema}" in template.system_prompt:
        rendered = template.system_prompt.replace("{schema}", schema)
    else:
        rendered = template.system_prompt + "\n\n实体定义：\n" + schema
    return {"system_prompt": rendered}


@router.post("/prompts/preview")
def preview_prompt(payload: PromptPreviewIn, db: Session = Depends(get_db)):
    template = db.query(PromptTemplate).filter(PromptTemplate.is_active == True).first()
    if template is None:
        raise HTTPException(status_code=404, detail="active prompt not found")
    return {"messages": render_messages(template, db, payload)}


@router.post("/prompts/dry-run")
async def dry_run_prompt(payload: PromptPreviewIn, db: Session = Depends(get_db)):
    template = db.query(PromptTemplate).filter(PromptTemplate.is_active == True).first()
    if template is None:
        raise HTTPException(status_code=404, detail="active prompt not found")
    messages = render_messages(template, db, payload)
    result = await LLMClient(load_llm_settings(mask_key=False)).chat(messages)
    parsed = parse_llm_entities(result.content, payload.sentence, payload.type_tag) if result.ok else []
    return {"llm": result.__dict__, "parsed": parsed, "messages": messages}

