# Persona and Avatar Intelligence

This guide covers how the project personalizes output to the user and how the optional Avatar Intelligence overlays help explain, score, and diversify generated content. Personalization is built from a persona graph, a persistent system prompt, writing rules, content angles, and local memory.

Every post is plain text — there's no audio or special format involved."Personalised to you" means the AI prompt is pre-loaded with four layers of context so the output reads like _you_ wrote it, not a generic AI:

**1. Your persona graph (`data/avatar/persona_graph.json`)** The authoritative identity source for every post: your name, role, location, specialties, and real project outcomes, stored as a structured JSON graph (projects, companies, skills, role history, and verifiable claims). Copy from `data/avatar/persona_graph.example.json`, fill in your own details, and edit directly in the repo — no env var required. Gitignored so your personal career data stays private. At startup, `load_avatar_state()` reads the graph and builds a ranked list of `EvidenceFact` objects used for all grounding, retrieval, and persona chat. Optionally enriched with live GitHub data via `services/github_service.py` — repo metadata plus compact README summaries (configurable) so the model has stronger project context.

**2. Persona system prompt (`PERSONA_SYSTEM_PROMPT` in `.env`)** A detailed persona loaded into every AI call, covering:

- Identity and credibility anchors — **domain-separated**: AI projects (2024–present) are listed separately from legacy infrastructure (TPG/USPS JMS work, pre-2024) with a hard rule forbidding the model from blending them
- Target audience, voice guidance, and forbidden phrases
- **Technical glossary** — 10 authoritative definitions (RAG, BM25, kNN, MCP, FastMCP, JMS, SentenceTransformers, CRISP-DM, etc.) with a hard rule: never expand an abbreviation that isn't in the glossary (prevents hallucinations like "RAG = Reactive Agent Framework")

**3. Writing rules (configurable via `.env`, loaded by `ollama_service.py`)** Per-pillar instructions injected into every AI call. All four are overridable in `.env` without touching code (`SSI_ESTABLISH_BRAND`, `SSI_FIND_RIGHT_PEOPLE`, `SSI_ENGAGE_WITH_INSIGHTS`, `SSI_BUILD_RELATIONSHIPS`). The defaults live in `services/shared.py`. Built-in rules:

- Never start with "I"
- Never use filler phrases ("Game changer", "Excited to share", "landscape", "leverage", etc.)
- No bullet points in the body — short punchy paragraphs only
- Hook in the first line (bold claim, surprising stat, or short story)

## Persona graph

The primary identity source is `data/avatar/persona_graph.json`, which stores name, role, location, companies, skills, projects, and verifiable claims in structured JSON. At startup, `load_avatar_state()` converts this graph into ranked `EvidenceFact` objects used for grounding, retrieval, and persona chat.

Below is a visual schema of the persona graph (see `data/avatar/persona_graph.json`):

```mermaid
classDiagram
    class Person {
        string name
        string title
        string location
        string[] links
    }
    class Company {
        string id
        string name
        string[] aliases
    }
    class Skill {
        string id
        string name
        string[] aliases
        string scope
    }
    class Project {
        string id
        string name
        string companyId
        string years
        string details
        string[] skills
        string[] aliases
    }
    class Claim {
        string id
        string text
        string[] projectIds
        string confidenceHint
    }

    Person "1" -- "*" Project : has
    Company "1" -- "*" Project : employs
    Project "*" -- "*" Skill : uses
    Project "*" -- "*" Claim : supports
    Claim "*" -- "*" Project : about
```

If your Markdown viewer does not support Mermaid, see the schema fields above or refer to the example JSON for structure.

The persona graph can also be enriched with live GitHub data through `services/github_service.py`, including repository metadata and compact README summaries. The README notes cached metadata in `github_repos_cache.json` and README summaries in `github_readmes_cache.json` with a 24-hour TTL.

GitHub enrichment details:

