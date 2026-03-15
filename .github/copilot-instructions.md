# GitHub Copilot Instructions — LinkedIn SSI Booster

## Project Purpose

Python automation tool that generates and schedules LinkedIn posts via the Buffer API to improve Shawn's LinkedIn Social Selling Index (SSI) across all four components.

## Tech Stack

- **Language**: Python 3.11+
- **AI**: Anthropic Claude (via `anthropic` SDK) — all LLM calls go through `services/claude_service.py`
- **Social Scheduling**: Buffer GraphQL API — all calls go through `services/buffer_service.py`
- **RSS Parsing**: `feedparser` — used in `services/content_curator.py`
- **Scheduling**: `APScheduler` + `pytz` (America/Toronto timezone)
- **Config**: `python-dotenv` — secrets from `.env` only

## Package Structure

```
linkedin_ssi_booster/
├── main.py                  # CLI entrypoint (argparse)
├── scheduler.py             # Optimal posting-time logic
├── content_calendar.py      # 4-week topic list
├── services/
│   ├── __init__.py
│   ├── claude_service.py    # Anthropic wrapper + SSI prompt templates
│   ├── buffer_service.py    # Buffer GraphQL wrapper
│   ├── content_curator.py   # RSS fetch + summarise + create Buffer ideas
│   └── ssi_tracker.py       # SSI score tracking + report
└── requirements.txt
```

## Import Conventions

- Always use absolute imports from the project root: `from services.X import Y`
- Scripts are run from the project root: `python main.py --generate`
- Never add `sys.path` manipulation inside source files

## Code Conventions

- Type-annotate all function parameters and return types
- Use `logging.getLogger(__name__)` — never `print()` for diagnostics
- Catch specific exceptions (never bare `except:`)
- Constants → `UPPER_SNAKE_CASE` at module top
- `--dry-run` flag to preview without hitting external APIs

## Secret Management

- All secrets via `os.getenv()` after `load_dotenv()`
- Required: `ANTHROPIC_API_KEY`, `BUFFER_API_KEY`
- Never suggest hardcoding keys or committing `.env`

## SSI Components (context for prompt suggestions)

| Key                    | Description                                               |
| ---------------------- | --------------------------------------------------------- |
| `establish_brand`      | Share builds, lessons, technical depth                    |
| `find_right_people`    | Tools, communities, questions that attract right audience |
| `engage_with_insights` | Summarise/react to AI news with a bold take               |
| `build_relationships`  | Behind-the-scenes stories, honest lessons                 |

## Preferences

- Concise, idiomatic Python — avoid unnecessary abstraction
- Prefer `pathlib.Path` over `os.path` for file operations
- Raise `ValueError` for invalid config at init time (fail fast)
- Keep Buffer and Anthropic calls in their respective service classes — do not scatter API calls across the codebase

## After Every Code Change

- Always run `python -m py_compile <changed_files>` immediately after editing any `.py` file
- Fix all syntax errors before considering a task complete
- Example: `python -m py_compile services/claude_service.py services/gemini_service.py services/ollama_service.py`
- **Update README.md** whenever you change how the tool is configured, how a feature works, or what env vars are required — keep the docs in sync with the code
