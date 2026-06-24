"""Baseline rule and gazetteer entity extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .cbdb_client import CBDBClient, cbdb_name_url
from .dictionaries import (
    COMMON_FALSE_PERSON,
    LOCATION_SUFFIXES,
    LOCATION_TERMS,
    OFFICE_SUFFIXES,
    OFFICE_TERMS,
    PERSON_SURNAMES,
)
from .gazetteer import find_terms, resolve_overlaps
from .schema import Document, Entity


TRAD_MAP = str.maketrans(
    {
        "书": "書",
        "实": "實",
        "录": "錄",
        "东": "東",
        "国": "國",
        "鲜": "鮮",
        "县": "縣",
        "府": "府",
        "职": "職",
        "学": "學",
        "士": "士",
        "广": "廣",
        "礼": "禮",
        "户": "戶",
        "吏": "吏",
        "部": "部",
        "师": "師",
        "阳": "陽",
        "阴": "陰",
        "兴": "興",
        "应": "應",
        "会": "會",
        "为": "為",
        "谕": "諭",
        "读": "讀",
        "讲": "講",
        "编": "編",
        "检": "檢",
        "讨": "討",
        "监": "監",
        "陈": "陳",
        "张": "張",
        "刘": "劉",
        "杨": "楊",
        "赵": "趙",
        "吴": "吳",
        "郑": "鄭",
        "孙": "孫",
        "马": "馬",
        "冯": "馮",
        "邓": "鄧",
        "许": "許",
        "钱": "錢",
        "卢": "盧",
        "叶": "葉",
        "万": "萬",
        "罗": "羅",
        "顾": "顧",
        "钟": "鍾",
        "韩": "韓",
        "谭": "譚",
        "龙": "龍",
        "龚": "龔",
        "裴": "裴",
        "陆": "陸",
        "卫": "衛",
        "叚": "段",
        "渊": "淵",
        "阁": "閣",
        "总": "總",
        "谕": "諭",
        "荣": "榮",
        "俨": "儼",
    }
)


OFFICE_STARTERS = (
    "中書省",
    "翰林院",
    "國子監",
    "文淵閣",
    "華蓋殿",
    "武英殿",
    "謹身殿",
    "左春坊",
    "右春坊",
    "都察院",
    "通政司",
    "大理寺",
    "太常寺",
    "詹事府",
    "行在",
    "戶部",
    "吏部",
    "禮部",
    "兵部",
    "刑部",
    "工部",
    "左軍",
    "右軍",
    "中軍",
    "前軍",
    "後軍",
)


PERSON_NAME_STOPS = (
    "總裁",
    "总裁",
    "監修",
    "监修",
    "纂修",
    "纂脩",
    "修纂",
    "催纂",
    "翰林",
    "國子",
    "国子",
    "文淵",
    "文渊",
    "華蓋",
    "华盖",
    "武英",
    "謹身",
    "谨身",
    "左春坊",
    "右春坊",
    "戶部",
    "户部",
    "吏部",
    "禮部",
    "礼部",
    "兵部",
    "刑部",
    "工部",
    "都察",
    "通政",
    "大理",
    "太常",
    "詹事",
    "按察",
    "布政",
    "臣",
)


def normalize_for_matching(text: str) -> str:
    """A small Simplified-to-Traditional compatibility map for baseline matching."""

    return text.translate(TRAD_MAP)


@dataclass
class EntityExtractor:
    """Rule-based MVP extractor with optional CBDB person linking."""

    cache_dir: Path
    offline: bool = True
    link_limit: int = 25

    def __post_init__(self) -> None:
        self.cbdb = CBDBClient(self.cache_dir / "cbdb", offline=self.offline)

    def extract_document(self, doc: Document) -> list[Entity]:
        text = normalize_for_matching(doc.text)
        entities: list[Entity] = []
        entities.extend(find_terms(text, OFFICE_TERMS, "OFF", "built-in-office", "gazetteer", 0.92))
        entities.extend(find_terms(text, LOCATION_TERMS, "LOC", "built-in-location", "gazetteer", 0.88))
        entities.extend(self._extract_suffix_entities(text, "OFF", OFFICE_SUFFIXES, 0.78))
        entities.extend(self._extract_suffix_entities(text, "LOC", LOCATION_SUFFIXES, 0.74))
        entities.extend(self._extract_official_name_patterns(text))
        entities = resolve_overlaps(entities)

        for entity in entities:
            entity.doc_id = doc.doc_id
            entity.text = doc.text[entity.start : entity.end]
            if entity.type == "OFF" and not entity.linked:
                entity.linked = {"source": "office-gazetteer", "name": entity.text}
            elif entity.type == "PER":
                entity.linked = self._link_person(entity.text)
            elif entity.type == "LOC" and not entity.linked:
                entity.linked = {"source": "local-gazetteer", "name": entity.text}
        return entities

    def _extract_suffix_entities(
        self,
        text: str,
        entity_type: str,
        suffixes: tuple[str, ...],
        score: float,
    ) -> list[Entity]:
        suffix_alt = "|".join(re.escape(s) for s in sorted(suffixes, key=len, reverse=True))
        if entity_type == "OFF":
            pattern = re.compile(rf"[\u4e00-\u9fff]{{1,10}}(?:{suffix_alt})")
            source = "office-suffix"
        else:
            pattern = re.compile(rf"[\u4e00-\u9fff]{{1,8}}(?:{suffix_alt})")
            source = "location-suffix"

        entities: list[Entity] = []
        for match in pattern.finditer(text):
            value = match.group(0)
            if entity_type == "LOC" and len(value) == 1:
                continue
            if entity_type == "OFF":
                value, start, end = self._trim_office_prefix(value, match.start(), match.end())
            else:
                value, start, end = self._trim_location_prefix(value, match.start(), match.end())
            if len(value) < 2:
                continue
            if entity_type == "LOC" and not self._looks_like_location(value):
                continue
            if entity_type == "OFF" and not self._looks_like_office(value):
                continue
            entities.append(
                Entity(
                    start=start,
                    end=end,
                    type=entity_type,
                    text=text[start:end],
                    score=score,
                    source=source,
                    method="suffix-rule",
                )
            )
        return entities

    @staticmethod
    def _trim_office_prefix(value: str, start: int, end: int) -> tuple[str, int, int]:
        for starter in OFFICE_STARTERS:
            index = value.find(starter)
            if index > 0:
                return value[index:], start + index, end
        markers = "以命升改授除為任兼署掌臣官"
        cut = 0
        for index, char in enumerate(value):
            if char in markers:
                cut = index + 1
        value = value[cut:]
        start += cut
        cut = EntityExtractor._person_prefix_cut(value)
        value = value[cut:]
        start += cut
        return value, start, end

    @staticmethod
    def _person_prefix_cut(value: str) -> int:
        if len(value) >= 4 and value[0] in PERSON_SURNAMES:
            suffix_start = len(value)
            for suffix in OFFICE_SUFFIXES:
                if value.endswith(suffix):
                    suffix_start = min(suffix_start, len(value) - len(suffix))
            if suffix_start in (2, 3):
                return suffix_start
        return 0

    @staticmethod
    def _trim_location_prefix(value: str, start: int, end: int) -> tuple[str, int, int]:
        markers = "於至往赴自從由攻克取守鎮置改升命遣賜給"
        cut = 0
        for index, char in enumerate(value):
            if char in markers:
                cut = index + 1
        value = value[cut:]
        start += cut
        return value, start, end

    @staticmethod
    def _looks_like_location(value: str) -> bool:
        if value in LOCATION_TERMS:
            return True
        if len(value) <= 4:
            return True
        admin_markers = ("布政", "按察", "都指揮", "宣慰", "宣撫", "長官", "軍民")
        return any(marker in value for marker in admin_markers)

    @staticmethod
    def _looks_like_office(value: str) -> bool:
        if value in OFFICE_TERMS:
            return True
        if len(value) <= 6:
            return True
        return any(starter in value for starter in OFFICE_STARTERS)

    def _extract_official_name_patterns(self, text: str) -> list[Entity]:
        """Extract names after official marker 臣 and before verbs/list separators."""

        entities: list[Entity] = []
        pattern = re.compile(r"臣\s*([\u4e00-\u9fff](?:\s*[\u4e00-\u9fff]){0,7})")
        for match in pattern.finditer(text):
            raw = re.sub(r"\s+", "", match.group(1))
            name = self._clean_person_name(raw)
            if not name:
                continue
            start, end = self._span_for_clean_name(text, match.start(1), match.end(1), name)
            entities.append(
                Entity(
                    start=start,
                    end=end,
                    type="PER",
                    text=text[start:end],
                    score=0.84,
                    source="official-list",
                    method="chen-name-rule",
                )
            )
        return entities

    @staticmethod
    def _span_for_clean_name(text: str, start: int, end: int, name: str) -> tuple[int, int]:
        """Map a whitespace-tolerant matched group back to the cleaned name span."""

        cursor = start
        while cursor < end and text[cursor].isspace():
            cursor += 1
        span_start = cursor
        seen = 0
        while cursor < end and seen < len(name):
            if not text[cursor].isspace():
                seen += 1
            cursor += 1
        while cursor > span_start and text[cursor - 1].isspace():
            cursor -= 1
        return span_start, cursor

    def _extract_context_names(self, text: str) -> list[Entity]:
        """Extract likely 2-3 character Chinese personal names near action contexts."""

        verbs = "曰言奏卒死降叛遣率命封討"
        pattern = re.compile(rf"([{''.join(PERSON_SURNAMES)}][\u4e00-\u9fff]{{1,2}})(?=[{verbs}])")
        entities: list[Entity] = []
        for match in pattern.finditer(text):
            name = self._clean_person_name(match.group(1))
            if not name:
                continue
            entities.append(
                Entity(
                    start=match.start(1),
                    end=match.end(1),
                    type="PER",
                    text=name,
                    score=0.69,
                    source="context-name",
                    method="surname-context-rule",
                )
            )
        return entities

    @staticmethod
    def _clean_person_name(raw: str) -> str | None:
        raw = re.sub(r"\s+", "", raw)
        stop_positions = [raw.find(stop) for stop in PERSON_NAME_STOPS if raw.find(stop) > 0]
        if stop_positions:
            raw = raw[: min(stop_positions)]
        raw = re.split(r"[等曰言奏謹上表聞至為以升授除兼掌署命遣率將帥封討攻守來貢卒死降叛]", raw, maxsplit=1)[0]
        if len(raw) == 4 and raw[-1] in PERSON_SURNAMES:
            raw = raw[:3]
        if not (2 <= len(raw) <= 4):
            return None
        if raw in COMMON_FALSE_PERSON:
            return None
        if raw[0] not in PERSON_SURNAMES:
            return None
        if any(token in raw for token in ("皇", "天下", "國王", "朝廷", "官軍")):
            return None
        return raw

    def _link_person(self, name: str) -> dict[str, object] | None:
        if self.link_limit <= 0:
            return {
                "source": "CBDB",
                "id": None,
                "name": name,
                "url": cbdb_name_url(name),
                "status": "not-requested",
            }
        self.link_limit -= 1
        data = self.cbdb.lookup_person(name)
        parsed = self.cbdb.parse_person(data)
        if parsed:
            return parsed
        return {
            "source": "CBDB",
            "id": None,
            "name": name,
            "url": cbdb_name_url(name),
            "status": "offline-or-not-found" if self.offline else "not-found",
        }
