from __future__ import annotations

from fastapi.testclient import TestClient


def test_api_end_to_end_smoke(tmp_path, monkeypatch) -> None:
    from backend import db as db_module
    from backend.main import create_app

    data_dir = tmp_path / "data"
    monkeypatch.setattr(db_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_module, "DB_PATH", data_dir / "app.db")

    client = TestClient(create_app())
    client.delete("/api/corpus/documents")
    sample = "卷之一○洪武元年春正月甲子詔中書省左丞相李善長宴占城國使○永樂三年夏雲南衛都督率軍討邊"
    imported = client.post(
        "/api/corpus/import-text",
        json={"source_name": "sample.txt", "text": sample, "clear_existing": True},
    )
    assert imported.status_code == 200
    assert imported.json()["documents"] == 2

    for step in ("time", "ner", "link", "embed", "cluster", "classify"):
        response = client.post(f"/api/pipeline/{step}", json={})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "done"

    entities = client.get("/api/search/entities?q=占城").json()["items"]
    assert entities
    timeline = client.get("/api/analytics/timeline").json()["items"]
    assert timeline
    assert timeline[0]["timeline_id"].startswith("T")
    assert timeline[0]["event_type_label"]
    assert "entities" in timeline[0]
    searched_timeline = client.get("/api/analytics/timeline?q=military").json()
    assert "facets" in searched_timeline
    assert "display" in searched_timeline
    charts = client.get("/api/analytics/charts").json()
    assert any(item["timeline_ids"] for item in charts["by_event"])
    assert all("label" in item for item in charts["by_event"])
    assert all("timeline_id_preview" in item for item in charts["by_event"])
    annotation = client.post(
        "/api/annotations",
        json={
            "document_id": timeline[0]["document_id"],
            "annotation_type": "event",
            "action": "confirm",
            "event_type": "appointment",
        },
    )
    assert annotation.status_code == 200
    annotated_timeline = client.get("/api/analytics/timeline").json()["items"]
    assert "citation" in annotated_timeline[0]
    assert "annotations" in annotated_timeline[0]
    export = client.get("/api/exports/jsonl")
    assert export.status_code == 200
    assert "events" in export.text
    assert "citation" in export.text
    assert "annotations" in export.text

    display_defaults = client.get("/api/display/settings")
    assert display_defaults.status_code == 200
    assert display_defaults.json()["event_labels"]["military"] == "軍事"
    saved_display = client.put(
        "/api/display/settings",
        json={
            "event_labels": {"military": "軍務"},
            "entity_labels": {"OFF": "官位"},
            "entity_colors": {"OFF": "#123456"},
        },
    )
    assert saved_display.status_code == 200
    assert saved_display.json()["event_labels"]["military"] == "軍務"
    assert saved_display.json()["entity_colors"]["OFF"] == "#123456"


