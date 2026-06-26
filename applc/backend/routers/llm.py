from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import db, utc_now

router = APIRouter()

DEFAULT_PROMPT = """請以歷史研究助理的角度分析所選時間軸節點。
請完成：
1. 用繁體中文概括史料內容。
2. 說明所選事件或實體在文本中的角色。
3. 提取可用於論文章節或資料庫標註的關鍵資訊。
4. 如文本證據不足，請清楚指出不確定處。"""

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
            {"role": "user", "content": "請只回覆 OK。"},
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
            {"role": "system", "content": "你是一位熟悉明實錄與中國古代史料的研究助理。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=900,
        temperature=0.2,
    )
    return {
        "timeline_id": context["timeline_id"],
        "target": target,
        "summary": _extract_message(result),
        "usage": result.get("usage"),
    }


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
        raise HTTPException(status_code=400, detail="請先在「設定」填寫 API Key。")
    if not settings.get("model"):
        raise HTTPException(status_code=400, detail="請先在「設定」填寫模型名稱。")


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


def _load_timeline_context(conn: Any, timeline_id: str) -> dict[str, Any]:
    event_id = _timeline_id_to_event_id(timeline_id)
    row = conn.execute(
        """
        SELECT ep.id AS event_id, ep.document_id, ep.event_type, ep.probability, ep.source,
               d.volume, d.seq, d.raw_text
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
    context["entities"] = [dict(item) for item in entities]
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
    entity_text = "、".join(
        f"{entity['text']}({entity['entity_type']})" for entity in context["entities"]
    ) or "無"
    date_text = "、".join(
        f"{date['text']}{f' / CE {date['ce_year']}' if date['ce_year'] else ''}" for date in context["dates"]
    ) or "無"
    variables = {
        "timeline_id": context["timeline_id"],
        "document_id": context["document_id"],
        "event_id": context["event_id"],
        "target_kind": target["kind"],
        "target_value": target["value"],
        "event_type": context["event_type"],
        "probability": context["probability"],
        "volume": context.get("volume") or "未分卷",
        "seq": context.get("seq"),
        "ce_year": context.get("ce_year") or "未定年",
        "historical_dates": date_text,
        "entities": entity_text,
        "text": context["raw_text"],
    }
    context_text = "\n".join(
        [
            f"時間軸ID：{variables['timeline_id']}",
            f"分析對象：{variables['target_kind']} / {variables['target_value']}",
            f"事件類型：{variables['event_type']}（P={variables['probability']}）",
            f"卷次：{variables['volume']}，段落序號：{variables['seq']}",
            f"年份/日期：{variables['historical_dates']}",
            f"相關實體：{variables['entities']}",
            f"原文：{variables['text']}",
        ]
    )
    try:
        instruction = template.format_map(_SafeFormatDict(variables))
    except ValueError:
        instruction = template
    return f"{instruction}\n\n【分析資料】\n{context_text}"


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
