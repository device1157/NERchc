# Research Sources and Artifact Manifest

This project is local-first. External models and datasets are not committed to git; they are fetched or imported into ignored folders under `data/` when the researcher chooses to use them.

## Runtime Artifact Status

Use the app's pipeline page or API:

```powershell
.\.venv\Scripts\python.exe run.py
```

```http
GET /api/models/status
POST /api/models/fetch
```

`POST /api/models/fetch` body:

```json
{"artifact_id":"text2vec-base-chinese","force":false}
```

## Models

| Artifact ID | Purpose | Source | Local cache | License / use note | Current behavior |
| --- | --- | --- | --- | --- | --- |
| `text2vec-base-chinese` | Neural paragraph embeddings | <https://huggingface.co/shibing624/text2vec-base-chinese> | `data/models/text2vec-base-chinese/` | Review the model card before redistribution. | Used by Step 4 when available; otherwise falls back to hashed embeddings. |
| `ckip-bert-base-chinese-ner` | Optional BERT NER adapter | <https://huggingface.co/ckiplab/bert-base-chinese-ner> | `data/models/ckip-bert-base-chinese-ner/` | GPL-3.0; do not bundle into redistributed closed packages. | Used by Step 2 only when locally available; otherwise dictionary/pattern NER remains active. |

The fetch endpoint uses `huggingface_hub.snapshot_download` when the dependency is installed. If the dependency or network is unavailable, it creates a `README_FETCH.md` marker in the target cache folder with manual instructions.

## Historical Datasets

| Artifact ID | Purpose | Source | Local cache | License / use note | Current behavior |
| --- | --- | --- | --- | --- | --- |
| `cbdb-api-cache` | People, offices, aliases, and biographical IDs | <https://projects.iq.harvard.edu/cbdb> | `data/imports/cbdb/` | Use the official API and cache results for reproducibility. | The app prepares a local cache folder; researchers can import curated CSV/JSON through `/api/resources/import`. |
| `chgis-v6` | Historical place names and GIS identifiers | <https://chgis.fas.harvard.edu/data/chgis> | `data/imports/chgis-v6/` | CHGIS has non-commercial/reuse restrictions; keep downloaded data local. | The app prepares a local cache folder; researchers can import derived dictionaries through `/api/resources/import`. |

## Calendar Conversion

Exact dates are evidence-only. The pipeline stores day-level dates only when a local converter can validate the reign year plus lunar month/day. If exact conversion is unavailable or incomplete, `time_mentions` keeps the CE year estimate and records `date_precision = "estimated_year"`.

Optional local converter:

```powershell
.\.venv\Scripts\python.exe -m pip install lunardate
```

The current adapter never guesses unsupported exact dates. It records the source in `calendar_source` and confidence in `calendar_confidence`.

## Bulk Dictionary Import Format

CSV columns:

```csv
type,text,canonical_id,aliases,event_type,metadata
location,南京,LOC-NANJING,"應天,金陵",,"{""source"":""CHGIS-derived""}"
event_keyword,任命,EVT-APPOINT,"授,命",appointment,"{}"
```

JSON format:

```json
{
  "items": [
    {
      "type": "target_entity",
      "text": "夏原吉",
      "canonical_id": "CBDB-...",
      "aliases": ["夏維喆"],
      "metadata": {"source": "CBDB"}
    }
  ]
}
```

Imported rows are stored in `knowledge_terms`; duplicate skipping compares term type, normalized text, and canonical ID.
