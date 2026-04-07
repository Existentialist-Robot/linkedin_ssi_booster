# LinkedIn SSI Booster — Buffer API Integration

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version: alpha-0.0.0.11](https://img.shields.io/badge/version-alpha--0.0.0.11-orange.svg)]()

Automates LinkedIn post generation and scheduling via local Ollama to systematically grow your LinkedIn Social Selling Index (SSI) score.

## What is the LinkedIn SSI?

The [LinkedIn Social Selling Index](https://www.linkedin.com/sales/ssi) is a 0–100 score LinkedIn updates daily. It measures how effectively you build your personal brand, find the right people, engage with insights, and build relationships — the four pillars LinkedIn's algorithm uses to determine how widely your content and profile are surfaced to others.

A higher SSI directly correlates with more profile views, post reach, and inbound connection requests. LinkedIn's own data shows that professionals with an SSI above 70 get 45% more opportunities than those below 30.

The score breaks down into four components (25 points each):

| Component                             | What LinkedIn measures                                                            |
| ------------------------------------- | --------------------------------------------------------------------------------- |
| **Establish your professional brand** | Completeness of profile, consistency of posting, saves/shares on your content     |
| **Find the right people**             | Profile searches landing on you, connection acceptance rate, right-audience reach |
| **Engage with insights**              | Shares, comments, and reactions on industry content; thought leadership signals   |
| **Build relationships**               | Connection growth, message response rate, relationship depth                      |

### Why automate it?

SSI decays if you go quiet — LinkedIn penalises inconsistency. Manually writing 3 posts per week, curating industry articles with original commentary, and maintaining an on-brand voice across hundreds of posts is simply not sustainable alongside a full-time engineering role.

This tool handles the repeatable parts:

- **Consistent cadence** — 3 posts/week scheduled to Buffer at proven engagement times (Tue/Wed/Fri 4 PM EST)
- **On-brand content** — every post is grounded in your real projects, real numbers, and real technical voice via a detailed persona prompt
- **All four SSI pillars** — the content calendar and curator rotate across all four components so no single pillar is neglected
- **Curation pipeline** — fetches today's AI/GovTech news, filters by your niche, and generates commentary that you can either:
  - push to Buffer Ideas for review and manual approval (default), or
  - schedule directly as posts to your Buffer queue (using `--type post`)

You control whether curated content is reviewed before publishing or scheduled directly. The tool removes the blank-page problem, but you decide what goes live.

## How it works

1. **Content calendar** — 4 weeks of topics, each mapped to a specific SSI component and angle, ensuring balanced coverage and unique perspectives
   - The calendar is defined in `content_calendar.py` as a dictionary with `week_1` to `week_4`, each containing a list of post topics.
   - Each topic includes:
     - `title`: The main subject of the post
     - `angle`: A unique perspective or story for that topic (prevents generic/rehash content)
     - `ssi_component`: One of `establish_brand`, `find_right_people`, `engage_with_insights`, or `build_relationships` — ensuring every post directly supports a specific SSI pillar
     - `hashtags`: A list of relevant hashtags (used for LinkedIn posts)
   - The calendar is designed to:
     - Rotate through all four SSI components over four weeks, so no pillar is neglected
     - Draw topics from real projects, technical wins, and lessons learned, not generic AI content
     - Provide a distinct "angle" for each post, so every week’s content feels fresh and specific

2. **AI generation** — Ollama generates posts as plain text, personalised to you (see below)

3. **Post scheduling** — The scheduler distributes posts from the calendar to Buffer at configured weekdays/times (default: Tue/Wed/Fri 4 PM Toronto time). Each week, max posts per channel equals the number of configured scheduler slots.
   - Scheduling is CLI-triggered (`python main.py --generate --schedule --week N`) — there is no always-running local background scheduler process in this repo.
   - The scheduler uses your `.env` SSI focus weights to determine how many posts per week should target each SSI component (e.g., if `establish_brand` is set to 40%, it will get more posts that week).
   - If there are not enough posts for a component, the scheduler fills remaining slots with available topics, always ensuring variety.
   - Posts are never repeated within a week, and the order within each component is preserved.

4. **Content curator** — fetches AI/GovTech news and creates ideas for curation posts

5. **SSI tracker** — weekly report with specific actions per component

## How post personalisation works

Every generated post is plain text — there's no audio or special format involved.  
"Personalised to you" means the AI prompt is pre-loaded with four layers of context so the output reads like _you_ wrote it, not a generic AI:

**1. Your profile (`PROFILE_CONTEXT` in `.env`)**  
Injected into every prompt: your name, role, location, specialties, and real project outcomes. Stored in `.env` (gitignored) so it stays private and out of source control. The profile is also enriched at startup with live GitHub data via `services/github_service.py` — repo metadata plus compact README summaries (configurable) so the model has stronger project context.

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
- `PROFILE_CONTEXT_MAX_CHARS` (default `120000`)

**2. Persona system prompt (`PERSONA_SYSTEM_PROMPT` in `.env`)**  
A detailed persona loaded into every AI call, covering:

- Identity and credibility anchors — **domain-separated**: AI projects (2024–present) are listed separately from legacy infrastructure (TPG/USPS JMS work, pre-2024) with a hard rule forbidding the model from blending them
- Target audience, voice guidance, and forbidden phrases
- **Technical glossary** — 10 authoritative definitions (RAG, BM25, kNN, MCP, FastMCP, JMS, SentenceTransformers, CRISP-DM, etc.) with a hard rule: never expand an abbreviation that isn't in the glossary (prevents hallucinations like "RAG = Reactive Agent Framework")

**3. Writing rules (configurable via `.env`, loaded by `ollama_service.py`)**  
Per-pillar instructions injected into every AI call. All four are overridable in `.env` without touching code (`SSI_ESTABLISH_BRAND`, `SSI_FIND_RIGHT_PEOPLE`, `SSI_ENGAGE_WITH_INSIGHTS`, `SSI_BUILD_RELATIONSHIPS`). The defaults live in `services/shared.py`. Built-in rules:

- Never start with "I"
- Never use filler phrases ("Game changer", "Excited to share", "landscape", "leverage", etc.)
- No bullet points in the body — short punchy paragraphs only
- Hook in the first line (bold claim, surprising stat, or short story)

The writing rules draw on **Neuro-Linguistic Programming (NLP)** principles — specifically pattern interrupts (scroll-stopping first lines), presupposition (assuming the reader already cares), and anchoring (pairing your name with specific technical outcomes so readers associate _you_ with the domain). The forbidden-phrases list functions as a negative anchor removal layer: stripping hollow corporate phrases forces the model toward concrete, specific language that builds credibility. For the theoretical underpinning, see [_Monsters and Magical Sticks, There's no Such Thing as Hypnosis?_ by Steven Heller & Terry Steele](https://www.amazon.com/Monsters-Magical-Sticks-Theres-Hypnosis-ebook/dp/B007WMOMXU) — an accessible introduction to how language patterns shape perception.
Notes: https://richardstep.com/downloads/tools/Notes--Monsters-and-Magic-Sticks.pdf

**4. Per-post angle and SSI mapping (`content_calendar.py`)**  
Each topic in the calendar has:

- a specific `angle` (e.g. _"contrast AI-TDD with vibe coding"_) so every post has a distinct point of view
- an explicit `ssi_component` so the system can guarantee all four SSI pillars are covered over time

For curated posts (`--curate`), `content_curator.py` filters RSS feeds by your niche keywords (RAG, Neo4j, GovTech, MCP, Spring AI…) so only domain-relevant articles are ever posted — not random tech news.

**Guaranteed output integrity**  
Hashtags (for `--generate` targeting LinkedIn) and source article links (for `--curate`) are always appended programmatically _after_ the model responds — never left to the model to include or place correctly. X posts skip hashtag appending entirely — X's 280-character limit leaves no room for them, and the prompt instructs the model to write a single tight paragraph instead of the multi-paragraph LinkedIn format.

`--generate` and `--curate` apply a three-layer grounding strategy:

1. **Fact retrieval** — a small set of relevant facts is retrieved from `PROFILE_CONTEXT` and injected into each prompt.
2. **Balance rules** — prompt-level instructions require every factual claim to come from either the article text or the provided profile facts, cap personal references to at most one per post, and forbid invented numbers/dates/companies.
3. **Truth gate** — a lightweight post-generation filter scans each sentence for numeric claims, year references, dollar amounts, and company-name patterns. Any sentence whose specific token is not found in the article text or grounding facts is silently removed. General opinions, hooks, and rhetorical questions pass through untouched.

### How Deterministic Grounding Works (Console, Generate, Curate)

Deterministic grounding is a safety layer that reduces hallucinated personal claims by forcing outputs to stay anchored to known profile facts.

#### What Problem It Solves

Large models are strong at style but can still invent plausible-sounding background details (project names, companies, years, implementation claims). Grounding prevents that by treating loaded profile context as the source of truth.

#### Grounding Pipeline

1. Parse profile facts  
   The app parses project bullets from `PROFILE_CONTEXT` into structured records: project, company, years, details.
2. Detect constraints from the request  
   Query intent is analyzed for project/company lookups and technology tags (for example Java, Spring, RAG, Neo4j).
3. Retrieve relevant facts  
   Facts are ranked and a top subset is selected for the current request.
4. Apply balance rules in prompts (`--generate` and `--curate`)  
   The model is told that every factual claim must come from the article or profile facts. Personal references are capped at one per post. Invented stats, dates, and company names are explicitly forbidden.
5. Post-process output with the truth gate  
   A lightweight deterministic filter strips sentences containing unsupported numeric/date/company claims. The rest of the post is left intact — no rewriting occurs.

#### Console Mode Behavior

When a question is factual (for example: what projects, where, when, what stack), console mode can answer deterministically from parsed facts with source references instead of relying on free-form generation.

#### Generate and Curate Behavior

For weekly generation and article curation:

- Relevant facts are selected per topic/article.
- Balance rules in the prompt cap personal references and require article-grounded claims.
- The truth gate strips sentences with unsupported numeric/date/company claims after generation.

This keeps posts authentic while lowering risk of fabricated bio details.

#### Environment Controls

You can tune tech matching with:

- `CONSOLE_GROUNDING_TECH_KEYWORDS`
- `CONSOLE_GROUNDING_TAG_EXPANSIONS`
- `CURATION_GROUNDING_TECH_KEYWORDS` (optional override for `--curate`)
- `CURATION_GROUNDING_TAG_EXPANSIONS` (optional override for `--curate`)

These controls affect which profile facts are considered relevant during retrieval.

Fallback behavior:

- If `CURATION_GROUNDING_TECH_KEYWORDS` is unset, `--curate` uses `CURATOR_KEYWORDS` for fact-tag matching.
- If `CURATION_GROUNDING_TAG_EXPANSIONS` is unset, `--curate` uses `CONSOLE_GROUNDING_TAG_EXPANSIONS`.

#### Truth Gate Behavior and Configuration

The truth gate runs after model generation (and cleanup) for LinkedIn generation and curation flows.
It checks each sentence independently and removes only sentences that contain unsupported specific claims.

What it checks:

- Numeric claims (for example: `40%`, `3x`, `500ms`, `2 hours`)
- Year references (for example: `2021`, `2024`)
- Dollar amounts (for example: `$2M`)
- Company-name style patterns in context (for example: "at Company Name", "for Company Name")

Evidence source used by the gate:

- Article text (for `--curate`)
- Retrieved profile grounding facts (`project`, `company`, `years`, `details`)

If a sentence contains one of the claim patterns above and its key token is not present in the evidence source, that sentence is removed.
If a sentence is opinion, framing, hook, or a rhetorical question without unsupported hard claims, it is kept.

Current configuration surface:

- There are no dedicated `.env` variables for truth-gate thresholds or regex patterns today.
- Truth-gate strictness is currently code-defined in `services/console_grounding.py`.
- Practical tuning in `.env` is indirect: improving retrieval relevance (`CONSOLE_GROUNDING_TECH_KEYWORDS`, `CONSOLE_GROUNDING_TAG_EXPANSIONS`, `CURATION_GROUNDING_TECH_KEYWORDS`, `CURATION_GROUNDING_TAG_EXPANSIONS`) increases available evidence and typically reduces unnecessary sentence removals.

Operational notes:

- The gate logs how many sentences were removed (example: `Truth gate removed 1 of 8 sentences`).
- The gate does not rewrite text; it only removes unsupported claim sentences.
- The gate is intentionally conservative and not a full external fact-checker.

#### Troubleshooting Grounding Quality

If grounded outputs feel too generic or personal references are missing, this is usually a retrieval-configuration issue rather than a generation issue.

Common symptoms and fixes:

- Symptom: Output avoids personal project references even when relevant.  
   Likely cause: `CONSOLE_GROUNDING_TECH_KEYWORDS` does not include terms used in your topic or `PROFILE_CONTEXT`.  
   Fix: Add missing terms (for example: `spring ai`, `sentence transformers`, `pubsub+`, `fastmcp`) in lowercase.

- Symptom: Broad prompts like "Java" or "Python" miss obvious related projects.  
   Likely cause: `CONSOLE_GROUNDING_TAG_EXPANSIONS` is too narrow.  
   Fix: Expand umbrella tags so broad queries include adjacent stack terms (for example `java:spring|jms|oracle|weblogic`).

- Symptom: Irrelevant personal facts are injected for unrelated topics.  
   Likely cause: Keyword list is too broad/noisy.  
   Fix: Remove vague terms and keep only high-signal domain vocabulary.

- Symptom: Console factual answers look right, but generate/curate still feel weakly grounded.  
   Likely cause: Curation articles use topic vocabulary that does not overlap console-oriented grounding keywords.  
   Fix: Set `CURATION_GROUNDING_TECH_KEYWORDS` (and optionally `CURATION_GROUNDING_TAG_EXPANSIONS`) so `--curate` retrieval reflects article language.

- Symptom: Good posts lose one useful sentence after generation.  
   Likely cause: The sentence contains a specific number/date/company token not present in article text or retrieved facts.  
   Fix: Expand grounding keywords/tag expansions so the correct fact is retrieved, or rephrase the prompt/topic so the claim appears in source evidence.

- Symptom: Truth gate often removes 2+ sentences for curation posts.  
   Likely cause: Retrieval signal is weak for that article domain, so evidence is too thin.  
   Fix: Add domain terms to `CURATION_GROUNDING_TECH_KEYWORDS` and map broader terms via `CURATION_GROUNDING_TAG_EXPANSIONS`.

Quick tuning workflow:

1. Start with a compact keyword set that mirrors your `PROFILE_CONTEXT` terms.
2. Add tag expansions for umbrella terms (`java`, `python`, `rag`).
3. Run `--console` with factual prompts and confirm retrieved facts match expectations.
4. Run `--generate --dry-run` and `--curate --dry-run` and inspect whether personal references are relevant and supported.
5. Iterate by adding/removing only a few terms at a time.

#### Important Scope

Grounding protects factual identity and project/company claims. It does not attempt to fact-check every external statement in third-party articles.

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys and persona
cp .env.example .env
# Edit .env and fill in ALL required values:
#   PROFILE_CONTEXT       → your name, role, projects (see template in .env.example)
#   PERSONA_SYSTEM_PROMPT → your voice/persona (template in .env.example)
#   BUFFER_API_KEY        → https://publish.buffer.com/settings/api
#   OLLAMA_BASE_URL       → default: http://localhost:11434
#   OLLAMA_MODEL          → default: llama3.2 (gemma4:26b recommended)
#   OLLAMA_NUM_CTX        → default: 4096 (increase to reduce prompt truncation)
#
# Optional — Bluesky stats (--bsky-stats):
#   BLUESKY_HANDLE       → your handle, e.g. you.bsky.social (optional, only if using Bluesky integration)

#   BLUESKY_APP_PASSWORD → generate at bsky.app → Settings → App Passwords (optional, only if using Bluesky integration)

# Optional — GitHub context enrichment and prompt budget tuning:
#   GITHUB_USER                  → GitHub username (enables repo enrichment)
#   GITHUB_TOKEN                 → optional token (higher API limits)
#   GITHUB_REPO_FILTER           → comma-separated repo names to include
#   GITHUB_INCLUDE_README_SUMMARIES → true/false (default true)
#   GITHUB_REPO_MAX_COUNT        → max repos included (default 12)
#   GITHUB_README_MAX_CHARS      → max chars per README summary (default 1200)
#   GITHUB_CONTEXT_MAX_CHARS     → max GitHub-derived context block size (default 30000)
#   PROFILE_CONTEXT_MAX_CHARS    → max total profile context after assembly (default 120000)
#   CONSOLE_GROUNDING_TECH_KEYWORDS → comma-separated tech terms used by deterministic --console grounding
#   CONSOLE_GROUNDING_TAG_EXPANSIONS → optional related-tag map (e.g. java:spring|jms|oracle)
#   CURATION_GROUNDING_TECH_KEYWORDS → optional comma-separated terms used only by --curate fact retrieval
#   CURATION_GROUNDING_TAG_EXPANSIONS → optional related-tag map used only by --curate

# Set up your personal content calendar (gitignored — keeps your strategy private)
cp content_calendar.example.py content_calendar.py
# Edit content_calendar.py and replace the placeholder topics with your own:
#   title    → post headline
#   angle    → the specific take or story you'll tell
#   ssi_component → establish_brand | find_right_people | engage_with_insights | build_relationships
#   hashtags → list of relevant hashtags
```

## Usage

```bash
# Generate + preview week 1 posts (dry run — no Buffer calls)
python main.py --generate --week 1 --dry-run

# Generate + schedule week 1 posts to Buffer (LinkedIn, default)
python main.py --generate --schedule --week 1

# Schedule to X instead of LinkedIn
python main.py --generate --schedule --week 1 --channel x

# Schedule to LinkedIn, X, Bluesky, and YouTube simultaneously
python main.py --generate --schedule --week 1 --channel all

# Generate YouTube Short scripts (hard-capped at 500 chars), print to screen, and save to yt-vid-data/
# Buffer scheduling is skipped because YouTube requires a video file upload
python main.py --generate --schedule --week 1 --channel youtube

# Curate AI news and push as Buffer Ideas (default — review before publishing)
python main.py --curate --dry-run
python main.py --curate

# Curate and schedule DIRECTLY to next available queue slot
# LinkedIn → post body + source URL + hashtags appended programmatically
python main.py --curate --type post --channel linkedin

# X → single punchy post (280-char limit, no hashtags)
python main.py --curate --type post --channel x

# Bluesky → single post (300-char limit, no hashtags)
python main.py --curate --type post --channel bluesky

# YouTube → generates 500-char spoken Short script, prints to screen, saves to yt-vid-data/
# Buffer push is skipped (YouTube requires a video file) — render with lipsync.video then upload manually
python main.py --curate --type post --channel youtube

# All channels — LinkedIn/X/Bluesky scheduled independently; YouTube script printed and saved to yt-vid-data/
python main.py --curate --type post --channel all

# Curate ideas targeted at X audience (Ideas board)
python main.py --curate --channel x

# Print weekly SSI action report
python main.py --report

# Record today's SSI component scores (from linkedin.com/sales/ssi)
python main.py --save-ssi 10.49 9.69 11.0 12.15

# Fetch live Bluesky profile + engagement stats
python main.py --bsky-stats

# Open interactive persona chat console (no Buffer calls)
python main.py --console
```

### `--generate` vs `--curate` vs `--dry-run`

| Flag                 | Source                                                   | What it does                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--generate`         | Your content calendar (`content_calendar.py`)            | Writes posts from your pre-planned topics + angles; `--schedule` pushes them to Buffer as **scheduled posts**                                                                                                                                                                                                                                                                                                 |
| `--curate`           | Live RSS feeds (Anthropic, HuggingFace, Google AI, etc.) | Fetches today's articles, filters by your niche keywords, generates commentary; default behaviour pushes to Buffer as **Ideas** (unscheduled drafts for review)                                                                                                                                                                                                                                               |
| `--console`          | Persona + profile context                                | Opens an interactive terminal chat with your persona/context loaded. No Buffer actions are performed in this mode. Console commands: `/help`, `/reset`, `/exit`. For factual bio/project queries, a deterministic grounding layer extracts and cites matching records from loaded `PROFILE_CONTEXT` (project/company/year/details). Tech term matching is configurable via `CONSOLE_GROUNDING_TECH_KEYWORDS`. |
| `--dry-run`          | Either                                                   | Prints generated posts to the terminal only — no calls to Buffer                                                                                                                                                                                                                                                                                                                                              |
| `--type idea`        | `--curate`                                               | _(default)_ Push curated posts to Buffer Ideas board for manual review before publishing. LinkedIn: source URL and hashtags appended programmatically (body → URL → hashtags).                                                                                                                                                                                                                                |
| `--type post`        | `--curate`                                               | Schedule curated posts **directly** to the next available Buffer queue slot. LinkedIn: source URL and hashtags appended after the post body. X: single post, 280-char limit, no hashtags. Bluesky: single post, 300-char limit, no hashtags. YouTube: script printed to screen and saved to `yt-vid-data/` — not pushed to Buffer (see below).                                                                |
| `--channel linkedin` | Either                                                   | Target LinkedIn only (default)                                                                                                                                                                                                                                                                                                                                                                                |
| `--channel x`        | Either                                                   | Target X (Twitter) only — 280-char hard limit, single paragraph, no hashtags appended; requires an X account connected in Buffer                                                                                                                                                                                                                                                                              |
| `--channel bluesky`  | Either                                                   | Target Bluesky only — same thread format as X; requires a Bluesky account connected in Buffer                                                                                                                                                                                                                                                                                                                 |
| `--channel youtube`  | Either                                                   | Generates a **spoken Short script** (500-char / ~100–150 words) for use with lipsync.video or similar avatar tools; persona controlled by `YOUTUBE_SHORT_SYSTEM_PROMPT` in `.env`; script is printed to screen and saved to `yt-vid-data/<timestamp>_<title>.txt` — **not pushed to Buffer** (Buffer requires a video file)                                                                                   |
| `--channel all`      | Either                                                   | Target LinkedIn, X, Bluesky, and YouTube in one run. LinkedIn/X/Bluesky are scheduled independently; YouTube is generated as a local script (printed + saved to `yt-vid-data/`) because Buffer YouTube requires a video upload. If X or Bluesky is not connected in Buffer, that channel is skipped with a warning (no crash).                                                                                |

**YouTube Short workflow:** The `--channel youtube` output is a **spoken script** for a lipsync.video avatar (or similar tool), targeting ~100–150 words (500-char hard cap). The script is printed to the terminal and saved to `yt-vid-data/<timestamp>_<title>.txt` for you to copy into lipsync.video. Buffer is **not** used — YouTube requires a video file, which must be uploaded manually after rendering. The avatar persona (name, intro line, subscribe CTA) is fully configurable via `YOUTUBE_SHORT_SYSTEM_PROMPT` in your `.env`.

**Why curate goes to Ideas by default:** The AI summarises articles it found today and adds your commentary, but you should review that commentary before it goes live. Buffer Ideas sit in a drafts inbox so you can edit, approve, or discard each one. Use `--type post` to skip the review step and schedule directly.

**LinkedIn post structure:** For all LinkedIn curation (`--curate`), the final post is always assembled in this order: AI-generated commentary body → source URL → hashtags. The URL and hashtags are stripped from the AI response and re-appended by the code, so their position is guaranteed regardless of what the model outputs.

### How the curation pipeline works

Each time you run `python main.py --curate`, the following happens:

1. **Fetch** — all RSS feeds are scanned (up to `CURATOR_MAX_PER_FEED` entries each, default 10; see [Customising RSS feeds and keywords](#customising-rss-feeds-and-keywords) to add your own)
2. **Filter** — only articles whose title or summary contains a niche keyword (RAG, LLM, neo4j, MCP, GovTech, etc.) are kept
3. **Shuffle** — the matched articles are randomly shuffled so you get a different selection each run, not always the same top entries
4. **Dedup check** — article titles are checked against `published_ideas_cache.json` (a local file); any article you've already pushed to Buffer is skipped
5. **Generate** — each selected article is sent to the AI with your persona prompt and an SSI component goal; the service writes a LinkedIn post with your commentary
6. **Append link** — the source article URL is always appended programmatically after the AI responds (never left to the model to include)
7. **Push to Buffer Ideas** — the post is created in your Buffer Ideas board for review; the idea title is prefixed with `[channel|ssi_component]` (e.g. `[linkedin|engage_with_insights]`) so you can filter by channel or pillar at a glance; the article title is written to the local cache so it won't be re-submitted on future runs

**Dedup cache** (`published_ideas_cache.json`): A sorted JSON array of article titles that have already been pushed. It lives at the project root and is gitignored — it's local state, not source code. If you want to re-submit an article (e.g. after editing the persona), just delete its title from the file or clear the file entirely.

```json
[
  "Beyond Semantic Similarity: Introducing NVIDIA NeMo Retriever",
  "The Multi-Agent Trap",
  "Why Care About Prompt Caching in LLMs?"
]
```

The cache path can be overridden with `IDEAS_CACHE_PATH` in `.env` if you want to store it elsewhere.

### Customising RSS feeds and keywords

Both the RSS feed list and the keyword filter are configurable via `.env` — no code changes needed.

**`CURATOR_KEYWORDS`** — comma-separated terms matched against article titles/summaries (overrides built-in list entirely):

```ini
CURATOR_KEYWORDS=RAG,LLM,neo4j,GovTech,Spring AI,MCP,vector search
```

**`CURATOR_RSS_FEEDS`** — JSON array of `{"name": "...", "url": "..."}` objects (overrides built-in list entirely):

```ini
CURATOR_RSS_FEEDS=[{"name":"Anthropic Blog","url":"https://www.anthropic.com/rss.xml"},{"name":"My Blog","url":"https://myblog.com/feed.xml"}]
```

Leave either variable unset to use the built-in defaults (6 AI/ML feeds + 19 niche keywords).

## AI Backend

All post generation uses **Ollama** — a locally-running LLM server. No cloud AI keys required.

```bash
# 1. Install Ollama
#    Linux/WSL:
curl -fsSL https://ollama.com/install.sh | sh
#    macOS/Windows: https://ollama.com/download

# 2. Start the server
ollama serve &

# 3. Pull a model (one-time) — gemma4:26b recommended
ollama pull gemma4:26b
# Smaller/faster alternatives:
# ollama pull qwen2.5:14b     (~9 GB, strong fallback)
# ollama pull llama3.2        (~2 GB)
# ollama pull mistral-nemo    (12b)

# 4. Set the model in .env
OLLAMA_MODEL=gemma4:26b
OLLAMA_NUM_CTX=16384

# Override model for a single run
OLLAMA_MODEL=llama3.2 python main.py --curate --dry-run
```

> **Tip:** `gemma4:26b` (MoE — 3.8B active params) gives the best post quality: native system role support,
> configurable thinking mode, and strong instruction-following across long prompts. `qwen2.5:14b` is a solid
> fallback if you're VRAM-constrained (~9 GB). `llama3.2` (3b) is fastest but lower quality.
> Increase `OLLAMA_NUM_CTX` (for example `16384` or `32768`) if you see prompt truncation in logs when grounding is enabled.

## SSI Component Mapping

Current scores are tracked in `ssi_history.json` (runtime file, gitignored). The table below shows targets only — run `--report` to see live scores with trend arrows.

| Component            | Target | Strategy                              |
| -------------------- | ------ | ------------------------------------- |
| Establish brand      | 25     | 3x/week posting via Buffer            |
| Find right people    | 20     | Connect with commenters, join groups  |
| Engage with insights | 25     | Curated posts + daily commenting      |
| Build relationships  | 25     | Reply to all comments, DM connections |
| **Total**            | **95** |                                       |

### How the content calendar and scheduling work together

1. **Calendar structure:**
   - The calendar (`content_calendar.py`) is a 4-week plan, with each week containing 3 topics. Each topic is mapped to an SSI component and has a unique angle.
2. **Scheduling logic:**
   - When you run `python main.py --generate --schedule --week N`, the scheduler:
     - Loads the topics for week N
     - Uses your `.env` SSI focus weights to allocate posts per component (e.g., if `engage_with_insights` is set to 40%, it will try to schedule more posts from that pillar)
     - Ensures no component is neglected, and fills any gaps with available topics
     - Schedules posts for Tue/Wed/Fri at 4 PM EST (Buffer queue)
     - Never repeats a topic within a week
3. **Result:**
   - Over 4 weeks, all four SSI pillars are covered in a balanced, data-driven way, with each post having a clear purpose and unique perspective.

### Customising scheduler.py behavior

The scheduler logic lives in `scheduler.py` and is driven by `.env` values.

Key controls:

- `SCHEDULER_TIMEZONE`  
   Local timezone used when calculating weekday/time slots before conversion to UTC for Buffer.

- `SCHEDULER_POSTING_SLOTS`  
   Comma-separated slot list in `day@HH:MM` format. Example: `tuesday@16:00,wednesday@16:00,friday@16:00`.

Rules for `SCHEDULER_POSTING_SLOTS`:

- Valid days: `monday`..`sunday` (lowercase recommended).
- Time uses 24-hour format (`HH:MM`).
- Slot order is preserved and used as posting order.
- Number of slots determines the max scheduled posts per week per channel.

Examples:

```ini
# Keep default 3-post cadence
SCHEDULER_TIMEZONE=America/Toronto
SCHEDULER_POSTING_SLOTS=tuesday@16:00,wednesday@16:00,friday@16:00

# 4-post cadence with custom times
SCHEDULER_TIMEZONE=America/Toronto
SCHEDULER_POSTING_SLOTS=monday@09:30,tuesday@16:00,thursday@11:00,friday@16:00
```

Important runtime behavior:

- Scheduling runs only when you execute `--generate --schedule`.
- The app computes future timestamps and writes them to Buffer.
- Buffer performs the actual publish at those scheduled times.
- There is no daemon/cron loop in this repo that continuously schedules in the background.

### Weekly SSI update workflow

1. Check [linkedin.com/sales/ssi](https://www.linkedin.com/sales/ssi) for your latest four component scores
2. Record them to history (this drives the report and trend arrows):

   ```bash
   python main.py --save-ssi <brand> <find> <engage> <build>
   # Example:
   python main.py --save-ssi 10.49 9.69 11.0 12.15
   ```

3. View your progress report:

   ```bash
   python main.py --report
   ```

The report shows progress bars toward each target, ↑/↓/↔ trend arrows vs the previous entry, and a history table of the last 5 weekly snapshots. No code edits needed — just `--save-ssi` + `--report`.

### Controlling post-type focus

Four percentage values in `.env` control how often each pillar gets a generated post. They should add up to 100 — bump a pillar up when it's lagging, dial it back when it improves:

```ini
SSI_FOCUS_ESTABLISH_BRAND=25
SSI_FOCUS_FIND_RIGHT_PEOPLE=27
SSI_FOCUS_ENGAGE_WITH_INSIGHTS=24
SSI_FOCUS_BUILD_RELATIONSHIPS=24
```

The system uses these as-is — no formulas to think about. If `find_right_people` drops on your SSI page, move some points toward it from whichever pillar is healthiest.

## File Structure

```
linkedin_ssi_booster/
├── main.py                    # CLI entry point + profile context assembly
├── content_calendar.py        # 4-week topic plan
├── scheduler.py               # Buffer post scheduling logic
├── requirements.txt
├── .env.example               # Template — copy to .env and fill in keys/persona
└── services/
    ├── buffer_service.py      # Buffer GraphQL API client
    ├── ollama_service.py      # Ollama local LLM — post generation + SSI instructions
    ├── shared.py              # Shared constants, persona prompt, SSI instructions
    ├── content_curator.py     # RSS feed scraper + summariser; guaranteed link append
    ├── github_service.py      # Live GitHub profile enrichment (repo metadata + README summaries)
    └── ssi_tracker.py         # SSI report + action items
```

## Get your API keys

- **Buffer API key**: https://publish.buffer.com/settings/api → Generate API Key
- **Ollama models**: https://ollama.com/library
- **Bluesky handle/app password** (optional): bsky.app → Settings → App Passwords
- **YouTube channel** (optional): connect at https://publish.buffer.com → Channels → Add Channel → YouTube
- **Track your SSI**: https://linkedin.com/sales/ssi

## License

MIT — see [LICENSE](LICENSE) for details.