- Source data: public repo name, description, primary language, topics, stars, and optional README summary text
- README handling: markdown is cleaned to plain text, then clipped to sentence boundaries for compact prompt injection
- Caching: repo metadata is cached in `github_repos_cache.json` and README summaries in `github_readmes_cache.json` (24h TTL)
- Filtering: use `GITHUB_REPO_FILTER` to include only selected repos
- Context budgeting: GitHub context is assembled with hard caps so prompts stay stable and fast

GitHub context controls in `.env`:

- `GITHUB_INCLUDE_README_SUMMARIES` (default `true`)
- `GITHUB_REPO_MAX_COUNT` (default `12`)
- `GITHUB_README_MAX_CHARS` (default `1200`)
- `GITHUB_CONTEXT_MAX_CHARS` (default `30000`)

Below is a class diagram of the GitHub repos cache structure (`github_repos_cache.json`):

```mermaid
classDiagram
    class GithubReposCache {
        float fetched_at
        Repo[] repos
    }
    class Repo {
        int id
        string node_id
        string name
        string full_name
        bool private
        Owner owner
        string html_url
        string description
        bool fork
        string url
        string language
        int stargazers_count
        int watchers_count
        int forks_count
        int open_issues_count
        string default_branch
        License license
        ... (many other GitHub API fields)
    }
    class Owner {
        string login
        int id
        string avatar_url
        string html_url
        ...
    }
    class License {
        string key
        string name
        string spdx_id
        string url
        ...
    }
    GithubReposCache --> "*" Repo : contains
    Repo --> Owner : owned by
    Repo --> License : licensed under
```

If your Markdown viewer does not support Mermaid, see the schema fields above or refer to the example JSON for structure.

## Persona system prompt

`PERSONA_SYSTEM_PROMPT` is loaded into every AI call and carries identity anchors, voice guidance, audience framing, forbidden phrases, and a technical glossary. 

The glossary is also a control mechanism: the model is told never to expand abbreviations that are not present in the approved glossary, which is meant to reduce hallucinated expansions such as incorrect RAG definitions.

## Writing rules

Per-pillar writing rules are configurable in `.env` through `SSI_ESTABLISH_BRAND`, `SSI_FIND_RIGHT_PEOPLE`, `SSI_ENGAGE_WITH_INSIGHTS`, and `SSI_BUILD_RELATIONSHIPS`, while defaults live in `services/shared.py`. The built-in rules include never starting with “I,” avoiding filler phrases, using short punchy paragraphs instead of bullets, and leading with a hook in the first line.

The README frames these rules as drawing on Neuro-Linguistic Programming ideas such as pattern interrupts, presupposition, and anchoring, while also referencing `docs/nlp-basics.md` for the repo’s communication primer.

## Per-post angle

Every topic in `content_calendar.py` carries both a unique `angle` and an `ssi_component`. The angle prevents generic rehash content, while the SSI mapping ensures that scheduled output rotates through all four Social Selling Index pillars over time.

## Explain mode

`--avatar-explain` adds transparency to scheduling and curation runs by showing which evidence IDs were retrieved, how facts scored, and which claim tokens were evaluated by the truth gate. The README positions this as the main diagnostic tool when a post feels weakly grounded or uses the wrong project context.

## Learning report

`--avatar-learn-report` reads moderation decisions from `data/avatar/learning_log.jsonl` and aggregates reason-code frequencies, common removals, and advisory recommendations. The documentation explicitly states that this report is read-only and does not modify the persona graph or configuration files.

Below is a class diagram of the learning log entry structure (`data/avatar/learning_log.jsonl`):

