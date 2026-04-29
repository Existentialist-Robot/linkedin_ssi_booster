# Testing and Development

The project ships with a comprehensive pytest suite covering the Avatar Intelligence engine, grounding and evidence retrieval, confidence scoring, continual learning (NLP-extracted knowledge), curation, spaCy NLP, integration flags, persona graph retrieval, and selection learning.

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
| 291         | 291    | 0      |

All tests pass as of April 29, 2026 (Python 3.12.2, pytest 9.0.3). The suite now also covers:

- Knowledge Graph subsystem (NetworkX)
- Hybrid BM25+graph retrieval and persona-aware reranking
- **Derivative of Truth framework** (truth gradient scoring, evidence/reasoning annotation, uncertainty logic)
- Avatar intelligence, curation, continual learning (NLP-extracted knowledge), learning, spaCy NLP, and all core automation features

**Derivative of Truth status:**

- All annotation logic, uncertainty calculation, and scoring tests pass (see `tests/test_derivative_of_truth.py`).
- Implementation is aligned with [design.md](features/derivative-of-truth/design.md) and [plan.md](features/derivative-of-truth/plan.md).

---

#### Test coverage by file

| Test file                               | What it covers                                                                                       |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `tests/test_avatar_state_loader.py`     | Persona graph and narrative memory loading, schema validation, and malformed-input fallback.         |
| `tests/test_buffer_service.py`          | Buffer GraphQL API wrapper, queue fetching, and idea creation.                                       |
| `tests/test_confidence_scoring.py`      | Signal extraction, score thresholds, and policy routing.                                             |
| `tests/test_content_curator.py`         | RSS curation pipeline, keyword filtering, and article processing.                                    |
| `tests/test_continual_learning.py`      | ExtractedFact/ExtractedKnowledgeGraph schema, loader, normalization, deduplication, and integration. |
| `tests/test_derivative_of_truth.py`     | Truth gradient scoring, evidence/reasoning annotation, and uncertainty logic.                        |
| `tests/test_evidence_mapping.py`        | Evidence ID stability, normalization, retrieval scoring, fallback, and explain output.               |
| `tests/test_integration_flags.py`       | CLI flag registration and invalid-value handling.                                                    |
| `tests/test_knowledge_graph.py`         | KnowledgeGraphManager, node/link schema, graph proximity, claim support, serialization, and queries. |
| `tests/test_learning_report.py`         | JSONL moderation capture, heuristics, aggregation, and report formatting.                            |
| `tests/test_persona_graph_retrieval.py` | Real persona graph loading, retrieval spot checks, and fallback logic.                               |
| `tests/test_selection_learning.py`      | Candidate logs, reconcile labeling, prior math, and ranking behavior.                                |
| `tests/test_spacy_nlp.py`               | Theme extraction, semantic similarity, and sentiment analysis (spaCy, rule-based).                   |

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
