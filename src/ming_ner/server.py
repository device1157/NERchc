"""Stdlib HTTP server for the Ming NER review WebUI."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .annotations import (
    DEFAULT_SETTINGS,
    annotation_id,
    append_annotation,
    load_settings,
    read_annotations,
    save_settings,
    validate_annotation,
)
from .data_api import document_entries, list_data_files, load_selected_document
from .export import analyze_selection_payload
from .metrics import strict_entity_metrics


class ReviewServer(TCPServer):
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        workspace: Path,
        input_dir: Path,
        output_dir: Path,
    ):
        super().__init__(server_address, handler_class)
        self.workspace = workspace.resolve()
        self.input_dir = input_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.ui_dir = self.workspace / "ui"
        self.review_dir = self.output_dir / "review"
        self.annotations_path = self.review_dir / "annotations" / "reviewed.jsonl"
        self.settings_path = self.review_dir / "settings.json"


class ReviewRequestHandler(BaseHTTPRequestHandler):
    server: ReviewServer

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/data-files":
                self.write_json({"files": list_data_files(self.server.input_dir)})
            elif parsed.path == "/api/entries":
                params = parse_qs(parsed.query)
                file_name = self.required_param(params, "file")
                doc = load_selected_document(self.server.input_dir, file_name)
                self.write_json({"file": file_name, "doc_id": doc.doc_id, "entries": document_entries(doc)})
            elif parsed.path == "/api/settings":
                self.write_json(load_settings(self.server.settings_path))
            elif parsed.path == "/api/metrics":
                self.write_json(self.current_metrics())
            elif parsed.path in {"/", "/ui", "/ui/"}:
                self.serve_file(self.server.ui_dir / "index.html")
            else:
                self.serve_static(parsed.path)
        except Exception as exc:
            self.write_error(exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self.read_json()
            if parsed.path == "/api/analyze":
                settings = load_settings(self.server.settings_path)
                threshold = float(body.get("weak_threshold") or settings["weak_threshold"])
                model_dir = body.get("model_dir")
                payload = analyze_selection_payload(
                    input_dir=self.server.input_dir,
                    output_dir=self.server.output_dir,
                    file_name=str(body["file"]),
                    start_entry=int(body["start_entry"]),
                    end_entry=int(body["end_entry"]),
                    model_dir=Path(model_dir) if model_dir else None,
                    weak_threshold=threshold,
                    offline=bool(body.get("offline", True)),
                    link_limit=int(body.get("link_limit", 25)),
                )
                self.write_json(payload)
            elif parsed.path == "/api/annotations":
                selection = body.get("selection") or {}
                file_name = str(selection.get("file") or body.get("file") or "")
                entry_start = int(selection.get("entry_start") or body.get("entry_start") or 1)
                entry_end = int(selection.get("entry_end") or body.get("entry_end") or entry_start)
                record = {
                    "id": body.get("id") or annotation_id(file_name, entry_start, entry_end),
                    "doc_id": selection.get("doc_id") or body.get("doc_id") or "",
                    "file": file_name,
                    "entry_start": entry_start,
                    "entry_end": entry_end,
                    "text": body["text"],
                    "entities": body.get("entities", []),
                    "weak_threshold": float(body.get("weak_threshold") or DEFAULT_SETTINGS["weak_threshold"]),
                }
                saved = append_annotation(self.server.annotations_path, record)
                self.write_json({"saved": saved, "metrics": self.current_metrics()})
            elif parsed.path == "/api/settings":
                self.write_json(save_settings(self.server.settings_path, body))
            else:
                self.write_response(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except Exception as exc:
            self.write_error(exc)

    @staticmethod
    def required_param(params: dict[str, list[str]], name: str) -> str:
        value = params.get(name, [""])[0]
        if not value:
            raise ValueError(f"Missing required query parameter: {name}")
        return value

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def write_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.write_response(status, data)

    def write_error(self, exc: Exception) -> None:
        self.write_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def write_response(self, status: HTTPStatus, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_static(self, request_path: str) -> None:
        if request_path.startswith("/ui/"):
            rel = unquote(request_path[len("/ui/") :])
            path = (self.server.ui_dir / rel).resolve()
            if self.server.ui_dir.resolve() not in path.parents and path != self.server.ui_dir.resolve():
                raise ValueError("Invalid static path")
            self.serve_file(path)
            return
        raise FileNotFoundError(request_path)

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND.value)
            return
        content = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def current_metrics(self) -> dict[str, Any]:
        settings = load_settings(self.server.settings_path)
        records = read_annotations(self.server.annotations_path)
        gold = [validate_annotation(record) for record in records]
        metrics, _ = strict_entity_metrics(
            gold,
            gold,
            target_f1=float(settings["target_f1"]),
            min_reviewed_segments=int(settings["min_reviewed_segments"]),
        )
        metrics["annotation_path"] = str(self.server.annotations_path)
        return metrics


def serve_review_app(workspace: Path, input_dir: Path, output_dir: Path, port: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    server = ReviewServer(
        ("127.0.0.1", port),
        ReviewRequestHandler,
        workspace=workspace,
        input_dir=input_dir,
        output_dir=output_dir,
    )
    print(f"Serving review UI at http://127.0.0.1:{port}/ui/")
    print(f"Data folder: {input_dir}")
    print(f"Review output: {output_dir / 'review'}")
    with server:
        server.serve_forever()
