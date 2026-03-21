# LinkedIn SSI Booster — Buffer API Integration

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version: alpha-0.0.0.2](https://img.shields.io/badge/version-alpha--0.0.0.2-orange.svg)]()

Automates LinkedIn post generation and scheduling via Claude AI, Google Gemini, or local Ollama to systematically grow your LinkedIn Social Selling Index (SSI) score.

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
- **Curation pipeline** — fetches today's AI/GovTech news, filters by your niche, and generates commentary for you to review in Buffer Ideas before publishing

You still review and approve curated posts before they go live. The tool removes the blank-page problem, not your judgment.

## How it works

1. **Content calendar** — 4 weeks of topics mapped to your 4 SSI components
2. **AI generation** — Claude, Gemini, or Ollama generates posts as plain text, personalised to you (see below)
3. **Buffer API** — schedules those text posts to LinkedIn at Tue/Wed/Fri 4 PM EST
4. **Content curator** — fetches AI/GovTech news and creates ideas for curation posts
5. **SSI tracker** — weekly report with specific actions per component

## How post personalisation works

Every generated post is plain text — there's no audio or special format involved.  
"Personalised to you" means the AI prompt is pre-loaded with four layers of context so the output reads like _you_ wrote it, not a generic AI:

**1. Your profile (`PROFILE_CONTEXT` in `.env`)**  
Injected into every prompt: your name, role, location, specialties, and real project outcomes. Stored in `.env` (gitignored) so it stays private and out of source control. The profile is also enriched at startup with live GitHub data via `services/github_service.py` — pinned repos, languages, and recent activity so the model has current project context.

**2. Persona system prompt (`PERSONA_SYSTEM_PROMPT` in `.env`)**  
A detailed persona loaded into every AI call, covering:

- Identity and credibility anchors — **domain-separated**: AI projects (2024–present) are listed separately from legacy infrastructure (TPG/USPS JMS work, pre-2024) with a hard rule forbidding the model from blending them
- Target audience, voice guidance, and forbidden phrases
- **Technical glossary** — 10 authoritative definitions (RAG, BM25, kNN, MCP, FastMCP, JMS, SentenceTransformers, CRISP-DM, etc.) with a hard rule: never expand an abbreviation that isn't in the glossary (prevents hallucinations like "RAG = Reactive Agent Framework")

**3. Writing rules (configurable via `.env`, shared by all AI backends)**  
Per-pillar instructions injected into every AI call. All four are overridable in `.env` without touching code (`SSI_ESTABLISH_BRAND`, `SSI_FIND_RIGHT_PEOPLE`, `SSI_ENGAGE_WITH_INSIGHTS`, `SSI_BUILD_RELATIONSHIPS`). The defaults live in `claude_service.py` and are imported by the Gemini and Ollama backends too. Built-in rules:

- Never start with "I"
- Never use filler phrases ("Game changer", "Excited to share", "landscape", "leverage", etc.)
- No bullet points in the body — short punchy paragraphs only
- Hook in the first line (bold claim, surprising stat, or short story)

The writing rules draw on **Neuro-Linguistic Programming (NLP)** principles — specifically pattern interrupts (scroll-stopping first lines), presupposition (assuming the reader already cares), and anchoring (pairing your name with specific technical outcomes so readers associate _you_ with the domain). The forbidden-phrases list functions as a negative anchor removal layer: stripping hollow corporate phrases forces the model toward concrete, specific language that builds credibility. For the theoretical underpinning, see [_Monsters and Magical Sticks_ by Steven Heller & Terry Steele](https://www.amazon.com/Monsters-Magical-Sticks-Hypnosis-Really/dp/1561840181) — an accessible introduction to how language patterns shape perception.

**4. Per-post angle (`content_calendar.py`)**  
Each topic has a specific `angle` field (e.g. _"contrast AI-TDD with vibe coding"_) so every post has a distinct point of view rather than rehashing the same generic take.

For curated posts (`--curate`), `content_curator.py` filters RSS feeds by your niche keywords (RAG, Neo4j, GovTech, MCP, Spring AI…) so only domain-relevant articles are ever posted — not random tech news.

**Guaranteed output integrity**  
Hashtags (for `--generate` targeting LinkedIn) and source article links (for `--curate`) are always appended programmatically _after_ the model responds — never left to the model to include or place correctly. X posts skip hashtag appending entirely — X's 280-character limit leaves no room for them, and the prompt instructs the model to write a single tight paragraph instead of the multi-paragraph LinkedIn format.

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and fill in ALL required values:
#   PROFILE_CONTEXT   → your name, role, projects (see template in .env.example)
#   PERSONA_SYSTEM_PROMPT → your voice/persona (template in .env.example)
#   BUFFER_API_KEY    → https://publish.buffer.com/settings/api
#   ANTHROPIC_API_KEY → https://console.anthropic.com          (for --generate default)
#   GEMINI_API_KEY    → https://aistudio.google.com/apikey     (for --gemini, free tier available)
#
# Optional — Bluesky stats (--bsky-stats):
#   BLUESKY_HANDLE       → your handle, e.g. samjd-zz.bsky.social
#   BLUESKY_APP_PASSWORD → generate at bsky.app → Settings → App Passwords
#
# Optional — only needed for --local mode:
#   OLLAMA_BASE_URL   → default: http://localhost:11434
#   OLLAMA_MODEL      → default: llama3.2
#   GEMINI_MODEL      → default: gemini-2.0-flash
```

## Usage

```bash
# Generate + preview week 1 posts with Claude (dry run — no Buffer calls)
python main.py --generate --week 1 --dry-run

# Generate + schedule week 1 posts to Buffer (LinkedIn, default)
python main.py --generate --schedule --week 1

# Schedule to X instead of LinkedIn
python main.py --generate --schedule --week 1 --channel x

# Schedule to LinkedIn, X, and Bluesky simultaneously
python main.py --generate --schedule --week 1 --channel all

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

# All channels — one post per channel scheduled independently
python main.py --curate --type post --channel all

# Curate ideas targeted at X audience (Ideas board)
python main.py --curate --channel x

# Print weekly SSI action report
python main.py --report

# Fetch live Bluesky profile + engagement stats
python main.py --bsky-stats
```

### `--generate` vs `--curate` vs `--dry-run`

| Flag                 | Source                                                   | What it does                                                                                                                                                                                                                                 |
| -------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--generate`         | Your content calendar (`content_calendar.py`)            | Writes posts from your pre-planned topics + angles; `--schedule` pushes them to Buffer as **scheduled posts**                                                                                                                                |
| `--curate`           | Live RSS feeds (Anthropic, HuggingFace, Google AI, etc.) | Fetches today's articles, filters by your niche keywords, generates commentary; default behaviour pushes to Buffer as **Ideas** (unscheduled drafts for review)                                                                              |
| `--dry-run`          | Either                                                   | Prints generated posts to the terminal only — no calls to Buffer                                                                                                                                                                             |
| `--type idea`        | `--curate`                                               | _(default)_ Push curated posts to Buffer Ideas board for manual review before publishing. LinkedIn: source URL and hashtags appended programmatically (body → URL → hashtags).                                                               |
| `--type post`        | `--curate`                                               | Schedule curated posts **directly** to the next available Buffer queue slot. LinkedIn: source URL and hashtags appended after the post body. X: single post, 280-char limit, no hashtags. Bluesky: single post, 300-char limit, no hashtags. |
| `--channel linkedin` | Either                                                   | Target LinkedIn only (default)                                                                                                                                                                                                               |
| `--channel x`        | Either                                                   | Target X (Twitter) only — 280-char hard limit, single paragraph, no hashtags appended; requires an X account connected in Buffer                                                                                                             |
| `--channel bluesky`  | Either                                                   | Target Bluesky only — same thread format as X; requires a Bluesky account connected in Buffer                                                                                                                                                |
| `--channel all`      | Either                                                   | Target LinkedIn, X, and Bluesky — each post is scheduled/created independently per channel                                                                                                                                                   |

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

## Choosing an AI backend

| Flag       | Backend                     | Cost                | Quality | Best for                    |
| ---------- | --------------------------- | ------------------- | ------- | --------------------------- |
| _(none)_   | Claude (`claude-opus-4-6`)  | Pay-per-token       | Best    | Final posts to publish      |
| `--gemini` | Gemini (`gemini-2.0-flash`) | Free tier available | Great   | Daily use without API costs |
| `--local`  | Ollama (local model)        | Free                | Good    | Drafting, offline, privacy  |

```bash
# Claude (default)
python main.py --generate --week 1 --dry-run

# Gemini — free tier, no Anthropic key needed
python main.py --generate --week 1 --gemini --dry-run
python main.py --curate --gemini --dry-run

# Ollama — fully local, no internet needed
python main.py --generate --week 1 --local --dry-run
python main.py --curate --local --dry-run
python main.py --curate --local --channel x --dry-run

# All flags compose freely — e.g. Gemini + X channel + dry-run
python main.py --curate --gemini --channel x --dry-run
```

## Local generation with Ollama (free, offline)

Use the `--local` flag to generate posts with a locally-running Ollama model
instead of calling any cloud API. Useful for drafting, testing, or keeping
data fully local.

```bash
# 1. Install Ollama
#    Linux (WSL included):
curl -fsSL https://ollama.com/install.sh | sh
#    macOS: download from https://ollama.com/download
#    Windows: download from https://ollama.com/download

# 2. Start the server (Linux/WSL — runs in background)
ollama serve &

# 3. Pull a model (one-time)
ollama pull llama3.2          # fast, good quality (~2 GB)
# ollama pull mistral         # alternative
# ollama pull llama3.1:8b    # larger / higher quality

# 4. Generate posts locally
python main.py --generate --week 1 --local --dry-run

# 5. Curate AI news locally — LinkedIn (default)
python main.py --curate --local --dry-run
python main.py --curate --local

# 6. Curate AI news locally — X (280-char mode, no hashtags)
python main.py --curate --local --channel x --dry-run
python main.py --curate --local --channel x

# 7. Schedule locally-generated posts to Buffer
python main.py --generate --schedule --week 1 --local

# 8. Override the model without editing .env
OLLAMA_MODEL=mistral python main.py --generate --week 1 --local --dry-run
```

> **Tip:** Claude produces the best LinkedIn copy. Gemini (`--gemini`) is a great
> free middle ground. Use Ollama (`--local`) for fast offline drafting, then
> regenerate with Claude or Gemini before scheduling.

## SSI Component Mapping

Current scores are tracked in `ssi_history.json` (runtime file, gitignored). The table below shows targets only — run `--report` to see live scores with trend arrows.

| Component            | Target | Strategy                              |
| -------------------- | ------ | ------------------------------------- |
| Establish brand      | 25     | 3x/week posting via Buffer            |
| Find right people    | 20     | Connect with commenters, join groups  |
| Engage with insights | 25     | Curated posts + daily commenting      |
| Build relationships  | 25     | Reply to all comments, DM connections |
| **Total**            | **95** |                                       |

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
    ├── claude_service.py      # Anthropic API — post generation + SSI instructions
    ├── gemini_service.py      # Google Gemini API — drop-in Claude replacement
    ├── ollama_service.py      # Local Ollama — drop-in Claude replacement
    ├── content_curator.py     # RSS feed scraper + summariser; guaranteed link append
    ├── github_service.py      # Live GitHub profile enrichment (pinned repos, languages)
    └── ssi_tracker.py         # SSI report + action items
```

## Get your API keys

- **Buffer API key**: https://publish.buffer.com/settings/api → Generate API Key
- **Anthropic API key**: https://console.anthropic.com → API Keys
- **Gemini API key** (free): https://aistudio.google.com/apikey
- **Ollama models**: https://ollama.com/library
- **Bluesky app password**: bsky.app → Settings → App Passwords (no extra permissions needed)
- **Track your SSI**: https://linkedin.com/sales/ssi

## License

MIT — see [LICENSE](LICENSE) for details.
