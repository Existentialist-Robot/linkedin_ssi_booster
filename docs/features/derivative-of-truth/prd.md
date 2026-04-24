# Product Requirements Document: Derivative of Truth Framework

## 1. Executive Summary

This feature introduces a new mathematical framework for AI truthfulness, inspired by "The Derivative of Truth: A New Mathematical Framework for AI Truthfulness." The goal is to move beyond static fact-checking and optimize for the _trajectory_ toward more reliable knowledge in all generated content. The framework will be integrated into the LinkedIn SSI Booster to improve trustworthiness, transparency, and explainability.

## 2. Project Context

- Current system uses a truth gate, BM25 retrieval, and confidence scoring to filter and rank claims.
- Limitation: Overconfidence, reward hacking, and hallucination can still occur due to pattern matching and lack of explicit uncertainty modeling.
- This feature will add a truth gradient metric, evidence/reasoning annotation, and uncertainty penalty to the scoring and reporting pipeline.

## 3. User Stories

- **As a user**, I want every generated post/claim to include a truth gradient score and evidence path, so I can trust and verify the system's outputs.
- **As a user**, I want the system to penalize overconfident, weakly supported claims, so my content remains credible and on-brand.
- **As a user**, I want to see uncertainty and evidence breakdowns in CLI reports, so I can understand the reasoning behind each output.
- **As a developer**, I want the system to accumulate and seek stronger evidence over time, so the knowledge base improves with use.

## 4. Functional Requirements

- Annotate all knowledge graph facts and claims with evidence strength, reasoning validity, and uncertainty.
- Compute a truth gradient score for each generated claim/post using the formula:
  - Truth_Gradient = ∇(Evidence × Reasoning × Consistency) - ∇(Uncertainty × Bias)
- Penalize claims where stated confidence exceeds actual evidence strength.
- Track and report evidence paths and uncertainty for all outputs.
- Integrate truth gradient scoring into the truth gate, confidence scoring, and explainability CLI.

## 5. Non-Functional Requirements

- **Performance:** Truth gradient computation must not noticeably slow down post generation or ranking.
- **Usability:** Evidence and uncertainty breakdowns must be clear and actionable in CLI reports.
- **Reliability:** The system must not block or fail if evidence annotations are missing; fallback to current scoring.
- **Maintainability:** All new logic must be modular and covered by unit tests.
- **Compatibility:** Must work with both NetworkX and (future) Neo4j knowledge graph backends.

## 6. Project System Integration

- Knowledge graph (NetworkX core, Neo4j future)
- Hybrid retriever and reranker
- Truth gate and confidence scoring
- Continual learning and evidence accumulation
- Explainability and reporting CLI

## 7. Dependencies

- Existing knowledge graph and claim support infrastructure
- BM25 retrieval and scoring
- spaCy NLP pipeline for evidence extraction
- CLI/reporting modules

## 8. Success Metrics

- All generated claims/posts include a truth gradient score and evidence path
- Overconfident, weakly supported claims are penalized or flagged
- Users can see uncertainty and evidence breakdowns in reports
- System demonstrates reduced hallucination and improved trustworthiness in output (qualitative and, if possible, quantitative evaluation)

## 9. Timeline & Milestones

- **Design & Schema Update:** 1 day
- **Evidence/Reasoning Annotation:** 2 days
- **Truth Gradient Scoring Logic:** 2 days
- **CLI/Reporting Integration:** 1 day
- **Testing & Validation:** 1 day
- **Docs & Release:** 1 day
- **Total:** ~1 week

---

**Reference:**

- [Derivative of Truth: Feature Idea](./idea.md)
- "The Derivative of Truth: A New Mathematical Framework for AI Truthfulness" (user summary)
- [docs/features/continual-learning/idea.md](../continual-learning/idea.md)
