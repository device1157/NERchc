# How It Works

This document explains how the Ming Shilu historical event extraction system works from the user interface down to the database and processing pipeline.

## 1. System Purpose

The system turns Ming Shilu-style historical text into structured research data. A user can upload or paste source text, run a rule-based processing pipeline, inspect extracted dates, entities, event types, timelines, charts, and then export the result for further analysis.

The application is local-first:

- The frontend is a plain HTML, CSS, and JavaScript single-page app.
- The backend is a FastAPI service.
- Data is stored in a local SQLite database under `data/app.db`.
- Uploaded raw text and export files live under `data/`.
- Optional AI analysis uses an OpenAI-compatible Chat Completions API configured by the user.

## 2. Runtime Flow

Start the system with:

```powershell
.\.venv\Scripts\python.exe run.py
```

The startup flow is:

1. `run.py` starts Uvicorn and serves `backend.main:app`.
2. `backend/main.py` calls `init_db()` before creating the app.
3. `init_db()` creates required SQLite tables and seeds default knowledge terms.
4. FastAPI mounts the API routers under `/api/...`.
5. FastAPI serves `frontend/index.html` at `/` and static assets from `/static`.
6. The browser loads `frontend/app.js`, which renders the navigation, stats cards, and current page.

## 3. Main Files

The project is organized into these main areas:

| Path | Role |
| --- | --- |
| `run.py` | Starts the local web server. |
| `backend/main.py` | Creates the FastAPI app, registers routers, serves frontend files. |
| `backend/db.py` | Defines SQLite path, schema, default seed terms, and DB helpers. |
| `backend/routers/` | API endpoints for corpus, resources, pipeline, search, analytics, exports, runs, and LLM. |
| `backend/services/` | Processing logic for preprocessing, time extraction, NER, linking, embeddings, clustering, classification. |
| `frontend/index.html` | Static page shell. |
| `frontend/app.js` | Single-page frontend logic and API calls. |
| `frontend/styles.css` | Visual design and responsive layout. |
| `tests/` | Smoke tests and service-level tests. |

## 4. Frontend Structure

The frontend is controlled by `frontend/app.js`. It keeps a small global `state` object:

```js
const state = {
  view: "corpus",
  stats: {},
  timelineFilters: {},
  timelineFocusId: "",
  aiResults: {},
};
```

The `views` array defines the sidebar pages:

| View | What it does |
| --- | --- |
| `corpus` | Upload or paste source text and preview parsed documents. |
| `resources` | Add and inspect knowledge terms such as places, offices, surnames, variants, and event keywords. |
| `pipeline` | Run processing steps individually or all at once. |
| `search` | Search paragraphs, entities, and events. |
| `timeline` | Display event timeline nodes with IDs and AI analysis controls. |
| `charts` | Display event, entity, year, and volume charts with timeline node IDs. |
| `exports` | Download JSONL or CSV output. |
| `settings` | Configure LLM API base link, model, API key, and analysis prompt. |

Rendering works like this:

1. `renderNav()` builds the sidebar buttons.
2. `render()` checks `state.view`.
3. The matching render function fills the `#view` panel.
4. Button handlers call backend APIs through the shared `api()` helper.
5. Errors are passed to `reportError()` and shown as toast messages.

The frontend escapes user-visible text with `escapeHtml()` before inserting source text, API errors, or model output into the DOM.

## 5. Corpus Import

Corpus import is handled by:

- Frontend: `renderCorpus()`, `uploadCorpus()`, `importText()`, `loadDocuments()`
- Backend: `backend/routers/corpus.py`
- Service: `backend/services/preprocess.py`

The user can:

- Upload a `.txt` file through `/api/corpus/upload`.
- Paste text through `/api/corpus/import-text`.
- Clear all documents through `DELETE /api/corpus/documents`.
- Preview documents through `GET /api/corpus/documents`.

When text is imported:

1. The backend decodes uploaded files using UTF-8, GB18030, Big5, or CP950 fallback rules.
2. `preprocess_text()` removes noise lines such as web/source headers.
3. Text is optionally converted to Traditional Chinese.
4. Volume markers are detected using patterns like `卷之一`.
5. Entries are split by Ming Shilu separators such as `○` and `●`.
6. Very long entries are chunked near punctuation.
7. Parsed entries are inserted into the `documents` table.

Each document row contains:

- Source file name.
- Volume.
- Sequence number.
- Raw paragraph text.
- Metadata JSON.
- Creation timestamp.

## 6. Knowledge Resources

Knowledge resources are stored in `knowledge_terms` and managed by `backend/routers/resources.py`.

Resource types include:

