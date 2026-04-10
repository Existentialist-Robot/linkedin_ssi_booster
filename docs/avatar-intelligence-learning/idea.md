# Feature Idea: Avatar Intelligence and Learning Engine

## Overview

Build a first-class "digital representative" layer that turns the current persona pipeline into a continuously improving avatar system.

Today, the app already has strong pieces:

- Persona prompting
- Deterministic grounding
- Post-generation truth-gate filtering
- Interactive moderation via `--interactive`

This feature formalizes identity, adds memory and feedback learning loops, and introduces confidence gating so the system becomes more reliable, more personal, and safer over time.

## Problem Statement (Project Context)

The current architecture performs well for generation and safety, but identity intelligence is still mostly prompt- and regex-driven.

Key gaps:

- Persona facts are extracted from free-form profile text at runtime, which is brittle as the profile grows.
- Truth-gate and grounding decisions are not converted into reusable learning signals.
- There is no persisted identity memory model for continuity across weeks/months.
- Publishing confidence is binary (post/idea), not policy-driven from evidence quality.
- Console experience labels and identity signaling are partially hardcoded rather than model-driven.

For a true personal digital avatar, the system should:

- Know who it represents with a structured identity model.
- Learn from corrections.
- Explain and justify its claims.
- Maintain narrative continuity.
- Adapt safely without drifting from factual constraints.

## Proposed Solution

Introduce an "Avatar Intelligence and Learning Engine" with five capabilities:

1. Structured Persona Graph (source of truth)

- Add a typed local model (JSON schema first, optional SQLite later) with entities:
  - Person
  - Project
  - Company
  - TimeRange
  - Skill
  - Claim
  - Relationship/alias metadata
- Treat `.env PROFILE_CONTEXT` as an import source during migration, then retire it.
- After import, the persona graph is the single canonical identity model.

2. Evidence-linked generation

- During retrieval, assign stable evidence IDs to selected facts.
- Keep evidence references through generation and truth-gate validation.
- Support deterministic explainability: "this claim came from fact X".

3. Interactive learning loop

- Persist truth-gate decisions from `--interactive` mode.
- Track approved removals vs user-kept sentences by reason code.
- Generate tuning suggestions (e.g., candidate `TRUTH_GATE_DOMAIN_TERMS` additions) from repeated false positives.

4. Confidence-based publish policy

- Compute a confidence score per post using:
  - Truth-gate removal count and severity
  - Grounding coverage
  - Unsupported-claim pressure
  - Channel format stress (character truncation pressure)
- Policy examples:
  - High confidence -> allow `post`
  - Medium confidence -> force `idea`
  - Low confidence -> block and request revision

5. Narrative continuity memory

- Persist rolling context of:
  - Recent positions/opinions
  - Open narrative arcs
  - Claims already made to audience
- Use this memory to avoid repetitive posts and maintain coherent avatar voice over time.

6. PROFILE_CONTEXT migration to persona graph

- During development, parse the existing `.env PROFILE_CONTEXT` and populate `persona_graph.json` directly.
- Switch the retrieval path from PROFILE_CONTEXT text as the primary identity source to the persona graph.
- Once the persona graph is verified and retrieval quality is confirmed, delete PROFILE_CONTEXT and all related env var references from `.env`, `.env.example`, and code.
- This is a development-time migration, not a user-facing tool — single-user project, no import/export CLI needed.

## Expected Benefits (Project User Impact)

- Stronger authenticity: output feels like a consistent personal representative, not disconnected one-off posts.
- Lower hallucination risk: claims map to explicit evidence.
- Better safety tuning: system learns from user moderation signals.
- Less manual correction: fewer avoidable truth-gate removals and fewer missed valid claims.
- Better engagement quality: continuity improves credibility and audience trust.

## Technical Considerations (Project Integration)

### Architecture alignment

- Keep current flow (`main.py` -> `services/ollama_service.py` -> truth gate) intact.
- Insert the new engine as a supporting domain layer used by both `--console` and generation/curation paths.

### Data model (v1)

- Add `data/avatar/persona_graph.json`
- Add `data/avatar/learning_log.jsonl`
- Add `data/avatar/narrative_memory.json`
- Add schema validation for each file at startup.

### Service design

