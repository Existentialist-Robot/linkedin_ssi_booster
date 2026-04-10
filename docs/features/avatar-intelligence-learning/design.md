# Technical Design: Avatar Intelligence and Learning Engine

## 1. Overview

This design implements the PRD for Avatar Intelligence and Learning Engine as an incremental enhancement to the existing LinkedIn SSI Booster pipeline.

Design goals:

- Preserve current generation/curation behavior by default.
- Add structured identity, explainable evidence, learning loop, confidence policy, and narrative continuity.
- Keep deterministic safety checks intact.

## 2. Architecture

### 2.1 High-level component architecture

```mermaid
flowchart LR
    CLI[main.py CLI] --> ORCH[Avatar Intelligence Orchestrator\nservices/avatar_intelligence.py]

    ORCH --> CG[console_grounding.py\nDeterministic grounding + truth gate]
    ORCH --> OLL[ollama_service.py\nGeneration and channel formatting]
    ORCH --> CUR[content_curator.py\nCuration orchestration]
    ORCH --> BUF[buffer_service.py\nBuffer publish/idea API]

    ORCH --> PG[(data/avatar/persona_graph.json)]
    ORCH --> NM[(data/avatar/narrative_memory.json)]
    ORCH --> LL[(data/avatar/learning_log.jsonl)]

    ORCH --> REP[Learn report + explain output]

    CUR --> BUF
    OLL --> CG
```

### 2.2 Runtime flow with confidence gate

```mermaid
flowchart TD
    A[Load profile + persona graph] --> B[Retrieve relevant facts]
    B --> C[Assign evidence IDs]
    C --> D[Build grounding block]
    D --> E[Generate draft via Ollama]
    E --> F[Truth gate validate]
    F --> G[Capture interactive decisions if enabled]
    G --> H[Compute confidence score]
    H --> I{Confidence policy}
    I -->|High| J[Direct post allowed]
    I -->|Medium| K[Idea mode / review]
    I -->|Low| L[Block direct publish + reason summary]
```

## 3. Design Principles

- Backward compatible first: persona graph replaces PROFILE_CONTEXT as canonical identity source during development.
- Deterministic safety preserved: current reason checks stay active.
- Human-in-the-loop learning: suggestions only, no autonomous config changes.
- Explainability by default-ready: evidence IDs and optional explain reports.

## 4. Module Design

### 4.1 New module: services/avatar_intelligence.py

Responsibilities:

- Load and validate persona graph and memory files.
- Normalize facts and assign evidence IDs.
- Build explainable grounding context blocks.
- Score confidence and enforce policy decisions.
- Record learning events from truth-gate interactions.
- Generate recommendations from repeated moderation patterns.

Core interfaces:

- `load_avatar_state() -> AvatarState`
- `retrieve_evidence(query, facts) -> list[EvidenceFact]`
- `build_grounding_context(evidence_facts) -> str`
- `score_confidence(draft, signals) -> ConfidenceResult`
- `decide_publish_mode(policy, confidence, requested_mode) -> PublishDecision`
- `record_learning_event(event) -> None`
- `build_learning_report() -> LearningReport`

### 4.2 main.py integration

Changes:

- Add optional CLI flags:
  - `--avatar-explain`
  - `--avatar-learn-report`
  - `--confidence-policy strict|balanced|draft-first`
- Route generate/curate operations through Avatar Intelligence orchestrator hooks.
- Persona graph is the sole identity source — PROFILE_CONTEXT and its parsing code are removed during development.

### 4.3 console_grounding.py integration

Changes:

- Replace PROFILE_CONTEXT text parsing with graph-backed fact retrieval from persona graph.
- Preserve current reason checks:
  - `unsupported_numeric`
  - `unsupported_year`
  - `unsupported_org`
  - `project_claim`
- Provide optional evidence ID references for explain mode.

### 4.4 ollama_service.py integration

Changes:

- Accept evidence-enriched grounding snippets in prompts.
- Return metadata needed by confidence scoring (length pressure, claim density hints).
- Maintain channel-specific behavior (LinkedIn/X/Bluesky/YouTube).

### 4.5 content_curator.py integration

Changes:

- Capture interactive truth-gate decisions in learning log.
- Apply confidence policy before direct post scheduling.
- Attach decision reason to logs and dry-run output.

## 5. Data Model Design

### 5.1 Persona graph file

Path: `data/avatar/persona_graph.json`

Proposed schema (v1):

