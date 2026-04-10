# Tasks: Avatar Intelligence and Learning Engine

## Agent Run Protocol

This feature is executed in one continuous run with two driver documents:

- Strategy driver: `docs/features/avatar-intelligence-learning/plan.md`
- Execution driver: `docs/features/avatar-intelligence-learning/tasks.md`

Required technical reference before and during execution:

- Design reference: `docs/features/avatar-intelligence-learning/design.md`

Operating rules:

- Follow this order exactly and do not skip forward:
  1. Epic 0
  2. Epic 1A
  3. Epic 1B
  4. Epic 1C
  5. Epic 1D
  6. Epic 1E
  7. Epic 2
  8. Epic 3
  9. Release Checklist
- Respect task dependencies inside each epic.
- Update task state immediately during execution (`[ ]` -> `[-]` -> `[x]`).
- If a verification gate fails, stay in the current epic and fix forward before continuing.
- At end of each epic, append a short progress note to `docs/features/avatar-intelligence-learning/plan.md`:
  - Completed tasks
  - Blockers/risks
  - Scope adjustments (if any)
- Use feature-flag-safe defaults so existing behavior remains unchanged unless explicitly enabled.
- Do not auto-edit `.env` or policy values from learning suggestions; output recommendations only.
- The agent must NOT run app workflow commands (`--generate`, `--curate`, `--schedule`, or `--dry-run`).
- Runtime workflow verification is user-executed; agent uses code-level checks, tests, and static validation only.

## Usage

- Status values:
  - `[ ]` Not started
  - `[-]` In progress
  - `[x]` Complete
- Each task includes dependencies and a verification target.

## Epic 0: Setup and Baseline

- [x] T0.1 Create feature branch
  - Depends on: none
  - Verify: branch exists and is active
- [x] T0.2 Collect user-provided baseline run artifacts for compare set
  - Depends on: T0.1
  - Verify: baseline artifacts are attached/available from user-run workflows (no agent app-run execution)
- [x] T0.3 Define acceptance prompt/article set for regression checks
  - Depends on: T0.1
  - Verify: test cases documented and reusable

## Epic 1A: Persona Graph Foundation

- [x] T1.1 Add avatar data directory scaffolding
  - Depends on: T0.1
  - Verify: `data/avatar/` created with required seed files
- [x] T1.2 Add seed file `persona_graph.json`
  - Depends on: T1.1
  - Verify: valid JSON parse
- [x] T1.3 Add seed file `narrative_memory.json`
  - Depends on: T1.1
  - Verify: valid JSON parse
- [x] T1.4 Add learning log creation path (`learning_log.jsonl`)
  - Depends on: T1.1
  - Verify: append path works and file is newline-delimited JSON
- [x] T1.5 Create module `services/avatar_intelligence.py`
  - Depends on: T1.2, T1.3
  - Verify: module imports without errors
- [x] T1.6 Implement avatar state loader + validation
  - Depends on: T1.5
  - Verify: valid files load; malformed files fallback safely
- [x] T1.7 Implement evidence fact normalization and ID assignment
  - Depends on: T1.6
  - Verify: IDs stable per run for same input order
- [x] T1.8 Implement grounding context builder from evidence facts
  - Depends on: T1.7
  - Verify: prompt block emitted with expected fact coverage
- [x] T1.9 Integrate graph-backed retrieval path in startup flow
  - Depends on: T1.8
  - Verify: runs with and without graph files produce expected fallback behavior

## Epic 1B: Learning Capture and Explainability

- [x] T2.1 Add interactive moderation event model
  - Depends on: T1.5
  - Verify: event includes timestamp/channel/reason/decision/hash/runId
- [x] T2.2 Hook truth-gate interactive decisions into learning log writer
  - Depends on: T2.1
  - Verify: each decision appends one valid JSONL record
- [x] T2.3 Add CLI flag `--avatar-explain`
  - Depends on: T1.9
  - Verify: flag is recognized and help text updated
- [x] T2.4 Emit explain output (evidence IDs + support summary)
  - Depends on: T2.3
  - Verify: explain output appears only when flag enabled
- [x] T2.5 Add CLI flag `--avatar-learn-report`
  - Depends on: T2.2
  - Verify: flag is recognized and command path exits cleanly
- [x] T2.6 Implement learning report aggregation
  - Depends on: T2.5
  - Verify: report handles empty, small, and large logs
- [x] T2.7 Add recommendation heuristics (advisory-only)
  - Depends on: T2.6
  - Verify: outputs suggestions without mutating config files

## Epic 1C: Confidence Scoring and Policy

- [x] T3.1 Define confidence signal model and score function
  - Depends on: T1.8, T2.2
  - Verify: deterministic score output for fixed inputs
- [x] T3.2 Implement signal extraction from generation + truth gate
  - Depends on: T3.1
  - Verify: all required signals populated
- [x] T3.3 Add policy decision function (`strict|balanced|draft-first`)
  - Depends on: T3.1
  - Verify: policy matrix behaves as specified for high/medium/low
- [x] T3.4 Add CLI flag `--confidence-policy`
  - Depends on: T3.3
  - Verify: invalid values fallback with warning
