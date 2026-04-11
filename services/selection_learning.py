"""
Selection Learning — candidate logging, Buffer publish reconciliation,
and acceptance-prior-based article ranking.

Flow
----
1. On each curation run ``log_candidate()`` appends a CandidateRecord to
   ``data/selection/generated_candidates.jsonl``.
2. After a successful Buffer push the caller updates the record's buffer_id
   via ``update_candidate_buffer_id()``.
3. ``reconcile_published()`` queries Buffer for SENT (published) posts, upserts
   them into ``data/selection/published_posts_cache.jsonl``, matches them to
   candidates (buffer_id → URL token → Jaccard text similarity), and labels
   candidates as selected=True/False based on a configurable acceptance window.
4. ``compute_acceptance_priors()`` reads labeled candidates and builds
   Beta-smoothed acceptance rates keyed by (source, ssi_component).
5. ``rank_articles()`` applies those priors plus freshness decay to re-order
   the RSS candidate list before generation, so better-performing source/topic
   combinations float to the top over time.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEFAULT_SELECTION_DIR = Path("data") / "selection"
CANDIDATES_LOG_PATH: Path = _DEFAULT_SELECTION_DIR / "generated_candidates.jsonl"
PUBLISHED_CACHE_PATH: Path = _DEFAULT_SELECTION_DIR / "published_posts_cache.jsonl"

# Acceptance window: candidates older than this without a published match are
# labelled selected=False (implicit rejection by the user).
ACCEPTANCE_WINDOW_DAYS: int = 14

# Minimum Jaccard token overlap required to consider two text snippets a match.
_JACCARD_THRESHOLD: float = 0.25

# Alpha weight for acceptance rate in article ranking formula.
_DEFAULT_RANK_ALPHA: float = 0.30

# Freshness half-life (days): score decays to 0.5 at this age.
_FRESHNESS_HALF_LIFE_DAYS: float = 7.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CandidateRecord:
    """One generated post candidate captured at curation time."""

    candidate_id: str           # UUID
    timestamp: str              # ISO-8601 UTC
    article_url: str            # RSS article URL (used for URL-token matching)
    article_title: str          # RSS article title
    article_source: str         # Feed name, e.g. "Hugging Face Blog"
    ssi_component: str          # establish_brand / find_right_people / …
    channel: str                # linkedin / x / bluesky / youtube / all
    text_hash: str              # SHA-256[:16] of the generated post body
    text_snippet: str           # first 200 chars of generated post (for matching)
    buffer_id: str | None       # Buffer post/idea id; None until pushed
    route: str                  # post | idea | block
    selected: bool | None       # None=pending, True=chosen, False=rejected
    selected_at: str | None     # ISO-8601 UTC when labelled
    run_id: str                 # UUID identifying the current tool run


@dataclass
class PublishedRecord:
    """One confirmed-published post fetched from Buffer (status=SENT)."""

    buffer_id: str              # Buffer post id (primary key)
    channel: str                # linkedin / x / bluesky
    text_snippet: str           # first 200 chars
    published_at: str           # ISO-8601 from Buffer dueAt field
    fetched_at: str             # ISO-8601 when we fetched from Buffer
    candidate_id: str | None    # linked CandidateRecord.candidate_id or None


# ---------------------------------------------------------------------------
# Low-level I/O helpers
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a newline-delimited JSON file; return empty list if missing."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("selection_learning: skipping malformed line %d in %s: %s", lineno, path, exc)
    return records


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object to a newline-delimited file, creating it if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _rewrite_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Atomically overwrite a JSONL file with *records*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Text hashing + token helpers
# ---------------------------------------------------------------------------


def _text_hash(text: str) -> str:
    """Return first 16 hex chars of SHA-256 of *text* (lowercase, stripped)."""
    return hashlib.sha256(text.lower().strip().encode()).hexdigest()[:16]


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens from *text*, 3+ chars, excluding stopwords."""
    _STOP = frozenset({
        "the", "and", "for", "that", "this", "with", "are", "was", "were",
        "you", "your", "our", "has", "have", "had", "not", "its", "but",
        "about", "from", "they", "than", "when", "what", "how",
    })
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP}


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity of word tokens between two strings."""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------------------
# Candidate logging
# ---------------------------------------------------------------------------


def make_candidate_id() -> str:
    """Return a new UUID4 string."""
    return str(uuid.uuid4())


def log_candidate(
    *,
    candidate_id: str,
    article_url: str,
    article_title: str,
    article_source: str,
    ssi_component: str,
    channel: str,
    post_text: str,
    buffer_id: str | None,
    route: str,
    run_id: str,
    path: Path | None = None,
) -> CandidateRecord:
    """Append one CandidateRecord to the candidates log and return it.

    *path* defaults to ``CANDIDATES_LOG_PATH``.  Pass an alternative path in
    tests to avoid writing to the real data directory.
    """
    record = CandidateRecord(
        candidate_id=candidate_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        article_url=article_url,
        article_title=article_title,
        article_source=article_source,
        ssi_component=ssi_component,
        channel=channel,
        text_hash=_text_hash(post_text),
        text_snippet=post_text[:200],
        buffer_id=buffer_id,
        route=route,
        selected=None,
        selected_at=None,
        run_id=run_id,
    )
    target = path or CANDIDATES_LOG_PATH
    try:
        _append_jsonl(target, asdict(record))
    except OSError as exc:
        logger.warning("selection_learning: candidate log write failed (continuing): %s", exc)
    return record


def update_candidate_buffer_id(
    candidate_id: str,
    buffer_id: str,
    path: Path | None = None,
) -> bool:
    """Set buffer_id on an existing candidate record in the log.

    Rewrites the file in-place.  Returns True if the record was found and
    updated, False if not found (logged as a warning).
    """
    target = path or CANDIDATES_LOG_PATH
    records = _read_jsonl(target)
    found = False
    for rec in records:
        if rec.get("candidate_id") == candidate_id:
            rec["buffer_id"] = buffer_id
            found = True
            break
    if found:
        _rewrite_jsonl(target, records)
    else:
        logger.warning(
            "selection_learning: candidate_id %s not found — buffer_id not updated", candidate_id
        )
    return found


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _match_candidate(
    published: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str | None:
    """Return the candidate_id of the best matching candidate for *published*, or None.

    Matching priority:
    1. buffer_id equality (exact)
    2. Article URL appears in published text snippet
    3. Jaccard token similarity of text snippets >= _JACCARD_THRESHOLD
    """
    pub_text = published.get("text_snippet", "")
    pub_buffer_id = published.get("buffer_id", "")

    # Pass 1: exact buffer_id
    for c in candidates:
        if c.get("buffer_id") and c["buffer_id"] == pub_buffer_id:
            return str(c["candidate_id"])

    # Pass 2: article URL token in published text
    for c in candidates:
        url = c.get("article_url", "")
        if url and url in pub_text:
            return str(c["candidate_id"])

    # Pass 3: Jaccard text similarity
    best_score = _JACCARD_THRESHOLD
    best_id: str | None = None
    for c in candidates:
        score = _jaccard(c.get("text_snippet", ""), pub_text)
        if score > best_score:
            best_score = score
            best_id = str(c["candidate_id"])
    return best_id


# ---------------------------------------------------------------------------
# Published cache helpers
# ---------------------------------------------------------------------------


def _load_published_ids(path: Path) -> set[str]:
    """Return the set of buffer_ids already in the published cache."""
    return {r["buffer_id"] for r in _read_jsonl(path) if r.get("buffer_id")}


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
    existing_ids = _load_published_ids(target)
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
        _append_jsonl(target, asdict(record))
    except OSError as exc:
        logger.warning("selection_learning: published cache write failed (continuing): %s", exc)


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def reconcile_published(
    buffer_service: Any,
    channel_ids: dict[str, str],
    *,
    candidates_path: Path | None = None,
    published_path: Path | None = None,
    acceptance_window_days: int = ACCEPTANCE_WINDOW_DAYS,
    limit_per_channel: int = 50,
) -> dict[str, int]:
    """Fetch SENT posts from Buffer, upsert into published cache, match to candidates.

    Args:
        buffer_service:        Initialised BufferService instance.
        channel_ids:           Mapping of channel name → Buffer channel id,
                               e.g. {"linkedin": "abc123"}.
        candidates_path:       Override path for candidates log (tests).
        published_path:        Override path for published cache (tests).
        acceptance_window_days: Candidates older than this without a published
                               match are labelled selected=False.
        limit_per_channel:     Max SENT posts to fetch per channel.

    Returns a dict with keys "fetched", "matched", "labelled_selected",
    "labelled_rejected".
    """
    c_path = candidates_path or CANDIDATES_LOG_PATH
    p_path = published_path or PUBLISHED_CACHE_PATH

    stats: dict[str, int] = {
        "fetched": 0,
        "matched": 0,
        "labelled_selected": 0,
        "labelled_rejected": 0,
    }

    candidates = _read_jsonl(c_path)
    # Only consider pending candidates (selected is null) for matching
    pending = [c for c in candidates if c.get("selected") is None]

    # Step 1: fetch published posts from Buffer and upsert into published cache
    for channel_name, channel_id in channel_ids.items():
        try:
            posts = buffer_service.get_published_posts(channel_id, limit=limit_per_channel)
        except Exception as exc:
            logger.warning(
                "selection_learning: failed to fetch published posts for %s: %s", channel_name, exc
            )
            continue

        for post in posts:
            buffer_id = post.get("id", "")
            text = post.get("text", "")
            published_at = post.get("dueAt", datetime.now(timezone.utc).isoformat())
            stats["fetched"] += 1

            # Match to a pending candidate
            candidate_id = _match_candidate(
                {"buffer_id": buffer_id, "text_snippet": text[:200]},
                pending,
            )
            upsert_published_record(
                buffer_id=buffer_id,
                channel=channel_name,
                text_snippet=text,
                published_at=published_at,
                candidate_id=candidate_id,
                path=p_path,
            )
            if candidate_id:
                stats["matched"] += 1

    # Step 2: label matched candidates as selected=True
    published_records = _read_jsonl(p_path)
    matched_candidate_ids: set[str] = {
        r["candidate_id"]
        for r in published_records
        if r.get("candidate_id")
    }

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=acceptance_window_days)
    changed = False

    for rec in candidates:
        cid = rec.get("candidate_id")
        if rec.get("selected") is not None:
            continue  # already labelled

        if cid in matched_candidate_ids:
            rec["selected"] = True
            rec["selected_at"] = now.isoformat()
            stats["labelled_selected"] += 1
            changed = True
        else:
            # Not matched — label as rejected if outside the acceptance window
            try:
                ts = datetime.fromisoformat(rec.get("timestamp", ""))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                ts = now  # malformed timestamp — treat as recent, skip rejection
            if ts < cutoff:
                rec["selected"] = False
                rec["selected_at"] = now.isoformat()
                stats["labelled_rejected"] += 1
                changed = True

    if changed:
        _rewrite_jsonl(c_path, candidates)

    logger.info(
        "selection_learning reconcile: fetched=%d matched=%d selected=%d rejected=%d",
        stats["fetched"],
        stats["matched"],
        stats["labelled_selected"],
        stats["labelled_rejected"],
    )
    return stats


# ---------------------------------------------------------------------------
# Acceptance priors
# ---------------------------------------------------------------------------


@dataclass
class FeaturePrior:
    """Beta-smoothed acceptance rate for one (source, ssi_component) bucket."""

    source: str
    ssi_component: str
    n_selected: int
    n_total: int
    acceptance_rate: float   # (n_selected + 1) / (n_total + 2) — Beta(1,1) smoothing


def compute_acceptance_priors(path: Path | None = None) -> dict[tuple[str, str], FeaturePrior]:
    """Read labeled candidates and compute Beta-smoothed priors per (source, ssi_component).

    Only candidates with selected != None (i.e. labelled) contribute.
    Low-count buckets are smoothed towards 0.5 via Beta(1,1) prior
    (effectively Laplace smoothing: add 1 to numerator and 2 to denominator).

    Returns a dict mapping (source, ssi_component) → FeaturePrior.
    """
    target = path or CANDIDATES_LOG_PATH
    records = [r for r in _read_jsonl(target) if r.get("selected") is not None]

    # Aggregate counts
    counts: dict[tuple[str, str], list[int]] = {}  # key → [n_selected, n_total]
    for rec in records:
        key = (rec.get("article_source", ""), rec.get("ssi_component", ""))
        if key not in counts:
            counts[key] = [0, 0]
        counts[key][1] += 1
        if rec.get("selected") is True:
            counts[key][0] += 1

    priors: dict[tuple[str, str], FeaturePrior] = {}
    for (source, ssi), (n_sel, n_tot) in counts.items():
        priors[(source, ssi)] = FeaturePrior(
            source=source,
            ssi_component=ssi,
            n_selected=n_sel,
            n_total=n_tot,
            acceptance_rate=(n_sel + 1) / (n_tot + 2),
        )
    return priors


def get_acceptance_rate(
    source: str,
    ssi_component: str,
    priors: dict[tuple[str, str], FeaturePrior],
) -> float:
    """Return the acceptance rate for (source, ssi_component).

    Falls back to broader source-only prior, then the global prior (0.5).
    """
    key = (source, ssi_component)
    if key in priors:
        return priors[key].acceptance_rate

    # Fallback 1: source only (average across all ssi_components for this source)
    source_rates = [p.acceptance_rate for (s, _), p in priors.items() if s == source]
    if source_rates:
        return sum(source_rates) / len(source_rates)

    # Fallback 2: global uninformative prior
    return 0.5


# ---------------------------------------------------------------------------
# Article ranking
# ---------------------------------------------------------------------------


def _freshness_score(published_date_str: str, half_life_days: float) -> float:
    """Exponential freshness decay: 1.0 when brand new, 0.5 at half_life_days.

    Returns 0.5 if the date is missing or unparseable (neutral).
    """
    if not published_date_str:
        return 0.5
    # feedparser may return RFC-2822 or ISO strings — try both
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(published_date_str, fmt)
            break
        except ValueError:
            continue
    else:
        return 0.5

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
    # Exponential decay: score = 0.5 ^ (age / half_life)
    import math
    return math.pow(0.5, age_days / half_life_days)


def _relevance_score(article: dict[str, Any], keywords: list[str]) -> float:
    """Normalized keyword match count against title + summary (0.0–1.0).

    Uses a soft cap of 10 matches.
    """
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    matches = sum(1 for kw in keywords if kw.lower() in text)
    return min(matches / 10.0, 1.0)


def rank_articles(
    articles: list[dict[str, Any]],
    priors: dict[tuple[str, str], FeaturePrior],
    *,
    ssi_component: str = "",
    keywords: list[str] | None = None,
    alpha: float = _DEFAULT_RANK_ALPHA,
    freshness_half_life_days: float = _FRESHNESS_HALF_LIFE_DAYS,
) -> list[dict[str, Any]]:
    """Re-rank *articles* using relevance, freshness, and acceptance prior.

    Scoring formula (all components 0.0–1.0, higher = better):
        score = (1 - alpha) * (0.5 * relevance + 0.5 * freshness)
                + alpha * acceptance_rate

    When *alpha* is 0 the ranking degenerates to pure relevance+freshness.
    When the acceptance history is sparse the Beta prior ensures new sources
    get a neutral 0.5 rate rather than 0.

    Args:
        articles:               List of article dicts (title, summary, source, published).
        priors:                 Output of ``compute_acceptance_priors()``.
        ssi_component:          Current SSI component (used for prior lookup).
        keywords:               Grounding keywords for relevance scoring.
        alpha:                  Weight for the acceptance prior term.
        freshness_half_life_days: Age in days where freshness score = 0.5.
    """
    kw_list = keywords or []
    scored: list[tuple[float, dict[str, Any]]] = []
    for article in articles:
        source = article.get("source", "")
        rel = _relevance_score(article, kw_list)
        fresh = _freshness_score(article.get("published", ""), freshness_half_life_days)
        acc = get_acceptance_rate(source, ssi_component, priors)
        score = (1.0 - alpha) * (0.5 * rel + 0.5 * fresh) + alpha * acc
        scored.append((score, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]
