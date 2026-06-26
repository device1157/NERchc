from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.artifacts import fetch_artifact, list_artifacts

router = APIRouter()


class FetchArtifactRequest(BaseModel):
    artifact_id: str
    force: bool = False


@router.get("/status")
def artifact_status() -> dict[str, Any]:
    return {"items": list_artifacts()}


@router.post("/fetch")
def artifact_fetch(payload: FetchArtifactRequest) -> dict[str, Any]:
    try:
        return fetch_artifact(payload.artifact_id, payload.force)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
