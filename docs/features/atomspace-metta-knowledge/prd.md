# Product Requirements Document: AtomSpace/MeTTa-Inspired Knowledge Graph for Incremental Learning

## Executive Summary

This feature introduces a flexible, graph-based knowledge representation layer inspired by AtomSpace and MeTTa (OpenCog) to the LinkedIn SSI Booster. The goal is to enable the system to represent, integrate, and reason over new knowledge as it is gathered from user interactions, content curation, and external sources—supporting advanced learning, explainability, and applied cognition.

## Project Context

- Current persona and domain knowledge are stored as lists or dicts, limiting expressiveness, incremental updates, and explainability.
- The system is designed for adaptive learning, content generation, and curation, with a focus on transparency and control.
- Users want to see how new knowledge is integrated, cited, and used in outputs.

## User Stories

- **As a power user**, I want new facts and experiences to be automatically integrated into the system’s knowledge base, so that the AI can reference and build on them in future outputs.
- **As a technical user**, I want to trace how a generated post or answer was grounded in specific facts or experiences, so I can trust and debug the system’s reasoning.
- **As a developer**, I want to extend the knowledge schema with new types of entities or relationships, so the system can adapt to new domains and use cases.

## Functional Requirements

- Represent new knowledge as nodes and typed links in a graph (hypergraph style)
- Attach metadata (source, confidence, timestamp) to each node/link
- Support incremental updates: add, link, or update knowledge without breaking existing data
- Enable graph traversal and pattern matching for retrieval and reasoning
- Integrate with the learning/memory subsystem: new knowledge is added as graph nodes/links
- Retrieve relevant subgraphs for grounding, post generation, and explanations
- Provide utilities for graph updates, queries, and serialization

## Non-Functional Requirements

- **Performance:** Graph operations must not noticeably slow down post generation or curation
- **Usability:** Graph structure and queries should be accessible to developers and advanced users
- **Reliability:** Integration must not break existing deterministic fact retrieval
- **Maintainability:** Schema and update logic should be documented and easily extensible
- **Explainability:** System must be able to show how a fact was used or cited in outputs

## Project System Integration

- Integrate with avatar learning subsystem for incremental knowledge updates
- Retrieval layer uses graph traversal to find relevant facts for grounding
- Optionally, expose graph queries for debugging, analytics, or advanced user queries
- Ensure compatibility with existing persona/domain fact ingestion

## Dependencies

- Python graph library (e.g., `networkx`)
- Existing avatar learning and fact retrieval subsystems
- (Optional) Neo4j or other graph DB for future scalability

## Success Metrics

- New knowledge is represented as graph nodes/links and can be incrementally updated
- System can retrieve and explain how a fact was used or cited
- Integration does not break existing deterministic fact retrieval
- Users report improved trust, transparency, and adaptability

## Timeline & Milestones

- **Prototype:** In-memory graph for new learned facts (1 week)
- **Integration:** Connect to learning/memory subsystem (1 week)
- **Retrieval:** Graph-based retrieval for grounding/explanation (1 week)
- **Docs & Examples:** Schema, update workflow, and example queries (1 week)
- **Review:** User/developer feedback and iteration (ongoing)
