# Product Requirements Document: Avatar Intelligence and Learning Engine

## 1. Executive Summary

The Avatar Intelligence and Learning Engine upgrades the LinkedIn SSI Booster from a prompt-centric content tool into a reliable personal digital representative. The feature introduces a structured persona model, evidence-linked grounding, interactive learning from moderation decisions, confidence-based publishing policy, and narrative continuity memory.

The objective is to improve authenticity, consistency, and factual safety while reducing manual cleanup effort.

## 2. Project Context

### Current system strengths

- Hybrid pipeline already exists: retrieval grounding, generation orchestration, deterministic truth gate, and publishing.
- Interactive truth gate supports manual moderation (`--interactive`).
- Persona and channel behavior are configurable via environment variables and prompt blocks.

### Current system gaps

- Persona knowledge is largely text-parsed and prompt-driven.
- Learning from user moderation is not persisted or reused.
- No formal confidence layer controls publish behavior.
- Continuity across runs is limited.

### Product intent

Represent the user as a trustworthy digital avatar that:

- Uses durable identity facts.
- Explains what it knows and why.
- Learns from operator feedback.
- Maintains continuity over time.
- Preserves existing safety guarantees.

## 3. Goals and Non-Goals

### Goals

- Establish a structured persona graph as the identity source of truth.
- Attach evidence references to grounded claims used in generation and validation.
- Capture moderation outcomes and convert recurring patterns into tuning suggestions.
- Enforce configurable confidence policy before direct posting.
- Preserve narrative continuity across weeks.

### Non-Goals (Phase 1)

- Full graph database backend.
- Autonomous mutation of `.env` or prompts without user approval.
- Multi-tenant or multi-user persona support.
- New external analytics SaaS dependencies.

## 4. Stakeholders and Users

### Primary user

- Individual creator/engineer using the tool as a personal posting agent.

### Secondary stakeholders

- Future maintainers of the pipeline.
- Audience consuming posts (indirect quality beneficiary).

### Stakeholder outcomes

- Higher trust in generated posts.
- Lower moderation overhead.
- Better long-run identity consistency.

## 5. User Stories and Acceptance Criteria

### Story 1: Structured identity retrieval

As a user, I want my persona represented by structured entities so factual retrieval remains stable as profile complexity grows.

Acceptance criteria:

- Persona graph loads from local file(s) with schema validation at startup.
- Retrieval can use graph data without requiring free-form regex parsing only.
- Existing behavior remains backward compatible when graph files are absent.

### Story 2: Explainable evidence usage

As a user, I want grounded claims to reference source evidence so I can trust the output.

Acceptance criteria:

- Retrieved facts are assigned stable evidence IDs per run.
- Generation path can emit an optional evidence summary (`--avatar-explain`).
- Evidence summary shows claim-support mapping for factual content.

### Story 3: Learning from moderation

As a user, I want interactive moderation choices to improve future quality so the system adapts safely.

Acceptance criteria:

- Each truth-gate interactive decision is logged with reason, sentence fingerprint, and outcome.
- A report command (`--avatar-learn-report`) summarizes recurrent false-positive patterns.
- Suggested config adjustments are advisory only and never auto-applied.

### Story 4: Confidence-based publish policy

As a user, I want risky outputs routed to review instead of direct posting.

Acceptance criteria:

- System computes confidence score per output.
- Configurable policy (`strict|balanced|draft-first`) controls post vs idea behavior.
- Low confidence blocks direct scheduling and provides reason summary.

### Story 5: Narrative continuity

As a user, I want posts to remain coherent over time and avoid repetition.

Acceptance criteria:

- Memory store tracks recent themes, claims, and stances.
- Generation context includes selected continuity snippets.
- Repetition checks lower confidence when new draft duplicates recent content.

## 6. Functional Requirements

### FR-1 Persona graph storage and validation

- Add local files:
  - `data/avatar/persona_graph.json`
  - `data/avatar/narrative_memory.json`
  - `data/avatar/learning_log.jsonl`
- Validate required fields and schema version.
- Fail gracefully with warnings and fallback path.

### FR-2 Retrieval integration

- Introduce `services/avatar_intelligence.py` as orchestration layer.
- Support graph-backed retrieval plus current deterministic fallback.
- Provide normalized fact objects with evidence IDs.

### FR-3 Evidence-linked generation

- Inject evidence-tagged grounding blocks into generation and curation prompts.
- Support optional explain output mode showing evidence summary.

### FR-4 Learning event capture

- Log interactive moderation outcomes with:
  - timestamp
  - channel
  - reason code
  - kept/removed
  - hashed sentence token
  - article/profile context hints
- Provide aggregate trend report.

### FR-5 Suggestion engine

- Produce suggested tuning actions based on repeated patterns, including:
  - potential domain-term candidates
  - tag-expansion opportunities
  - retrieval keyword gaps
- Mark all suggestions as manual-review required.

### FR-6 Confidence scoring

- Compute score from weighted signals:
  - truth-gate removals by severity
  - grounding coverage ratio
  - unsupported-claim pressure
  - truncation/format pressure by channel
  - narrative repetition score