| Type | Used for |
| --- | --- |
| `location` | Place names and aliases. |
| `office` | Official titles and office names. |
| `target_entity` | Research-specific target entities. |
| `variant` | Character variant normalization. |
| `surname` | Person-name candidate extraction. |
| `event_keyword` | Event classification keywords. |

On startup, `seed_default_terms()` inserts default terms such as Ming reign terms, locations, offices, variant mappings, and event keywords. The seed only inserts missing default rows and does not erase user-added terms.

When a user adds a term:

1. The frontend posts to `/api/resources/terms`.
2. The backend normalizes the text with `to_traditional()` and `compact_text()`.
3. Aliases are stored as JSON.
4. Extra information such as `event_type` or variant canonical form is stored in `metadata_json`.

These resources affect later NER, linking, and event classification runs.

## 7. Pipeline Overview

The pipeline is exposed by `backend/routers/pipeline.py`. Each step is wrapped by `run_step()` from `backend/services/pipeline.py`.

`run_step()` records execution status in `pipeline_runs`:

1. Insert a row with status `running`.
2. Execute the step function.
3. Update status to `done` and store the result message.
4. If an exception occurs, update status to `error` and re-raise the error.

The UI can run each step separately or call `/api/pipeline/all`, which runs:

```text
time -> ner -> link -> embed -> cluster -> classify
```

The order matters because later steps depend on earlier tables.

## 8. Step 1: Time Extraction

Implemented in `backend/services/time_extractor.py`.

Input table:

- `documents`

Output table:

- `time_mentions`

What it does:

- Searches for Ming reign names such as `洪武`, `永樂`, `宣德`, etc.
- Reads Chinese numerals such as `元`, `三`, `十`, `廿`.
- Extracts lunar month and day if present.
- Detects sexagenary cycle terms such as `甲子`.
- Converts reign year to CE year using the `REIGN_START` map.

Example logic:

```text
永樂三年 -> 1403 + 3 - 1 = 1405
```

Each time mention records:

- Character start and end offsets.
- Matched text.
- Reign name.
- Ganzhi term.
- Lunar month and day.
- CE year if known.
- Confidence score.

Current limitation: it uses offline rules and does not yet perform exact historical calendar conversion.

## 9. Step 2: Named Entity Recognition

Implemented in `backend/services/ner.py`.

Input tables:

- `documents`
- `knowledge_terms`

Output table:

- `entities`

Entity types produced by the system:

| Entity Type | Meaning |
| --- | --- |
| `LOC` | Location. |
| `OFF` | Office or official title. |
| `TARGET` | Research target entity. |
| `PER` | Person candidate. |

NER uses three strategies:

1. Dictionary matching from `knowledge_terms`.
2. Office-title regex patterns such as terms ending with `都督`, `指揮使`, `尚書`, or `丞相`.
3. Person-name candidate extraction using known surnames and title context.

Variant terms are used during matching so that forms like simplified/traditional variants can still match. Overlapping entity candidates are resolved by preferring earlier, longer, and higher-confidence matches.

## 10. Step 3: Entity Linking

Implemented in `backend/services/linker.py`.

Input tables:

- `entities`
- `knowledge_terms`

Output table:

- `entity_links`

What linking does:

1. Normalize the extracted entity text.
2. Compare it against allowed knowledge term types.
3. Score candidates using weighted edit distance.
4. Add a small bonus when the first character matches.
5. Keep links with score at least `0.58`.

The mapping from entity type to possible knowledge term types is:

| Entity Type | Candidate term types |
| --- | --- |
| `LOC` | `location`, `target_entity` |
| `OFF` | `office` |
| `TARGET` | `target_entity`, `location` |
| `PER` | `target_entity` |

The result links an extracted mention to a canonical ID and canonical text.

## 11. Step 4: Paragraph Embeddings

Implemented in `backend/services/embedding.py`.

Input tables:

- `documents`
- `entities`

Output table:

- `paragraph_vectors`

The current embedding method is a lightweight fallback named:

```text
char-entity-hash-dbow-v1
```

It creates a 128-dimensional vector from:

- Individual Chinese characters.
- Character bigrams.
- Entity type markers such as `<LOC>`.
- Entity-specific markers such as `<OFF:都督>`.

Tokens are hashed into vector dimensions with a signed hashing trick, then normalized. This avoids requiring a heavy external ML model while still giving usable similarity features for clustering.

## 12. Step 5: Clustering

Implemented in `backend/services/clustering.py`.

Input table:

- `paragraph_vectors`

Output tables:

- `clusters`
- `cluster_summaries`

What clustering does:

