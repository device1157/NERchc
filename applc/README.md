# Ming Shilu Historical Event Extraction Platform

Local web application for processing historical Chinese text into searchable entities, linked records, clustered paragraph templates, event classifications, timelines, charts, and exports.

This implementation intentionally replaces the earlier LLM distillation workflow. It uses a thesis-style pipeline: corpus import, knowledge dictionaries, time extraction, rule/CRF-style NER, entity linking, paragraph embeddings, cosine K-means clustering, and multi-class event classification.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open `http://127.0.0.1:8788` if the browser does not open automatically.

## Workflow

1. Upload or paste a Ming Shilu-style `.txt` corpus.
2. Add or edit knowledge resources: target entities, locations, official titles, aliases, character variants, surnames, and event keywords.
3. Run the six processing steps: time extraction, NER, entity linking, embedding, clustering, and classification.
4. Search entities/events and inspect timeline and charts.
5. Export JSONL or CSV for downstream analysis.

## Notes

- The first version uses offline date rules. Exact historical calendar conversion can be added through the calendar adapter later.
- External CRF++ and LIBSVM binaries are not required. Python-native fallbacks keep the system runnable on Windows.
- `data/` contains the SQLite database, uploaded corpus, vectors, and exports. It is intentionally ignored by git.
