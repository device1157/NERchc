from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "app.db"


class Base(DeclarativeBase):
    pass


def now() -> datetime:
    return datetime.utcnow()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, default=1)
    volume: Mapped[str | None] = mapped_column(String(100))
    seq: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    sentences: Mapped[list["Sentence"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Sentence(Base):
    __tablename__ = "sentences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_offset: Mapped[int] = mapped_column(Integer, default=0)
    sampled: Mapped[bool] = mapped_column(Boolean, default=False)
    split: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="pending")

    document: Mapped[Document] = relationship(back_populates="sentences")
    annotations: Mapped[list["Annotation"]] = relationship(back_populates="sentence", cascade="all, delete-orphan")


class EntityType(Base):
    __tablename__ = "entity_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, default=1)
    tag: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    definition: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[str] = mapped_column(Text, default="")
    positive_examples: Mapped[str] = mapped_column(Text, default="[]")
    negative_examples: Mapped[str] = mapped_column(Text, default="[]")
    color: Mapped[str] = mapped_column(String(30), default="#d97706")
    freq: Mapped[float | None] = mapped_column(Float)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id"), nullable=False)
    entity_type_tag: Mapped[str] = mapped_column(String(30), nullable=False)
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="llm")
    score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="unconfirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    sentence: Mapped[Sentence] = relationship(back_populates="annotations")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id"), nullable=False)
    entity_type_tag: Mapped[str] = mapped_column(String(30), nullable=False)
    is_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    response_text: Mapped[str | None] = mapped_column(Text)
    parsed_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error_msg: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class TrainRun(Base):
    __tablename__ = "train_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, default=1)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"))
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    progress_json: Mapped[str] = mapped_column(Text, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    checkpoint_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    ref_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


DEFAULT_ENTITY_TYPES = [
    {
        "tag": "PER",
        "label": "人名",
        "definition": "明实录文本中的具体人物姓名、封号或可唯一指代个人的称谓。",
        "rules": "排除年号、庙号、泛称。边界只取人名本体，不含官职。",
        "positive_examples": ["李善長", "朱元璋"],
        "negative_examples": ["洪武", "皇帝"],
        "color": "#c2410c",
    },
    {
        "tag": "LOC",
        "label": "地名",
        "definition": "国家、州府县、山川关隘等地理实体。",
        "rules": "边界保留完整地名；单字地名默认需人工复核。",
        "positive_examples": ["占城", "中都"],
        "negative_examples": ["天下"],
        "color": "#047857",
    },
    {
        "tag": "OFF",
        "label": "官职",
        "definition": "官署、官名、职衔、爵位等制度性身份称谓。",
        "rules": "优先保留完整官职短语，不含任职者姓名。",
        "positive_examples": ["中書省左丞相", "翰林學士"],
        "negative_examples": ["其臣"],
        "color": "#1d4ed8",
    },
]

DEFAULT_SYSTEM_PROMPT = """你是明实录命名实体识别标注员。请只依据给定句子抽取指定类型实体。

实体定义：
{schema}

输出要求：
1. 只输出 JSON 数组。
2. 数组元素格式为 {"text": "实体原文", "type": "短标签", "score": 0.0到1.0}。
3. 若没有该类型实体，输出 []。
4. 不要改写原文，不要输出解释。"""

DEFAULT_USER_TEMPLATE = "句子：{sentence}\n请抽取实体类型：{type_label}（{type_tag}）。"


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.get(Project, 1) is None:
            db.add(Project(id=1, name="default"))
        if db.query(EntityType).count() == 0:
            for item in DEFAULT_ENTITY_TYPES:
                db.add(
                    EntityType(
                        project_id=1,
                        tag=item["tag"],
                        label=item["label"],
                        definition=item["definition"],
                        rules=item["rules"],
                        positive_examples=json_dumps(item["positive_examples"]),
                        negative_examples=json_dumps(item["negative_examples"]),
                        color=item["color"],
                    )
                )
        if db.query(PromptTemplate).count() == 0:
            db.add(
                PromptTemplate(
                    project_id=1,
                    name="默认 UniNER 单类型模板",
                    system_prompt=DEFAULT_SYSTEM_PROMPT,
                    user_template=DEFAULT_USER_TEMPLATE,
                    is_active=True,
                )
            )
        db.commit()


def row_to_dict(row: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        data[column.name] = value
    return data

