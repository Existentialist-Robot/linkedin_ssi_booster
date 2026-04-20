# Testing and Development

The project ships with a comprehensive pytest suite covering the Avatar Intelligence engine, grounding and evidence retrieval, confidence scoring, continual learning (NLP-extracted knowledge), curation, spaCy NLP, integration flags, persona graph retrieval, and selection learning. The README states that all 201 tests pass with zero external API calls required.

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

For tests that depend on environment variables such as `BUFFER_API_KEY`, the README recommends loading `.env` values with `python-dotenv`, including `python -m dotenv run -- python -m pytest tests/test_buffer_service.py -v`.

## Test coverage and results (latest)

### Summary

| Total tests | Passed | Failed |
| ----------- | ------ | ------ |
| 201         | 201    | 0      |

All tests pass as of April 19, 2026. The suite covers avatar intelligence, curation, continual learning (NLP-extracted knowledge), learning, spaCy NLP, and all core automation features.

---

#### Test coverage by file

| Test file                               | What it covers                                                                                       |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `tests/test_avatar_state_loader.py`     | Persona graph and narrative memory loading, schema validation, and malformed-input fallback.         |
| `tests/test_evidence_mapping.py`        | Evidence ID stability, normalization, retrieval scoring, fallback, and explain output.               |
| `tests/test_learning_report.py`         | JSONL moderation capture, heuristics, aggregation, and report formatting.                            |
| `tests/test_confidence_scoring.py`      | Signal extraction, score thresholds, and policy routing.                                             |
| `tests/test_integration_flags.py`       | CLI flag registration and invalid-value handling.                                                    |
| `tests/test_persona_graph_retrieval.py` | Real persona graph loading, retrieval spot checks, and fallback logic.                               |
| `tests/test_selection_learning.py`      | Candidate logs, reconcile labeling, prior math, and ranking behavior.                                |
| `tests/test_spacy_nlp.py`               | Theme extraction, semantic similarity, and sentiment analysis (spaCy, rule-based).                   |
| `tests/test_continual_learning.py`      | ExtractedFact/ExtractedKnowledgeGraph schema, loader, normalization, deduplication, and integration. |

## Repository structure

yt-vid-data/ # YouTube video text and media

Project file tree (top-level):

```
├── main.py
├── scheduler.py
├── content_calendar.py
├── requirements.txt
├── README.md
├── services/
│   ├── avatar_intelligence.py
│   ├── buffer_service.py
│   ├── ...
├── data/
│   ├── avatar/
│   └── selection/
├── docs/
│   ├── features/
│   └── ...
├── tests/
│   ├── test_*.py
│   └── fixtures/
├── media/
├── yt-vid-data/
└── ...
```

User-private runtime state is under `data/avatar/` and `data/selection/` (local, gitignored).
