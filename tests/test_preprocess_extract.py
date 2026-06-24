import tempfile
import unittest
from pathlib import Path

from ming_ner.extract import EntityExtractor
from ming_ner.preprocess import clean_text
from ming_ner.schema import Document


class PipelineSmokeTests(unittest.TestCase):
    def test_clean_text_removes_html_residue(self):
        text = "甲&nbsp;乙</p>\n\n\n○丙"
        self.assertEqual(clean_text(text), "甲 乙\n○丙")

    def test_extractor_finds_core_entities(self):
        doc = Document(
            doc_id="sample",
            title="sample",
            source_path="sample.txt",
            text="户部尚书臣夏原吉奏朝鲜国王李祹遣使来贡方物",
        )
        with tempfile.TemporaryDirectory() as tmp:
            extractor = EntityExtractor(cache_dir=Path(tmp), offline=True)
            entities = extractor.extract_document(doc)
        values = {(entity.type, entity.text) for entity in entities}
        self.assertIn(("OFF", "户部尚书"), values)
        self.assertIn(("PER", "夏原吉"), values)
        self.assertTrue(("LOC", "朝鲜") in values or ("LOC", "朝鲜国") in values)


if __name__ == "__main__":
    unittest.main()
