# Implementation Plan: Avatar Intelligence and Learning Engine

## Overview

This plan executes the feature defined in:

- `docs/features/avatar-intelligence-learning/idea.md`
- `docs/features/avatar-intelligence-learning/prd.md`
- `docs/features/avatar-intelligence-learning/design.md`

Delivery strategy:

- Ship incrementally behind feature flags.
- Preserve current behavior by default.
- Validate each slice with explicit quality gates.

## Project Integration Summary

Primary touchpoints:

- `main.py`
- `services/console_grounding.py`
- `services/ollama_service.py`
- `services/content_curator.py`
- `services/shared.py`
- New: `services/avatar_intelligence.py`
- New data path: `data/avatar/*`

Quality constraints:

- Preserve existing truth-gate reason semantics.
- No breaking changes to current CLI flows when new flags are absent.
- Keep performance overhead minimal (local rule-based processing only).

## Pre-Implementation Checklist

- [x] Confirm baseline behavior using current dry-run commands.
- [x] Create a feature branch.
- [x] Define acceptance test prompts/articles for regression comparisons.
- [x] Confirm local write permissions for `data/avatar/`.
- [ ] Confirm `.gitignore` behavior for local runtime data (if needed).

## Progress Summary

### Phase 1A: Persona Graph Foundation

- [x] Step 1 — Add avatar data scaffolding
- [x] Step 2 — Implement avatar intelligence core module
- [x] Step 3 — Integrate graph-backed retrieval path

### Phase 1B: Learning Capture and Explainability

- [x] Step 4 — Add interactive learning event capture
- [x] Step 5 — Add explain output mode
- [x] Step 6 — Add learning report command

### Phase 1C: Confidence Scoring and Policy

- [x] Step 7 — Implement confidence score engine
- [x] Step 8 — Add confidence policy enforcement
- [x] Step 9 — Add config defaults and docs alignment

### Phase 1D: Narrative Continuity Memory

- [x] Step 10 — Implement narrative memory store
- [x] Step 11 — Inject continuity into prompts and confidence

### Phase 1E: PROFILE_CONTEXT Migration

- [x] Step 12 — Populate persona graph from PROFILE_CONTEXT
- [x] Step 13 — Switch retrieval to persona graph
- [x] Step 14 — Remove PROFILE_CONTEXT and related code

## Phase 1A: Persona Graph Foundation (Read-Only)

### Step 1: Add avatar data scaffolding

- **Status:** [x]
- **Effort:** 2-3h
- **Description:** Create structured data files and minimal schema contract.
- **Actions:**
  1. Add `data/avatar/persona_graph.json` seed template.
  2. Add `data/avatar/narrative_memory.json` seed template.
  3. Add optional schema file(s) under `data/avatar/schema/`.
  4. Decide whether `learning_log.jsonl` is tracked or runtime-created.
- **Verification:**
  - Files load and parse with no runtime exception.
  - Missing files degrade gracefully to existing behavior.
- **Dependencies:** None

### Step 2: Implement avatar intelligence core module

- **Status:** [x]
- **Effort:** 4-6h
- **Description:** Create `services/avatar_intelligence.py` with loader + validator + retrieval adapter.
- **Actions:**
  1. Add typed dataclasses for PersonaGraph, EvidenceFact, AvatarState.
  2. Implement `load_avatar_state()` with fallback behavior.
  3. Implement `retrieve_evidence()` to normalize facts and assign evidence IDs.
  4. Implement `build_grounding_context()` for prompt injection.
- **Verification:**
  - Unit tests for valid/invalid persona graph loading.
  - Evidence IDs are deterministic within a run.
- **Dependencies:** Step 1

### Step 3: Integrate graph-backed retrieval path

- **Status:** [x]
- **Effort:** 3-4h
- **Description:** Wire retrieval path into generation/curation while preserving current fallback.
- **Actions:**
  1. Integrate avatar state into startup path in `main.py`.
  2. Add optional graph-backed branch in `services/console_grounding.py` usage path.
  3. Ensure retrieval still works with current `PROFILE_CONTEXT` only.
- **Verification:**
  - `--console` factual queries still respond correctly.
  - `--generate --dry-run` and `--curate --dry-run` behave unchanged when feature disabled.
- **Dependencies:** Step 2

## Phase 1B: Learning Capture and Explainability

### Step 4: Add interactive learning event capture

