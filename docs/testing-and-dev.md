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
| 166         | 166    | 0      |

All tests pass as of April 16, 2026. The suite covers avatar intelligence, curation, learning, spaCy NLP, and all core automation features.

---

#### Test coverage by file

| Test file                               | What it covers                                                                               |
| --------------------------------------- | -------------------------------------------------------------------------------------------- |
| `tests/test_avatar_state_loader.py`     | Persona graph and narrative memory loading, schema validation, and malformed-input fallback. |
| `tests/test_evidence_mapping.py`        | Evidence ID stability, normalization, retrieval scoring, and explain output.                 |
| `tests/test_learning_report.py`         | JSONL moderation capture, heuristics, aggregation, and report formatting.                    |
| `tests/test_confidence_scoring.py`      | Signal extraction, score thresholds, and policy routing.                                     |
| `tests/test_integration_flags.py`       | CLI flag registration and invalid-value handling.                                            |
| `tests/test_persona_graph_retrieval.py` | Real persona graph loading and retrieval spot checks.                                        |
| `tests/test_selection_learning.py`      | Candidate logs, reconcile labeling, prior math, and ranking behavior.                        |
| `tests/test_spacy_nlp.py`               | Theme extraction, semantic similarity, and sentiment analysis (spaCy, rule-based).           |

## Repository structure

The README’s file tree shows the project organized around a CLI entrypoint, services for Buffer, Ollama, curation, GitHub enrichment, and SSI tracking, plus persona data, tests, and feature docs under `docs/`. It also places user-private runtime state under `data/avatar/` and `data/selection/`, both of which are described as local and gitignored.


