from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "app.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_data_dirs() -> None:
    for name in ("corpus/raw", "exports", "imports", "models", "vectors"):
        (DATA_DIR / name).mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT NOT NULL,
  volume TEXT,
  seq INTEGER NOT NULL,
  raw_text TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_volume ON documents(volume);

CREATE TABLE IF NOT EXISTS knowledge_terms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  canonical_id TEXT,
  text TEXT NOT NULL,
  normalized_text TEXT NOT NULL,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_terms_type ON knowledge_terms(type);
CREATE INDEX IF NOT EXISTS idx_knowledge_terms_norm ON knowledge_terms(normalized_text);

CREATE TABLE IF NOT EXISTS time_mentions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  start INTEGER NOT NULL,
  end INTEGER NOT NULL,
  text TEXT NOT NULL,
  reign TEXT,
  ganzhi TEXT,
  lunar_month INTEGER,
  lunar_day INTEGER,
  ce_year INTEGER,
  calendar_date TEXT,
  date_precision TEXT NOT NULL DEFAULT 'estimated_year',
  calendar_source TEXT,
  calendar_confidence REAL,
  confidence REAL NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_time_mentions_document ON time_mentions(document_id);
CREATE INDEX IF NOT EXISTS idx_time_mentions_ce_year ON time_mentions(ce_year);

CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  start INTEGER NOT NULL,
  end INTEGER NOT NULL,
  text TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  method TEXT NOT NULL,
  confidence REAL NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_document ON entities(document_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_text ON entities(text);

CREATE TABLE IF NOT EXISTS entity_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  canonical_id TEXT,
  canonical_text TEXT NOT NULL,
  match_score REAL NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entity_links_entity ON entity_links(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_links_canonical ON entity_links(canonical_text);

CREATE TABLE IF NOT EXISTS paragraph_vectors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  model_name TEXT NOT NULL,
  vector_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_paragraph_vectors_doc_model
ON paragraph_vectors(document_id, model_name);

CREATE TABLE IF NOT EXISTS clusters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  cluster_id INTEGER NOT NULL,
  similarity REAL NOT NULL,
  label TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clusters_cluster ON clusters(cluster_id);

CREATE TABLE IF NOT EXISTS cluster_summaries (
  cluster_id INTEGER PRIMARY KEY,
  label TEXT,
  size INTEGER NOT NULL,
  keywords_json TEXT NOT NULL DEFAULT '[]',
  template_text TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  probability REAL NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_predictions_doc ON event_predictions(document_id);
CREATE INDEX IF NOT EXISTS idx_event_predictions_type ON event_predictions(event_type);

CREATE TABLE IF NOT EXISTS user_annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  annotation_type TEXT NOT NULL,
  action TEXT NOT NULL DEFAULT 'add',
  target_id INTEGER,
  start INTEGER,
  end INTEGER,
  text TEXT,
  entity_type TEXT,
  event_type TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_annotations_doc ON user_annotations(document_id);
CREATE INDEX IF NOT EXISTS idx_user_annotations_type ON user_annotations(annotation_type);

CREATE TABLE IF NOT EXISTS ai_analysis_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timeline_id TEXT NOT NULL,
  event_id INTEGER,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  target_kind TEXT NOT NULL,
  target_value TEXT NOT NULL,
  entity_id INTEGER,
  model TEXT NOT NULL,
  prompt TEXT NOT NULL,
  summary TEXT NOT NULL,
  usage_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_timeline ON ai_analysis_results(timeline_id);
CREATE INDEX IF NOT EXISTS idx_ai_analysis_document ON ai_analysis_results(document_id);

CREATE TABLE IF NOT EXISTS ai_chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timeline_id TEXT NOT NULL,
  event_id INTEGER,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  model TEXT,
  usage_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_chat_timeline ON ai_chat_messages(timeline_id);
CREATE INDEX IF NOT EXISTS idx_ai_chat_document ON ai_chat_messages(document_id);

CREATE TABLE IF NOT EXISTS model_artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  artifact_id TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,
  source_url TEXT NOT NULL,
  local_path TEXT NOT NULL,
  status TEXT NOT NULL,
  license_note TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_model_artifacts_kind ON model_artifacts(kind);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  step TEXT NOT NULL,
  status TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def init_db() -> None:
    ensure_data_dirs()
    with connect() as conn:
        conn.executescript(SCHEMA)
        migrate_db(conn)
        seed_default_terms(conn)


def migrate_db(conn: sqlite3.Connection) -> None:
    _ensure_columns(
        conn,
        "time_mentions",
        {
            "calendar_date": "TEXT",
            "date_precision": "TEXT NOT NULL DEFAULT 'estimated_year'",
            "calendar_source": "TEXT",
            "calendar_confidence": "REAL",
        },
    )


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


DEFAULT_TERMS = [
    ("surname", "SUR-ZHU", "朱", [], {"note": "Hundred Family Surnames seed"}),
    ("surname", "SUR-LI", "李", [], {"note": "Hundred Family Surnames seed"}),
    ("surname", "SUR-WANG", "王", [], {"note": "Hundred Family Surnames seed"}),
    ("surname", "SUR-ZHANG", "張", ["张"], {"note": "Hundred Family Surnames seed"}),
    ("location", "LOC-YINGTIAN", "應天", ["应天", "應天府", "应天府"], {}),
    ("location", "LOC-BEIPING", "北平", ["北京"], {}),
    ("location", "LOC-NANJING", "南京", ["金陵"], {}),
    ("location", "LOC-ZHANCHENG", "占城", [], {}),
    ("location", "LOC-YUNNAN", "雲南", ["云南"], {}),
    ("office", "OFF-ZHONGSHU", "中書省左丞相", ["中书省左丞相", "左丞相"], {}),
    ("office", "OFF-DUDU", "都督", [], {}),
    ("office", "OFF-ZHIHUISHI", "指揮使", ["指挥使"], {}),
    ("target_entity", "GARRISON-YUNNAN", "雲南衛", ["云南卫"], {"category": "wei-so"}),
    ("variant", "VAR-TAI", "臺", ["台"], {"canonical": "臺"}),
    ("variant", "VAR-GUO", "國", ["国"], {"canonical": "國"}),
    ("variant", "VAR-WEI", "衛", ["卫"], {"canonical": "衛"}),
    ("event_keyword", "EVT-MIL", "軍事", ["征", "討", "兵", "軍", "都督", "衛"], {"event_type": "military"}),
    ("event_keyword", "EVT-TRIBUTE", "朝貢", ["贡", "貢", "來朝", "遣使"], {"event_type": "tribute"}),
    ("event_keyword", "EVT-APPOINT", "任官", ["授", "陞", "升", "拜", "除", "命"], {"event_type": "appointment"}),
    ("event_keyword", "EVT-PUNISH", "刑罰", ["誅", "斬", "罰", "罪", "獄"], {"event_type": "punishment"}),
    ("event_keyword", "EVT-DISASTER", "災異", ["旱", "水", "蝗", "震", "災"], {"event_type": "disaster"}),
    ("event_keyword", "EVT-FINANCE", "財政", ["稅", "糧", "鈔", "戶部"], {"event_type": "finance"}),
]


def seed_default_terms(conn: sqlite3.Connection) -> None:
    existing = {
        (row["type"], row["canonical_id"], row["text"])
        for row in conn.execute("SELECT type, canonical_id, text FROM knowledge_terms").fetchall()
    }
    now = utc_now()
    rows = [
            (term_type, canonical_id, text, text, json_dumps(aliases), json_dumps(metadata), now)
            for term_type, canonical_id, text, aliases, metadata in DEFAULT_TERMS
            if (term_type, canonical_id, text) not in existing
    ]
    if rows:
        conn.executemany(
            """
            INSERT INTO knowledge_terms
            (type, canonical_id, text, normalized_text, aliases_json, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
