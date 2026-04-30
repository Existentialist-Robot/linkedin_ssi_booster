"""Published-cache write helpers."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from services.selection_learning._constants import PUBLISHED_CACHE_PATH
from services.selection_learning._models import PublishedRecord
from services.selection_learning._storage import JsonlStore

logger = logging.getLogger(__name__)


def upsert_published_record(
    *,
    buffer_id: str,
    channel: str,
    text_snippet: str,
    published_at: str,
    candidate_id: str | None = None,
    path: Path | None = None,
) -> None:
    """Write a PublishedRecord to the published cache (skip if already present)."""
    target = path or PUBLISHED_CACHE_PATH
    existing_ids = JsonlStore.load_published_ids(target)
    if buffer_id in existing_ids:
        return
    record = PublishedRecord(
        buffer_id=buffer_id,
        channel=channel,
        text_snippet=text_snippet[:200],
        published_at=published_at,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        candidate_id=candidate_id,
    )
    try:
        JsonlStore.append(target, asdict(record))
    except OSError as exc:
        logger.warning("selection_learning: published cache write failed (continuing): %s", exc)
