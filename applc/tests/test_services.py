from __future__ import annotations

import math

from backend.services.embedding import embed_paragraph
from backend.services.entity_display import entity_display_text, normalize_entity_type
from backend.services.classifier import _load_event_keywords, classify_text
from backend.services.linker import similarity
from backend.services.ner import extract_entities
from backend.services.preprocess import preprocess_text
from backend.services.time_extractor import extract_time_mentions


def test_preprocess_splits_volume_and_entries() -> None:
    text = "明實錄\n卷之一○洪武元年春正月甲子詔中書省左丞相李善長宴占城使○遣雲南衛軍"
    docs = preprocess_text("sample.txt", text)
    assert len(docs) == 2
    assert docs[0].volume == "卷之一"
    assert "洪武元年" in docs[0].raw_text


def test_preprocess_handles_wenxue100_parenthesized_volumes() -> None:
    text = """
更多经典著作，请登录文学100网（http://www.wenxue100.com）
书名：03明实录仁宗实录（15卷）
作者：明·官修

仁宗昭皇帝实录序
据中央图书馆藏旧钞本誊录影印北平图书馆本此行误作仁宗昭皇帝实录卷之一

仁宗昭皇帝实录（卷一）
　　仁宗敬天体道&nbsp; 昭皇帝讳高炽○洪熙元年正月甲子命中書省左丞相李善長

仁宗昭皇帝实录（卷二）
　　永樂三年夏雲南衛都督率軍討邊
"""
    docs = preprocess_text("renzong.txt", text)
    assert len(docs) == 3
    assert docs[0].volume == "卷一"
    assert docs[-1].volume == "卷二"
    assert all("文学100" not in doc.raw_text for doc in docs)
    assert all("&nbsp;" not in doc.raw_text for doc in docs)
    assert "昭皇帝諱高熾" in docs[0].raw_text


def test_time_extraction_normalizes_reign_year() -> None:
    mentions = extract_time_mentions("洪武二年春正月甲子詔")
    assert mentions[0]["reign"] == "洪武"
    assert mentions[0]["ce_year"] == 1369
    assert mentions[0]["ganzhi"] == "甲子"


def test_time_extraction_supports_formal_ming_numerals() -> None:
    mentions = extract_time_mentions("永樂貳拾貳年柒月辛卯上賓")
    assert mentions[0]["reign"] == "永樂"
    assert mentions[0]["ce_year"] == 1424
    assert mentions[0]["lunar_month"] == 7
    assert mentions[0]["ganzhi"] == "辛卯"


def test_dictionary_ner_extracts_location_and_office() -> None:
    terms = [
        {"type": "location", "text": "占城", "aliases_json": "[]", "metadata_json": "{}"},
        {"type": "office", "text": "中書省左丞相", "aliases_json": "[\"左丞相\"]", "metadata_json": "{}"},
        {"type": "variant", "text": "國", "aliases_json": "[\"国\"]", "metadata_json": "{\"canonical\":\"國\"}"},
    ]
    entities = extract_entities("占城國王遣使中書省左丞相李善長宴之", terms)
    assert any(item["entity_type"] == "LOC" and item["text"] == "占城" for item in entities)
    assert any(item["entity_type"] == "OFF" for item in entities)


def test_person_name_term_extracts_per_and_display_format() -> None:
    terms = [
        {"type": "person_name", "text": "夏原吉", "aliases_json": "[]", "metadata_json": "{}"},
    ]
    entities = extract_entities("命夏原吉治水", terms)
    assert any(item["entity_type"] == "PER" and item["text"] == "夏原吉" for item in entities)
    assert normalize_entity_type("人名") == "PER"
    assert entity_display_text("夏原吉", "PER") == '人名|"夏原吉"'


def test_office_patterns_do_not_absorb_person_names() -> None:
    terms = [
        {"type": "surname", "text": "李", "aliases_json": "[]", "metadata_json": "{}"},
        {"type": "person_name", "text": "夏原吉", "aliases_json": "[]", "metadata_json": "{}"},
        {"type": "office", "text": "中書省左丞相", "aliases_json": "[\"左丞相\"]", "metadata_json": "{}"},
        {"type": "office", "text": "戶部尚書", "aliases_json": "[\"户部尚书\"]", "metadata_json": "{}"},
    ]
    entities = extract_entities("命夏原吉為戶部尚書。中書省左丞相李善長宴之", terms)
    people = {item["text"] for item in entities if item["entity_type"] == "PER"}
    offices = {item["text"] for item in entities if item["entity_type"] == "OFF"}

    assert {"夏原吉", "李善長"} <= people
    assert "戶部尚書" in offices
    assert "中書省左丞相" in offices
    assert all("夏原吉" not in office and "李善長" not in office for office in offices)


def test_event_classifier_uses_phrase_context_for_ambiguous_words() -> None:
    keywords = _load_event_keywords([])

    assignment = classify_text("命夏原吉治水", keywords, threshold=0.2)
    assert assignment[0][0] == "appointment"
    assert all(event_type != "disaster" for event_type, _probability in assignment)
    assert classify_text("占城遣使來朝貢方物", keywords, threshold=0.2)[0][0] == "tribute"
    assert classify_text("都督率軍討邊", keywords, threshold=0.2)[0][0] == "military"
    assert classify_text("永樂二年封朱高熾為皇太子", keywords, threshold=0.2)[0][0] == "appointment"


def test_link_similarity_handles_close_forms() -> None:
    assert similarity("雲南衛", "云南卫") < 1.0
    assert similarity("雲南衛", "雲南衛") == 1.0
    assert similarity("雲南衛", "雲南府") > 0.5


def test_embedding_is_normalized() -> None:
    vector = embed_paragraph("洪武元年占城來朝貢", [{"entity_type": "LOC", "start": 4, "end": 6}])
    norm = math.sqrt(sum(value * value for value in vector))
    assert len(vector) == 128
    assert 0.99 <= norm <= 1.01
