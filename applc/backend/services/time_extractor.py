from __future__ import annotations

import re
from typing import Any

from backend.db import db, utc_now
from backend.services.calendar import convert_exact_date

REIGN_START = {
    "洪武": 1368,
    "建文": 1399,
    "永樂": 1403,
    "永乐": 1403,
    "洪熙": 1425,
    "宣德": 1426,
    "正統": 1436,
    "正统": 1436,
    "景泰": 1450,
    "天順": 1457,
    "天顺": 1457,
    "成化": 1465,
    "弘治": 1488,
    "正德": 1506,
    "嘉靖": 1522,
    "隆慶": 1567,
    "隆庆": 1567,
    "萬曆": 1573,
    "万历": 1573,
    "泰昌": 1620,
    "天啟": 1621,
    "天启": 1621,
    "崇禎": 1628,
    "崇祯": 1628,
}

GANZHI = "甲子乙丑丙寅丁卯戊辰己巳庚午辛未壬申癸酉甲戌乙亥丙子丁丑戊寅己卯庚辰辛巳壬午癸未甲申乙酉丙戌丁亥戊子己丑庚寅辛卯壬辰癸巳甲午乙未丙申丁酉戊戌己亥庚子辛丑壬寅癸卯甲辰乙巳丙午丁未戊申己酉庚戌辛亥壬子癸丑甲寅乙卯丙辰丁巳戊午己未庚申辛酉壬戌癸亥"
GANZHI_TERMS = [GANZHI[i : i + 2] for i in range(0, len(GANZHI), 2)]
REIGN_PATTERN = "|".join(sorted(REIGN_START, key=len, reverse=True))
NUMERAL_CHARS = r"一二三四五六七八九十百千〇零壹貳叁參肆伍陸柒捌玖拾佰仟兩两廿卅卄\d"
DATE_RE = re.compile(
    rf"(?P<reign>{REIGN_PATTERN})(?P<year>元|[{NUMERAL_CHARS}]+)?年?"
    rf"(?:[春夏秋冬閏闰])?"
    rf"(?P<month>[正冬臘腊{NUMERAL_CHARS}]+)?月?"
    rf"(?P<ganzhi>{'|'.join(GANZHI_TERMS)})?"
    rf"(?P<day>[初{NUMERAL_CHARS}]+)?日?"
)
GANZHI_RE = re.compile("|".join(GANZHI_TERMS))

NUMERAL_MAP = {
    "元": 1,
    "正": 1,
    "一": 1,
    "壹": 1,
    "二": 2,
    "貳": 2,
    "贰": 2,
    "兩": 2,
    "两": 2,
    "三": 3,
    "叁": 3,
    "參": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陸": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
    "十": 10,
    "拾": 10,
    "冬": 11,
    "臘": 12,
    "腊": 12,
}


def chinese_number(value: str | None) -> int | None:
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value in NUMERAL_MAP:
        return NUMERAL_MAP[value]
    value = (
        value.replace("初", "")
        .replace("廿", "二十")
        .replace("卄", "二十")
        .replace("卅", "三十")
        .replace("拾", "十")
        .replace("佰", "百")
        .replace("仟", "千")
    )
    for formal, plain in (
        ("壹", "一"),
        ("貳", "二"),
        ("贰", "二"),
        ("兩", "二"),
        ("两", "二"),
        ("叁", "三"),
        ("參", "三"),
        ("肆", "四"),
        ("伍", "五"),
        ("陸", "六"),
        ("陆", "六"),
        ("柒", "七"),
        ("捌", "八"),
        ("玖", "九"),
    ):
        value = value.replace(formal, plain)
    if value == "十":
        return 10
    if "十" in value:
        head, _, tail = value.partition("十")
        tens = NUMERAL_MAP.get(head, 1 if head == "" else 0)
        ones = NUMERAL_MAP.get(tail, 0) if tail else 0
        return tens * 10 + ones
    total = 0
    for char in value:
        total = total * 10 + NUMERAL_MAP.get(char, 0)
    return total or None


def run_time_extraction() -> dict[str, Any]:
    with db() as conn:
        documents = conn.execute("SELECT id, raw_text FROM documents").fetchall()
        conn.execute("DELETE FROM time_mentions")
        now = utc_now()
        count = 0
        for doc in documents:
            for item in extract_time_mentions(doc["raw_text"]):
                conn.execute(
                    """
                    INSERT INTO time_mentions
                    (document_id, start, end, text, reign, ganzhi, lunar_month, lunar_day, ce_year,
                     calendar_date, date_precision, calendar_source, calendar_confidence, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc["id"],
                        item["start"],
                        item["end"],
                        item["text"],
                        item.get("reign"),
                        item.get("ganzhi"),
                        item.get("lunar_month"),
                        item.get("lunar_day"),
                        item.get("ce_year"),
                        item.get("calendar_date"),
                        item.get("date_precision", "estimated_year"),
                        item.get("calendar_source"),
                        item.get("calendar_confidence"),
                        item["confidence"],
                        now,
                    ),
                )
                count += 1
        return {"documents": len(documents), "time_mentions": count}


def extract_time_mentions(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for match in DATE_RE.finditer(text):
        if not match.group("reign"):
            continue
        if not any(match.group(name) for name in ("year", "month", "ganzhi", "day")):
            continue
        year = chinese_number(match.group("year")) or 1
        reign = match.group("reign")
        ce_year = REIGN_START.get(reign)
        if ce_year is not None:
            ce_year = ce_year + year - 1
        item = {
            "start": match.start(),
            "end": match.end(),
            "text": match.group(0),
            "reign": reign,
            "ganzhi": match.group("ganzhi"),
            "lunar_month": chinese_number(match.group("month")),
            "lunar_day": chinese_number(match.group("day")),
            "ce_year": ce_year,
            "confidence": 0.88 if ce_year else 0.55,
        }
        conversion = convert_exact_date(
            ce_year,
            item["lunar_month"],
            item["lunar_day"],
            item["ganzhi"],
        )
        item.update(
            {
                "calendar_date": conversion.calendar_date,
                "date_precision": conversion.date_precision,
                "calendar_source": conversion.calendar_source,
                "calendar_confidence": conversion.calendar_confidence,
            }
        )
        results.append(item)
        occupied.append((match.start(), match.end()))
    for match in GANZHI_RE.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        results.append(
            {
                "start": match.start(),
                "end": match.end(),
                "text": match.group(0),
                "ganzhi": match.group(0),
                "date_precision": "unknown",
                "calendar_source": "ganzhi_only",
                "calendar_confidence": 0.1,
                "confidence": 0.35,
            }
        )
    return results
