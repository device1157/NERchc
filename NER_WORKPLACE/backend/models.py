from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMSettingsIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    temperature: float | None = 0
    max_tokens: int | None = 800
    timeout_seconds: int | None = 60
    concurrency: int | None = 2
    rps: float | None = 1


class EntityTypeIn(BaseModel):
    tag: str
    label: str
    definition: str = ""
    rules: str = ""
    positive_examples: list[str] = Field(default_factory=list)
    negative_examples: list[str] = Field(default_factory=list)
    color: str = "#d97706"
    freq: float | None = None


class PromptIn(BaseModel):
    name: str
    system_prompt: str
    user_template: str
    is_active: bool = False


class PromptPreviewIn(BaseModel):
    sentence: str
    type_tag: str
    type_label: str | None = None


class PreprocessIn(BaseModel):
    step: str = "all"
    filename: str | None = None
    clean_regex: str | None = None
    convert_s2t: bool = True
    min_sentence_len: int = 50
    max_sentence_len: int = 200
    sample_size: int = 600
    reset_existing: bool = True


class SampleIn(BaseModel):
    sample_size: int = 600
    stratify: bool = True


class AnnotationIn(BaseModel):
    sentence_id: int
    entity_type_tag: str
    start: int
    end: int
    text: str | None = None
    source: str = "human"
    score: float | None = None
    status: str = "added"


class AnnotationUpdateIn(BaseModel):
    id: int
    entity_type_tag: str | None = None
    start: int | None = None
    end: int | None = None
    text: str | None = None
    status: str | None = None


class ReviewConfirmIn(BaseModel):
    sentence_id: int


class SplitAssignIn(BaseModel):
    train_volumes: list[str] = Field(default_factory=list)
    test_volumes: list[str] = Field(default_factory=list)
    test_ratio: float = 0.2


class DatasetBuildIn(BaseModel):
    name: str = "reviewed_dataset"
    positive_negative_ratio: float = 2.0
    include_llm_only: bool = False
    split_ratio: float = 0.8
    config: dict[str, Any] = Field(default_factory=dict)


class TrainStartIn(BaseModel):
    dataset_id: int | None = None
    encoder: str = "hsc748NLP/GujiRoBERTa_jian_fan"
    max_len: int = 192
    batch_size: int = 8
    learning_rate: float = 5e-6
    epochs: int = 3
    use_crf: bool = False
    simulate: bool = True


class InferIn(BaseModel):
    text: str
    checkpoint_path: str | None = None

