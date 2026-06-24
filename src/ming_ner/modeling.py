"""Optional Hugging Face token-classification training and inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .annotations import read_annotations
from .bioes import ID2LABEL, LABEL2ID, bioes_to_spans, spans_to_bioes


def require_transformers() -> tuple[Any, Any, Any, Any]:
    try:
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer
        from transformers import TrainingArguments, Trainer
    except ImportError as exc:
        raise RuntimeError("Training requires torch and transformers") from exc
    return torch, AutoModelForTokenClassification, AutoTokenizer, (TrainingArguments, Trainer)


class NERDataset:
    def __init__(self, records: list[dict[str, Any]], tokenizer: Any, max_length: int):
        self.items: list[dict[str, Any]] = []
        for record in records:
            text = record["text"]
            char_labels = spans_to_bioes(len(text), record.get("entities", []))
            tokens = list(text)
            encoded = tokenizer(
                tokens,
                is_split_into_words=True,
                truncation=True,
                max_length=max_length,
                padding="max_length",
            )
            word_ids = encoded.word_ids()
            label_ids = []
            for word_id in word_ids:
                if word_id is None or word_id >= len(char_labels):
                    label_ids.append(-100)
                else:
                    label_ids.append(LABEL2ID[char_labels[word_id]])
            encoded["labels"] = label_ids
            self.items.append({key: value for key, value in encoded.items()})

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.items[index]


def split_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train = [record for record in records if record.get("split") == "train"]
    dev = [record for record in records if record.get("split") in {"dev", "test"}]
    if not train:
        cutoff = max(1, int(len(records) * 0.8))
        train = records[:cutoff]
        dev = records[cutoff:] or records[:1]
    return train, dev


def train_token_classifier(
    annotations: Path,
    output_dir: Path,
    model_name: str = "bert-base-chinese",
    epochs: int = 8,
    batch_size: int = 8,
    learning_rate: float = 3e-5,
    max_length: int = 256,
) -> None:
    torch, AutoModelForTokenClassification, AutoTokenizer, trainer_bits = require_transformers()
    TrainingArguments, Trainer = trainer_bits
    records = read_annotations(annotations)
    if not records:
        raise RuntimeError(f"No annotations found: {annotations}")
    train_records, dev_records = split_records(records)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    train_data = NERDataset(train_records, tokenizer, max_length=max_length)
    dev_data = NERDataset(dev_records, tokenizer, max_length=max_length)
    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=len(ID2LABEL),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )
    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        logging_steps=20,
        save_strategy="epoch",
        eval_strategy="epoch",
        report_to=[],
    )
    trainer = Trainer(model=model, args=args, train_dataset=train_data, eval_dataset=dev_data)
    trainer.train()
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    meta = {
        "model_name": model_name,
        "labels": ID2LABEL,
        "train_records": len(train_records),
        "dev_records": len(dev_records),
        "max_length": max_length,
    }
    (output_dir / "training_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


class ModelPredictor:
    def __init__(self, model_dir: Path, max_length: int = 256):
        torch, AutoModelForTokenClassification, AutoTokenizer, _ = require_transformers()
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        self.model = AutoModelForTokenClassification.from_pretrained(str(model_dir))
        self.model.eval()
        self.max_length = max_length

    def predict(self, text: str) -> list[dict[str, Any]]:
        tokens = list(text)
        encoded = self.tokenizer(
            tokens,
            is_split_into_words=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        word_ids = encoded.word_ids()
        with self.torch.no_grad():
            outputs = self.model(**encoded)
            probs = outputs.logits.softmax(dim=-1)[0]
            pred_ids = probs.argmax(dim=-1).tolist()
            pred_scores = probs.max(dim=-1).values.tolist()
        char_labels = ["O"] * len(text)
        char_scores = [0.0] * len(text)
        seen: set[int] = set()
        for token_index, word_id in enumerate(word_ids):
            if word_id is None or word_id in seen or word_id >= len(text):
                continue
            seen.add(word_id)
            char_labels[word_id] = ID2LABEL.get(pred_ids[token_index], "O")
            char_scores[word_id] = float(pred_scores[token_index])
        spans = bioes_to_spans(char_labels, text=text)
        for span in spans:
            start = int(span["start"])
            end = int(span["end"])
            scores = char_scores[start:end] or [0.0]
            span["score"] = sum(scores) / len(scores)
            span["source"] = "model"
            span["method"] = "model-token-classifier"
            span["linked"] = None
        return spans