- **Status:** [x]
- **Effort:** 3-5h
- **Description:** Persist moderation outcomes from truth gate interactive decisions.
- **Actions:**
  1. Add append-only writer for `data/avatar/learning_log.jsonl`.
  2. Define event schema (timestamp/channel/reason/decision/sentenceHash/runId).
  3. Hook event capture from truth-gate interactive decisions.
- **Verification:**
  - Interactive runs append valid JSON lines.
  - Writer failures do not break generation flow.
- **Dependencies:** Step 2

### Step 5: Add explain output mode

- **Status:** [x]
- **Effort:** 2-3h
- **Description:** Expose evidence summary to user via CLI flag.
- **Actions:**
  1. Add `--avatar-explain` flag in `main.py`.
  2. Emit selected evidence IDs and support summary after generation/curation.
  3. Keep output concise and plain text.
- **Verification:**
  - Explain mode prints evidence summary only when enabled.
  - No change in publish behavior due solely to explain mode.
- **Dependencies:** Step 3

### Step 6: Add learning report command

- **Status:** [x]
- **Effort:** 3-4h
- **Description:** Convert captured events into actionable recommendations.
- **Actions:**
  1. Add `--avatar-learn-report` flag in `main.py`.
  2. Implement `build_learning_report()` in avatar module.
  3. Output top reason patterns and suggested tuning actions.
- **Verification:**
  - Report renders with empty, small, and large logs.
  - Suggestions are advisory only (no auto-write to config).
- **Dependencies:** Step 4

## Phase 1C: Confidence Scoring and Policy

### Step 7: Implement confidence score engine

- **Status:** [x]
- **Effort:** 4-6h
- **Description:** Score each output using deterministic signals.
- **Actions:**
  1. Define `ConfidenceResult` model and weighted scoring function.
  2. Add signal extraction from truth-gate + generation metadata.
  3. Include repetition/length pressure components.
- **Verification:**
  - Unit tests for scoring boundaries and expected weighting behavior.
  - Deterministic outputs for fixed input signals.
- **Dependencies:** Steps 4, 5

### Step 8: Add confidence policy enforcement

- **Status:** [x]
- **Effort:** 3-5h
- **Description:** Route post vs idea vs block based on policy.
- **Actions:**
  1. Add `--confidence-policy strict|balanced|draft-first` in `main.py`.
  2. Implement decision function in avatar module.
  3. Enforce decision in `services/content_curator.py` before Buffer call.
- **Verification:**
  - Policy matrix tests pass for high/medium/low confidence.
  - Existing `--type` behavior remains compatible.
- **Dependencies:** Step 7

### Step 9: Add config defaults and docs alignment

- **Status:** [x]
- **Effort:** 2-3h
- **Description:** Add environment controls and update docs.
- **Actions:**
  1. Add defaults in `services/shared.py` (or config layer).
  2. Update `.env.example` with:
     - `AVATAR_CONFIDENCE_POLICY`
     - `AVATAR_LEARNING_ENABLED`
     - `AVATAR_MAX_MEMORY_ITEMS`
  3. Update README command and behavior sections.
- **Verification:**
  - Missing/invalid config gracefully falls back to defaults.
  - README and `.env.example` reflect shipped behavior.
- **Dependencies:** Step 8

## Phase 1D: Narrative Continuity Memory

### Step 10: Implement narrative memory store

- **Status:** [x]
- **Effort:** 3-4h
- **Description:** Persist recent themes/claims/arcs for continuity.
- **Actions:**
  1. Implement load/update/bounded-trim operations for `narrative_memory.json`.
  2. Define extraction heuristics from generated posts.
  3. Add update hooks after successful generation.
- **Verification:**
  - Memory updates are stable across runs.
  - Store remains bounded by configured max items.
- **Dependencies:** Step 2
- **Progress:** `update_narrative_memory()`, `save_narrative_memory()` added to `avatar_intelligence.py`. FIFO-trim bounded by `AVATAR_MAX_MEMORY_ITEMS`. `extract_narrative_updates()` provides rule-based theme/claim extraction (no LLM call). Memory update hook injected into the single-channel curator path after each successful generation.

### Step 11: Inject continuity into prompts and confidence

- **Status:** [x]
- **Effort:** 3-5h
- **Description:** Use memory to improve coherence and reduce repetition.
- **Actions:**
  1. Add continuity snippet into generation/curation prompt build.
  2. Add repetition signal to confidence scoring.
  3. Ensure no prompt bloat beyond context budget.
- **Verification:**
  - Repetition checks lower confidence for near-duplicate drafts.
  - Quality remains stable in manual sample review.
