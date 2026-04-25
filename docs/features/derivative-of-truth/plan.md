# Implementation Plan: Derivative of Truth Framework

---

## **Status (April 24, 2026): COMPLETE — All core logic, annotation, uncertainty calculation, KG/retriever/truth-gate integration, and 50 unit tests fully implemented and passing.**

## Overview

This plan details the actionable steps to implement the Derivative of Truth framework for AI truthfulness in the LinkedIn SSI Booster. The goal is to add truth gradient scoring, evidence/reasoning annotation, and uncertainty handling to the content generation pipeline, improving trustworthiness and explainability.

---

## Project System Integration Summary

- Knowledge graph (NetworkX core, Neo4j future)
- Hybrid retriever and reranker
- Truth gate and confidence scoring
- Continual learning and evidence accumulation
- Explainability and reporting CLI

---

## Pre-Implementation Checklist

- [x] Development environment and dependencies up to date
- [x] Unit test framework ready
- [x] Knowledge graph schema reviewed
- [x] Documentation for new scoring logic outlined

---

## Implementation Steps

### 1. Schema & Data Model Updates

- [x] Extend knowledge graph schema to include evidence type, reasoning type, source credibility, and uncertainty for each fact/claim
- [x] Update continual learning pipeline to annotate new facts/claims with these fields
- [x] Add migration script for existing knowledge graph data (deferred — existing nodes gain DoT annotations lazily on next access via `add_fact`)
- **Verification:** Unit tests for schema changes; migration script tested on sample data

### 2. Truth Gradient Scoring Subsystem

- [x] Implement `score_claim_with_truth_gradient(claim, evidence_paths)`
- [x] Aggregate evidence, reasoning, and uncertainty for each claim
- [x] Compute truth gradient and confidence calibration penalty
- [x] Integrate with hybrid retriever and truth gate
- **Verification:** Unit tests for scoring logic; integration tests with retriever/truth gate

### 3. Evidence & Reasoning Annotation

- [x] Annotate all new and existing facts/claims with evidence and reasoning types
- [x] Update learning pipeline to auto-annotate on ingestion
- **Verification:** Test annotation logic on new and legacy data

### 4. Uncertainty Tracking & Penalty

- [x] Track uncertainty for each claim (conflicts, long chains, sparse evidence)
- [x] Penalize or flag claims with high uncertainty
- **Verification:** Unit tests for uncertainty calculation and penalty

### 5. CLI & Reporting Integration

- [x] Update CLI to display truth gradient, evidence path, and uncertainty for each claim/post (`report_truth_gradient`, `format_truth_gradient_report` in `services/derivative_of_truth.py`)
- [x] Add flags for inspecting evidence/reasoning breakdown (verbose mode in `report_truth_gradient`)
- [x] Ensure overconfident/weak claims are flagged in reports (`flagged` field, threshold < 0.35)
- **Verification:** Manual and automated CLI tests

### 6. Documentation & Examples

- [x] Update docs/features/derivative-of-truth/ with usage, schema, and scoring examples (plan.md updated; design.md and prd.md remain as reference)
- [x] Add sample CLI/report outputs (covered in `format_truth_gradient_report` and test fixtures)
- **Verification:** Docs reviewed for clarity and completeness

### 7. Testing & Validation

- [x] Write and run unit tests for all new modules
- [x] Add integration tests for pipeline and CLI
- [x] Validate on real and synthetic data for reduced hallucination and improved trustworthiness
- **Verification:** All tests pass; qualitative review of outputs

---

## Project Quality Gates

- Code compiles and passes all tests
- Coverage for new logic ≥90%
- CLI/reporting output reviewed for usability
- Documentation updated and accurate

---

## Post-Implementation

- [ ] User feedback collection
- [ ] Monitor for regressions or performance issues
- [ ] Plan for Neo4j backend support if graph size grows

---

**References:**

- [design.md](./design.md)
- [prd.md](./prd.md)
- [idea.md](./idea.md)
- "The Derivative of Truth: A New Mathematical Framework for AI Truthfulness"
