"""Dictionary matching helpers."""

from __future__ import annotations

from collections.abc import Iterable

from .schema import Entity


def find_terms(
    text: str,
    terms: Iterable[str],
    entity_type: str,
    source: str,
    method: str,
    score: float,
) -> list[Entity]:
    """Find non-overlapping gazetteer terms, preferring longer terms."""

    matches: list[Entity] = []
    sorted_terms = sorted({term for term in terms if term}, key=len, reverse=True)
    occupied: list[tuple[int, int]] = []

    for term in sorted_terms:
        start = text.find(term)
        while start != -1:
            end = start + len(term)
            if not any(start < b and end > a for a, b in occupied):
                matches.append(
                    Entity(
                        start=start,
                        end=end,
                        type=entity_type,
                        text=text[start:end],
                        score=score,
                        source=source,
                        method=method,
                    )
                )
                occupied.append((start, end))
            start = text.find(term, start + 1)
    return matches


def resolve_overlaps(entities: Iterable[Entity]) -> list[Entity]:
    """Resolve overlapping spans by type priority, length, and score."""

    priority = {"OFF": 3, "PER": 2, "LOC": 1}
    selected: list[Entity] = []
    for entity in sorted(
        entities,
        key=lambda e: (
            e.start,
            -(e.end - e.start),
            -priority.get(e.type, 0),
            -e.score,
        ),
    ):
        if any(entity.start < kept.end and entity.end > kept.start for kept in selected):
            continue
        selected.append(entity)
    return sorted(selected, key=lambda e: (e.start, e.end, e.type))
