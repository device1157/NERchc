import json
import tempfile
import unittest
from pathlib import Path

from ming_ner.annotations import AnnotationValidationError, read_annotations, validate_annotation
from ming_ner.bioes import bioes_to_spans, spans_to_bioes
from ming_ner.data_api import document_entries, list_data_files
from ming_ner.export import analyze_selection_payload
from ming_ner.metrics import strict_entity_metrics
from ming_ner.preprocess import load_document


class ReviewWorkflowTests(unittest.TestCase):
    def test_data_file_listing_excludes_non_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("○甲", encoding="utf-8")
            (root / "b.md").write_text("skip", encoding="utf-8")
            files = list_data_files(root)
        self.assertEqual([item["name"] for item in files], ["a.txt"])

    def test_entry_parsing_offsets_are_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.txt"
            path.write_text("卷之一\n○甲乙\n○丙丁", encoding="utf-8")
            doc = load_document(path)
            entries = document_entries(doc)
        self.assertEqual(entries[0]["start"], 0)
        self.assertEqual(doc.text[entries[1]["start"]], "○")
        self.assertIn("甲乙", entries[1]["preview"])

    def test_analyze_selection_returns_only_selected_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            out = root / "out"
            data.mkdir()
            (data / "sample.txt").write_text("卷之一\n○户部尚书臣夏原吉奏\n○朝鲜国王来贡", encoding="utf-8")
            payload = analyze_selection_payload(data, out, "sample.txt", 3, 3, offline=True)
        self.assertIn("朝鲜", payload["text"])
        self.assertNotIn("夏原吉", payload["text"])

    def test_annotation_validation_checks_span_text(self):
        record = {
            "id": "x",
            "text": "臣夏原吉奏",
            "entities": [{"start": 1, "end": 4, "type": "PER", "text": "夏原吉"}],
        }
        self.assertEqual(validate_annotation(record)["entities"][0]["text"], "夏原吉")
        bad = {
            "id": "x",
            "text": "臣夏原吉奏",
            "entities": [{"start": 1, "end": 4, "type": "PER", "text": "错"}],
        }
        with self.assertRaises(AnnotationValidationError):
            validate_annotation(bad)

    def test_bioes_round_trip(self):
        text = "臣夏原吉奏"
        entities = [{"start": 1, "end": 4, "type": "PER", "text": "夏原吉"}]
        labels = spans_to_bioes(len(text), entities)
        spans = bioes_to_spans(labels, text=text)
        self.assertEqual(spans, [{"start": 1, "end": 4, "type": "PER", "text": "夏原吉"}])

    def test_metrics_require_300_segments_and_per_type_f1(self):
        gold = [
            {
                "id": "one",
                "text": "臣夏原吉奏",
                "entities": [{"start": 1, "end": 4, "type": "PER", "text": "夏原吉"}],
            }
        ]
        metrics, errors = strict_entity_metrics(gold, gold, min_reviewed_segments=300)
        self.assertEqual(metrics["status"], "not_enough_reviewed_data")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
