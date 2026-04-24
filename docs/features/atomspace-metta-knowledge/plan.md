# Implementation Plan: AtomSpace/MeTTa-Inspired Knowledge Graph for Incremental Learning

## Overview

This plan details the step-by-step implementation of a hybrid BM25 + NetworkX knowledge graph subsystem for incremental learning, retrieval, and persona-aware reranking in the LinkedIn SSI Booster. The design preserves the current truth gate and BM25-centric workflow, adding graph intelligence as an additive layer.

---

## Project System Integration Summary

- **BM25 Retriever:** Remains the primary candidate selector for claims, facts, memory, and summaries.
- **NetworkX Knowledge Graph:** Adds persona-aware reranking and claim support, linking persona ↔ skills ↔ projects ↔ claims ↔ domain facts.
- **Hybrid Scoring:** final = 0.7 × bm25 + 0.2 × graph proximity + 0.1 × claim support.
- **Truth Gate:** Continues to use BM25 and token checks; graph support is optional and additive.

---

## Pre-Implementation Checklist

- [x] Review and document current BM25 and truth gate logic
- [x] Select and install Python graph library (`networkx`)
- [x] Define minimal node/link schema (Person, Project, Skill, Fact, etc.)
- [x] Plan serialization format for graph (JSON/GraphML)
- [x] Ensure test coverage for existing retrieval and truth gate

---

## Implementation Steps

### 1. Knowledge Graph Subsystem

- [x] Implement `KnowledgeGraphManager` class
  - [x] Methods: `add_fact`, `link_entities`, `query`, `serialize_graph`, `load_graph`
  - [x] Node/link schema with metadata (source, confidence, timestamp)
- [x] Integrate with avatar learning: add new facts/links as knowledge is acquired
- [x] Add serialization (save/load graph)
- [x] Unit tests for graph operations

### 2. Hybrid Retrieval & Reranking

- [x] Implement `HybridRetriever` class
  - [x] Use BM25 to select top candidates
  - [x] Compute graph proximity (shortest path from persona to candidate)
  - [x] Compute claim support (number/strength of supporting links)
  - [x] Combine scores per formula: final = 0.7 × bm25 + 0.2 × graph proximity + 0.1 × claim support
- [x] Integrate with post generation and grounding
- [x] Unit tests for hybrid scoring and reranking

### 3. Optional: Truth Gate Enhancement

- [x] (Optional) Add graph-based claim support to truth gate
  - [x] If enabled, require both BM25 and graph support for high-confidence claims
  - [x] Unit tests for enhanced truth gate

### 4. Documentation & Examples

- [x] Document graph schema, update workflow, and scoring logic
- [x] Provide example queries and usage patterns
- [x] Update README and feature docs

---

## Project Quality Gates

- [x] All new code is type-annotated and tested
- [x] No regression in existing BM25/truth gate logic
- [x] Graph operations do not noticeably slow down generation/curation
- [x] Documentation is complete and accurate

---

## Testing Phase

- [x] Unit tests for graph and hybrid retrieval
- [x] Integration tests for end-to-end post generation
- [x] Manual validation of persona-aware reranking

---

## Post-Implementation

- [x] Solicit user/developer feedback
- [x] Monitor performance and correctness
- [x] Plan for future graph DB (Neo4j) if scale/complexity grows

---

## Status Tracking

- [x] Not Started
- [x] In Progress
- [x] Complete
- [x] Blocked
- [x] Review Required
- [x] Quality Check Failed
- [x] Integration Pending
