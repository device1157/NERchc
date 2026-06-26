from __future__ import annotations

import re
from dataclasses import dataclass

from backend.services.normalization import compact_text, strip_noise_lines, to_traditional

VOLUME_NUMERAL = r"[一二三四五六七八九十百千〇零\d]+"
VOLUME_MARKER_RE = re.compile(r"@@VOLUME:([^@\n]+)@@")
VOLUME_HEADING_RE = re.compile(
    rf"(?m)^\s*(?:[\u4e00-\u9fff]{{0,24}}實錄)?[（(]\s*(卷(?:之)?{VOLUME_NUMERAL})\s*[）)]\s*$"
)
STANDALONE_VOLUME_RE = re.compile(rf"(?m)^\s*(卷(?:之)?{VOLUME_NUMERAL})\s*$")
INLINE_VOLUME_RE = re.compile(rf"(?<!實錄)(卷之{VOLUME_NUMERAL})(?=[○●\s])")
NON_BODY_KEYWORDS = ("序", "進表", "进表", "凡例", "目錄", "目录")


@dataclass(frozen=True)
class ParsedDocument:
    source_name: str
    volume: str
    seq: int
    raw_text: str
    meta: dict


def preprocess_text(source_name: str, text: str, convert_traditional: bool = True) -> list[ParsedDocument]:
    cleaned = strip_noise_lines(text)
    if convert_traditional:
        cleaned = to_traditional(cleaned)
    cleaned = _mark_volumes(cleaned)
    docs: list[ParsedDocument] = []
    segments = _split_volume_segments(cleaned)
    if not segments:
        cleaned = cleaned.replace("　", "")
        docs.extend(_split_entries(source_name, "未分卷", cleaned, 1))
        return docs

    seq = 1
    for volume, body in segments:
        entries = _split_entries(source_name, volume, body.replace("　", ""), seq)
        docs.extend(entries)
        seq += len(entries)
    return docs


def _mark_volumes(text: str) -> str:
    text = VOLUME_HEADING_RE.sub(lambda match: f"\n@@VOLUME:{match.group(1)}@@\n", text)
    text = STANDALONE_VOLUME_RE.sub(lambda match: f"\n@@VOLUME:{match.group(1)}@@\n", text)
    return INLINE_VOLUME_RE.sub(lambda match: f"\n@@VOLUME:{match.group(1)}@@\n", text)


def _split_volume_segments(text: str) -> list[tuple[str, str]]:
    matches = list(VOLUME_MARKER_RE.finditer(text))
    if not matches:
        return []
    segments: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            segments.append((match.group(1).strip(), body))
    return segments


def _split_entries(source_name: str, volume: str, text: str, start_seq: int) -> list[ParsedDocument]:
    raw_entries = re.split(r"[○●]", text)
    entries: list[ParsedDocument] = []
    seq = start_seq
    for index, raw in enumerate(raw_entries):
        body = compact_text(raw)
        if not body:
            continue
        if index < 3 and any(keyword in body[:20] for keyword in NON_BODY_KEYWORDS):
            continue
        for chunk in _chunk_long_entry(body):
            entries.append(
                ParsedDocument(
                    source_name=source_name,
                    volume=volume,
                    seq=seq,
                    raw_text=chunk,
                    meta={"entry_index": index},
                )
            )
            seq += 1
    return entries


def _chunk_long_entry(text: str, max_len: int = 900) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_len)
        if end < len(text):
            pivot = max(text.rfind(mark, start, end) for mark in ("。", "；", "，"))
            if pivot > start + 120:
                end = pivot + 1
        chunks.append(text[start:end])
        start = end
    return chunks
