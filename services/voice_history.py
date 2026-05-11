"""
Voice History — past writing samples for style-grounded generation.

Ingests LinkedIn comment exports (CSV) and published Buffer posts, then
builds a compact voice-example block that is injected into Ollama generation
prompts so the LLM learns the user's authentic tone and structure.

Populates: data/avatar/voice_history.json  (gitignored)

Config (via .env):
    VOICE_HISTORY_ENABLED      — true/false (default: true)
    VOICE_HISTORY_SAMPLE_SIZE  — examples injected per prompt (default: 4)
    VOICE_HISTORY_MIN_CHARS    — minimum sample length in chars (default: 150)
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VOICE_HISTORY_PATH = Path("data/avatar/voice_history.json")
_SCHEMA_VERSION = "1.0"
_DEFAULT_MIN_CHARS = 150
_DEFAULT_SAMPLE_SIZE = 4


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _sample_id(source_key: str, text: str) -> str:
    raw = f"{source_key}||{text[:120]}"
    return "vh-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def load_voice_history() -> list[dict]:
    if not VOICE_HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(VOICE_HISTORY_PATH.read_text(encoding="utf-8"))
        return data.get("samples", [])
    except (json.JSONDecodeError, IOError):
        return []


def save_voice_history(samples: list[dict]) -> None:
    VOICE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOICE_HISTORY_PATH.write_text(
        json.dumps(
            {"schemaVersion": _SCHEMA_VERSION, "samples": samples},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    logger.info("Voice history saved: %d samples → %s", len(samples), VOICE_HISTORY_PATH)


# ---------------------------------------------------------------------------
# Ingestion: LinkedIn Comments CSV
# ---------------------------------------------------------------------------


def _group_by_post(rows: list[dict]) -> dict[str, list[dict]]:
    """Group CSV rows by post URL (same thread)."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        link = (row.get("Link") or "").strip()
        groups.setdefault(link, []).append(row)
    return groups


