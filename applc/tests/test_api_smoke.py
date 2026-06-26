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
    charts = client.get("/api/analytics/charts").json()
    assert any(item["timeline_ids"] for item in charts["by_event"])
    export = client.get("/api/exports/jsonl")
    assert export.status_code == 200
    assert "events" in export.text


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


def test_llm_endpoint_candidates() -> None:
    from backend.routers.llm import _chat_completions_urls

    assert _chat_completions_urls("https://www.juaiapi.com/")[0] == "https://www.juaiapi.com/v1/chat/completions"
    assert _chat_completions_urls("https://api.openai.com/v1") == ["https://api.openai.com/v1/chat/completions"]
    assert _chat_completions_urls("http://localhost:1234/v1/chat/completions") == [
        "http://localhost:1234/v1/chat/completions"
    ]
