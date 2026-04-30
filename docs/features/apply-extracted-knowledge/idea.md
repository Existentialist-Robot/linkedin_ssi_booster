# Feature Idea: Apply Extracted Knowledge

## Overview

`extracted_knowledge.json` is populated every `--curate --learn` run with facts
spaCy extracts from RSS articles. The pipeline is complete up to that point:
facts are written to disk, loaded into `AvatarState.extracted_knowledge`,
normalised into `ExtractedEvidenceFact` objects with BM25-ready tokens, and a
`build_extracted_grounding_context()` helper exists to format them for prompts.

The last mile is missing: **nothing consumes them downstream**.

This feature closes that gap across four integration points.

---

## Problem Statement

The extraction pipeline was built but never wired into generation, retrieval,
scoring, or topic selection. The result is that curated articles grow a facts
log that has zero influence on what the LLM writes, what evidence the DoT
scorer uses, or what topics get prioritised — making `--learn` a bookkeeping
exercise rather than a learning loop.

---

## Proposed Solution — Four Integration Points

### 1. Prompt Grounding (highest value, lowest effort)

**What:** Inject recently extracted facts into the `summarise_for_curation()`
prompt alongside persona facts.

**Where:**

- `services/ollama_service.py` → `summarise_for_curation()`
- `services/avatar_intelligence.py` → `build_extracted_grounding_context()`
  (already built, never called)

**How:**

1. Add `extracted_facts: list[ExtractedEvidenceFact] | None = None` parameter
   to `summarise_for_curation()`.
2. Call `build_extracted_grounding_context(extracted_facts)` and append the
   result into `prompt` between the grounding block and format instructions.
3. In `content_curator.py`, resolve extracted facts from `AvatarState` using
   `normalize_extracted_facts(state)` and pass them through.
4. Cap at the N most-recent facts (env var `EXTRACTED_CONTEXT_LIMIT`, default
   `10`) to stay within context budget.

**Effect:** The LLM writes posts that reference industry events it has actually
read — not just its training weights. Post quality improves for fast-moving
topics (new model releases, framework launches, etc.).

---

### 2. BM25 Retrieval Corpus (medium effort)

**What:** Add `ExtractedEvidenceFact` facts into the hybrid retriever's BM25
corpus so the system can retrieve recently learned facts as evidence when
scoring claims.

**Where:**

- `services/hybrid_retriever.py` — corpus build step
- `services/avatar_intelligence.py` → `_extracted_fact_tokens()` (already
  built, never passed to the retriever)

**How:**

1. Extend `HybridRetriever.__init__()` (or its corpus builder) to accept
   `extracted_facts: list[ExtractedEvidenceFact]`.
2. Tokenise each fact using `_extracted_fact_tokens()` and append to the BM25
   document list alongside persona facts.
3. Tag retrieved documents with `source="extracted_knowledge"` so downstream
   consumers (DoT, explainability) can identify their origin.

**Effect:** When the truth gate or DoT scorer searches for evidence supporting
a claim about, say, "Claude persistent memory", recently extracted facts become
candidates — not just persona data. Retrieval becomes current.

---

### 3. DoT Evidence Paths (medium effort)

**What:** Build `EvidencePath` objects from `ExtractedEvidenceFact` facts, the
same way `_fact_to_evidence_path()` already builds them from persona
`ProjectFact` objects.

**Where:**

- `services/content_curator.py` → `_fact_to_evidence_path()` pattern
- `services/derivative_of_truth.py` — evidence path scoring

**How:**

1. Add `_extracted_fact_to_evidence_path(fact: ExtractedEvidenceFact, claim_text: str) -> EvidencePath`.
2. Use `EVIDENCE_TYPE_SECONDARY`, `REASONING_TYPE_STATISTICAL`, credibility
   derived from the fact's `confidence` field (`high=0.85`, `medium=0.65`,
   `low=0.45`).
3. Compute token overlap between `claim_text` and `fact.statement` (same
   formula as `_fact_to_evidence_path`).
4. In `curate_and_create_ideas()`, append extracted-fact paths to `_dot_paths`
   alongside persona-fact paths and the article path.

**Effect:** The DoT truth gradient now reflects whether the generated post
aligns with _recently learned external knowledge_, not just persona data and
the current article. The report gains a new evidence source category.

---

### 4. Adaptive Topic Selection (lower effort)

**What:** Use the tags and entities accumulating in `extracted_knowledge.json`
to bias which `content_calendar.py` topics get selected, making the weekly
topic list adaptive to what the industry is actually writing about.

**Where:**

- `content_calendar.py` or `services/content_curator.py` → `_pick_ssi_component()` / topic selection
- `services/avatar_intelligence.py` → `ExtractedKnowledgeGraph.facts`

**How:**

1. After loading `AvatarState`, aggregate tag/entity frequency from the last N
   extracted facts (env var `TOPIC_SIGNAL_WINDOW`, default `50`).
2. Build a simple frequency map: `{"anthropic": 3, "aiops": 2, "nlp": 1, …}`.
3. When selecting from the content calendar, score each topic's keyword overlap
   against the frequency map and apply a soft upweight (multiply selection
   weight by `1 + match_score`).
4. No hard overrides — the calendar remains the source of truth; extracted
   knowledge only tilts probability.

**Effect:** If the last 50 extracted facts are heavy on "agentic AI" and
"persistent memory", posts on those topics surface more frequently without
requiring manual calendar edits.

---

## Technical Considerations

- **Context budget:** Extracted facts added to prompts must be capped. Estimate
  ~60 tokens per fact; `EXTRACTED_CONTEXT_LIMIT=10` ≈ 600 tokens. Monitor
  total prompt size — Ollama context window is typically 4096–8192 tokens.
- **Relevance filtering:** Don't inject all extracted facts blindly. Filter to
  facts whose tags/entities overlap with the current article's topic before
  injecting into the prompt (same BM25 pattern used in `_grounding_facts_for_article`).
- **Staleness:** Extracted facts should carry a recency signal. Add an env var
  `EXTRACTED_KNOWLEDGE_MAX_AGE_DAYS` (default `30`) and filter out older facts
  before injection or retrieval.
- **Confidence gating:** Only inject/retrieve facts with `confidence != "low"`
  by default; expose `EXTRACTED_MIN_CONFIDENCE` env var for override.
- **Backward compatibility:** All four integration points are additive — if
  `extracted_knowledge.json` is missing or empty, existing behaviour is
  unchanged.

---

## Success Criteria

- [ ] `summarise_for_curation()` accepts and injects extracted facts into the
      prompt; output references specific recent industry events when relevant
- [ ] Hybrid retriever returns extracted-knowledge facts as BM25 candidates
- [ ] DoT `--dot-report` shows extracted-fact evidence paths with source label
      `extracted_knowledge`
- [ ] Topic selection measurably shifts toward trending tags over a 2-week run
- [ ] All existing 291 tests continue to pass; new tests cover each integration
- [ ] `--dry-run` behaviour unchanged (no side effects)
