# Acceptance Test Set — Avatar Intelligence and Learning Engine

Regression test cases derived from baseline run artifacts (2026-04-10).
Used for post-migration comparison: verify persona graph produces equivalent
identity grounding as PROFILE_CONTEXT before removal.

## Test Articles

These three articles from the baseline represent all four SSI components
(build_relationships covered by Epic 1A+ regression runs).

### TC-01: LangChain + MongoDB Partnership

- **URL:** `https://blog.langchain.com/announcing-the-langchain-mongodb-partnership-the-ai-agent-stack-that-runs-on-the-database-you-already-trust/`
- **SSI Component:** `find_right_people`
- **Regression assertions:**
  - LinkedIn post references Answer42 or 9-agent pipeline
  - Post includes engagement question (ends with `?`)
  - X post ≤ 280 chars (verify channel constraint)
  - No hallucinated projects introduced
  - Hashtags include at least one of: `#AIEngineering`, `#AgenticWorkflows`

### TC-02: How to Run Claude Code Agents in Parallel

- **URL:** `https://towardsdatascience.com/how-to-run-claude-code-agents-in-parallel/`
- **SSI Component:** `establish_brand`
- **Regression assertions:**
  - LinkedIn post references Answer42 or Spring Batch
  - Post takes a contrarian/practitioner framing
  - YouTube Short includes "AI engineer or Java dev" CTA
  - No hallucinated companies (e.g. not employer names not in graph)
  - Hashtags include at least one of: `#AIEngineering`, `#MultiAgentSystems`

### TC-03: Croissant: a metadata format for ML-ready datasets

- **URL:** `http://blog.research.google/2024/03/croissant-metadata-format-for-ml-ready.html`
- **SSI Component:** `engage_with_insights`
- **Regression assertions:**
  - LinkedIn post references Answer42 pipeline context
  - Post challenges the article's premise (contrarian take)
  - Engagement question present in LinkedIn post
  - Hashtags include `#MachineLearning` or `#DataEngineering`

## Identity Signal Assertions (all test cases)

Apply to every generated post in the regression set:

| Signal           | Expected                                   | Source entity                  |
| ---------------- | ------------------------------------------ | ------------------------------ |
| Primary project  | `Answer42` appears in ≥1 channel           | `projects[].name = "Answer42"` |
| Pipeline detail  | `9-agent` or `Spring Batch` in ≥1 channel  | `projects[].details`           |
| External sources | `Crossref` or `Semantic Scholar` optional  | `projects[].details`           |
| Audience CTA     | `AI engineer or Java dev` in YouTube Short | `person.title` or `skills`     |
| No hallucination | No org names absent from persona graph     | validate via grounding test    |

## Regression Check Protocol

1. After persona graph is populated (T7.2), run:
   ```
   python main.py --curate --dry-run
   ```
2. Capture output.
3. Manually verify TC-01, TC-02, TC-03 identity signal assertions.
4. If all pass → retrieval cutover (T7.3) is safe to execute.

## Notes

- These are developer-executed checks per design.md section 16.5.
- Article availability may vary; use cached summary if URL is stale.
- Regression is qualitative (identity signal presence), not exact string match.
