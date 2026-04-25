# Feature Idea: Online Control via Decoding/Routing (`--dot-learn` Mode)

## Overview

Introduce a new CLI mode (`--dot-learn`) that enables the system to run an automated, overnight pipeline for prompt optimization and evidence-grounded generation. This mode leverages the Derivative of Truth (DoT) framework as an online critic to steer LLM outputs through candidate generation, scoring, and selection—without model fine-tuning.

## Problem Statement (Project Context)

Manual prompt engineering and retrieval tuning are time-consuming and require expert intervention. There is a need for an automated, data-driven way to iteratively improve prompt templates, retrieval strategies, and decoding parameters to maximize factuality, grounding, and explainability in generated content.

## Proposed Solution

Implement an "online control" pipeline that:

- Runs on a large batch of prompts (e.g., from RSS feeds or synthetic generation)
- For each prompt:
  - Retrieves context (BM25 + Knowledge Graph)
  - Generates multiple completions with varied decoding parameters
  - Scores each completion using `score_claim_with_truth_gradient`
  - Selects the highest-scoring candidate above a threshold
  - Optionally retries or flags for review if no strong candidates
  - Logs all candidates, scores, and explanations for analysis
- Optionally presents top candidates and explanations for user review
- Iteratively updates prompt templates and retrieval strategies based on what yields the highest truth_gradient

## Expected Benefits (Project User Impact)

- Rapid, automated improvement of prompt and retrieval quality
- Higher factuality, grounding, and explainability in outputs
- No need for model fine-tuning—safe, low-risk, and fast iteration
- Transparent logs for analysis and future supervised or RL training
- User can review and adopt the best prompt/retrieval strategies

## Technical Considerations (Project Integration)

- Integrates with existing BM25, Knowledge Graph, and DoT scoring pipeline
- Uses the same evidence annotation and truth_gradient scoring as production
- CLI flag (`--dot-learn`) triggers the batch pipeline
- Supports batch input from RSS feeds, curated prompts, or synthetic data
- Logs all results for offline analysis and future training

## Project System Integration

- Main entrypoint: `main.py` (add `--dot-learn` mode)
- Uses services: `hybrid_retriever`, `knowledge_graph`, `derivative_of_truth`
- Output: logs, updated prompt templates, and optionally user review interface

## Initial Scope

- Batch pipeline for overnight runs
- Candidate generation, scoring, and selection
- Logging and reporting of all candidates and scores
- Optional user review of top candidates
- No model fine-tuning in initial version

## Success Criteria

- System can run overnight on a large prompt set without intervention
- Outputs show measurable improvement in truth_gradient scores over time
- Logs and reports are available for analysis
- User can update prompt templates and retrieval strategies based on results

---

This feature will enable rapid, automated, and explainable improvement of your RAG pipeline—making the most of your Derivative of Truth framework with minimal engineering overhead.

---

## Example Prompts (for Understanding)

**Unoptimized Prompt:**

Summarize the following article for a LinkedIn post.

---

**Optimized Prompt #1 (Evidence Grounding):**

Summarize the following article for a LinkedIn post.

- Use only facts that are directly supported by the article or my persona knowledge graph.
- Highlight one technical insight and one practical takeaway.
- Avoid generic statements; cite numbers, names, or outcomes where possible.
- If a claim cannot be grounded in evidence, omit or flag it.
- Article: [ARTICLE TEXT HERE]

---

**Optimized Prompt #2 (Transparency/Compliance Focus):**

Summarize the following article for a LinkedIn post.

- For every claim, explicitly cite the supporting sentence or fact from the article or my persona knowledge graph.
- If a claim cannot be directly supported, add a parenthetical note: (evidence not found).
- List all sources and references at the end of the summary.
- Avoid paraphrasing unsupported content; only include what can be traced to evidence.
- Article: [ARTICLE TEXT HERE]

---
