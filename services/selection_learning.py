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

from services.spacy_nlp import get_spacy_nlp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEFAULT_SELECTION_DIR = Path("data") / "selection"
CANDIDATES_LOG_PATH: Path = _DEFAULT_SELECTION_DIR / "generated_candidates.jsonl"
PUBLISHED_CACHE_PATH: Path = _DEFAULT_SELECTION_DIR / "published_posts_cache.jsonl"

# Acceptance window: candidates older than this without a published match are
# labelled selected=False (implicit rejection by the user).
ACCEPTANCE_WINDOW_DAYS: int = 21

# Minimum Jaccard token overlap required to consider two text snippets a match.
_JACCARD_THRESHOLD: float = 0.25

# Alpha weight for acceptance rate in article ranking formula.
_DEFAULT_RANK_ALPHA: float = 0.30

# Freshness half-life (days): score decays to 0.5 at this age.
_FRESHNESS_HALF_LIFE_DAYS: float = 10.5


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
    themes: list[str] = field(default_factory=list)  # NLP-extracted themes
    sentiment: dict[str, Any] = field(default_factory=dict)  # Sentiment analysis
    user_feedback: dict[str, Any] = field(default_factory=dict)  # User ratings, manual overrides


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
    enable_nlp: bool = True,
) -> CandidateRecord:
    """Append one CandidateRecord to the candidates log and return it.

    *path* defaults to ``CANDIDATES_LOG_PATH``.  Pass an alternative path in
    tests to avoid writing to the real data directory.
    *enable_nlp* controls whether to run spaCy NLP analysis (can disable for dry-run).
    """
    # Extract themes and sentiment using spaCy if enabled
    themes: list[str] = []
    sentiment: dict[str, Any] = {}
    
    if enable_nlp:
        try:
            nlp = get_spacy_nlp()
            themes = nlp.extract_themes(post_text)
            sentiment = nlp.analyze_sentiment(post_text)
            logger.debug(
                "selection_learning: extracted %d themes, sentiment=%s",
                len(themes),
                sentiment.get("polarity", "unknown"),
            )
        except Exception as exc:
            logger.warning("selection_learning: NLP analysis failed (continuing): %s", exc)
    
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
        themes=themes,
        sentiment=sentiment,
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
# Similarity-based repetition detection
# ---------------------------------------------------------------------------