- New module proposal: `services/avatar_intelligence.py`
- Responsibilities:
  - Persona graph loading/validation
  - Evidence ID assignment
  - Confidence scoring
  - Learning event capture
  - Tuning recommendation generation

### Prompting and policy

- Split prompt responsibilities into:
  - Identity policy
  - Voice policy
  - Channel policy
- Keep `PERSONA_SYSTEM_PROMPT` support for backward compatibility.

### Safety and compliance

- Preserve existing deterministic checks (`unsupported_numeric`, `unsupported_year`, `unsupported_org`, `project_claim`).
- Learning loop should suggest config updates, not auto-apply without user approval.

### Performance

- Keep inference overhead low by:
  - Local JSON memory with bounded size
  - Fast lookup indexes for project/skill aliases
  - Lightweight confidence scoring (no extra model calls required in v1)

## Project System Integration

### `main.py`

- Add optional flags:
  - `--avatar-explain` (show evidence summary)
  - `--avatar-learn-report` (show tuning suggestions)
  - `--confidence-policy` (strict|balanced|draft-first)

### `services/console_grounding.py`

- Replace/augment regex-only parsing with graph-backed retrieval.
- Continue using existing deterministic fallbacks for resilience.

### `services/ollama_service.py`

- Inject evidence-tagged grounding blocks.
- Use confidence score metadata on output.

### `services/content_curator.py`

- Capture moderation and publish outcomes into learning log.
- Apply confidence policy before scheduling direct posts.

### `.env` / config

- Add optional controls:
  - `AVATAR_CONFIDENCE_POLICY=balanced`
  - `AVATAR_LEARNING_ENABLED=true`
  - `AVATAR_MAX_MEMORY_ITEMS=200`

## Initial Scope

### In scope (Phase 1)

- Persona graph JSON model and loader.
- Evidence IDs for retrieved facts.
- Learning log from truth-gate interactive decisions.
- Confidence scoring and publish policy gate.
- Basic narrative memory (recent claims + themes).
- Populate persona graph from existing PROFILE_CONTEXT during development.
- Full cutover: retire and delete PROFILE_CONTEXT, persona graph becomes canonical.

### Out of scope (Phase 1)

- Full graph database backend.
- Autonomous self-editing of `.env` or prompts.
- Multi-user personas.
- External analytics integrations beyond current local metrics.

## Implementation Feasibility

- Complexity: Medium-high, but incremental.
- Risk: Manageable if introduced behind feature flags.
- Migration: Developer populates persona graph from existing PROFILE_CONTEXT during implementation. After verification, PROFILE_CONTEXT is deleted.

## Risks and Mitigations

- Risk: Over-constraining generation and reducing creativity.
  - Mitigation: confidence policy modes and clear fallback behavior.
- Risk: Learning loop overfits to short-term user choices.
  - Mitigation: require repeated signals before suggestions.
- Risk: Identity drift from stale persona graph.
  - Mitigation: add simple sync workflow from profile updates.
- Risk: Migration breaks existing retrieval quality.
  - Mitigation: pre/post `--dry-run` comparison before committing cutover; git history provides rollback.

## Success Criteria

- 30-50% reduction in avoidable truth-gate removals over baseline runs.
- Fewer user manual corrections per curation batch.
- Increased consistency in recurring themes across 4-week windows.
- Deterministic evidence trace available for factual claims in console/generation flows.
- No regression in current safety checks and no increase in unsupported claim leakage.

## Measurement Plan

- Track per-run metrics:
  - `truth_gate_removed_total`
  - `truth_gate_removed_by_reason`
  - `interactive_keep_rate`
  - `confidence_score_distribution`
  - `publish_mode_decisions` (post vs idea vs blocked)
- Compare baseline (current main) vs feature-flag-enabled runs for 2-4 weeks.

## Rollout Plan

1. Phase 1A: Persona graph + evidence IDs (read-only mode)
2. Phase 1B: Learning log capture + reporting (no policy enforcement)
3. Phase 1C: Confidence policy enforcement (balanced default)
4. Phase 1D: Narrative continuity memory in generation prompts

## Why This Matters

This evolves the project from "AI-assisted post generation" to a true "personal digital representative" architecture:

- identity-grounded
- evidence-aware
- learning-capable
- continuity-preserving
- safety-first

That aligns directly with your stated goal: a reliable avatar that represents the user, not just a text generator.