1. Load vectors for all documents.
2. Choose `k` automatically as approximately `sqrt(n)`, limited to 2-8 clusters, unless the API request provides `k`.
3. Run cosine K-means.
4. Store each document's cluster assignment and similarity to its centroid.
5. Store a summary per cluster with common bigram keywords and a short template text.

This lets the system group similar paragraph patterns, which can support thesis-style template analysis.

## 13. Step 6: Event Classification

Implemented in `backend/services/classifier.py`.

Input tables:

- `documents`
- `knowledge_terms` where `type = event_keyword`

Output table:

- `event_predictions`

The classifier uses keyword scoring:

1. Load event keywords from user knowledge terms.
2. Merge them with built-in defaults for categories such as `military`, `appointment`, `tribute`, `punishment`, `disaster`, and `finance`.
3. Count keyword occurrences in each paragraph.
4. Weight longer keywords slightly more.
5. Normalize scores into probabilities.
6. Store every event type above the threshold.
7. If no event keyword matches, store `uncategorized`.

The default threshold is `0.2`. The output source is currently labeled `keyword_svm_fallback`, meaning it is a Python-native fallback that can later be replaced with a trained classifier.

## 14. Timeline

The timeline page is powered by `GET /api/analytics/timeline`.

The query can filter by:

- `timeline_id`
- `event_type`
- `entity`
- `limit`

Each timeline item combines:

- `event_predictions`
- `documents`
- `time_mentions`
- `entities`

Timeline IDs are generated from `event_predictions.id`:

```text
event_predictions.id = 1 -> T0001
event_predictions.id = 23 -> T0023
```

This ID is important because the statistics charts also display the timeline IDs involved in each count. A user can click an ID in the chart and jump back to the matching timeline node.

Each timeline node shows:

- Timeline ID.
- CE year or `未定年`.
- Event type.
- Original paragraph text.
- Historical date strings.
- Probability.
- Related entity chips.
- A dropdown for choosing event or entity as AI analysis target.
- An `AI 分析` button.

## 15. Statistics Charts

The charts page is powered by `GET /api/analytics/charts`.

It returns four chart groups:

| Group | Source |
| --- | --- |
| `by_event` | Counts rows in `event_predictions` by event type. |
| `by_entity_type` | Counts extracted entities by entity type. |
| `by_year` | Counts documents by extracted CE year. |
| `by_volume` | Counts documents by volume. |

Each chart row also includes related timeline IDs where available. This fixes the problem where a user could see `appointment = 2` or `military = 2` but not know which timeline nodes created those counts.

In the frontend:

1. `renderBars()` draws the bar.
2. It displays `timeline_ids` as clickable chips.
3. Clicking a chip calls `openTimelineId()`.
4. The app switches to the timeline page and filters by that ID.

## 16. Search

Search is implemented in `backend/routers/search.py`.

The frontend lets the user choose:

- Paragraph search.
- Entity search.
- Event search.

The API endpoints are:

| Endpoint | Searches |
| --- | --- |
| `GET /api/search/paragraphs` | `documents.raw_text`, with optional entity and event filters. |
| `GET /api/search/entities` | Entity text and linked canonical text. |
| `GET /api/search/events` | Event predictions, optionally filtered by event type and year range. |

Search results include enough context to show original paragraph text, event type, entity type, canonical text, CE year, and source volume.

## 17. Exports

Exports are implemented in `backend/routers/exports.py`.

Supported export formats:

| Endpoint | Output |
| --- | --- |
| `GET /api/exports/jsonl` | One JSON object per document. |
| `GET /api/exports/csv` | Table with document ID, volume, sequence, CE year, events, entities, and text. |

The JSONL export includes:

- Document metadata.
- Time mentions.
- Entities.
- Entity links.
- Event predictions.

The CSV export is flatter and easier to open in spreadsheet tools.

## 18. LLM Settings and AI Analysis

LLM support is implemented in:

- Frontend: settings page and timeline `AI 分析` button.
- Backend: `backend/routers/llm.py`.
- Database: `app_settings`.

The settings page stores:

- API base link.
- Model name.
- API key.
- Prompt template.

API keys are stored locally in SQLite. The backend does not return the full key to the frontend. It only returns:

- `has_api_key`
- `api_key_preview`

The system uses OpenAI-compatible Chat Completions format. A request is sent with:

```json
{
  "model": "...",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "temperature": 0.2,
  "max_tokens": 900
}
```

Endpoint handling is flexible:

- If the base link ends with `/chat/completions`, that full endpoint is used.
- If the base link ends with `/v1`, the backend appends `/chat/completions`.
- If the base link is a root URL, the backend tries `/v1/chat/completions` first, then `/chat/completions`.

The test button sends a tiny prompt asking the model to reply `OK`.

AI analysis works like this:

