"""Constants and default paths for selection learning."""

from __future__ import annotations

from pathlib import Path

DEFAULT_SELECTION_DIR = Path("data") / "selection"
CANDIDATES_LOG_PATH: Path = DEFAULT_SELECTION_DIR / "generated_candidates.jsonl"
PUBLISHED_CACHE_PATH: Path = DEFAULT_SELECTION_DIR / "published_posts_cache.jsonl"

# Acceptance window: candidates older than this without a published match are
# labelled selected=False (implicit rejection by the user).
ACCEPTANCE_WINDOW_DAYS: int = 21

# Minimum Jaccard token overlap required to consider two text snippets a match.
JACCARD_THRESHOLD: float = 0.25

# Alpha weight for acceptance rate in article ranking formula.
DEFAULT_RANK_ALPHA: float = 0.30

# Freshness half-life (days): score decays to 0.5 at this age.
FRESHNESS_HALF_LIFE_DAYS: float = 10.5
