"""Export pipeline results to UI-ready JSON."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from .annotations import DEFAULT_SETTINGS
from .data_api import load_selected_document, slice_document_by_entries
from .extract import EntityExtractor
from .gazetteer import resolve_overlaps
from .modeling import ModelPredictor
from .preprocess import load_documents
from .schema import Document, Entity


def combine_documents(documents: list[Document], extracted: dict[str, list[Entity]]) -> tuple[str, list[Entity]]:
    """Concatenate documents and shift entity offsets into combined text coordinates."""

    chunks: list[str] = []
    shifted_entities: list[Entity] = []
    offset = 0
    for index, doc in enumerate(documents):
        if index:
            sep = "\n\n"
            chunks.append(sep)
            offset += len(sep)
        header = f"【{doc.title}】\n"
        chunks.append(header)
        offset += len(header)
        chunks.append(doc.text)
        for entity in extracted.get(doc.doc_id, []):
            shifted = Entity(
                start=entity.start + offset,
                end=entity.end + offset,
                type=entity.type,
                text=entity.text,
                score=entity.score,
                source=entity.source,
                method=entity.method,
                doc_id=entity.doc_id,
                linked=entity.linked,
                status=entity.status,
                meta=entity.meta,
            )
            shifted_entities.append(shifted)
        offset += len(doc.text)
    return "".join(chunks), shifted_entities


def build_entities_payload(
    input_dir: Path,
    output_dir: Path,
    sample_chars: int | None = None,
    offline: bool = True,
    link_limit: int = 25,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    documents = load_documents(input_dir, sample_chars=sample_chars)
    extractor = EntityExtractor(cache_dir=output_dir / "cache", offline=offline, link_limit=link_limit)
    extracted = {doc.doc_id: extractor.extract_document(doc) for doc in documents}
    text, entities = combine_documents(documents, extracted)

    payload = {
        "title": "明实录实体抽取结果",
        "source": f"{input_dir} ({len(documents)} files)",
        "text": text,
        "entities": [entity.to_dict() for entity in entities],
        "documents": [
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "source_path": doc.source_path,
                "chars": len(doc.text),
            }
            for doc in documents
        ],
        "meta": {
            "pipeline": "rule-gazetteer-mvp",
            "offline": offline,
            "sample_chars_per_file": sample_chars,
        },
    }
    return payload


def mark_weak_labels(entities: list[Entity], weak_threshold: float) -> list[Entity]:
    for entity in entities:
        entity.status = "weak_label" if entity.score < weak_threshold else "strong_label"
        entity.meta["weak_threshold"] = weak_threshold
    return entities


def model_entities(text: str, model_dir: Path | None) -> list[Entity]:
    if not model_dir or not model_dir.exists():
        return []
    predictor = ModelPredictor(model_dir)
    entities: list[Entity] = []
    for span in predictor.predict(text):
        entities.append(
            Entity(
                start=int(span["start"]),
                end=int(span["end"]),
                type=str(span["type"]),
                text=str(span["text"]),
                score=float(span.get("score") or 0.0),
                source="model",
                method="model-token-classifier",
                linked=None,
            )
        )
    return entities


def merge_model_and_rule_entities(model: list[Entity], rules: list[Entity]) -> list[Entity]:
    """Model spans are primary; high-confidence rules fill non-overlapping gaps."""

    merged = list(model)
    for rule in rules:
        if rule.score < 0.88:
            continue
        if any(rule.start < kept.end and rule.end > kept.start for kept in merged):
            continue
        merged.append(rule)
    return resolve_overlaps(merged)


def analyze_selection_payload(
    input_dir: Path,
    output_dir: Path,
    file_name: str,
    start_entry: int,
    end_entry: int,
    model_dir: Path | None = None,
    weak_threshold: float = DEFAULT_SETTINGS["weak_threshold"],
    offline: bool = True,
    link_limit: int = 25,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_doc = load_selected_document(input_dir, file_name)
    doc, selection = slice_document_by_entries(source_doc, start_entry, end_entry)
    extractor = EntityExtractor(cache_dir=output_dir / "cache", offline=offline, link_limit=link_limit)
    rule_entities = extractor.extract_document(doc)
    predicted = model_entities(doc.text, model_dir)
    if predicted:
        entities = merge_model_and_rule_entities(predicted, rule_entities)
    else:
        entities = rule_entities
    mark_weak_labels(entities, weak_threshold)
    payload = {
        "id": f"{selection['doc_id']}_{start_entry:06d}_{end_entry:06d}",
        "title": doc.title,
        "source": f"{selection['file']} entries {start_entry}-{end_entry}",
        "text": doc.text,
        "entities": [entity.to_dict() for entity in entities],
        "documents": [
            {
                "doc_id": source_doc.doc_id,
                "title": source_doc.title,
                "source_path": source_doc.source_path,
                "chars": len(source_doc.text),
            }
        ],
        "selection": selection,
        "meta": {
            "pipeline": "model-primary-with-rule-fallback" if predicted else "rule-gazetteer-mvp",
            "weak_threshold": weak_threshold,
            "model_dir": str(model_dir) if model_dir else None,
        },
    }
    return payload


def write_outputs(payload: dict[str, Any], output_dir: Path, ui_src: Path | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "entities.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts = Counter(entity["type"] for entity in payload["entities"])
    by_doc = Counter(entity.get("doc_id", "") for entity in payload["entities"])
    summary = {
        "entity_count": len(payload["entities"]),
        "type_counts": dict(sorted(counts.items())),
        "document_counts": dict(sorted(by_doc.items())),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if ui_src:
        ui_dir = output_dir / "ui"
        ui_dir.mkdir(exist_ok=True)
        shutil.copy2(ui_src, ui_dir / "index.html")
