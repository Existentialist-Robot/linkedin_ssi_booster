# LinkedIn SSI Booster — Claude Code Guide

## Session startup

Run this at the start of every session before doing anything else:

```
python main.py --check-expiry
```

This checks whether any tracked API keys are within 10 days of expiry and fires a one-per-day warning if so. It is safe to run and exits immediately if nothing is expiring.

If the output shows a `[KEY EXPIRY]` or `[KEY EXPIRED]` line, rotate the key immediately and update `.env` before proceeding with any other task.

## Key environment variables

| Variable | Purpose |
|---|---|
| `BUFFER_API_KEY` | Primary Buffer account (LinkedIn, X, Threads, YouTube) |
| `BUFFER_API_KEY_B` | Secondary Buffer account (Facebook, Instagram, Bluesky) |
| `BUFFER_API_KEY_B_EXPIRES` | ISO date of secondary key expiry (e.g. `2026-08-09`) |
| `OLLAMA_BASE_URL` | Ollama endpoint (default `http://localhost:11434`) |

## Channel routing

- **Primary account** (`BUFFER_API_KEY`): `linkedin`, `x`, `threads`, `youtube`
- **Secondary account** (`BUFFER_API_KEY_B`): `facebook`, `instagram`, `bluesky`

The routing is automatic. Running `--channel facebook` will use `BUFFER_API_KEY_B` with the `SOCIAL_SYSTEM_PROMPT` tone (more direct, less polished than LinkedIn).

## Post review files

All draft and final post copy lives in `data/post_reviews/`. Each file contains:
- Draft, critique, and final version for each post
- Buffer IDs and scheduled dates
- Prompt rules and persona changes derived from feedback

Do not regenerate posts that already have a `### Final Version` section unless explicitly asked.

## Private repo only

This repo should **not** be pushed to any public upstream. Push only to the private origin remote.
