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
| 330         | 330    | 0      |

All tests pass as of April 30, 2026 (Python 3.12.2, pytest 9.0.3). The suite now also covers:

- Knowledge Graph subsystem (NetworkX)
- Hybrid BM25+graph retrieval and persona-aware reranking (now active in production via `ContentCurator`)
- GitHub repo context enrichment (`github_service.py` now wired into `main.py`, console mode, and curation)
- **Derivative of Truth framework** (truth gradient scoring, evidence/reasoning annotation, uncertainty logic)
- **Extracted knowledge application flow** (prompt grounding injection, extracted evidence scoring paths, and adaptive topic signal)
- **Truth Gate — DoT + spaCy integration upgrade** (overlap-enriched evidence paths, per-sentence DoT scoring, spaCy similarity floor, spaCy NER org-name check)
- **Truth Gate false-positive hardening** (filters concept/service ORG false positives like `S3`, `Java 21`, and `AI Q&A`)
- **Multi-file domain knowledge loading** (`load_avatar_state()` now auto-merges `domain_knowledge_*.json` files such as Java/Python packs)
- **`content_curator` package refactor** (`services/content_curator.py` split into a proper Python package with seven focused submodules)
- **`avatar_intelligence` package refactor** (`services/avatar_intelligence.py` split into a proper Python package with ten focused submodules: `_paths`, `_models`, `_loaders`, `_normalizers`, `_retrieval`, `_grounding`, `_learning`, `_confidence`, `_narrative`, `_extraction`)
- **`console_grounding` package refactor** (`services/console_grounding.py` split into a proper Python package with focused submodules: `_config`, `_models`, `_profile_parser`, `_retrieval`, `_gate_helpers`, `_truth_gate`)
- Avatar intelligence, curation, continual learning (NLP-extracted knowledge), learning, spaCy NLP, and all core automation features

**Derivative of Truth status:**

- All annotation logic, uncertainty calculation, and scoring tests pass (see `tests/test_derivative_of_truth.py`).
- Implementation is aligned with [design.md](features/derivative-of-truth/design.md) and [plan.md](features/derivative-of-truth/plan.md).

**Truth Gate — DoT + spaCy upgrade status (April 30, 2026):**

- `EvidencePath.overlap` is now computed (Jaccard token overlap per sentence↔fact) — 4-term DoT formula is active.
- Per-sentence DoT scoring runs before the keep/remove decision; `weak_dot_gradient` is a first-class removal reason.
- spaCy `compute_similarity` floor check (`TRUTH_GATE_SPACY_SIM_FLOOR`, default `0.10`) flags numeric/org sentences with low semantic support.
- spaCy NER `ORG` extraction replaces `_ORG_NAME_RE` regex (regex fallback preserved when spaCy unavailable).
- ORG false-positive filters now skip known concept/service tokens (e.g., `S3`) and tech-version entities (e.g., `Java 21`).
- Compound tech phrases containing concept tokens (e.g., `AI Q&A`) are no longer treated as unsupported organizations.
- `TruthGateMeta` gains `dot_per_sentence_scores: list[float]` and `spacy_sim_scores: dict[str, float]`.
- Default spaCy model upgraded to `en_core_web_md` (word vectors loaded via `SPACY_MODEL` env var) — eliminates the W007 no-word-vectors warning.
- Avatar state loading now merges sibling `domain_knowledge_*.json` files (for example `domain_knowledge_java.json` and `domain_knowledge_python.json`) into one domain knowledge graph.
- See [idea.md](features/truth-gate-dot/idea.md) for full design rationale.

**Active production modules (as of April 30, 2026):**

| Module                                   | Status    | Integration point                                                                                        |
| ---------------------------------------- | --------- | -------------------------------------------------------------------------------------------------------- |
| `services/github_service.py`             | ✅ Active | `main.py` startup; context passed to `run_console()` and `ContentCurator` system prompt                  |
| `services/hybrid_retriever.py`           | ✅ Active | `ContentCurator.__init__` bootstraps KG + `HybridRetriever`; used in `_grounding_facts_for_article()`    |
| `services/ollama_service.py`             | ✅ Active | `summarise_for_curation()` injects extracted grounding context (via `build_extracted_grounding_context`) |
| `services/content_curator/curator.py`    | ✅ Active | `ContentCurator` class — orchestrates article fetching, AI generation, confidence routing, Buffer push    |
| `services/content_curator/_config.py`    | ✅ Active | RSS feeds, keywords, SSI weights/hints, env constants                                                    |
| `services/content_curator/_rss_fetcher.py` | ✅ Active | `fetch_relevant_articles()`, `fetch_article_text()`                                                    |
| `services/content_curator/_ssi_picker.py` | ✅ Active | `build_topic_signal()`, `pick_ssi_component()` — adaptive SSI component tilt from extracted facts        |
| `services/content_curator/_evidence_paths.py` | ✅ Active | Converts persona/domain/extracted facts into `EvidencePath` objects for DoT scoring                 |
| `services/content_curator/_text_utils.py` | ✅ Active | `truncate_at_sentence()`, `extract_hashtags()`, `append_url_and_hashtags()`                             |
| `services/content_curator/_grounding.py` | ✅ Active | `load_curation_grounding_keywords()`, `load_curation_grounding_tag_expansions()`                         |
| `services/console_grounding/_truth_gate.py` | ✅ Active | `truth_gate()` and `truth_gate_result()` with DoT + spaCy safety checks                                   |
| `services/console_grounding/_retrieval.py` | ✅ Active | Query constraints, deterministic fact ranking, and grounded reply construction                              |

