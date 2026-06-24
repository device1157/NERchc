"""Data-file and entry selection helpers for the WebUI/API."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .preprocess import load_document
from .schema import Document


ENTRY_START_RE = re.compile(r"(?m)^(?:○|卷之?[一二三四五六七八九十百千万〇零\d]+)")


def safe_data_file(input_dir: Path, file_name: str) -> Path:
    """Resolve a user-selected data file without allowing path traversal."""

    root = input_dir.resolve()
    path = (root / file_name).resolve()
    if root != path.parent or path.suffix.lower() != ".txt" or not path.exists():
        for candidate in sorted(root.glob("*.txt")):
            if candidate.stem == file_name:
                return candidate.resolve()
        raise ValueError(f"Invalid data file: {file_name}")
    return path


def list_data_files(input_dir: Path) -> list[dict[str, Any]]:
    files = []
    for path in sorted(input_dir.glob("*.txt")):
        files.append(
            {
                "name": path.name,
                "doc_id": path.stem,
                "size": path.stat().st_size,
            }
        )
    return files


def document_entries(doc: Document, preview_chars: int = 80) -> list[dict[str, Any]]:
    """Split cleaned document text into entry metadata with stable offsets."""

    starts = [match.start() for match in ENTRY_START_RE.finditer(doc.text)]
    if not starts or starts[0] != 0:
        starts.insert(0, 0)
    entries: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(doc.text)
        chunk = doc.text[start:end].strip()
        if not chunk:
            continue
        preview = " ".join(chunk.split())[:preview_chars]
        entries.append(
            {
                "entry_id": len(entries) + 1,
                "start": start,
                "end": end,
                "preview": preview,
            }
        )
    return entries


def load_selected_document(input_dir: Path, file_name: str) -> Document:
    return load_document(safe_data_file(input_dir, file_name), sample_chars=None)


def slice_document_by_entries(
    doc: Document,
    start_entry: int,
    end_entry: int,
) -> tuple[Document, dict[str, Any]]:
    entries = document_entries(doc)
    if not entries:
        raise ValueError("No entries found in selected document")
    start_entry = max(1, int(start_entry))
    end_entry = min(len(entries), int(end_entry))
    if start_entry > end_entry:
        raise ValueError("start_entry must be <= end_entry")

    start = entries[start_entry - 1]["start"]
    end = entries[end_entry - 1]["end"]
    selected = Document(
        doc_id=doc.doc_id,
        title=f"{doc.title} entries {start_entry}-{end_entry}",
        source_path=doc.source_path,
        text=doc.text[start:end],
    )
    meta = {
        "file": Path(doc.source_path).name,
        "doc_id": doc.doc_id,
        "entry_start": start_entry,
        "entry_end": end_entry,
        "source_start": start,
        "source_end": end,
        "entry_count": len(entries),
    }
    return selected, meta
