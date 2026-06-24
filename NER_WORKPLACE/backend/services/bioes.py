from __future__ import annotations


def entities_to_bioes(text: str, entities: list[dict]) -> list[str]:
    labels = ["O"] * len(text)
    for entity in sorted(entities, key=lambda x: (x["start"], x["end"])):
        start = max(0, int(entity["start"]))
        end = min(len(text), int(entity["end"]))
        tag = entity.get("type") or entity.get("entity_type_tag")
        if not tag or start >= end:
            continue
        if any(label != "O" for label in labels[start:end]):
            continue
        length = end - start
        if length == 1:
            labels[start] = f"S-{tag}"
        else:
            labels[start] = f"B-{tag}"
            for i in range(start + 1, end - 1):
                labels[i] = f"I-{tag}"
            labels[end - 1] = f"E-{tag}"
    return labels


def bioes_to_entities(text: str, labels: list[str]) -> list[dict]:
    entities = []
    i = 0
    while i < min(len(text), len(labels)):
        label = labels[i]
        if label == "O" or "-" not in label:
            i += 1
            continue
        prefix, tag = label.split("-", 1)
        if prefix == "S":
            entities.append({"start": i, "end": i + 1, "type": tag, "text": text[i : i + 1]})
            i += 1
            continue
        if prefix == "B":
            start = i
            i += 1
            while i < len(labels) and labels[i] == f"I-{tag}":
                i += 1
            if i < len(labels) and labels[i] == f"E-{tag}":
                i += 1
                entities.append({"start": start, "end": i, "type": tag, "text": text[start:i]})
            continue
        i += 1
    return entities

