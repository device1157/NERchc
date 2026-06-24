from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SECRETS_PATH = ROOT_DIR / "config" / "secrets.json"

DEFAULT_LLM_SETTINGS: dict[str, Any] = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model_name": "gpt-4o",
    "temperature": 0,
    "max_tokens": 800,
    "timeout_seconds": 60,
    "concurrency": 2,
    "rps": 1,
}


def _mask_key(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return value[:2] + "****"
    return f"{value[:3]}****{value[-4:]}"


def load_llm_settings(mask_key: bool = False) -> dict[str, Any]:
    settings = dict(DEFAULT_LLM_SETTINGS)
    if SECRETS_PATH.exists():
        try:
            settings.update(json.loads(SECRETS_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    if mask_key:
        settings["api_key"] = _mask_key(settings.get("api_key"))
        settings["has_api_key"] = bool(load_llm_settings(mask_key=False).get("api_key"))
    return settings


def save_llm_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_llm_settings(mask_key=False)
    incoming = {k: v for k, v in payload.items() if v is not None}
    if incoming.get("api_key") in {"", None}:
        incoming.pop("api_key", None)
    current.update(incoming)
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_llm_settings(mask_key=True)

