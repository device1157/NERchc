from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.classifier import run_classification
from backend.services.clustering import run_clustering
from backend.services.embedding import run_embeddings
from backend.services.linker import run_entity_linking
from backend.services.ner import run_ner
from backend.services.pipeline import run_step
from backend.services.time_extractor import run_time_extraction

router = APIRouter()


class ClusterRequest(BaseModel):
    k: int | None = None


class ClassifyRequest(BaseModel):
    threshold: float = 0.2


@router.post("/time")
def time_step() -> dict[str, Any]:
    return run_step("time", run_time_extraction)


@router.post("/ner")
def ner_step() -> dict[str, Any]:
    return run_step("ner", run_ner)


@router.post("/link")
def link_step() -> dict[str, Any]:
    return run_step("link", run_entity_linking)


@router.post("/embed")
def embed_step() -> dict[str, Any]:
    return run_step("embed", run_embeddings)


@router.post("/cluster")
def cluster_step(payload: ClusterRequest | None = None) -> dict[str, Any]:
    k = payload.k if payload else None
    return run_step("cluster", lambda: run_clustering(k))


@router.post("/classify")
def classify_step(payload: ClassifyRequest | None = None) -> dict[str, Any]:
    threshold = payload.threshold if payload else 0.2
    return run_step("classify", lambda: run_classification(threshold))


@router.post("/all")
def all_steps() -> dict[str, Any]:
    results = [
        time_step(),
        ner_step(),
        link_step(),
        embed_step(),
        cluster_step(),
        classify_step(),
    ]
    return {"steps": results}
