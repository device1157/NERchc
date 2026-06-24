from __future__ import annotations

from fastapi import APIRouter

from ..models import LLMSettingsIn
from ..services.llm_client import LLMClient
from ..settings_store import load_llm_settings, save_llm_settings

router = APIRouter(tags=["settings"])


@router.get("/settings/llm")
def get_llm_settings():
    return load_llm_settings(mask_key=True)


@router.post("/settings/llm")
def post_llm_settings(payload: LLMSettingsIn):
    return save_llm_settings(payload.model_dump())


@router.post("/settings/llm/test")
async def test_llm_settings(payload: LLMSettingsIn | None = None):
    settings = load_llm_settings(mask_key=False)
    if payload is not None:
        incoming = {k: v for k, v in payload.model_dump().items() if v is not None}
        if incoming.get("api_key") == "":
            incoming.pop("api_key", None)
        settings.update(incoming)
    result = await LLMClient(settings).test()
    return result.__dict__

