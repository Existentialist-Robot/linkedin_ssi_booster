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

- [ ] Review and document current BM25 and truth gate logic
- [ ] Select and install Python graph library (`networkx`)
- [ ] Define minimal node/link schema (Person, Project, Skill, Fact, etc.)
- [ ] Plan serialization format for graph (JSON/GraphML)
- [ ] Ensure test coverage for existing retrieval and truth gate

---

## Implementation Steps

### 1. Knowledge Graph Subsystem

- [ ] Implement `KnowledgeGraphManager` class
  - [ ] Methods: `add_fact`, `link_entities`, `query`, `serialize_graph`, `load_graph`
  - [ ] Node/link schema with metadata (source, confidence, timestamp)
- [ ] Integrate with avatar learning: add new facts/links as knowledge is acquired
- [ ] Add serialization (save/load graph)
- [ ] Unit tests for graph operations

### 2. Hybrid Retrieval & Reranking

- [ ] Implement `HybridRetriever` class
  - [ ] Use BM25 to select top candidates
  - [ ] Compute graph proximity (shortest path from persona to candidate)
  - [ ] Compute claim support (number/strength of supporting links)
  - [ ] Combine scores per formula: final = 0.7 × bm25 + 0.2 × graph proximity + 0.1 × claim support
- [ ] Integrate with post generation and grounding
- [ ] Unit tests for hybrid scoring and reranking

### 3. Optional: Truth Gate Enhancement

- [ ] (Optional) Add graph-based claim support to truth gate
  - [ ] If enabled, require both BM25 and graph support for high-confidence claims
  - [ ] Unit tests for enhanced truth gate

### 4. Documentation & Examples

- [ ] Document graph schema, update workflow, and scoring logic
- [ ] Provide example queries and usage patterns
- [ ] Update README and feature docs

---

## Project Quality Gates

- [ ] All new code is type-annotated and tested
- [ ] No regression in existing BM25/truth gate logic
- [ ] Graph operations do not noticeably slow down generation/curation
- [ ] Documentation is complete and accurate

---

## Testing Phase

- [ ] Unit tests for graph and hybrid retrieval
- [ ] Integration tests for end-to-end post generation
- [ ] Manual validation of persona-aware reranking

---

## Post-Implementation

- [ ] Solicit user/developer feedback
- [ ] Monitor performance and correctness
- [ ] Plan for future graph DB (Neo4j) if scale/complexity grows

---

## Status Tracking

- [ ] Not Started
- [ ] In Progress
- [ ] Complete
- [ ] Blocked
- [ ] Review Required
- [ ] Quality Check Failed
- [ ] Integration Pending
