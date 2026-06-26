from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import ROOT_DIR, db, json_dumps, rows_to_dicts, utc_now
from backend.services.citations import format_citation
from backend.services.entity_display import entity_display_text

router = APIRouter()

DEFAULT_PROMPT = """你是明實錄研究助手。請根據下列時間軸節點，整理：
1. 事件性質與可能分類
2. 相關人物、地點、官職
3. 此段資料對研究問題的意義
4. 仍需人工核對的地方
"""

DEFAULT_SETTINGS = {
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "prompt_template": DEFAULT_PROMPT,
}


class LlmSettingsUpdate(BaseModel):
    base_url: str = Field(default=DEFAULT_SETTINGS["base_url"])
    model: str = Field(default=DEFAULT_SETTINGS["model"])
    api_key: str | None = None
    clear_api_key: bool = False
    prompt_template: str = Field(default=DEFAULT_PROMPT)


class LlmTestRequest(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


class AnalyzeRequest(BaseModel):
    timeline_id: str
    target_kind: str = "event"
    target_value: str
    entity_id: int | None = None


class ChatRequest(BaseModel):
    timeline_id: str
    message: str = Field(min_length=1)


class MarkdownExportRequest(BaseModel):
    timeline_id: str


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    with db() as conn:
        settings = _load_settings(conn)
    return _public_settings(settings)


@router.put("/settings")
def save_settings(payload: LlmSettingsUpdate) -> dict[str, Any]:
    base_url = _normalize_base_url(payload.base_url)
    model = payload.model.strip()
    prompt_template = payload.prompt_template.strip() or DEFAULT_PROMPT
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required.")
    with db() as conn:
        existing = _load_settings(conn)
        next_settings = {
            **existing,
            "base_url": base_url,
            "model": model,
            "prompt_template": prompt_template,
        }
        if payload.clear_api_key:
            next_settings["api_key"] = ""
        elif payload.api_key and payload.api_key.strip():
            next_settings["api_key"] = payload.api_key.strip()
        _save_settings(conn, next_settings)
    return _public_settings(next_settings)


@router.post("/test")
def test_connection(payload: LlmTestRequest | None = None) -> dict[str, Any]:
    with db() as conn:
        settings = _load_settings(conn)
    if payload:
        if payload.base_url:
            settings["base_url"] = _normalize_base_url(payload.base_url)
        if payload.model:
            settings["model"] = payload.model.strip()
        if payload.api_key:
            settings["api_key"] = payload.api_key.strip()
    _require_llm_settings(settings)
    result = _chat_completion(
        settings,
        [
            {"role": "system", "content": "You test whether an OpenAI-compatible API is reachable."},
            {"role": "user", "content": "Reply OK."},
        ],
        max_tokens=16,
        temperature=0,
    )
    return {
        "ok": True,
        "model": settings["model"],
        "endpoint": result.get("_endpoint"),
        "message": _extract_message(result) or "OK",
    }


@router.post("/analyze")
def analyze_timeline_node(payload: AnalyzeRequest) -> dict[str, Any]:
    with db() as conn:
        settings = _load_settings(conn)
        context = _load_timeline_context(conn, payload.timeline_id)
    _require_llm_settings(settings)
    target = _resolve_target(context, payload)
    prompt = _build_analysis_prompt(settings["prompt_template"], context, target)
    result = _chat_completion(
        settings,
        [
            {"role": "system", "content": "你是明實錄與中國歷史資料研究助手。請根據證據回答，不要捏造。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=900,
        temperature=0.2,
    )
    summary = _extract_message(result)
    with db() as conn:
        _save_analysis_result(conn, context, target, settings, prompt, summary, result.get("usage"))
    return {
        "timeline_id": context["timeline_id"],
        "target": target,
        "summary": summary,
        "usage": result.get("usage"),
    }


@router.get("/results")
def list_analysis_results(
    timeline_id: str | None = None,
    document_id: int | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if timeline_id:
        conditions.append("timeline_id = ?")
        params.append(timeline_id)
    if document_id is not None:
        conditions.append("document_id = ?")
        params.append(document_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM ai_analysis_results
            {where}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return {"items": rows_to_dicts(rows)}


@router.post("/chat")
def chat_about_timeline(payload: ChatRequest) -> dict[str, Any]:
    with db() as conn:
        settings = _load_settings(conn)
        context = _load_timeline_context(conn, payload.timeline_id)
        analyses = _load_analysis_rows(conn, context["timeline_id"])
        history = _load_chat_rows(conn, context["timeline_id"])
    _require_llm_settings(settings)
    messages = _build_chat_messages(context, analyses, history, payload.message)
    result = _chat_completion(settings, messages, max_tokens=900, temperature=0.2)
    answer = _extract_message(result)
    with db() as conn:
        _save_chat_message(conn, context, "user", payload.message, settings["model"], None)
        _save_chat_message(conn, context, "assistant", answer, settings["model"], result.get("usage"))
        saved = _load_chat_rows(conn, context["timeline_id"])
    return {
        "timeline_id": context["timeline_id"],
        "message": payload.message,
        "answer": answer,
        "saved_messages": saved,
    }


@router.post("/export-markdown")
def export_timeline_markdown(payload: MarkdownExportRequest) -> dict[str, Any]:
    with db() as conn:
        context = _load_timeline_context(conn, payload.timeline_id)
        analyses = _load_analysis_rows(conn, context["timeline_id"])
        history = _load_chat_rows(conn, context["timeline_id"])
    out_dir = ROOT_DIR / "Aimd"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{context['timeline_id']}_{timestamp}.md"
    path = out_dir / filename
    path.write_text(_markdown_content(context, analyses, history), encoding="utf-8")
    return {"timeline_id": context["timeline_id"], "path": str(path), "filename": filename}


def _load_settings(conn: Any) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    settings = {**DEFAULT_SETTINGS, "api_key": ""}
    settings.update({row["key"]: row["value"] for row in rows})
    return settings


def _save_settings(conn: Any, settings: dict[str, str]) -> None:
    now = utc_now()
    rows = [(key, value, now) for key, value in settings.items()]
    conn.executemany(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        rows,
    )


def _public_settings(settings: dict[str, str]) -> dict[str, Any]:
    api_key = settings.get("api_key", "")
    return {
        "base_url": settings.get("base_url", DEFAULT_SETTINGS["base_url"]),
        "model": settings.get("model", DEFAULT_SETTINGS["model"]),
        "prompt_template": settings.get("prompt_template", DEFAULT_PROMPT),
        "has_api_key": bool(api_key),
        "api_key_preview": f"...{api_key[-4:]}" if api_key else "",
    }


def _normalize_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise HTTPException(status_code=400, detail="API base link is required.")
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        raise HTTPException(status_code=400, detail="API base link must start with http:// or https://.")
    return value


def _require_llm_settings(settings: dict[str, str]) -> None:
    if not settings.get("api_key"):
        raise HTTPException(status_code=400, detail="請先在設定頁輸入 LLM API Key。")
    if not settings.get("model"):
        raise HTTPException(status_code=400, detail="請先在設定頁輸入模型名稱。")


def _chat_completion(
    settings: dict[str, str],
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": settings["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    errors: list[str] = []
    urls = _chat_completions_urls(settings["base_url"])
    for index, url in enumerate(urls):
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {settings['api_key']}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
                if isinstance(result, dict):
                    result["_endpoint"] = url
                return result
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            errors.append(f"{url} -> HTTP {exc.code}: {_compact_error(detail)}")
            if exc.code in {404, 405} and index < len(urls) - 1:
                continue
            raise HTTPException(status_code=502, detail=_format_llm_error(errors)) from exc
        except urllib.error.URLError as exc:
            errors.append(f"{url} -> connection failed: {exc.reason}")
            if index < len(urls) - 1:
                continue
            raise HTTPException(status_code=502, detail=_format_llm_error(errors)) from exc
        except TimeoutError as exc:
            errors.append(f"{url} -> timed out")
            if index < len(urls) - 1:
                continue
            raise HTTPException(status_code=504, detail=_format_llm_error(errors)) from exc
        except json.JSONDecodeError as exc:
            errors.append(f"{url} -> response is not valid JSON")
            raise HTTPException(status_code=502, detail=_format_llm_error(errors)) from exc
    raise HTTPException(status_code=502, detail=_format_llm_error(errors))


def _chat_completions_urls(base_url: str) -> list[str]:
    value = base_url.rstrip("/")
    if value.endswith("/chat/completions"):
        return [value]
    if re.search(r"/v\d+$", value):
        return [f"{value}/chat/completions"]
    return [f"{value}/v1/chat/completions", f"{value}/chat/completions"]


def _format_llm_error(errors: list[str]) -> str:
    if not errors:
        return "Cannot connect to LLM API."
    return "Cannot connect to LLM API. Tried: " + " | ".join(errors)


def _compact_error(detail: str) -> str:
    try:
        payload = json.loads(detail)
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)
            return str(payload.get("message") or payload)
    except json.JSONDecodeError:
        pass
    return detail[:500]


def _extract_message(result: dict[str, Any]) -> str:
    choices = result.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    text = choices[0].get("text")
    return text.strip() if isinstance(text, str) else ""


def _save_analysis_result(
    conn: Any,
    context: dict[str, Any],
    target: dict[str, Any],
    settings: dict[str, str],
    prompt: str,
    summary: str,
    usage: Any,
) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO ai_analysis_results
        (timeline_id, event_id, document_id, target_kind, target_value, entity_id,
         model, prompt, summary, usage_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            context["timeline_id"],
            context["event_id"],
            context["document_id"],
            target["kind"],
            target["value"],
            target.get("entity_id"),
            settings["model"],
            prompt,
            summary,
            json_dumps(usage or {}),
            now,
            now,
        ),
    )


def _save_chat_message(
    conn: Any,
    context: dict[str, Any],
    role: str,
    content: str,
    model: str | None,
    usage: Any,
) -> None:
    conn.execute(
        """
        INSERT INTO ai_chat_messages
        (timeline_id, event_id, document_id, role, content, model, usage_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            context["timeline_id"],
            context["event_id"],
            context["document_id"],
            role,
            content,
            model,
            json_dumps(usage or {}),
            utc_now(),
        ),
    )


def _load_analysis_rows(conn: Any, timeline_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, target_kind, target_value, model, summary, created_at, updated_at
        FROM ai_analysis_results
        WHERE timeline_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (timeline_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def _load_chat_rows(conn: Any, timeline_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, role, content, model, usage_json, created_at
        FROM ai_chat_messages
        WHERE timeline_id = ?
        ORDER BY id
        """,
        (timeline_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def _build_chat_messages(
    context: dict[str, Any],
    analyses: list[dict[str, Any]],
    history: list[dict[str, Any]],
    user_message: str,
) -> list[dict[str, str]]:
    summary_text = "\n\n".join(item["summary"] for item in analyses[:3]) or "尚未有 AI 總結。"
    context_text = _plain_context_text(context)
    messages = [
        {
            "role": "system",
            "content": "你是明實錄研究助手。請只根據提供的時間軸節點、既有總結與對話紀錄回答；若資料不足，請明確說明。",
        },
        {
            "role": "user",
            "content": f"時間軸節點資料：\n{context_text}\n\n既有 AI 總結：\n{summary_text}",
        },
    ]
    for item in history[-12:]:
        role = item["role"] if item["role"] in {"user", "assistant"} else "user"
        messages.append({"role": role, "content": item["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def _markdown_content(context: dict[str, Any], analyses: list[dict[str, Any]], history: list[dict[str, Any]]) -> str:
    lines = [
        f"# AI 總結：{context['timeline_id']}",
        "",
        f"- Timeline ID: {context['timeline_id']}",
        f"- Document ID: {context['document_id']}",
        f"- Event: {context['event_type']}",
        f"- Probability: {context['probability']}",
        f"- Citation: {format_citation(context, context.get('ce_year'))}",
        f"- CE Year: {context.get('ce_year') or '未知'}",
        "",
        "## 原文",
        "",
        context["raw_text"],
        "",
        "## 日期",
        "",
    ]
    lines.extend(f"- {date['text']} / CE {date.get('ce_year') or '未知'}" for date in context["dates"])
    lines.extend(["", "## 實體", ""])
    lines.extend(f"- {entity_display_text(entity['text'], entity['entity_type'])} ({entity['entity_type']})" for entity in context["entities"])
    lines.extend(["", "## AI 總結", ""])
    if analyses:
        for item in analyses:
            lines.extend([f"### {item['target_kind']} / {item['target_value']}", "", item["summary"], ""])
    else:
        lines.extend(["尚未有 AI 總結。", ""])
    lines.extend(["## 後續追問", ""])
    if history:
        for item in history:
            speaker = "使用者" if item["role"] == "user" else "AI"
            lines.extend([f"### {speaker} ({item['created_at']})", "", item["content"], ""])
    else:
        lines.extend(["尚未有追問紀錄。", ""])
    return "\n".join(lines)


def _plain_context_text(context: dict[str, Any]) -> str:
    entity_text = "、".join(entity_display_text(entity["text"], entity["entity_type"]) for entity in context["entities"]) or "無"
    date_text = "、".join(f"{date['text']} / CE {date.get('ce_year') or '未知'}" for date in context["dates"]) or "無"
    return "\n".join(
        [
            f"Timeline ID: {context['timeline_id']}",
            f"Event: {context['event_type']}",
            f"Probability: {context['probability']}",
            f"Volume/Seq: {context.get('volume') or '未知'} / {context.get('seq')}",
            f"Dates: {date_text}",
            f"Entities: {entity_text}",
            f"Text: {context['raw_text']}",
        ]
    )


def _load_timeline_context(conn: Any, timeline_id: str) -> dict[str, Any]:
    event_id = _timeline_id_to_event_id(timeline_id)
    row = conn.execute(
        """
        SELECT ep.id AS event_id, ep.document_id, ep.event_type, ep.probability, ep.source,
               d.source_name, d.volume, d.seq, d.raw_text
        FROM event_predictions ep
        JOIN documents d ON d.id = ep.document_id
        WHERE ep.id = ?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Timeline node was not found.")
    context = dict(row)
    dates = conn.execute(
        """
        SELECT id, text, ce_year, reign, ganzhi, lunar_month, lunar_day, confidence
        FROM time_mentions
        WHERE document_id = ?
        ORDER BY start, id
        """,
        (context["document_id"],),
    ).fetchall()
    entities = conn.execute(
        """
        SELECT e.id, e.text, e.entity_type, e.start, e.end, e.confidence,
               l.canonical_id, l.canonical_text
        FROM entities e
        LEFT JOIN entity_links l ON l.entity_id = e.id
        WHERE e.document_id = ?
        ORDER BY e.start, e.id
        """,
        (context["document_id"],),
    ).fetchall()
    context["timeline_id"] = _format_timeline_id(context["event_id"])
    context["dates"] = [dict(item) for item in dates]
    context["entities"] = [
        {**dict(item), "display_text": entity_display_text(item["text"], item["entity_type"])}
        for item in entities
    ]
    context["ce_year"] = next((item["ce_year"] for item in context["dates"] if item["ce_year"] is not None), None)
    return context


def _timeline_id_to_event_id(timeline_id: str) -> int:
    match = re.match(r"^T?0*(\d+)$", timeline_id.strip(), flags=re.IGNORECASE)
    if not match:
        raise HTTPException(status_code=400, detail="Timeline ID must look like T0001.")
    return int(match.group(1))


def _format_timeline_id(event_id: int) -> str:
    return f"T{event_id:04d}"


def _resolve_target(context: dict[str, Any], payload: AnalyzeRequest) -> dict[str, Any]:
    kind = payload.target_kind if payload.target_kind in {"event", "entity"} else "event"
    if kind == "entity" and payload.entity_id is not None:
        for entity in context["entities"]:
            if entity["id"] == payload.entity_id:
                return {
                    "kind": "entity",
                    "value": entity["text"],
                    "entity_id": entity["id"],
                    "entity_type": entity["entity_type"],
                }
    if kind == "entity":
        return {"kind": "entity", "value": payload.target_value, "entity_id": payload.entity_id}
    return {"kind": "event", "value": context["event_type"], "event_id": context["event_id"]}


def _build_analysis_prompt(template: str, context: dict[str, Any], target: dict[str, Any]) -> str:
    entity_text = "、".join(entity_display_text(entity["text"], entity["entity_type"]) for entity in context["entities"]) or "無"
    date_text = "、".join(
        f"{date['text']}{f' / CE {date['ce_year']}' if date['ce_year'] else ''}"
        for date in context["dates"]
    ) or "無"
    variables = {
        "timeline_id": context["timeline_id"],
        "document_id": context["document_id"],
        "event_id": context["event_id"],
        "target_kind": target["kind"],
        "target_value": target["value"],
        "event_type": context["event_type"],
        "probability": context["probability"],
        "volume": context.get("volume") or "未知",
        "seq": context.get("seq"),
        "ce_year": context.get("ce_year") or "未知",
        "historical_dates": date_text,
        "entities": entity_text,
        "text": context["raw_text"],
    }
    context_text = "\n".join(
        [
            f"Timeline ID: {variables['timeline_id']}",
            f"分析目標: {variables['target_kind']} / {variables['target_value']}",
            f"事件類型: {variables['event_type']} (p={variables['probability']})",
            f"卷/序號: {variables['volume']} / {variables['seq']}",
            f"日期: {variables['historical_dates']}",
            f"實體: {variables['entities']}",
            f"原文: {variables['text']}",
        ]
    )
    try:
        instruction = template.format_map(_SafeFormatDict(variables))
    except ValueError:
        instruction = template
    return f"{instruction}\n\n節點資料：\n{context_text}"


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
