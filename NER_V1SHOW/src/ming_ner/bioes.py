"""BIOES label conversion for token classification."""

from __future__ import annotations

from .annotations import ENTITY_TYPES


LABELS = ["O"] + [
    f"{prefix}-{entity_type}"
    for entity_type in ENTITY_TYPES
    for prefix in ("B", "I", "E", "S")
]
ID2LABEL = {index: label for index, label in enumerate(LABELS)}
LABEL2ID = {label: index for index, label in ID2LABEL.items()}


def spans_to_bioes(length: int, entities: list[dict[str, object]]) -> list[str]:
    labels = ["O"] * length
    for entity in sorted(entities, key=lambda item: (int(item["start"]), int(item["end"]))):
        start = int(entity["start"])
        end = int(entity["end"])
        entity_type = str(entity["type"])
        if end - start == 1:
            labels[start] = f"S-{entity_type}"
        else:
            labels[start] = f"B-{entity_type}"
            for index in range(start + 1, end - 1):
                labels[index] = f"I-{entity_type}"
            labels[end - 1] = f"E-{entity_type}"
    return labels


def bioes_to_spans(labels: list[str], text: str | None = None) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    index = 0
    while index < len(labels):
        label = labels[index]
        if label == "O" or "-" not in label:
            index += 1
            continue
        prefix, entity_type = label.split("-", 1)
        if prefix == "S":
            start, end = index, index + 1
            spans.append(_span(start, end, entity_type, text))
            index += 1
            continue
        if prefix == "B":
            start = index
            index += 1
            while index < len(labels) and labels[index] == f"I-{entity_type}":
                index += 1
            if index < len(labels) and labels[index] == f"E-{entity_type}":
                index += 1
            end = index
            spans.append(_span(start, end, entity_type, text))
            continue
        index += 1
    return spans


def _span(start: int, end: int, entity_type: str, text: str | None) -> dict[str, object]:
    data: dict[str, object] = {"start": start, "end": end, "type": entity_type}
    if text is not None:
        data["text"] = text[start:end]
    return data
