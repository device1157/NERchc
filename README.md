# Ming Shilu Entity Extraction MVP

This workspace implements the executable MVP described in `明实录实体抽取技术方案_v2.md`.

It reads the `.txt` files in `data/`, cleans HTML/noisy text, extracts core entities with deterministic dictionaries and Ming Shilu-specific rules, optionally links person names through the CBDB JSON API with local cache, exports `entities.json`, and provides a static HTML UI for reviewing annotations.

## Quick Start

```powershell
python -m ming_ner build --input-dir data --output-dir outputs\demo --sample-chars 6000 --offline
python -m ming_ner serve --output-dir outputs\demo --port 8765
```

Then open `http://127.0.0.1:8765/ui/`.

The WebUI can now select a `.txt` file from `data/`, choose an entry range, run analysis, edit weak labels, and save reviewed gold labels.

## Outputs

- `outputs/demo/entities.json`: UI-ready annotation data.
- `outputs/demo/summary.json`: counts by entity type and source document.
- `outputs/demo/ui/index.html`: static annotation viewer.
- `outputs/demo/review/annotations/reviewed.jsonl`: saved WebUI corrections.
- `outputs/demo/review/settings.json`: weak-label and accuracy settings.

## Review and Training Workflow

1. Start the review server:

```powershell
python -m ming_ner serve --input-dir data --output-dir outputs\demo --port 8765
```

2. In the WebUI, choose a source file and entry range, then correct weak labels.

3. Train a model after collecting reviewed annotations:

```powershell
python -m ming_ner train --annotations outputs\demo\review\annotations\reviewed.jsonl --output-dir models\ming-ner-bert
```

4. Evaluate prediction JSONL against reviewed gold:

```powershell
python -m ming_ner evaluate --annotations outputs\demo\review\annotations\reviewed.jsonl --predictions outputs\predictions.jsonl --output-dir outputs\eval
```

The target is strict span+type F1 >= 0.80 for each of PER, LOC, and OFF after at least 300 reviewed segments.

## Notes

This MVP intentionally does not claim trained-model quality. It is a working baseline that matches the planned interfaces:

- `PER`: extracted from explicit official-list patterns such as `...臣夏原吉`, plus name/context rules.
- `LOC`: extracted from built-in historical place/foreign-state gazetteers and administrative suffix rules.
- `OFF`: extracted from built-in Ming official-title gazetteers and suffix rules.
- `linked`: populated by the CBDB API when online mode is enabled, otherwise left as cached/local metadata.

When gold annotations are available, a GujiBERT/CRF or GLiNER model can be added behind the same `EntityExtractor` interface and keep the UI/export layer unchanged.