- [x] T3.5 Enforce confidence policy in curate publish path
  - Depends on: T3.4
  - Verify: post/idea/block routing follows policy
- [x] T3.6 Integrate decision reason logging
  - Depends on: T3.5
  - Verify: logs include score + reason + route
- [x] T3.7 Add env defaults and wiring in config/shared layer
  - Depends on: T3.4
  - Verify: defaults apply when env vars absent

## Epic 1D: Narrative Continuity Memory

- [ ] T4.1 Implement narrative memory read/update/trim operations
  - Depends on: T1.6
  - Verify: bounded memory persists across runs
- [ ] T4.2 Extract recent themes/claims from successful outputs
  - Depends on: T4.1
  - Verify: memory updates with expected fields
- [ ] T4.3 Inject continuity snippets into prompt assembly
  - Depends on: T4.2
  - Verify: prompt includes continuity context within budget
- [ ] T4.4 Add repetition signal into confidence scoring
  - Depends on: T4.3, T3.1
  - Verify: near-duplicate drafts reduce confidence score

## Epic 1E: PROFILE_CONTEXT Migration

- [ ] T7.1 Parse PROFILE_CONTEXT into persona graph entities
  - Depends on: T1.6
  - Verify: persona graph contains all parseable projects/companies/skills from PROFILE_CONTEXT
- [ ] T7.2 Populate and commit persona_graph.json
  - Depends on: T7.1
  - Verify: output passes schema validation; entity counts match expectations
- [ ] T7.3 Switch retrieval to persona graph as sole identity source
  - Depends on: T7.2, T1.9
  - Verify: retrieval uses graph facts; PROFILE_CONTEXT is not parsed for identity
- [ ] T7.4 Remove PROFILE_CONTEXT parsing code from retrieval path
  - Depends on: T7.3
  - Verify: no PROFILE_CONTEXT text parsing remains in console_grounding.py retrieval
- [ ] T7.5 Remove PROFILE_CONTEXT from .env and .env.example
  - Depends on: T7.4
  - Verify: app starts and runs without PROFILE_CONTEXT
- [ ] T7.6 Remove PROFILE_CONTEXT_MAX_CHARS and related env var references
  - Depends on: T7.5
  - Verify: no references to PROFILE_CONTEXT or PROFILE_CONTEXT_MAX_CHARS in code or config
- [ ] T7.7 Remove PROFILE_CONTEXT loading code from main.py and services
  - Depends on: T7.6
  - Verify: no dead PROFILE_CONTEXT code remains

## Epic 2: Docs and Config Alignment

- [ ] T5.1 Update `.env.example` with avatar controls
  - Depends on: T3.7, T7.6
  - Verify: new env vars documented with defaults and behavior; PROFILE_CONTEXT removed
- [ ] T5.2 Update README command/options and behavior sections
  - Depends on: T2.4, T2.6, T3.5, T7.7
  - Verify: docs match implemented flags and routing behavior; persona graph documented as identity source
- [ ] T5.3 Add operational notes for explain/report/confidence workflow
  - Depends on: T5.2
  - Verify: runbook-level guidance present

## Epic 3: Testing and Validation

- [ ] T6.1 Add unit tests for avatar state loader and schema validation
  - Depends on: T1.6
  - Verify: pass on valid and malformed fixtures
- [ ] T6.2 Add unit tests for evidence mapping and explain output
  - Depends on: T1.7, T2.4
  - Verify: deterministic and correct mapping
- [ ] T6.3 Add unit tests for learning report and recommendation rules
  - Depends on: T2.7
  - Verify: expected suggestions from synthetic logs
- [ ] T6.4 Add unit tests for confidence scoring and policy routing
  - Depends on: T3.5
  - Verify: thresholds and routes pass matrix tests
- [ ] T6.5 Add integration tests for generate/curate with new flags
  - Depends on: T2.4, T3.5
  - Verify: end-to-end flows complete without regression
- [ ] T6.6 Add integration tests for persona graph retrieval cutover
  - Depends on: T7.7
  - Verify: retrieval with persona graph active, app runs without PROFILE_CONTEXT
- [ ] T6.7 Run syntax compilation gate
  - Depends on: T6.1-T6.6
  - Verify: `python -m py_compile` passes for changed Python files
- [ ] T6.8 Run regression checks for existing truth-gate behavior
  - Depends on: T6.5, T6.6
  - Verify: no breaking change in existing reason semantics

## Release Checklist

- [ ] R1 Feature flags default-safe (no behavior change when not enabled)
- [ ] R2 Performance spot-check completed (local overhead acceptable)
- [ ] R3 Baseline-vs-feature comparison report completed (2-4 week window target)
- [ ] R4 Migration verified: persona graph populated, PROFILE_CONTEXT removed, retrieval works without it
- [ ] R5 Final docs review complete
- [ ] R6 Merge and release notes prepared

## Suggested Execution Order

1. Epic 0
2. Epic 1A
3. Epic 1B
4. Epic 1C
5. Epic 1D
6. Epic 1E
7. Epic 2
8. Epic 3
9. Release Checklist