1. User chooses a timeline node.
2. User selects either the event type or one extracted entity as target.
3. Frontend posts to `/api/llm/analyze`.
4. Backend loads the timeline context from the database.
5. Backend fills the prompt with context variables.
6. Backend calls the configured LLM API.
7. The model answer is returned and shown in the timeline node.

Prompt variables available to the user include:

| Variable | Meaning |
| --- | --- |
| `{timeline_id}` | Timeline node ID such as `T0001`. |
| `{document_id}` | Database document ID. |
| `{event_id}` | Event prediction ID. |
| `{target_kind}` | `event` or `entity`. |
| `{target_value}` | Selected event type or entity text. |
| `{event_type}` | Predicted event type. |
| `{probability}` | Event probability. |
| `{volume}` | Source volume. |
| `{seq}` | Document sequence number. |
| `{ce_year}` | Extracted CE year or unknown marker. |
| `{historical_dates}` | Extracted historical date strings. |
| `{entities}` | Related entities in the paragraph. |
| `{text}` | Original paragraph text. |

## 19. Database Tables

The SQLite schema is defined in `backend/db.py`.

| Table | Purpose |
| --- | --- |
| `documents` | Imported paragraph-level corpus records. |
| `knowledge_terms` | User and default dictionaries for resources, variants, and events. |
| `time_mentions` | Extracted date and reign mentions. |
| `entities` | Extracted entity mentions. |
| `entity_links` | Canonical links for extracted entities. |
| `paragraph_vectors` | Hashed paragraph embedding vectors. |
| `clusters` | Document-to-cluster assignments. |
| `cluster_summaries` | Cluster labels, keywords, and representative text. |
| `event_predictions` | Event types and probabilities per document. |
| `pipeline_runs` | Execution history for pipeline steps. |
| `app_settings` | Local settings such as LLM config and prompt template. |

Most processing output tables reference `documents.id` with cascading delete. Clearing the corpus deletes documents and automatically clears dependent rows.

## 20. API Map

Main API groups:

| Prefix | Router | Responsibility |
| --- | --- | --- |
| `/api/corpus` | `corpus.py` | Import, upload, list, stats, clear corpus. |
| `/api/resources` | `resources.py` | Manage knowledge terms. |
| `/api/pipeline` | `pipeline.py` | Run processing steps. |
| `/api/search` | `search.py` | Search paragraphs, entities, events. |
| `/api/analytics` | `analytics.py` | Timeline and charts. |
| `/api/exports` | `exports.py` | JSONL and CSV export. |
| `/api/runs` | `runs.py` | Pipeline run history. |
| `/api/llm` | `llm.py` | LLM settings, connection test, AI analysis. |

## 21. Testing

Tests live in `tests/`.

`tests/test_api_smoke.py` checks:

- End-to-end corpus import.
- All pipeline steps.
- Entity search.
- Timeline output.
- Chart timeline IDs.
- Export output.
- LLM settings save and masking.
- LLM endpoint candidate generation.

`tests/test_services.py` checks service-level behavior such as preprocessing, time extraction, NER, linking, embeddings, clustering, and classification.

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 22. Typical User Workflow

A complete workflow looks like this:

1. Open the app in the browser.
2. Go to `語料`.
3. Upload a `.txt` file or paste source text.
4. Go to `知識資源` and adjust dictionaries if needed.
5. Go to `處理流程`.
6. Run the full pipeline.
7. Go to `時間軸` to inspect extracted events.
8. Go to `統計圖` to understand distribution and click node IDs for evidence.
9. Go to `設定` to configure LLM access and prompt.
10. Return to `時間軸`, choose a node, and run `AI 分析`.
11. Go to `導出` to download JSONL or CSV.

## 23. Current Limitations

The current implementation is designed as a runnable thesis-style MVP. Some parts are intentionally lightweight:

- Date conversion is rule-based and does not yet convert exact lunar dates.
- NER is rule/dictionary-based rather than a trained CRF model.
- Embeddings are hashed character/entity vectors rather than a neural embedding model.
- Clustering uses a Python-native K-means fallback.
- Event classification uses keyword scoring rather than a trained SVM or transformer.
- LLM analysis depends on a user-provided external API and API key.

These limitations are also extension points. The code is organized so each service can be replaced by a stronger model later while keeping the database and UI flow stable.

## 24. Extension Ideas

Possible future improvements:

- Add exact Chinese calendar conversion.
- Add editable correction UI for dates, entities, and event labels.
- Add trained NER and event classification models.
- Store AI analysis results in a dedicated table.
- Add source citation export with timeline IDs.
- Add chart filters for volume, year range, event type, and entity.
- Add import/export for knowledge resource dictionaries.