def ingest_comments_csv(
    csv_path: str | Path,
    min_chars: int = _DEFAULT_MIN_CHARS,
    dry_run: bool = False,
) -> tuple[int, list[dict]]:
    """Parse a LinkedIn Comments.csv export and add substantive comments to voice_history.

    Groups comments by post URL so multi-comment threads are captured together.
    Returns (new_count, preview_list) — preview_list is every candidate regardless
    of dry_run, useful for logging.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Comments CSV not found: {path}")

    rows: list[dict] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            text = (row.get("Message") or "").strip()
            if text:
                rows.append(row)

    # Sort chronologically within each thread
    def _parse_date(row: dict) -> str:
        return (row.get("Date") or "")[:10]

    groups = _group_by_post(rows)

    existing = load_voice_history()
    existing_ids = {s["id"] for s in existing}
    new_samples: list[dict] = []
    preview: list[dict] = []

    for link, thread_rows in groups.items():
        thread_rows = sorted(thread_rows, key=_parse_date)

        # Add each substantive individual comment
        for row in thread_rows:
            text = (row.get("Message") or "").strip()
            date_short = _parse_date(row)
            if len(text) < min_chars:
                continue
            sid = _sample_id(link, text)
            entry = {
                "id": sid,
                "text": text,
                "source": "linkedin_comment",
                "date": date_short,
                "channel": "linkedin",
                "char_count": len(text),
                "source_url": link,
            }
            preview.append(entry)
            if sid not in existing_ids:
                new_samples.append(entry)
                existing_ids.add(sid)

        # If the thread has 3+ messages, also add a concatenated "thread" sample
        # so the LLM sees how Eden responds across a conversation
        all_texts = [(row.get("Message") or "").strip() for row in thread_rows]
        substantive_texts = [t for t in all_texts if len(t) >= 30]
        if len(substantive_texts) >= 3:
            joined = "\n→ ".join(substantive_texts)
            joined_date = _parse_date(thread_rows[-1])
            sid = _sample_id(f"thread:{link}", joined)
            entry = {
                "id": sid,
                "text": f"[thread] {joined}",
                "source": "linkedin_thread",
                "date": joined_date,
                "channel": "linkedin",
                "char_count": len(joined),
                "source_url": link,
            }
            preview.append(entry)
            if sid not in existing_ids:
                new_samples.append(entry)
                existing_ids.add(sid)

    if not dry_run and new_samples:
        save_voice_history(existing + new_samples)

    return len(new_samples), preview


# ---------------------------------------------------------------------------
# Ingestion: Buffer published posts
# ---------------------------------------------------------------------------


def ingest_buffer_posts(
    published_posts: list[dict],
    channel: str = "linkedin",
    min_chars: int = _DEFAULT_MIN_CHARS,
    dry_run: bool = False,
) -> int:
    """Add published Buffer posts to voice_history as style samples.

    published_posts: list of dicts from BufferService.get_published_posts().
    Returns number of new samples added.
    """
    existing = load_voice_history()
    existing_ids = {s["id"] for s in existing}
    new_samples: list[dict] = []

    for post in published_posts:
        text = (post.get("text") or "").strip()
        if len(text) < min_chars:
            continue
        post_id = post.get("id", "")
        sid = _sample_id(post_id, text)
        if sid in existing_ids:
            continue
        sent_at = post.get("sentAt") or post.get("dueAt") or ""
        new_samples.append({
            "id": sid,
            "text": text,
            "source": "buffer_post",
            "date": sent_at[:10],
            "channel": channel,
            "char_count": len(text),
            "source_url": "",
        })
        existing_ids.add(sid)

    if not dry_run and new_samples:
        save_voice_history(existing + new_samples)

    return len(new_samples)


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------


def build_voice_examples_block(
    channel: str = "linkedin",
    n: Optional[int] = None,
    min_chars: Optional[int] = None,
    seed: Optional[int] = None,
) -> str:
    """Return a compact voice-example block for prompt injection.

    Selects up to n samples from voice_history for the given channel.
    Returns empty string when disabled or no samples are available.
    Voice examples are only injected for longer-form channels (linkedin, threads).
    """
    enabled = os.getenv("VOICE_HISTORY_ENABLED", "true").strip().lower()
    if enabled not in ("1", "true", "yes", "on"):
        return ""

    if channel not in ("linkedin", "threads"):
        return ""

    n = n or int(os.getenv("VOICE_HISTORY_SAMPLE_SIZE", str(_DEFAULT_SAMPLE_SIZE)))
    min_chars = min_chars or int(os.getenv("VOICE_HISTORY_MIN_CHARS", str(_DEFAULT_MIN_CHARS)))

    samples = load_voice_history()
    if not samples:
        return ""

    eligible = [
        s for s in samples
        if s.get("char_count", 0) >= min_chars
        and s.get("source") != "linkedin_thread"  # threads inject separately
    ]

    # Prefer channel-matched samples but fall back to all if thin
    channel_matched = [s for s in eligible if s.get("channel") == channel]
    pool = channel_matched if len(channel_matched) >= n else eligible

    if not pool:
        return ""

    # Recent pool for recency bias, then random sample for variety
    pool.sort(key=lambda s: s.get("date", ""), reverse=True)
    pool = pool[:max(n * 4, 20)]
    rng = random.Random(seed)
    chosen = rng.sample(pool, min(n, len(pool)))
    chosen.sort(key=lambda s: s.get("date", ""))

    src_label = {"linkedin_comment": "comment", "buffer_post": "post", "linkedin_thread": "thread"}
    lines = [
        "Voice examples — your real writing (study tone and cadence; do NOT repeat these topics):"
    ]
    for s in chosen:
        label = src_label.get(s.get("source", ""), "sample")
        month = (s.get("date") or "")[:7]
        snippet = s["text"][:450]
        if len(s["text"]) > 450:
            snippet += "..."
        lines.append(f'[{label}, {month}] "{snippet}"')

    return "\n".join(lines)


def stats() -> dict:
    """Return summary stats for the current voice history."""
    samples = load_voice_history()
    by_source: dict[str, int] = {}
    for s in samples:
        src = s.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1
    return {"total": len(samples), "by_source": by_source}