- `schemaVersion: string`
- `person: { name, title, location, links[] }`
- `projects[]: { id, name, companyId, years, details, skills[], aliases[] }`
- `companies[]: { id, name, aliases[] }`
- `skills[]: { id, name, aliases[], scope: domain|project_specific }`
- `claims[]: { id, text, projectIds[], confidenceHint }`

### 5.2 Narrative memory file

Path: `data/avatar/narrative_memory.json`

Proposed schema (v1):

- `recentThemes[]`
- `recentClaims[]`
- `openNarrativeArcs[]`
- `lastUpdated`

### 5.3 Learning log file

Path: `data/avatar/learning_log.jsonl`

Each line event:

- `timestamp`
- `channel`
- `reasonCode`
- `decision: kept|removed`
- `sentenceHash`
- `articleRef`
- `projectRefs[]`
- `runId`

### 5.4 Data model diagram

```mermaid
erDiagram
    PERSON ||--o{ PROJECT : owns
    COMPANY ||--o{ PROJECT : sponsors
    PROJECT }o--o{ SKILL : uses
    PROJECT ||--o{ CLAIM : supports
    PERSON ||--o{ NARRATIVE_ITEM : maintains
    PERSON ||--o{ LEARNING_EVENT : records

    PERSON {
      string id
      string name
      string title
      string location
    }
    COMPANY {
      string id
      string name
    }
    PROJECT {
      string id
      string name
      string years
      string details
    }
    SKILL {
      string id
      string name
      string scope
    }
    CLAIM {
      string id
      string text
      string confidenceHint
    }
    NARRATIVE_ITEM {
      string id
      string type
      string value
      datetime lastUsed
    }
    LEARNING_EVENT {
      string id
      datetime timestamp
      string reasonCode
      string decision
      string sentenceHash
    }
```

## 6. Sequence Design

### 6.1 Curate flow with learning and policy

```mermaid
sequenceDiagram
    participant U as User
    participant M as main.py
    participant AI as avatar_intelligence.py
    participant CG as console_grounding.py
    participant OL as ollama_service.py
    participant CU as content_curator.py
    participant BF as buffer_service.py
    participant DS as data/avatar/*

    U->>M: run --curate [--interactive] [--confidence-policy]
    M->>AI: load_avatar_state()
    AI->>DS: read persona_graph + memory + learning logs
    M->>CU: curate_and_create_ideas(...)
    CU->>AI: retrieve_evidence(article + context)
    AI->>CG: retrieve_relevant_facts(...)
    AI-->>CU: evidence facts + IDs
    CU->>OL: summarise_for_curation(... grounding facts ...)
    OL->>CG: truth_gate(text, article, facts, interactive)
    CG-->>AI: moderation events (if interactive)
    AI->>DS: append learning events
    CU->>AI: score_confidence(draft, signals)
    AI-->>CU: publish decision + reasons
    alt direct post allowed
      CU->>BF: create_scheduled_post(...)
    else review mode
      CU->>BF: create_idea(...)
    else blocked
      CU-->>M: skip publish + reason
    end
    M-->>U: summary + optional explain output
```

## 7. Confidence Scoring Design

### 7.1 Signals

- `truth_gate_removed_count`
- `truth_gate_reason_severity`
- `grounding_coverage_ratio`
- `unsupported_claim_pressure`
- `channel_length_pressure`
- `narrative_repetition_score`

### 7.2 Policy mapping

- strict:
  - high -> post
  - medium/low -> idea or block
- balanced:
  - high/medium -> post
  - low -> idea or block
- draft-first:
  - all -> idea unless explicit override flag

### 7.3 Explain output

When `--avatar-explain` is enabled, return:

- selected evidence IDs
- confidence score + contributing signals
- final publish decision + reason summary

## 8. Learning Engine Design

### 8.1 Event capture

Trigger points:

- Interactive truth-gate sentence decisions.
- Confidence-policy route decision (post/idea/block).
- Optional post-publication outcome summary (future phase).

### 8.2 Recommendation logic (rule-based v1)

- If repeated `project_claim` kept by user on same term -> suggest domain-term candidate.
- If repeated numeric removals with known source references missing -> suggest retrieval keyword/tag expansion review.
- If repeated low confidence due to length pressure -> suggest channel prompt adjustment.

### 8.3 Reporting

`--avatar-learn-report` outputs:

- top reason codes by frequency
- top kept-vs-removed mismatch patterns
- suggested tuning actions with confidence labels

## 9. Configuration Design

Add to `.env.example`:

