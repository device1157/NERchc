from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .db import init_db
from .routers import annotate, corpus, dataset, prompt, results, review, schema, settings, tasks, train

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="明实录目标蒸馏 NER 工作台", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(settings.router, prefix="/api")
    app.include_router(corpus.router, prefix="/api")
    app.include_router(schema.router, prefix="/api")
    app.include_router(prompt.router, prefix="/api")
    app.include_router(annotate.router, prefix="/api")
    app.include_router(review.router, prefix="/api")
    app.include_router(dataset.router, prefix="/api")
    app.include_router(train.router, prefix="/api")
    app.include_router(results.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app


app = create_app()

