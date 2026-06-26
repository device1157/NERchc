from __future__ import annotations

import html
import re
from typing import Iterable

from backend.db import json_loads

try:
    from opencc import OpenCC
except Exception:  # pragma: no cover - optional dependency fallback
    OpenCC = None  # type: ignore[assignment]

_OPENCC_S2T = None


FALLBACK_S2T = str.maketrans(
    {
        "国": "國",
        "卫": "衛",
        "军": "軍",
        "书": "書",
        "丞": "丞",
        "县": "縣",
        "贡": "貢",
        "来": "來",
        "诏": "詔",
        "陈": "陳",
        "张": "張",
        "刘": "劉",
        "赵": "趙",
        "杨": "楊",
        "吴": "吳",
        "汉": "漢",
        "万": "萬",
        "乐": "樂",
        "启": "啟",
        "台": "臺",
        "号": "號",
        "岁": "歲",
        "辽": "遼",
        "宁": "寧",
        "广": "廣",
        "东": "東",
        "发": "發",
        "迁": "遷",
        "镇": "鎮",
        "边": "邊",
        "扰": "擾",
        "贼": "賊",
        "灭": "滅",
        "粮": "糧",
        "税": "稅",
    }
)

PUNCT_RE = re.compile(r"[\s　]+")


def to_traditional(text: str) -> str:
    converter = _get_opencc_s2t()
    if converter is not None:
        return converter.convert(text)
    return text.translate(FALLBACK_S2T)


def _get_opencc_s2t():
    global _OPENCC_S2T
    if OpenCC is None:
        return None
    if _OPENCC_S2T is None:
        try:
            _OPENCC_S2T = OpenCC("s2t")
        except Exception:
            return None
    return _OPENCC_S2T


def compact_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\ufeff", "")
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)
    text = text.replace("\xa0", "")
    text = PUNCT_RE.sub("", text)
    return text.strip()


def normalize_for_match(text: str, variant_terms: Iterable[dict]) -> str:
    value = to_traditional(compact_text(text))
    for term in variant_terms:
        metadata = json_loads(term.get("metadata_json"), {})
        canonical = metadata.get("canonical") or term.get("text")
        for alias in json_loads(term.get("aliases_json"), []):
            if alias:
                value = value.replace(alias, canonical)
        if term.get("text"):
            value = value.replace(term["text"], canonical)
    return value


def strip_noise_lines(text: str) -> str:
    text = html.unescape(text)
    lines = []
    noise_patterns = (
        "明實錄",
        "明实录",
        "更多經典著作",
        "更多经典著作",
        "文學100",
        "文学100",
        "書名：",
        "书名：",
        "作者：",
        "校勘",
        "影印",
        "http",
        "www.",
        "版權",
        "版权",
    )
    for raw_line in text.splitlines():
        line = raw_line.replace("\xa0", " ").strip()
        if not line:
            continue
        if any(pattern in line for pattern in noise_patterns) and len(line) < 80:
            continue
        lines.append(line)
    return "\n".join(lines)