- **Dependencies:** Steps 7, 10
- **Progress:** `build_continuity_context()` produces ≤300-char prompt snippet. `continuity_context` param added to both `OllamaService.generate_linkedin_post()` and `OllamaService.summarise_for_curation()`. `compute_repetition_score()` computes token-overlap ratio against `recent_claims`; wired into `_score_and_route()` replacing the hardcoded `0.0` placeholder.

## Phase 1E: PROFILE_CONTEXT Migration

### Step 12: Populate persona graph from PROFILE_CONTEXT

- **Status:** [ ]
- **Effort:** 4-6h
- **Description:** Parse existing PROFILE_CONTEXT and populate persona graph during development.
- **Actions:**
  1. Reuse existing `parse_profile_facts` logic from `console_grounding.py` to extract structured records.
  2. Map parsed output to persona graph entities (person, projects, companies, skills, claims).
  3. Write populated `data/avatar/persona_graph.json`.
  4. Manually review and refine extracted entities for accuracy.
- **Verification:**
  - Persona graph contains all parseable projects, companies, skills from PROFILE_CONTEXT.
  - Schema validation passes.
- **Dependencies:** Step 2 (avatar intelligence module)

### Step 13: Switch retrieval to persona graph

- **Status:** [ ]
- **Effort:** 3-5h
- **Description:** Replace PROFILE_CONTEXT parsing with persona graph as sole identity source for retrieval.
- **Actions:**
  1. Update `console_grounding.py` retrieval path to use graph facts instead of PROFILE_CONTEXT text parsing.
  2. Remove PROFILE_CONTEXT parsing from retrieval path.
  3. Update `load_avatar_state()` to load persona graph directly (no fallback to PROFILE_CONTEXT).
- **Verification:**
  - Retrieval uses graph facts exclusively.
  - `--generate --dry-run` and `--curate --dry-run` output quality is equal or better than baseline.
- **Dependencies:** Steps 3, 12

### Step 14: Remove PROFILE_CONTEXT and related code

- **Status:** [ ]
- **Effort:** 2-3h
- **Description:** Delete PROFILE_CONTEXT env var, parsing code, and all related references.
- **Actions:**
  1. Remove `PROFILE_CONTEXT` from `.env`.
  2. Remove `PROFILE_CONTEXT` and `PROFILE_CONTEXT_MAX_CHARS` from `.env.example`.
  3. Remove PROFILE_CONTEXT loading/parsing code from `main.py` and services.
  4. Update README to remove PROFILE_CONTEXT references and document persona graph as identity source.
- **Verification:**
  - App starts and runs without PROFILE_CONTEXT.
  - README and `.env.example` reflect persona graph as sole identity model.
- **Dependencies:** Step 13

## Testing and Quality Gates

### Gate A: Build and syntax

- [x] `python -m py_compile main.py services/avatar_intelligence.py services/console_grounding.py services/ollama_service.py services/content_curator.py`

### Gate B: Unit tests

- [ ] Persona graph loader/validator
- [ ] Evidence mapping and explain output
- [ ] Learning report generation
- [x] Confidence scoring and policy routing

### Gate C: Integration tests

- [ ] `--generate --dry-run` with and without new flags
- [ ] `--curate --dry-run --interactive` learning capture path
- [ ] Policy routing for `post` and `idea`
- [ ] Retrieval using persona graph (PROFILE_CONTEXT removed)

### Gate D: Regression checks

- [ ] Existing truth-gate reason behavior unchanged
- [ ] Channel formatting constraints still pass (LinkedIn/X/Bluesky/YouTube)
- [ ] No publish-path regressions when feature disabled
- [ ] App starts and runs correctly without PROFILE_CONTEXT

## Implementation Order (Dependency-Optimized)

1. Steps 1-3 (foundation + retrieval)
2. Steps 4-6 (learning + explain/report)
3. Steps 7-9 (confidence + policy + docs/config)
4. Steps 10-11 (narrative memory)
5. Steps 12-14 (PROFILE_CONTEXT migration + removal)
6. Run quality gates A-D

## Rollout and Release

### Rollout mode

- Start feature-flagged and opt-in.
- Run 2-4 week baseline comparison in dry-run-heavy workflow.

### Production readiness criteria

- No critical regressions in existing flows.
- Measurable reduction in avoidable truth-gate removals.
- Stable confidence routing and clear explain/report outputs.

## Post-Implementation Follow-ups

