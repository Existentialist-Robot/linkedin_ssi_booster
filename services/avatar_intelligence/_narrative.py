"""Narrative continuity memory for the avatar_intelligence package."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from services.avatar_intelligence._models import NarrativeMemory
from services.avatar_intelligence._paths import NARRATIVE_MEMORY_PATH

logger = logging.getLogger(__name__)

_CLAIM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(you can|you should|you must|always|never|every|the key|the trick|the secret|the best way)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(is (the|a) (major|critical|key|core|main|primary))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(more (important|effective|efficient|scalable) than)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(will (replace|change|transform|disrupt))\b",
        re.IGNORECASE,
    ),
]

_THEME_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "that", "this", "it", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "will", "would", "can", "could",
    "should", "may", "might", "by", "from", "as", "about", "into", "through",
})


def update_narrative_memory(
    memory: NarrativeMemory,
    themes: list[str],
    claims: list[str],
    arcs: list[str],
    max_items: int | None = None,
) -> NarrativeMemory:
    """Append new items to narrative memory and trim to *max_items* (FIFO).

    Each list is trimmed independently so no category starves another.
    When *max_items* is None, falls back to ``AVATAR_MAX_MEMORY_ITEMS``.
    """
    from services.shared import AVATAR_MAX_MEMORY_ITEMS as _DEFAULT_MAX  # lazy — avoid circular

    limit = max_items if max_items is not None else _DEFAULT_MAX

    def _merge_trim(existing: list[str], new: list[str]) -> list[str]:
        merged = existing + [item for item in new if item not in existing]
        return merged[-limit:]

    return NarrativeMemory(
        recent_themes=_merge_trim(memory.recent_themes, themes),
        recent_claims=_merge_trim(memory.recent_claims, claims),
        open_narrative_arcs=_merge_trim(memory.open_narrative_arcs, arcs),
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


def save_narrative_memory(memory: NarrativeMemory, path: Path | None = None) -> None:
    """Persist *memory* to *path* (defaults to ``NARRATIVE_MEMORY_PATH``).

    Failures emit a warning so the publish path is never interrupted.
    """
    target = path or NARRATIVE_MEMORY_PATH
    payload = {
        "recentThemes": memory.recent_themes,
        "recentClaims": memory.recent_claims,
        "openNarrativeArcs": memory.open_narrative_arcs,
        "lastUpdated": memory.last_updated,
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.debug(
            "Narrative memory saved to %s (%d themes, %d claims)",
            target,
            len(memory.recent_themes),
            len(memory.recent_claims),
        )
    except OSError as exc:
        logger.warning("Narrative memory save failed (continuing): %s", exc)


def extract_narrative_updates(
    post_text: str,
    ssi_component: str,
    article_title: str = "",
) -> dict[str, list[str]]:
    """Extract themes, claims, and open arcs from a successfully-generated post.

    Returns a dict with keys ``themes``, ``claims``, ``arcs``.  Rule-based,
    no LLM call — deterministic and fast.

    Themes: top non-stopword tokens from ssi_component + article_title.
    Claims: sentences matching known claim patterns.
    Arcs:   empty list in v1 (reserved for future turn-taking signals).
    """
    raw_tokens = re.findall(r"[a-zA-Z]{3,}", f"{ssi_component} {article_title}".lower())
    themes = list(dict.fromkeys(t for t in raw_tokens if t not in _THEME_STOPWORDS))[:10]

    sentences = re.split(r"(?<=[.!?])\s+", post_text.strip())
    claims: list[str] = []
    for sent in sentences:
        sent_stripped = sent.strip()
        if any(p.search(sent_stripped) for p in _CLAIM_PATTERNS):
            norm = sent_stripped.rstrip(".!?,;").lower()
            if len(norm) >= 20 and norm not in claims:
                claims.append(norm)
    claims = claims[:5]

    return {"themes": themes, "claims": claims, "arcs": []}


def build_continuity_context(memory: NarrativeMemory, max_chars: int = 300) -> str:
    """Build a prompt-ready continuity snippet from narrative memory.

    Returns an empty string when memory has no useful content.  The output
    is trimmed to *max_chars* and is safe to include verbatim in any prompt.
    """
    parts: list[str] = []
    if memory.recent_themes:
        top_themes = memory.recent_themes[-5:]
        parts.append("Recent topics you have written about: " + ", ".join(top_themes) + ".")
    if memory.open_narrative_arcs:
        top_arcs = memory.open_narrative_arcs[-3:]
        parts.append(
            "Open narrative threads to vary or continue: " + "; ".join(top_arcs) + "."
        )
    if not parts:
        return ""
    snippet = " ".join(parts)
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rsplit(" ", 1)[0].rstrip(",;") + "..."
    return snippet


def compute_repetition_score(post_text: str, memory: NarrativeMemory) -> float:
    """Return a [0.0, 1.0] score representing how much *post_text* repeats recent claims.

    Score is the fraction of recent claims whose key tokens overlap ≥ 50 %
    with *post_text*, capped at 1.0.  Score of 0.0 = no repetition.
    """
    if not memory.recent_claims:
        return 0.0

    post_tokens: frozenset[str] = frozenset(
        t.lower()
        for t in re.findall(r"[a-zA-Z]{3,}", post_text)
        if t.lower() not in _THEME_STOPWORDS
    )
    if not post_tokens:
        return 0.0

    overlap_count = 0
    for claim in memory.recent_claims:
        claim_tokens = frozenset(
            t.lower()
            for t in re.findall(r"[a-zA-Z]{3,}", claim)
            if t.lower() not in _THEME_STOPWORDS
        )
        if not claim_tokens:
            continue
        overlap = len(post_tokens & claim_tokens) / len(claim_tokens)
        if overlap >= 0.5:
            overlap_count += 1

    return round(min(overlap_count / len(memory.recent_claims), 1.0), 4)
