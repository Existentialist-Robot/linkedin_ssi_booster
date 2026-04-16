# Usage Guide

The CLI centers on three main workflows: scheduling from a private content calendar, curating from live RSS sources, and running a grounded interactive console. A `--dry-run` mode is available across flows to generate and inspect outputs without making Buffer API calls.

## Main commands

```bash
python main.py --schedule --week 1 --dry-run
python main.py --curate --dry-run
python main.py --console
python main.py --report
python main.py --save-ssi 10.49 9.69 11.0 12.15
```

`--schedule` uses `content_calendar.py`, `--curate` uses live RSS feeds filtered by niche keywords, and `--console` opens an interactive persona chat with deterministic grounding for factual project and bio queries. The documentation also lists `/help`, `/reset`, and `/exit` as console commands.

## Schedule mode

`--schedule --week N` generates posts from the selected week of the content calendar and schedules them through Buffer unless `--dry-run` is supplied. The scheduler uses configured posting slots and SSI focus weights from `.env`, preserves topic order within components, and avoids repeating topics within a week.

Examples:

```bash
python main.py --schedule --week 1
python main.py --schedule --week 1 --channel x
python main.py --schedule --week 1 --channel all
python main.py --schedule --week 1 --avatar-explain
```

## Curate mode

`--curate` scans RSS feeds, filters by domain keywords, ranks candidate articles, generates commentary, and by default sends outputs to the Buffer Ideas board for review. Adding `--type post` bypasses the draft-first behavior and schedules curated posts directly to the next available queue slot.

Examples:

```bash
python main.py --curate
python main.py --curate --type post --channel linkedin
python main.py --curate --type post --channel x
python main.py --curate --confidence-policy strict
python main.py --curate --avatar-explain
```

## Channel behavior

The README documents channel-specific output rules across LinkedIn, X, Bluesky, YouTube, and `all`. LinkedIn appends source URLs and hashtags programmatically, while X and Bluesky are shorter single-post outputs without hashtag appending, and YouTube produces spoken Short scripts that are saved locally rather than sent to Buffer.

| Channel    | Behavior                                                                                                |
| ---------- | ------------------------------------------------------------------------------------------------------- |
| `linkedin` | Default channel; source URL and hashtags are appended programmatically for curation output.             |
| `x`        | 280-character limit, single paragraph, no hashtag append.                                               |
| `bluesky`  | 300-character limit, X-like post behavior.                                                              |
| `youtube`  | Generates a spoken script, prints it, and saves it to `yt-vid-data/`; not pushed to Buffer.             |
| `all`      | Runs LinkedIn, X, Bluesky, and YouTube together, with YouTube still handled as a local script artifact. |

## Curation pipeline

On each `--curate` run, the project fetches RSS entries, filters them by keyword match, ranks them by relevance, freshness, and acceptance priors, deduplicates against local caches, generates commentary, logs candidates, appends article links, and routes the result to Buffer Ideas or scheduled posts depending on flags. This makes curation both content-generation and data-collection infrastructure for later reconciliation.

## Reconcile mode

`--reconcile` compares Buffer-published posts against `data/selection/generated_candidates.jsonl` using exact Buffer post ID, article URL, or Jaccard token similarity. Matched candidates become `selected=True`, older unmatched candidates become `selected=False`, and these labels feed Beta-smoothed acceptance priors for future curation ranking.

## YouTube workflow

YouTube output is intentionally treated as a script-generation path rather than a publish path because Buffer requires a video file for YouTube. The generated script is designed for avatar or lip-sync tools, printed to screen, and written to `yt-vid-data/<timestamp>_<title>.txt` for manual rendering and upload.
