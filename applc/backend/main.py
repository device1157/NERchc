from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.db import ROOT_DIR, init_db
from backend.routers import analytics, corpus, exports, llm, pipeline, resources, runs, search

FRONTEND_DIR = ROOT_DIR / "frontend"


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="Ming Shilu Historical Event Platform", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(corpus.router, prefix="/api/corpus", tags=["corpus"])
    app.include_router(resources.router, prefix="/api/resources", tags=["resources"])
    app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
    app.include_router(exports.router, prefix="/api/exports", tags=["exports"])
    app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
    app.include_router(llm.router, prefix="/api/llm", tags=["llm"])

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
