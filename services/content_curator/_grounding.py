"""
Curation grounding configuration loaders.
Reads env vars to produce keyword sets and tag-expansion maps used by the
curator's fact retrieval layer.
"""

import os

from services.content_curator._config import KEYWORDS
from services.console_grounding import get_console_grounding_tag_expansions_from_graph


def load_curation_grounding_keywords() -> set[str]:
    """Load keywords used specifically for curation fact retrieval.

    Falls back to CURATOR_KEYWORDS when not explicitly configured.
    """
    raw = os.getenv("CURATION_GROUNDING_TECH_KEYWORDS", "").strip()
    if raw:
        return {part.strip().lower() for part in raw.split(",") if part.strip()}
    return {kw.strip().lower() for kw in KEYWORDS if kw.strip()}


def load_curation_grounding_tag_expansions() -> dict[str, set[str]]:
    """Load curation-specific tag expansions with console defaults fallback.

    Env format:
      CURATION_GROUNDING_TAG_EXPANSIONS=llm:rag|embeddings|vector search;java:spring|jms
    """
    raw = os.getenv("CURATION_GROUNDING_TAG_EXPANSIONS", "").strip()
    if not raw:
        return get_console_grounding_tag_expansions_from_graph()

    expansions: dict[str, set[str]] = {}
    for block in raw.split(";"):
        block = block.strip()
        if not block or ":" not in block:
            continue
        base, values = block.split(":", 1)
        base = base.strip().lower()
        related = {v.strip().lower() for v in values.split("|") if v.strip()}
        if base and related:
            expansions[base] = related
    return expansions or get_console_grounding_tag_expansions_from_graph()