- Expose score and decision reason in logs.

### FR-7 Confidence policy enforcement

- Add runtime policy switch:
  - `strict`: only high confidence posts can schedule directly
  - `balanced`: medium/high can schedule; low is idea-only
  - `draft-first`: all curated outputs become ideas unless explicitly overridden
- Maintain compatibility with existing `--type` behavior.

### FR-8 CLI additions

- Add optional flags:
  - `--avatar-explain`
  - `--avatar-learn-report`
  - `--confidence-policy`
- Keep current commands operational without new flags.

### FR-9 Observability

- Add structured logs for confidence decisions and learning summaries.
- Preserve existing truth-gate reason reporting.

## 7. Non-Functional Requirements

### NFR-1 Performance

- Additional processing overhead must not materially slow normal generation flow.
- Target added local-processing overhead: <= 150 ms per post on average (excluding model latency).

### NFR-2 Reliability

- Missing or malformed avatar files must not crash normal generation by default.
- System should degrade to current behavior with warnings.

### NFR-3 Safety

- Existing deterministic checks (`unsupported_numeric`, `unsupported_year`, `unsupported_org`, `project_claim`) must remain active and unchanged unless explicitly configured.

### NFR-4 Maintainability

- New module boundaries must keep responsibilities clear and testable.
- Data files must be versioned with migration notes.

### NFR-5 Privacy

- Learning logs remain local by default.
- No automatic external transmission of moderation data.

### NFR-6 Usability

- Report outputs should be human-readable and actionable.
- Suggested changes must include rationale and confidence.

## 8. Project System Integration

### Code integration points

- `main.py`
  - Add flags and command routing.
- `services/console_grounding.py`
  - Add graph-backed retrieval path while preserving deterministic fallback.
- `services/ollama_service.py`
  - Accept evidence-enriched grounding blocks and confidence metadata.
- `services/content_curator.py`
  - Log moderation outcomes and enforce publish policy decisions.
- `services/shared.py`
  - Add optional policy defaults.

### Configuration additions

- `AVATAR_CONFIDENCE_POLICY=balanced`
- `AVATAR_LEARNING_ENABLED=true`
- `AVATAR_MAX_MEMORY_ITEMS=200`

### Data artifacts

- `data/avatar/persona_graph.json`
- `data/avatar/narrative_memory.json`
- `data/avatar/learning_log.jsonl`

## 9. Dependencies

### Internal dependencies

- Existing truth gate and grounding modules.
- Existing generation and curation flows.
- Existing CLI orchestration.

### External dependencies

- None required for Phase 1 beyond current stack.
- Optional future dependency: lightweight schema validation package if needed.

## 10. Risks and Mitigations

### Risk 1: Over-constrained output quality

- Mitigation: policy modes and feature flags; keep balanced as default.

### Risk 2: Learning loop overfitting

- Mitigation: threshold repeated observations before recommendations.

### Risk 3: Persona graph drift

- Mitigation: add import/sync workflow from profile context and clear update instructions.

### Risk 4: Adoption friction

- Mitigation: backward compatibility and opt-in flags in early phases.

## 11. Success Metrics

### Primary metrics

- 30-50% reduction in avoidable truth-gate removals across comparable runs.
- Decrease in manual corrections per curation batch.
- Increase in grounded claim coverage with evidence mapping.

### Secondary metrics

- Confidence score stability over time.
- Reduction in repeated thematic content over rolling windows.
- No increase in unsupported claim leakage rate.

### Operational metrics to track

- `truth_gate_removed_total`
- `truth_gate_removed_by_reason`
- `interactive_keep_rate`
- `confidence_score_distribution`
- `publish_mode_decisions`

## 12. Timeline and Milestones

### Milestone 1: Persona graph foundation (Phase 1A)

- Persona graph file, loader, and schema validation.
- Read-only integration with fallback.

### Milestone 2: Evidence and learning capture (Phase 1B)

- Evidence IDs in retrieval path.
- Learning log capture from interactive moderation.
- Report output for learning trends.

### Milestone 3: Confidence policy (Phase 1C)

- Confidence score computation.
- Policy enforcement in curation/posting path.
- Decision reason logging.

### Milestone 4: Narrative continuity (Phase 1D)

- Memory store for recent claims/themes.
- Prompt integration for continuity.
- Repetition-aware confidence adjustment.

## 13. Open Questions

- Should confidence policy apply equally to `--generate` and `--curate` at launch, or start with curation only?
- What minimum confidence threshold should map to each policy tier in the first release?
- Should evidence summaries be visible by default in interactive mode, or only on explicit flag?

## 14. Rollout Strategy

- Release behind feature flags first.
- Run parallel dry-run evaluation against baseline for 2-4 weeks.
- Promote balanced policy to default after metrics validate improvements.

## 15. Definition of Done

- All Phase 1 milestones implemented with backward compatibility.
- README and `.env.example` updated for new controls and commands.
- Basic regression tests added for retrieval, truth gate, and confidence decisions.
- Baseline-vs-feature comparison report demonstrates improvement without safety regressions.