def test_research_grade_endpoints(tmp_path, monkeypatch) -> None:
    from backend import db as db_module
    from backend.main import create_app

    data_dir = tmp_path / "data"
    monkeypatch.setattr(db_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_module, "DB_PATH", data_dir / "app.db")

    client = TestClient(create_app())
    imported = client.post(
        "/api/resources/import",
        files={"file": ("terms.csv", "type,text,canonical_id,aliases,event_type\nlocation,南京,LOC-NJ,\"金陵,應天\",\n".encode("utf-8"), "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1

    status = client.get("/api/models/status")
    assert status.status_code == 200
    assert any(item["artifact_id"] == "text2vec-base-chinese" for item in status.json()["items"])

    fetch = client.post("/api/models/fetch", json={"artifact_id": "cbdb-api-cache"})
    assert fetch.status_code == 200
    assert fetch.json()["status"] == "manual_required"

    sample = "瘞豢?銝僑南京"
    corpus = client.post(
        "/api/corpus/import-text",
        json={"source_name": "research.txt", "text": sample, "clear_existing": True},
    )
    assert corpus.status_code == 200
    doc = client.get("/api/corpus/documents").json()["items"][0]
    entity_annotation = client.post(
        "/api/annotations",
        json={
            "document_id": doc["id"],
            "annotation_type": "entity",
            "action": "add",
            "text": "南京",
            "entity_type": "LOC",
        },
    )
    assert entity_annotation.status_code == 200
    assert client.post("/api/pipeline/ner", json={}).status_code == 200
    entities = client.get("/api/search/entities?q=南京").json()["items"]
    assert entities


def test_llm_settings_smoke(tmp_path, monkeypatch) -> None:
    from backend import db as db_module
    from backend.main import create_app

    data_dir = tmp_path / "data"
    monkeypatch.setattr(db_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_module, "DB_PATH", data_dir / "app.db")

    client = TestClient(create_app())
    defaults = client.get("/api/llm/settings")
    assert defaults.status_code == 200
    assert defaults.json()["has_api_key"] is False

    saved = client.put(
        "/api/llm/settings",
        json={
            "base_url": "http://127.0.0.1:9999/v1",
            "model": "local-test-model",
            "api_key": "secret-test-key",
            "prompt_template": "請分析 {timeline_id}：{text}",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["has_api_key"] is True
    assert saved.json()["api_key_preview"] == "...-key"

    cleared = client.put(
        "/api/llm/settings",
        json={
            "base_url": "http://127.0.0.1:9999/v1",
            "model": "local-test-model",
            "clear_api_key": True,
            "prompt_template": "請分析 {timeline_id}：{text}",
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["has_api_key"] is False

    test_without_key = client.post("/api/llm/test", json={})
    assert test_without_key.status_code == 400


def test_cbdb_person_update_and_llm_markdown_export(tmp_path, monkeypatch) -> None:
    from backend import db as db_module
    from backend.main import create_app
    from backend.routers import llm as llm_router
    from backend.services import cbdb as cbdb_service

    data_dir = tmp_path / "data"
    monkeypatch.setattr(db_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_module, "DB_PATH", data_dir / "app.db")

    def fake_fetch_cbdb_person(name: str, timeout: int = 20) -> list[dict[str, str]]:
        return [{"c_personid": "123", "c_name_chn": name, "c_alt_name": "維喆"}]

    def fake_chat_completion(settings, messages, max_tokens, temperature):
        return {"choices": [{"message": {"content": "這是一段測試回答。"}}], "usage": {"total_tokens": 5}}

    monkeypatch.setattr(cbdb_service, "fetch_cbdb_person", fake_fetch_cbdb_person)
    monkeypatch.setattr(llm_router, "_chat_completion", fake_chat_completion)

    client = TestClient(create_app())
    cbdb_update = client.post("/api/resources/cbdb/update", json={"names": ["夏原吉"]})
    assert cbdb_update.status_code == 200, cbdb_update.text
    assert cbdb_update.json()["imported"] == 1
    terms = client.get("/api/resources/terms?type=person_name").json()["items"]
    assert terms and terms[0]["canonical_id"] == "CBDB-123"

    corpus = client.post(
        "/api/corpus/import-text",
        json={"source_name": "ai.txt", "text": "夏原吉治水。", "clear_existing": True},
    )
    assert corpus.status_code == 200
    for step in ("ner", "link", "classify"):
        response = client.post(f"/api/pipeline/{step}", json={})
        assert response.status_code == 200, response.text
    timeline = client.get("/api/analytics/timeline").json()["items"]
    assert timeline
    assert any(entity.get("display_text") == '人名|"夏原吉"' for entity in timeline[0]["entities"])

    settings = client.put(
        "/api/llm/settings",
        json={
            "base_url": "http://127.0.0.1:9999/v1",
            "model": "mock-model",
            "api_key": "test-key",
            "prompt_template": "請分析 {timeline_id}",
        },
    )
    assert settings.status_code == 200
    timeline_id = timeline[0]["timeline_id"]
    analysis = client.post(
        "/api/llm/analyze",
        json={"timeline_id": timeline_id, "target_kind": "event", "target_value": "uncategorized"},
    )
    assert analysis.status_code == 200, analysis.text
    chat = client.post("/api/llm/chat", json={"timeline_id": timeline_id, "message": "還能怎樣解讀？"})
    assert chat.status_code == 200, chat.text
    assert len(chat.json()["saved_messages"]) == 2
    export = client.post("/api/llm/export-markdown", json={"timeline_id": timeline_id})
    assert export.status_code == 200, export.text
    with open(export.json()["path"], encoding="utf-8") as handle:
        content = handle.read()
    assert "AI 總結" in content
    assert '人名|"夏原吉"' in content
    assert "還能怎樣解讀？" in content


def test_llm_endpoint_candidates() -> None:
    from backend.routers.llm import _chat_completions_urls

    assert _chat_completions_urls("https://www.juaiapi.com/")[0] == "https://www.juaiapi.com/v1/chat/completions"
    assert _chat_completions_urls("https://api.openai.com/v1") == ["https://api.openai.com/v1/chat/completions"]
    assert _chat_completions_urls("http://localhost:1234/v1/chat/completions") == [
        "http://localhost:1234/v1/chat/completions"
    ]
