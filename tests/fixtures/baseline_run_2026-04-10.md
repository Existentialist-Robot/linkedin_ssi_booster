# Baseline Run Artifacts — 2026-04-10

Captured from `--curate --dry-run` before Avatar Intelligence feature implementation.
Used as regression compare set for post-migration validation.

## Run Summary

- **Date:** 2026-04-10
- **Command:** `python main.py --curate --dry-run`
- **Model:** gemma4 (Q4_K_M, 17.3 GiB, CPU-only, 6 threads)
- **Model load time:** ~92 seconds
- **Articles found:** 115 relevant across 15 feeds
- **Identity source:** PROFILE_CONTEXT (pre-migration)

## Skipped Articles (empty curation output)

- `https://solace.com/blog/benefits-solace-event-portal-mcp-server-build-manage-event-driven-system/`
  - Reason: `Curation output was empty after cleanup`
- `https://aws.amazon.com/blogs/machine-learning/from-isolated-alerts-to-contextual-intelligence-agentic-maritime-anomaly-analysis-with-generative-ai/`
  - Reason: `Curation output was empty after cleanup`

## Generated Posts (baseline sample)

### 1. LangChain + MongoDB Partnership

- **Source:** LangChain Blog
- **SSI Component:** `find_right_people`
- **Channel:** all (LinkedIn, X, Bluesky, YouTube Short)
- **Generation time:** ~5m17s (first article — model cold start)
- **LinkedIn:** Addresses production agent memory fragmentation; references Answer42 9-agent Spring Batch pipeline; ends with engagement question about vector DB trade-offs.
- **X:** Focuses on state management bottleneck.
- **Bluesky:** Agentic pipelines / persistent memory angle.
- **YouTube Short:** Answer42 9-agent pipeline context; "signal over noise" CTA.
- **Hashtags:** `#AIEngineering #VectorSearch #MongoDB #AgenticWorkflows #SoftwareArchitecture`

### 2. How to Run Claude Code Agents in Parallel

- **Source:** Towards Data Science
- **SSI Component:** `establish_brand`
- **Channel:** all
- **Generation time:** ~1m35s (warm model)
- **LinkedIn:** Parallelism = orchestration problem; Answer42 9-agent pipeline cited; "distributed debugging nightmare" framing; spec-driven anchor.
- **X:** State management angle.
- **Bluesky:** Orchestration overhead framing.
- **YouTube Short:** Answer42 context drift; Spring Batch harness; "expensive chaos" punchline.
- **Hashtags:** `#AIEngineering #MultiAgentSystems #SoftwareEngineering #AgenticWorkflows`

### 3. Croissant: a metadata format for ML-ready datasets

- **Source:** Google AI Blog
- **SSI Component:** `engage_with_insights`
- **Channel:** all
- **Generation time:** ~2m30s (warm model)
- **LinkedIn:** Data discovery > data scaling framing; Croissant targets correct friction point; Answer42 pipeline cited; ends with engagement question.
- **X:** Contrarian take — better ingestion pipelines needed, not just better descriptions.
- **Bluesky:** Metadata for retrieval, not just easier loading.
- **YouTube Short:** Data format chaos is real bottleneck; "research to production" framing.
- **Hashtags:** `#MLCommons #MachineLearning #DataEngineering #Croissant #AI`

## Key Identity Signals in Baseline Output

Consistent persona signals observed across all posts (sourced from PROFILE_CONTEXT):

- **Project:** Answer42 (9-agent Spring Batch pipeline)
- **Skills/domains:** AI engineering, Spring Batch, multi-agent systems, RAG, vector search
- **Data sources cited:** Crossref, Semantic Scholar (Answer42 context)
- **Tone:** Practitioner voice, contrarian takes, ends with engagement question on LinkedIn
- **CTA:** "If you're an AI engineer or Java dev who wants signal over noise — subscribe." (YouTube)
- **Self-reference style:** "When I built..." / "In my Answer42 pipeline..."

## Regression Baseline Expectations (post-migration)

After persona graph migration the following must hold:

1. Answer42 project claims still appear in LinkedIn posts.
2. Spring Batch / 9-agent pipeline references appear in `establish_brand` posts.
3. Crossref + Semantic Scholar still cited in Answer42 context.
4. YouTube CTA remains consistent ("AI engineer or Java dev").
5. No new hallucinated projects or companies introduced.
6. Article skip behavior for empty curation output unchanged.
