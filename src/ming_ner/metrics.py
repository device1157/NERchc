"""Strict entity-level evaluation helpers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .annotations import ENTITY_TYPES, read_annotations


def entity_key(entity: dict[str, Any]) -> tuple[int, int, str]:
    return int(entity["start"]), int(entity["end"]), str(entity["type"])


def strict_entity_metrics(
    gold_records: list[dict[str, Any]],
    pred_records: list[dict[str, Any]],
    target_f1: float = 0.8,
    min_reviewed_segments: int = 300,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pred_by_id = {record.get("id"): record for record in pred_records}
    counts = {
        entity_type: Counter({"tp": 0, "fp": 0, "fn": 0})
        for entity_type in ENTITY_TYPES
    }
    errors: list[dict[str, Any]] = []

    for gold in gold_records:
        pred = pred_by_id.get(gold.get("id"), {"entities": []})
        gold_sets = {entity_type: set() for entity_type in ENTITY_TYPES}
        pred_sets = {entity_type: set() for entity_type in ENTITY_TYPES}
        for entity in gold.get("entities", []):
            gold_sets[entity["type"]].add(entity_key(entity))
        for entity in pred.get("entities", []):
            if entity.get("type") in pred_sets:
                pred_sets[entity["type"]].add(entity_key(entity))

        for entity_type in ENTITY_TYPES:
            tp = gold_sets[entity_type] & pred_sets[entity_type]
            fp = pred_sets[entity_type] - gold_sets[entity_type]
            fn = gold_sets[entity_type] - pred_sets[entity_type]
            counts[entity_type]["tp"] += len(tp)
            counts[entity_type]["fp"] += len(fp)
            counts[entity_type]["fn"] += len(fn)
            for start, end, _ in sorted(fp):
                errors.append(
                    {
                        "id": gold.get("id"),
                        "type": entity_type,
                        "error": "false_positive",
                        "start": start,
                        "end": end,
                        "text": pred.get("text", "")[start:end],
                    }
                )
            for start, end, _ in sorted(fn):
                errors.append(
                    {
                        "id": gold.get("id"),
                        "type": entity_type,
                        "error": "false_negative",
                        "start": start,
                        "end": end,
                        "text": gold.get("text", "")[start:end],
                    }
                )

    by_type: dict[str, Any] = {}
    passed = len(gold_records) >= min_reviewed_segments
    for entity_type in ENTITY_TYPES:
        tp = counts[entity_type]["tp"]
        fp = counts[entity_type]["fp"]
        fn = counts[entity_type]["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        by_type[entity_type] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
        if f1 < target_f1:
            passed = False

    if len(gold_records) < min_reviewed_segments:
        status = "not_enough_reviewed_data"
    elif passed:
        status = "passed"
    else:
        status = "below_target"

    metrics = {
        "status": status,
        "target_f1": target_f1,
        "min_reviewed_segments": min_reviewed_segments,
        "reviewed_segments": len(gold_records),
        "by_type": by_type,
    }
    return metrics, errors


def write_metrics(metrics: dict[str, Any], errors: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "errors.jsonl").open("w", encoding="utf-8") as handle:
        for error in errors:
            handle.write(json.dumps(error, ensure_ascii=False) + "\n")


def evaluate_annotation_files(
    gold_path: Path,
    pred_path: Path,
    output_dir: Path,
    target_f1: float = 0.8,
    min_reviewed_segments: int = 300,
) -> dict[str, Any]:
    metrics, errors = strict_entity_metrics(
        read_annotations(gold_path),
        read_annotations(pred_path),
        target_f1=target_f1,
        min_reviewed_segments=min_reviewed_segments,
    )
    write_metrics(metrics, errors, output_dir)
    return metrics
