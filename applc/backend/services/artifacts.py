from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from backend.db import DATA_DIR, db, json_dumps, utc_now


ARTIFACTS: dict[str, dict[str, str]] = {
    "text2vec-base-chinese": {
        "kind": "embedding_model",
        "source_url": "https://huggingface.co/shibing624/text2vec-base-chinese",
        "local_path": "models/text2vec-base-chinese",
        "license_note": "Hugging Face model card should be reviewed before redistribution.",
    },
    "ckip-bert-base-chinese-ner": {
        "kind": "ner_model",
        "source_url": "https://huggingface.co/ckiplab/bert-base-chinese-ner",
        "local_path": "models/ckip-bert-base-chinese-ner",
        "license_note": "GPL-3.0 model; do not bundle into redistributed closed packages.",
    },
    "cbdb-api-cache": {
        "kind": "external_dataset",
        "source_url": "https://projects.iq.harvard.edu/cbdb",
        "local_path": "imports/cbdb",
        "license_note": "Use the official API and cache responses locally for reproducibility.",
    },
    "chgis-v6": {
        "kind": "external_dataset",
        "source_url": "https://chgis.fas.harvard.edu/data/chgis",
        "local_path": "imports/chgis-v6",
        "license_note": "CHGIS has non-commercial/reuse restrictions; download locally only.",
    },
}


def artifact_path(artifact_id: str) -> Path:
    spec = ARTIFACTS[artifact_id]
    return DATA_DIR / spec["local_path"]


def list_artifacts() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM model_artifacts ORDER BY artifact_id").fetchall()
        by_id = {row["artifact_id"]: dict(row) for row in rows}
    items = []
    for artifact_id, spec in ARTIFACTS.items():
        path = DATA_DIR / spec["local_path"]
        row = by_id.get(artifact_id, {})
        has_local_files = _has_artifact_payload(path)
        status = row.get("status") or ("ready" if has_local_files else "missing")
        items.append(
            {
                "artifact_id": artifact_id,
                "kind": spec["kind"],
                "source_url": spec["source_url"],
                "local_path": str(path),
                "status": status,
                "license_note": spec["license_note"],
                "metadata": _load_metadata(row.get("metadata_json")),
                "updated_at": row.get("updated_at"),
            }
        )
    return items


def fetch_artifact(artifact_id: str, force: bool = False) -> dict[str, Any]:
    if artifact_id not in ARTIFACTS:
        raise ValueError(f"Unknown artifact: {artifact_id}")
    spec = ARTIFACTS[artifact_id]
    path = DATA_DIR / spec["local_path"]
    path.mkdir(parents=True, exist_ok=True)
    if _has_artifact_payload(path) and not force:
        _record_artifact(artifact_id, spec, path, "ready", {"message": "Already available locally."})
        return _artifact_result(artifact_id, spec, path, "ready", "Already available locally.")

    if artifact_id in {"text2vec-base-chinese", "ckip-bert-base-chinese-ner"}:
        result = _fetch_huggingface_snapshot(artifact_id, spec, path, force)
    else:
        result = _prepare_manual_dataset_cache(artifact_id, spec, path)
    _record_artifact(artifact_id, spec, path, result["status"], result["metadata"])
    return result


def _fetch_huggingface_snapshot(artifact_id: str, spec: dict[str, str], path: Path, force: bool) -> dict[str, Any]:
    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except Exception:
        marker = path / "README_FETCH.md"
        marker.write_text(_manual_fetch_text(artifact_id, spec), encoding="utf-8")
        return _artifact_result(
            artifact_id,
            spec,
            path,
            "needs_dependency",
            "Install huggingface_hub or sentence-transformers, then retry fetch.",
        )

    repo_id = spec["source_url"].removeprefix("https://huggingface.co/")
    if force and path.exists():
        shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(repo_id=repo_id, local_dir=str(path), local_dir_use_symlinks=False)
        return _artifact_result(artifact_id, spec, path, "ready", "Snapshot downloaded.")
    except Exception as exc:
        marker = path / "README_FETCH.md"
        marker.write_text(_manual_fetch_text(artifact_id, spec), encoding="utf-8")
        return _artifact_result(artifact_id, spec, path, "error", f"Fetch failed: {exc}")


def _prepare_manual_dataset_cache(artifact_id: str, spec: dict[str, str], path: Path) -> dict[str, Any]:
    marker = path / "README_FETCH.md"
    marker.write_text(_manual_fetch_text(artifact_id, spec), encoding="utf-8")
    return _artifact_result(
        artifact_id,
        spec,
        path,
        "manual_required",
        "Dataset cache folder prepared; download/import must follow the official source terms.",
    )


def _manual_fetch_text(artifact_id: str, spec: dict[str, str]) -> str:
    return "\n".join(
        [
            f"# {artifact_id}",
            "",
            f"Source: {spec['source_url']}",
            f"License note: {spec['license_note']}",
            "",
            "This folder is intentionally ignored by git. Keep downloaded research artifacts local.",
            "",
        ]
    )


def _record_artifact(
    artifact_id: str,
    spec: dict[str, str],
    path: Path,
    status: str,
    metadata: dict[str, Any],
) -> None:
    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO model_artifacts
            (artifact_id, kind, source_url, local_path, status, license_note, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
              kind=excluded.kind,
              source_url=excluded.source_url,
              local_path=excluded.local_path,
              status=excluded.status,
              license_note=excluded.license_note,
              metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at
            """,
            (
                artifact_id,
                spec["kind"],
                spec["source_url"],
                str(path),
                status,
                spec["license_note"],
                json_dumps(metadata),
                now,
                now,
            ),
        )


def _artifact_result(
    artifact_id: str,
    spec: dict[str, str],
    path: Path,
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "kind": spec["kind"],
        "source_url": spec["source_url"],
        "local_path": str(path),
        "status": status,
        "license_note": spec["license_note"],
        "message": message,
        "metadata": {"message": message},
    }


def _load_metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _has_artifact_payload(path: Path) -> bool:
    if not path.is_dir():
        return False
    files = [item for item in path.iterdir() if item.name != "README_FETCH.md"]
    return bool(files)