def find_similar_candidates(
    post_text: str,
    candidates: list[dict[str, Any]] | None = None,
    similarity_threshold: float = 0.75,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Find candidates similar to *post_text* using spaCy semantic similarity.
    
    This helps detect repetitive content before publishing. Returns candidates
    with similarity >= *similarity_threshold*, sorted by similarity (highest first).
    
    Args:
        post_text: The post text to check for similarity
        candidates: List of candidate dicts to check against (if None, loads from path)
        similarity_threshold: Minimum similarity score (0.0–1.0) to consider a match
        path: Override path for candidates log (tests)
        
    Returns:
        List of similar candidate dicts with added 'similarity_score' field
    """
    if candidates is None:
        target = path or CANDIDATES_LOG_PATH
        candidates = _read_jsonl(target)
    
    nlp = get_spacy_nlp()
    similar: list[tuple[float, dict[str, Any]]] = []
    
    for candidate in candidates:
        candidate_text = candidate.get("text_snippet", "")
        if not candidate_text:
            continue
        
        try:
            similarity = nlp.compute_similarity(post_text, candidate_text)
            if similarity >= similarity_threshold:
                # Add similarity score to the candidate dict
                enriched = candidate.copy()
                enriched["similarity_score"] = similarity
                similar.append((similarity, enriched))
        except Exception as exc:
            logger.debug(
                "selection_learning: similarity computation failed for candidate %s: %s",
                candidate.get("candidate_id", "unknown"),
                exc,
            )
            continue
    
    # Sort by similarity (highest first)
    similar.sort(key=lambda x: x[0], reverse=True)
    return [candidate for _, candidate in similar]


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
    """Beta-smoothed acceptance rate for one feature bucket."""

    feature_key: str         # e.g., "source:Hugging Face Blog" or "theme:llm"
    feature_value: str       # The actual value
    n_selected: int
    n_total: int
    acceptance_rate: float   # (n_selected + 1) / (n_total + 2) — Beta(1,1) smoothing
    boost_factor: float = 1.0  # Multiplier for ranking (can be >1 to boost, <1 to suppress)

    # Legacy fields for backward compatibility
    @property
    def source(self) -> str:
        """Extract source from feature_key if it's a source feature."""
        if self.feature_key == "source":
            return self.feature_value
        return ""
    
    @property
    def ssi_component(self) -> str:
        """Extract ssi_component from feature_key if it's an ssi feature."""
        if self.feature_key == "ssi_component":
            return self.feature_value
        return ""


def compute_acceptance_priors(
    path: Path | None = None,
    include_themes: bool = True,
    min_theme_count: int = 3,
) -> dict[tuple[str, str], FeaturePrior]:
    """Read labeled candidates and compute Beta-smoothed priors per (source, ssi_component).

    Only candidates with selected != None (i.e. labelled) contribute.
    Low-count buckets are smoothed towards 0.5 via Beta(1,1) prior
    (effectively Laplace smoothing: add 1 to numerator and 2 to denominator).

    Args:
        path: Override path for candidates log (tests)
        include_themes: Whether to compute theme-based priors in addition to source/ssi
        min_theme_count: Minimum occurrences for a theme to get its own prior
    
    Returns a dict mapping (source, ssi_component) → FeaturePrior.
    """
    target = path or CANDIDATES_LOG_PATH
    records = [r for r in _read_jsonl(target) if r.get("selected") is not None]

    # Aggregate counts for source+ssi combinations
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
        # Compute boost factor based on performance
        # High performers (>70% acceptance) get boosted, low performers (<30%) get suppressed
        raw_rate = n_sel / max(1, n_tot)
        if n_tot >= 5:  # Only apply boost/suppress with sufficient data
            if raw_rate > 0.70:
                boost = 1.2  # 20% boost for high performers
            elif raw_rate < 0.30:
                boost = 0.8  # 20% suppression for low performers
            else:
                boost = 1.0
        else:
            boost = 1.0  # Neutral for low-count sources
        
        priors[(source, ssi)] = FeaturePrior(
            feature_key="source+ssi",
            feature_value=f"{source}|{ssi}",
            n_selected=n_sel,
            n_total=n_tot,
            acceptance_rate=(n_sel + 1) / (n_tot + 2),
            boost_factor=boost,
        )
    
    # Also compute theme-based priors if enabled
    if include_themes:
        theme_counts: dict[str, list[int]] = {}  # theme → [n_selected, n_total]
        for rec in records:
            themes = rec.get("themes", [])
            selected = rec.get("selected") is True
            for theme in themes:
                if theme not in theme_counts:
                    theme_counts[theme] = [0, 0]
                theme_counts[theme][1] += 1
                if selected:
                    theme_counts[theme][0] += 1
        
        # Only create priors for themes with sufficient data
        for theme, (n_sel, n_tot) in theme_counts.items():
            if n_tot >= min_theme_count:
                raw_rate = n_sel / max(1, n_tot)
                if n_tot >= 5:
                    if raw_rate > 0.70:
                        boost = 1.15  # Smaller boost for themes (they're more granular)
                    elif raw_rate < 0.30:
                        boost = 0.85
                    else:
                        boost = 1.0
                else:
                    boost = 1.0
                
                # Use a composite key (theme, "") to distinguish from source priors
                priors[(f"theme:{theme}", "")] = FeaturePrior(
                    feature_key="theme",
                    feature_value=theme,
                    n_selected=n_sel,
                    n_total=n_tot,
                    acceptance_rate=(n_sel + 1) / (n_tot + 2),
                    boost_factor=boost,
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
    source_rates = [p.acceptance_rate for (s, _), p in priors.items() 
                    if not s.startswith("theme:") and s == source]
    if source_rates:
        return sum(source_rates) / len(source_rates)

    # Fallback 2: global uninformative prior
    return 0.5


def get_boost_factor(
    source: str,
    ssi_component: str,
    themes: list[str],
    priors: dict[tuple[str, str], FeaturePrior],
) -> float:
    """Return the combined boost factor for an article based on source, ssi, and themes.
    
    Combines boost factors from multiple signals:
    - Source+SSI combination
    - Individual themes (if available)
    
    Returns a multiplier to apply to the article's ranking score.
    """
    boost = 1.0
    
    # Get source+ssi boost
    key = (source, ssi_component)
    if key in priors:
        boost *= priors[key].boost_factor
    
    # Get theme boosts (average across all matching themes)
    theme_boosts: list[float] = []
    for theme in themes:
        theme_key = (f"theme:{theme}", "")
        if theme_key in priors:
            theme_boosts.append(priors[theme_key].boost_factor)
    
    if theme_boosts:
        avg_theme_boost = sum(theme_boosts) / len(theme_boosts)
        boost *= avg_theme_boost
    
    # Cap the total boost to prevent extreme values
    return max(0.5, min(2.0, boost))


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
    use_boost_factors: bool = True,
    extract_themes: bool = True,
) -> list[dict[str, Any]]:
    """Re-rank *articles* using relevance, freshness, acceptance prior, and boost factors.

    Scoring formula (all components 0.0–1.0, higher = better):
        base_score = (1 - alpha) * (0.5 * relevance + 0.5 * freshness) + alpha * acceptance_rate
        final_score = base_score * boost_factor (if use_boost_factors=True)

    The boost_factor is computed from historical performance:
    - High-performing sources/themes (>70% acceptance) get boosted (1.2x or 1.15x)
    - Low-performing sources/themes (<30% acceptance) get suppressed (0.8x or 0.85x)
    - Average performers stay neutral (1.0x)

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
        use_boost_factors:      Apply boost/suppress multipliers based on historical performance.
        extract_themes:         Extract themes from articles using spaCy for theme-based ranking.
    """
    kw_list = keywords or []
    
    # Optionally extract themes from articles using spaCy
    if extract_themes:
        try:
            nlp = get_spacy_nlp()
            for article in articles:
                if "themes" not in article:  # Only extract if not already present
                    text = f"{article.get('title', '')} {article.get('summary', '')}"
                    article["themes"] = nlp.extract_themes(text[:1000])  # Limit text length
        except Exception as exc:
            logger.debug("selection_learning: theme extraction failed (continuing): %s", exc)
    
    scored: list[tuple[float, dict[str, Any]]] = []
    for article in articles:
        source = article.get("source", "")
        themes = article.get("themes", [])
        
        # Compute base score
        rel = _relevance_score(article, kw_list)
        fresh = _freshness_score(article.get("published", ""), freshness_half_life_days)
        acc = get_acceptance_rate(source, ssi_component, priors)
        base_score = (1.0 - alpha) * (0.5 * rel + 0.5 * fresh) + alpha * acc
        
        # Apply boost factor if enabled
        if use_boost_factors:
            boost = get_boost_factor(source, ssi_component, themes, priors)
            final_score = base_score * boost
            logger.debug(
                "selection_learning: ranked article '%s' - base=%.3f boost=%.2f final=%.3f",
                article.get("title", "")[:50],
                base_score,
                boost,
                final_score,
            )
        else:
            final_score = base_score
        
        scored.append((final_score, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]
    return [a for _, a in scored]


# ---------------------------------------------------------------------------
# Feedback mechanism
# ---------------------------------------------------------------------------


def record_user_feedback(
    candidate_id: str,
    feedback_type: str,
    feedback_value: Any,
    *,
    path: Path | None = None,
) -> bool:
    """Record user feedback (rating, manual override) for a candidate.
    
    This allows users to provide explicit feedback on generated posts,
    which can be used to refine the learning algorithm.
    
    Args:
        candidate_id: The UUID of the candidate to update
        feedback_type: Type of feedback (e.g., "rating", "override", "upvote", "downvote")
        feedback_value: The feedback value (e.g., 5 for a 1-5 rating, True for upvote)
        path: Override path for candidates log (tests)
    
    Returns:
        True if the candidate was found and updated, False otherwise
    """
    target = path or CANDIDATES_LOG_PATH
    records = _read_jsonl(target)
    found = False
    
    for rec in records:
        if rec.get("candidate_id") == candidate_id:
            if "user_feedback" not in rec:
                rec["user_feedback"] = {}
            rec["user_feedback"][feedback_type] = feedback_value
            rec["user_feedback"]["last_updated"] = datetime.now(timezone.utc).isoformat()
            found = True
            break
    
    if found:
        _rewrite_jsonl(target, records)
        logger.info(
            "selection_learning: recorded %s feedback for candidate %s: %s",
            feedback_type,
            candidate_id,
            feedback_value,
        )
    else:
        logger.warning(
            "selection_learning: candidate_id %s not found — feedback not recorded",
            candidate_id,
        )
    
    return found


def apply_user_feedback_to_selection(
    *,
    path: Path | None = None,
    upvote_as_selected: bool = True,
    downvote_as_rejected: bool = False,
) -> int:
    """Apply user feedback to candidate selection labels.
    
    This processes user_feedback entries and updates the selected field
    accordingly. For example, upvotes can be treated as explicit selections.
    
    Args:
        path: Override path for candidates log (tests)
        upvote_as_selected: Treat upvotes as selected=True
        downvote_as_rejected: Treat downvotes as selected=False
    
    Returns:
        Number of candidates updated
    """
    target = path or CANDIDATES_LOG_PATH
    records = _read_jsonl(target)
    updated = 0
    
    for rec in records:
        feedback = rec.get("user_feedback", {})
        if not feedback:
            continue
        
        # Skip if already labeled by reconciliation
        if rec.get("selected") is not None:
            continue
        
        # Apply upvote feedback
        if upvote_as_selected and feedback.get("upvote") is True:
            rec["selected"] = True
            rec["selected_at"] = datetime.now(timezone.utc).isoformat()
            updated += 1
        
        # Apply downvote feedback
        elif downvote_as_rejected and feedback.get("downvote") is True:
            rec["selected"] = False
            rec["selected_at"] = datetime.now(timezone.utc).isoformat()
            updated += 1
        
        # Apply manual override (highest priority)
        if "override" in feedback:
            rec["selected"] = feedback["override"]
            rec["selected_at"] = datetime.now(timezone.utc).isoformat()
            updated += 1
    
    if updated > 0:
        _rewrite_jsonl(target, records)
        logger.info(
            "selection_learning: applied user feedback to %d candidates",
            updated,
        )
    
    return updated
