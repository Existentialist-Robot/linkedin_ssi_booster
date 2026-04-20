# Testing and Development

The project ships with a pytest suite focused on the Avatar Intelligence engine, grounding behavior, confidence scoring, integration flags, persona graph retrieval, and selection learning. The README states that all 138 tests pass with zero external API calls required.

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

Project file tree (top-level):

```
linkedin_ssi_booster/
├── main.py                  # CLI entrypoint (argparse)
├── scheduler.py             # Optimal posting-time logic
├── content_calendar.py      # 4-week topic list
├── services/
│   ├── __init__.py
│   ├── claude_service.py    # Anthropic wrapper + SSI prompt templates
│   ├── buffer_service.py    # Buffer GraphQL wrapper
│   ├── content_curator.py   # RSS fetch + summarise + create Buffer ideas
│   ├── ollama_service.py    # Ollama LLM wrapper
│   ├── github_service.py    # GitHub enrichment
│   ├── ssi_tracker.py       # SSI score tracking + report
│   ├── spacy_nlp.py         # spaCy NLP pipeline
│   ├── avatar_intelligence.py # Persona, knowledge, continual learning
│   └── shared.py            # Shared utilities/constants
├── data/
│   ├── avatar/
│   │   ├── persona_graph.json
│   │   ├── domain_knowledge.json
│   │   ├── narrative_memory.json
│   │   ├── extracted_knowledge.json
│   │   └── ...
│   └── selection/
│       └── ...
├── docs/
│   ├── features/
│   │   ├── continual-learning/idea.md
│   │   └── ...
│   ├── ai-backend-and-models.md
│   ├── architecture.md
│   ├── persona-and-avatar.md
│   ├── ssi-and-strategy.md
│   └── ...
├── tests/
│   ├── test_avatar_state_loader.py
│   ├── test_evidence_mapping.py
│   ├── test_learning_report.py
│   ├── test_confidence_scoring.py
│   ├── test_integration_flags.py
│   ├── test_persona_graph_retrieval.py
│   ├── test_selection_learning.py
│   ├── test_spacy_nlp.py
│   ├── test_continual_learning.py
│   └── fixtures/
│       └── ...
├── requirements.txt
├── README.md
└── ...
```

User-private runtime state is under `data/avatar/` and `data/selection/` (local, gitignored).