- `AVATAR_CONFIDENCE_POLICY=balanced`
- `AVATAR_LEARNING_ENABLED=true`
- `AVATAR_MAX_MEMORY_ITEMS=200`

Behavior:

- Missing config uses defaults.
- Invalid policy values fall back to `balanced` with warning.

## 10. Error Handling and Fallbacks

- Missing `data/avatar/*` files:
  - Log warning and continue with current deterministic flow.
- Malformed JSON schema:
  - Log validation errors and disable avatar intelligence features for that run.
- Learning log write failure:
  - Continue generation/publish path; emit warning only.
- Confidence engine exception:
  - Default decision to existing requested mode and log fallback reason.

## 11. Security and Privacy

- Keep learning and memory files local.
- No external telemetry in v1.
- Sentence content stored as hash in learning log for privacy-preserving trend analysis.

## 12. Performance Design

- In-memory caches for persona graph and recent memory windows per run.
- Bounded memory list size using `AVATAR_MAX_MEMORY_ITEMS`.
- Rule-based confidence and recommendation logic (no extra model calls in v1).

## 13. Test Strategy

### 13.1 Unit tests

- Persona graph schema validation.
- Evidence ID stability and mapping.
- Confidence score computation and policy mapping.
- Learning recommendation generation rules.

### 13.2 Integration tests

- Curate with interactive mode and learning-log persistence.
- Generate with explain mode output.
- Fallback behavior when avatar files are absent.

### 13.3 Regression tests

- Ensure existing truth-gate checks remain functionally unchanged.
- Validate no regressions in channel formatting constraints.

## 14. Rollout Plan

Phase 1A:

- Add avatar intelligence module and data files (read-only retrieval support).

Phase 1B:

- Add learning event capture and report generation.

Phase 1C:

- Add confidence scoring and policy enforcement.

Phase 1D:

- Add narrative continuity memory injection.

Phase 1E:

- Populate persona graph from existing PROFILE_CONTEXT during development.
- Switch retrieval to persona graph as sole identity source.
- Remove PROFILE_CONTEXT env var, parsing code, and related references.

## 15. Design Decisions Summary

- Keep deterministic safety and human approval central.
- Introduce intelligence incrementally with explicit fallbacks.
- Treat explainability and learning as first-class outputs, not side effects.
- Preserve compatibility with existing commands and operational workflow.

## 16. PROFILE_CONTEXT Migration Design

### 16.1 Migration overview

PROFILE_CONTEXT is currently the primary identity source — a free-form text blob in `.env` that is parsed at runtime for project/company/skill facts. This migration replaces it with the structured persona graph as the single canonical identity model.

This is a development-time migration, not a user-facing tool. The developer populates the persona graph during implementation, verifies quality, and then removes PROFILE_CONTEXT entirely.

### 16.2 Population approach

During development:

1. Parse existing PROFILE_CONTEXT using `console_grounding.py` fact parser (reuse `parse_profile_facts`).
2. Extract structured entities:
   - Person: name, title, location from header lines.
   - Projects: from bullet patterns (`- ProjectName (Company, Years): details`).
   - Companies: deduplicated from project entries.
   - Skills: extracted from details fields and tech keywords.
   - Claims: factual statements with project references.
3. Populate `data/avatar/persona_graph.json` with extracted data.
4. Review and manually refine the graph as needed.

### 16.3 Retrieval cutover

After persona graph is populated and verified:

1. Update retrieval path in `console_grounding.py` to use graph facts instead of PROFILE_CONTEXT text parsing.
2. Remove PROFILE_CONTEXT parsing code from the retrieval path.
3. Persona graph becomes the sole identity source — no fallback to PROFILE_CONTEXT.

### 16.4 PROFILE_CONTEXT removal

Once retrieval cutover is verified:

1. Remove `PROFILE_CONTEXT` from `.env`.
2. Remove `PROFILE_CONTEXT` from `.env.example`.
3. Remove `PROFILE_CONTEXT_MAX_CHARS` from `.env` and `.env.example`.
4. Remove PROFILE_CONTEXT loading/parsing code from `main.py` and services.
5. Update README to remove all PROFILE_CONTEXT references and document persona graph as the identity source.
6. GitHub enrichment (`services/github_service.py`) continues to work independently.

### 16.5 Verification

Developer verification during implementation:

1. Compare persona graph entity coverage against original PROFILE_CONTEXT.
2. Run `--generate --dry-run` and `--curate --dry-run` with persona graph.
3. Compare output quality against baseline (pre-migration dry-run artifacts).
4. Git history provides rollback if needed.