```mermaid
classDiagram
    class LearningLogEntry {
        string timestamp
        string channel
        string route
        string policy
        float confidence_score
        string confidence_level
        string dominant_signal
        string reason
        string article_ref
        string run_id
    }
    LearningLogEntry : timestamp - ISO timestamp
    LearningLogEntry : channel - e.g. linkedin, youtube, all
    LearningLogEntry : route - post, idea, etc.
    LearningLogEntry : policy - routing policy
    LearningLogEntry : confidence_score - float (0.0–1.0)
    LearningLogEntry : confidence_level - high/medium/low
    LearningLogEntry : dominant_signal - main signal for decision
    LearningLogEntry : reason - human-readable explanation
    LearningLogEntry : article_ref - source article URL
    LearningLogEntry : run_id - batch/run identifier
```

If your Markdown viewer does not support Mermaid, see the schema fields above or refer to the example JSONL for structure.

## Confidence policy

Curated posts receive a confidence score based on truth-gate signal, grounding quality, and narrative repetition. The routing policy can then be set to `strict`, `balanced`, or `draft-first`, controlling whether high-, medium-, or low-confidence outputs are scheduled, sent to Ideas, or blocked.

| Policy        | High confidence | Medium confidence | Low confidence |
| ------------- | --------------- | ----------------- | -------------- |
| `strict`      | Scheduled post  | Ideas board       | Blocked        |
| `balanced`    | Scheduled post  | Scheduled post    | Ideas board    |
| `draft-first` | Ideas board     | Ideas board       | Ideas board    |

## Narrative memory

The local memory file `data/avatar/narrative_memory.json` stores extracted themes and bold-assertion claims from generated posts, curated articles, and interactive console chat. Narrative memory is a short-term, session-aware context store that powers continuity, diversity, and explainability across all modes of the system.

**What it contains:**

- **recentThemes:** FIFO list of keywords and topics recently discussed, generated, or focused on (e.g., “reinforcement learning”, “agentic patterns”, “cloudflare mesh”, “build relationships”). These help the system avoid repetition, reinforce ongoing topics, and provide context for new content or answers.
- **recentClaims:** FIFO list of recent, user-specific claims, insights, or statements (e.g., “the real engineering bottleneck is the inefficiency of maintaining unique copies for every specific task”). These can be surfaced as evidence, context, or inspiration for new posts, answers, or explanations.
- **openNarrativeArcs:** (future) List for tracking ongoing storylines, projects, or multi-step explanations that are not yet resolved or closed.
- **lastUpdated:** ISO timestamp of the last update to this memory file.

**How it’s used:**

- Narrative memory is referenced in all retrieval and grounding operations—including automated post generation, curation, and interactive console chat.
- When you ask questions or generate posts, the system can pull supporting facts, stories, or context from narrative memory, just like it does from persona and domain knowledge.
- It helps the agent avoid repeating itself, maintain continuity, and cite your own prior statements as evidence or context.
- If your query or prompt matches a theme or claim in narrative memory, it can be surfaced as supporting evidence or context—helping the system stay contextually aware of your recent topics, claims, and ongoing narrative arcs.
- The most recent items also contribute to a repetition penalty in confidence scoring, discouraging repetitive framing across weeks.

**Example structure:**

```json
{
    "recentThemes": ["reinforcement", "learning", "agentic", "patterns", ...],
    "recentClaims": [
        "the real engineering bottleneck is the inefficiency of maintaining unique copies for every specific task",
        "verifiable rewards beat llm-as-a-judge every time"
    ],
    "openNarrativeArcs": [],
    "lastUpdated": "2026-04-19T18:41:11.539183+00:00"
}
```

Below is a class diagram of the narrative memory structure (`data/avatar/narrative_memory.json`):

```mermaid
classDiagram
    class NarrativeMemory {
        string[] recentThemes
        string[] recentClaims
        string[] openNarrativeArcs
        string lastUpdated
    }
    NarrativeMemory : recentThemes - FIFO list of extracted themes
    NarrativeMemory : recentClaims - FIFO list of bold claims
    NarrativeMemory : openNarrativeArcs - (future) unresolved story arcs
    NarrativeMemory : lastUpdated - ISO timestamp
```

If your Markdown viewer does not support Mermaid, see the schema fields above or refer to the example JSON for structure.
