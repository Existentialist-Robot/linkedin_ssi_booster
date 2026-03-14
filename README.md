# LinkedIn SSI Booster — Buffer API Integration

Automates LinkedIn post generation and scheduling via Claude AI, Google Gemini, or local Ollama

- Buffer API to systematically grow your Social Selling Index (SSI) score.

## How it works

1. **Content calendar** — 4 weeks of topics mapped to your 4 SSI components
2. **AI generation** — Claude, Gemini, or Ollama generates posts as plain text, personalised to you (see below)
3. **Buffer API** — schedules those text posts to LinkedIn at Tue/Wed/Fri 4 PM EST
4. **Content curator** — fetches AI/GovTech news and creates ideas for curation posts
5. **SSI tracker** — weekly report with specific actions per component

## How post personalisation works

Every generated post is plain text — there's no audio or special format involved.  
"Personalised to you" means the AI prompt is pre-loaded with four layers of context so the output reads like _you_ wrote it, not a generic AI:

**1. Your profile (`PROFILE_CONTEXT` in `main.py`)**  
Injected into every prompt: your name, role, location, specialties (RAG, Neo4j, Java 21, etc.) and real project outcomes (G7 GovAI: 397k docs sub-500ms; S1gnal.Zero: hackathon winner; Answer42: 9-agent pipeline). The profile is also enriched at startup with live GitHub data via `services/github_service.py` — pinned repos, languages, and recent activity so the model has current project context.

**2. Persona system prompt (`PERSONA_SYSTEM_PROMPT` in `.env`)**  
A detailed persona loaded into every AI call, covering:

- Identity and credibility anchors — **domain-separated**: AI projects (2024–present) are listed separately from legacy infrastructure (TPG/USPS JMS work, pre-2024) with a hard rule forbidding the model from blending them
- Target audience, voice guidance, and forbidden phrases
- **Technical glossary** — 10 authoritative definitions (RAG, BM25, kNN, MCP, FastMCP, JMS, SentenceTransformers, CRISP-DM, etc.) with a hard rule: never expand an abbreviation that isn't in the glossary (prevents hallucinations like "RAG = Reactive Agent Framework")

**3. Writing rules (`SSI_COMPONENT_INSTRUCTIONS` in `claude_service.py`)**  
Hard rules baked into the system prompt:

- Never start with "I"
- Never use filler phrases ("Game changer", "Excited to share", "landscape", "leverage", etc.)
- No bullet points in the body — short punchy paragraphs only
- Hook in the first line (bold claim, surprising stat, or short story)

**4. Per-post angle (`content_calendar.py`)**  
Each topic has a specific `angle` field (e.g. _"contrast AI-TDD with vibe coding"_) so every post has a distinct point of view rather than rehashing the same generic take.

For curated posts (`--curate`), `content_curator.py` filters RSS feeds by your niche keywords (RAG, Neo4j, GovTech, MCP, Spring AI…) so only domain-relevant articles are ever posted — not random tech news.

**Guaranteed output integrity**  
Hashtags (for `--generate`) and source article links (for `--curate`) are always appended programmatically _after_ the model responds — never left to the model to include or place correctly.

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your keys:
#   BUFFER_API_KEY    → https://publish.buffer.com/settings/api
#   ANTHROPIC_API_KEY → https://console.anthropic.com          (for --generate default)
#   GEMINI_API_KEY    → https://aistudio.google.com/apikey     (for --gemini, free tier available)
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

# Generate + schedule week 1 posts to Buffer
python main.py --generate --schedule --week 1

# Curate AI news and push as Buffer ideas (for review before publishing)
python main.py --curate --dry-run
python main.py --curate

# Print weekly SSI action report
python main.py --report
```

### `--generate` vs `--curate` vs `--dry-run`

| Flag         | Source                                                   | What it does                                                                                                                                  |
| ------------ | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `--generate` | Your content calendar (`content_calendar.py`)            | Writes posts from your pre-planned topics + angles; `--schedule` pushes them to Buffer as **scheduled posts**                                 |
| `--curate`   | Live RSS feeds (Anthropic, HuggingFace, Google AI, etc.) | Fetches today's articles, filters by your niche keywords, generates commentary; pushes to Buffer as **Ideas** (unscheduled drafts for review) |
| `--dry-run`  | Either                                                   | Prints generated posts to the terminal only — no calls to Buffer                                                                              |

**Why curate goes to Ideas, not the queue:** The AI summarises articles it found today and adds your commentary, but you should review that commentary before it goes live. Buffer Ideas sit in a drafts inbox so you can edit, approve, or discard each one.

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

# 5. Schedule locally-generated posts to Buffer
python main.py --generate --schedule --week 1 --local

# 6. Override the model without editing .env
OLLAMA_MODEL=mistral python main.py --generate --week 1 --local --dry-run
```

> **Tip:** Claude produces the best LinkedIn copy. Gemini (`--gemini`) is a great
> free middle ground. Use Ollama (`--local`) for fast offline drafting, then
> regenerate with Claude or Gemini before scheduling.

## SSI Component Mapping

| Component            | Current | Target | Strategy                              |
| -------------------- | ------- | ------ | ------------------------------------- |
| Establish brand      | 10.46   | 25     | 3x/week posting via Buffer            |
| Find right people    | 9.47    | 20     | Connect with commenters, join groups  |
| Engage with insights | 11.00   | 25     | Curated posts + daily commenting      |
| Build relationships  | 11.85   | 25     | Reply to all comments, DM connections |
| **Total**            | **43**  | **95** |                                       |

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
- **Track your SSI**: https://linkedin.com/sales/ssi