---

#### Test coverage by file

| Test file                                  | What it covers                                                                                                                                                         |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_avatar_state_loader.py`        | Persona graph and narrative memory loading, schema validation, malformed-input fallback, and automatic merge of `domain_knowledge_*.json` sources.                   |
| `tests/test_buffer_service.py`             | Buffer GraphQL API wrapper, queue fetching, and idea creation.                                                                                                         |
| `tests/test_confidence_scoring.py`         | Signal extraction, score thresholds, and policy routing.                                                                                                               |
| `tests/test_content_curator.py`            | RSS curation pipeline, keyword filtering, article processing, topic signal, SSI component tilt, and `EvidencePath` construction — updated to reference new submodule paths. |
| `tests/test_continual_learning.py`         | ExtractedFact/ExtractedKnowledgeGraph schema, loader, normalization, deduplication, and integration.                                                                   |
| `tests/test_derivative_of_truth.py`        | Truth gradient scoring, evidence/reasoning annotation, and uncertainty logic.                                                                                          |
| `tests/test_evidence_mapping.py`           | Evidence ID stability, normalization, retrieval scoring, fallback, and explain output.                                                                                 |
| `tests/test_integration_flags.py`          | CLI flag registration and invalid-value handling.                                                                                                                      |
| `tests/test_knowledge_graph.py`            | KnowledgeGraphManager, node/link schema, graph proximity, claim support, serialization, and queries.                                                                   |
| `tests/test_learning_report.py`            | JSONL moderation capture, heuristics, aggregation, and report formatting.                                                                                              |
| `tests/test_persona_graph_retrieval.py`    | Real persona graph loading, retrieval spot checks, and fallback logic.                                                                                                 |
| `tests/test_selection_learning.py`         | Candidate logs, reconcile labeling, prior math, and ranking behavior.                                                                                                  |
| `tests/test_spacy_nlp.py`                  | Theme extraction, semantic similarity, and sentiment analysis (spaCy, rule-based). Default model is `en_core_web_md` (configurable via `SPACY_MODEL`).                 |
| `tests/test_ollama_extracted_grounding.py` | Prompt injection of extracted knowledge context into curation generation.                                                                                              |
| `tests/test_truth_gate_dot.py`             | Truth Gate — DoT + spaCy upgrade: overlap computation, per-sentence DoT scoring, spaCy similarity floor, spaCy NER org-name check, concept/service false-positive filters (`S3`, `Java 21`, `AI Q&A`), and `TruthGateMeta` field coverage. |
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
│   ├── content_curator/          # refactored package (was content_curator.py)
│   │   ├── __init__.py           # public API re-exports
│   │   ├── curator.py            # ContentCurator class
│   │   ├── _config.py            # RSS feeds, keywords, SSI weights
│   │   ├── _rss_fetcher.py       # article fetching
│   │   ├── _text_utils.py        # string helpers
│   │   ├── _evidence_paths.py    # EvidencePath builders
│   │   ├── _ssi_picker.py        # topic signal + SSI component selection
│   │   └── _grounding.py        # grounding keyword/tag loaders
│   ├── avatar_intelligence/      # refactored package (was avatar_intelligence.py)
│   │   ├── __init__.py           # public API re-exports + load_avatar_state wrapper
│   │   ├── _paths.py             # path constants (PERSONA_GRAPH_PATH, etc.)
│   │   ├── _models.py            # all dataclasses (AvatarState, EvidenceFact, etc.)
│   │   ├── _loaders.py           # schema validators + file loaders
│   │   ├── _normalizers.py       # evidence/domain/extracted fact normalization
│   │   ├── _retrieval.py         # BM25 + fallback evidence retrieval
│   │   ├── _grounding.py         # grounding context builders
│   │   ├── _learning.py          # moderation event capture + learning report
│   │   ├── _confidence.py        # confidence scoring + publish-mode routing
│   │   ├── _narrative.py         # narrative memory update + continuity context
│   │   └── _extraction.py        # spaCy fact extraction + save helpers
│   ├── console_grounding/        # refactored package (was console_grounding.py)
│   │   ├── __init__.py           # public API re-exports
│   │   ├── _config.py            # env/config knobs and keyword defaults
│   │   ├── _models.py            # ProjectFact, QueryConstraints, TruthGateMeta
│   │   ├── _profile_parser.py    # PROFILE_CONTEXT bullet parsing
│   │   ├── _retrieval.py         # deterministic retrieval + grounded replies
│   │   ├── _gate_helpers.py      # regex/BM25 helpers and evidence checks
│   │   └── _truth_gate.py        # truth gate orchestration + moderation hooks
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
