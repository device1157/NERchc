from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

try:
    from opencc import OpenCC
except Exception:  # pragma: no cover - optional dependency
    OpenCC = None

VOLUME_RE = re.compile(r"([卷捲]之[一二三四五六七八九十百千〇零\d]+)")
NON_BODY_HINTS = ("序", "凡例", "進表", "目录", "目錄", "校勘", "提要")
SENTENCE_END = "。！？；"


@dataclass
class ProcessedDocument:
    volume: str
    seq: int
    text: str
    meta: dict


@dataclass
class ProcessedSentence:
    idx: int
    text: str
    char_offset: int


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def clean_text(text: str, clean_regex: str | None = None) -> str:
    text = text.replace("\ufeff", "").replace("\u3000", "")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(hint in line for hint in ("免责声明", "广告", "扫描", "OCR")):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"[［\[].*?[］\]]", "", text)
    text = re.sub(r"\s+", "", text)
    if clean_regex:
        text = re.sub(clean_regex, "", text)
    return text


def convert_simplified_to_traditional(text: str, enabled: bool = True) -> tuple[str, str]:
    if not enabled:
        return text, "disabled"
    if OpenCC is None:
        return text, "fallback_no_opencc"
    return OpenCC("s2t").convert(text), "opencc_s2t"


def split_documents(text: str) -> list[ProcessedDocument]:
    parts = VOLUME_RE.split(text)
    documents: list[ProcessedDocument] = []
    current_volume = "未分卷"
    seq_by_volume: dict[str, int] = {}

    if len(parts) == 1:
        body = _drop_front_matter(text)
        return _split_volume_items(current_volume, body, seq_by_volume)

    prefix = parts[0]
    if prefix and "○" in prefix:
        documents.extend(_split_volume_items(current_volume, _drop_front_matter(prefix), seq_by_volume))

    for i in range(1, len(parts), 2):
        current_volume = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        documents.extend(_split_volume_items(current_volume, _drop_front_matter(body), seq_by_volume))
    return documents


def _drop_front_matter(text: str) -> str:
    first_marker = text.find("○")
    if first_marker >= 0:
        head = text[:first_marker]
        if len(head) > 500 or any(hint in head[:300] for hint in NON_BODY_HINTS):
            return text[first_marker:]
    return text


def _split_volume_items(volume: str, body: str, seq_by_volume: dict[str, int]) -> list[ProcessedDocument]:
    chunks = [chunk.strip("○ \n\r\t") for chunk in body.split("○")]
    result = []
    for chunk in chunks:
        if len(chunk) < 10:
            continue
        if any(chunk.startswith(hint) for hint in NON_BODY_HINTS):
            continue
        seq_by_volume[volume] = seq_by_volume.get(volume, 0) + 1
        result.append(
            ProcessedDocument(
                volume=volume,
                seq=seq_by_volume[volume],
                text=chunk,
                meta={"segmentation": "volume_marker_and_circle"},
            )
        )
    return result


def punctuate_document(text: str) -> tuple[str, str]:
    if any(mark in text for mark in SENTENCE_END):
        return text, "already_punctuated"
    pieces = re.split(r"([也矣焉耳云詔曰奏曰])", text)
    out = []
    for i in range(0, len(pieces), 2):
        segment = pieces[i]
        suffix = pieces[i + 1] if i + 1 < len(pieces) else ""
        if not segment and not suffix:
            continue
        out.append(segment + suffix)
        if suffix:
            out.append("。")
    punctuated = "".join(out).strip("。")
    if not punctuated:
        punctuated = text
    return punctuated, "fallback_rules"


def split_sentences(text: str, min_len: int = 50, max_len: int = 200) -> list[ProcessedSentence]:
    punctuated, _ = punctuate_document(text)
    raw_units = re.split(r"(?<=[。！？；])", punctuated)
    sentences: list[ProcessedSentence] = []
    search_from = 0
    idx = 0
    for unit in raw_units:
        unit = unit.strip()
        if not unit:
            continue
        for piece in _split_long_unit(unit, max_len=max_len):
            piece = piece.strip()
            if len(piece) < 2:
                continue
            offset = text.find(piece.strip(SENTENCE_END), search_from)
            if offset < 0:
                offset = search_from
            search_from = max(offset + len(piece.strip(SENTENCE_END)), search_from)
            if len(piece) < min_len and sentences:
                prev = sentences[-1]
                merged = prev.text + piece
                if len(merged) <= max_len:
                    sentences[-1] = ProcessedSentence(idx=prev.idx, text=merged, char_offset=prev.char_offset)
                    continue
            idx += 1
            sentences.append(ProcessedSentence(idx=idx, text=piece, char_offset=offset))
    return sentences


def _split_long_unit(unit: str, max_len: int) -> list[str]:
    if len(unit) <= max_len:
        return [unit]
    soft_parts = re.split(r"(?<=[，、])", unit)
    chunks: list[str] = []
    current = ""
    for part in soft_parts:
        if len(current) + len(part) <= max_len:
            current += part
            continue
        if current:
            chunks.append(current)
        current = part
        while len(current) > max_len:
            chunks.append(current[:max_len])
            current = current[max_len:]
    if current:
        chunks.append(current)
    return chunks


def classify_style(text: str) -> str:
    if any(k in text for k in ("朝貢", "來朝", "貢")):
        return "朝贡"
    if any(k in text for k in ("詔", "制曰", "敕")):
        return "诏令"
    if any(k in text for k in ("奏", "疏", "言")):
        return "奏议"
    return "纪事"


def stratified_sample(items: list[tuple[int, str, str]], sample_size: int, seed: int = 13) -> set[int]:
    """items: (sentence_id, volume, text)."""
    rng = random.Random(seed)
    if sample_size >= len(items):
        return {item[0] for item in items}
    buckets: dict[tuple[str, str], list[int]] = {}
    for sentence_id, volume, text in items:
        buckets.setdefault((volume, classify_style(text)), []).append(sentence_id)
    selected: set[int] = set()
    for ids in buckets.values():
        quota = max(1, round(sample_size * len(ids) / len(items)))
        selected.update(rng.sample(ids, min(quota, len(ids))))
    if len(selected) > sample_size:
        selected = set(rng.sample(list(selected), sample_size))
    remaining = [item[0] for item in items if item[0] not in selected]
    while len(selected) < sample_size and remaining:
        pick = rng.choice(remaining)
        remaining.remove(pick)
        selected.add(pick)
    return selected
