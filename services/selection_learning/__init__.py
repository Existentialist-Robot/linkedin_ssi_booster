"""Selection Learning package.

Public API is kept backward-compatible with the former
``services/selection_learning.py`` module while implementation is split into
focused helper services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.selection_learning._constants import (
    ACCEPTANCE_WINDOW_DAYS,
    CANDIDATES_LOG_PATH,
    PUBLISHED_CACHE_PATH,
)
from services.selection_learning._feedback import FeedbackService
from services.selection_learning._logging import CandidateService, make_candidate_id
from services.selection_learning._models import CandidateRecord, FeaturePrior, PublishedRecord
from services.selection_learning._priors import PriorService
from services.selection_learning._published import upsert_published_record
from services.selection_learning._ranking import RankingService
from services.selection_learning._reconcile import ReconcileService
from services.selection_learning._text import TextMatcher
from services.spacy_nlp import get_spacy_nlp


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
    """Append one CandidateRecord to the candidates log and return it."""
    return CandidateService(get_spacy_nlp).log_candidate(
        candidate_id=candidate_id,
        article_url=article_url,
        article_title=article_title,
        article_source=article_source,
        ssi_component=ssi_component,
        channel=channel,
        post_text=post_text,
        buffer_id=buffer_id,
        route=route,
        run_id=run_id,
        path=path,
        enable_nlp=enable_nlp,
    )


def update_candidate_buffer_id(
    candidate_id: str,
    buffer_id: str,
    path: Path | None = None,
) -> bool:
    """Set buffer_id on an existing candidate record in the log."""
    return CandidateService.update_candidate_buffer_id(candidate_id, buffer_id, path=path)


def find_similar_candidates(
    post_text: str,
    candidates: list[dict[str, Any]] | None = None,
    similarity_threshold: float = 0.75,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Find candidates similar to *post_text* using spaCy semantic similarity."""
    return CandidateService(get_spacy_nlp).find_similar_candidates(
        post_text,
        candidates=candidates,
        similarity_threshold=similarity_threshold,
        path=path,
    )


def reconcile_published(
    buffer_service: Any,
    channel_ids: dict[str, str],
    *,
    candidates_path: Path | None = None,
    published_path: Path | None = None,
    acceptance_window_days: int = ACCEPTANCE_WINDOW_DAYS,
    limit_per_channel: int = 50,
) -> dict[str, int]:
    """Fetch SENT posts, upsert into cache, match and label candidates."""
    return ReconcileService.reconcile_published(
        buffer_service,
        channel_ids,
        candidates_path=candidates_path,
        published_path=published_path,
        acceptance_window_days=acceptance_window_days,
        limit_per_channel=limit_per_channel,
    )


def compute_acceptance_priors(
    path: Path | None = None,
    include_themes: bool = True,
    min_theme_count: int = 3,
) -> dict[tuple[str, str], FeaturePrior]:
    """Read labeled candidates and compute Beta-smoothed priors."""
    return PriorService.compute_acceptance_priors(
        path=path,
        include_themes=include_themes,
        min_theme_count=min_theme_count,
    )


def get_acceptance_rate(
    source: str,
    ssi_component: str,
    priors: dict[tuple[str, str], FeaturePrior],
) -> float:
    """Return acceptance rate for a source/component bucket with fallbacks."""
    return PriorService.get_acceptance_rate(source, ssi_component, priors)


def get_boost_factor(
    source: str,
    ssi_component: str,
    themes: list[str],
    priors: dict[tuple[str, str], FeaturePrior],
) -> float:
    """Return combined source/theme boost multiplier."""
    return PriorService.get_boost_factor(source, ssi_component, themes, priors)


def rank_articles(
    articles: list[dict[str, Any]],
    priors: dict[tuple[str, str], FeaturePrior],
    *,
    ssi_component: str = "",
    keywords: list[str] | None = None,
    alpha: float = 0.30,
    freshness_half_life_days: float = 10.5,
    use_boost_factors: bool = True,
    extract_themes: bool = True,
) -> list[dict[str, Any]]:
    """Re-rank articles using relevance, freshness, priors, and boosts."""
    return RankingService(get_spacy_nlp).rank_articles(
        articles,
        priors,
        ssi_component=ssi_component,
        keywords=keywords,
        alpha=alpha,
        freshness_half_life_days=freshness_half_life_days,
        use_boost_factors=use_boost_factors,
        extract_themes=extract_themes,
    )


def record_user_feedback(
    candidate_id: str,
    feedback_type: str,
    feedback_value: Any,
    *,
    path: Path | None = None,
) -> bool:
    """Record user feedback (rating/override/upvote/downvote) for a candidate."""
    return FeedbackService.record_user_feedback(
        candidate_id,
        feedback_type,
        feedback_value,
        path=path,
    )


def apply_user_feedback_to_selection(
    *,
    path: Path | None = None,
    upvote_as_selected: bool = True,
    downvote_as_rejected: bool = False,
) -> int:
    """Apply user feedback values to selected/selected_at labels."""
    return FeedbackService.apply_user_feedback_to_selection(
        path=path,
        upvote_as_selected=upvote_as_selected,
        downvote_as_rejected=downvote_as_rejected,
    )


def _jaccard(a: str, b: str) -> float:
    """Backward-compatible helper export for tests/callers."""
    return TextMatcher.jaccard(a, b)


def _match_candidate(
    published: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str | None:
    """Backward-compatible helper export for tests/callers."""
    return TextMatcher.match_candidate(published, candidates)


__all__ = [
    "ACCEPTANCE_WINDOW_DAYS",
    "CANDIDATES_LOG_PATH",
    "PUBLISHED_CACHE_PATH",
    "CandidateRecord",
    "PublishedRecord",
    "FeaturePrior",
    "make_candidate_id",
    "log_candidate",
    "update_candidate_buffer_id",
    "find_similar_candidates",
    "upsert_published_record",
    "reconcile_published",
    "compute_acceptance_priors",
    "get_acceptance_rate",
    "get_boost_factor",
    "rank_articles",
    "record_user_feedback",
    "apply_user_feedback_to_selection",
    "get_spacy_nlp",
    "_jaccard",
    "_match_candidate",
]