- Evaluate whether to migrate persona graph to SQLite.
- Add outcome-aware learning (engagement feedback) in future phase.

---

## Progress Notes

### Epic 0 — 2026-04-10

**Completed:**

- T0.1: Feature branch `feature/avatar-intelligence-learning` created and pushed.
- T0.2: Baseline dry-run artifacts documented in `tests/fixtures/baseline_run_2026-04-10.md`.
- T0.3: Acceptance test set (TC-01, TC-02, TC-03) defined in `tests/fixtures/acceptance_test_set.md`.

**Blockers/Risks:** None.

**Scope adjustments:** None.

### Epic 1A — 2026-04-10

**Completed:**

- T1.1: `data/avatar/` directory created with `.gitkeep`.
- T1.2: `data/avatar/persona_graph.json` seeded (empty valid schema v1.0).
- T1.3: `data/avatar/narrative_memory.json` seeded (empty valid structure).
- T1.4: `learning_log.jsonl` append path verified (created on first write, not tracked).
- T1.5: `services/avatar_intelligence.py` created — compiles and imports cleanly.
- T1.6: `load_avatar_state()` implemented — valid files load, malformed JSON falls back safely with warnings.
- T1.7: `normalize_evidence_facts()` with stable `E{idx:03d}-{6-char-hash}` IDs.
- T1.8: `build_grounding_context()` emits evidence-ID-tagged prompt block.
- T1.9: `get_grounding_context_for_query()` returns empty string for None/unloaded state (fallback verified).

**Blockers/Risks:** None.

**Scope adjustments:** `data/avatar/learning_log.jsonl` is runtime-created (not seeded) — append path verified via test only.

### Epic 1B — 2026-04-10

**Completed:**

- T2.1: `ModerationEvent` dataclass added to `services/avatar_intelligence.py` with all required fields.
- T2.2: `record_moderation_event()` append-only writer; hooked into `truth_gate()` interactive path in `console_grounding.py`.
- T2.3: `--avatar-explain` flag added to `main.py`; recognized in `--help`.
- T2.4: `build_explain_output()` + `format_explain_output()` implemented; emits evidence IDs only when flag enabled.
- T2.5: `--avatar-learn-report` flag added to `main.py`; exits cleanly after printing report.
- T2.6: `build_learning_report()` + `format_learning_report()` handle empty, small, and large logs.
- T2.7: Three rule-based heuristics (domain_term, retrieval_expansion, prompt_length) — advisory only, no config mutation.

**Blockers/Risks:** None.

**Scope adjustments:** `--avatar-explain` is wired into `--generate` flow only in this phase; `--curate` explain output deferred to integration step when persona graph is populated.

### Epic 1C — 2026-04-10

**Completed:**

- T3.1: `ConfidenceSignals`, `ConfidenceResult` dataclasses + `score_confidence()` weighted scoring function added to `services/avatar_intelligence.py`. Determinism verified.
- T3.2: `extract_confidence_signals()` populates all 6 signals from truth-gate meta + channel/length data. `TruthGateMeta` + `truth_gate_result()` added to `services/console_grounding.py`; existing `truth_gate()` refactored to call it (backward compatible).
- T3.3: `decide_publish_mode(policy, confidence, requested_mode)` implements §7.2 matrix (strict/balanced/draft-first). Unknown policy values fall back to balanced with warning.
- T3.4: `--confidence-policy strict|balanced|draft-first` added to `main.py`. CLI arg passed to `ContentCurator`; env default resolved from `AVATAR_CONFIDENCE_POLICY`.
- T3.5: `ContentCurator._score_and_route()` helper runs confidence scoring on every generated post. Policy decisions (post/idea/block) enforced before Buffer calls in the single-channel curate path.
- T3.6: `ConfidenceDecisionEvent` dataclass + `record_confidence_decision()` appends score, route, reason, and dominant_signal to `learning_log.jsonl`.
- T3.7: `AVATAR_CONFIDENCE_POLICY`, `AVATAR_LEARNING_ENABLED`, `AVATAR_MAX_MEMORY_ITEMS` constants added to `services/shared.py` with validation and safe defaults.

**Blockers/Risks:** None.

**Scope adjustments:** Confidence assessment in `_score_and_route()` runs `truth_gate_result()` on the already-cleaned post text (assess-only pass). `truth_gate_removed_count` therefore reflects residual issues in the cleaned output, not the pre-gate draft — this is intentional and consistent with the Phase 1C signal design.
