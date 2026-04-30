"""Truth gradient scoring core logic."""

from __future__ import annotations

import logging

from services.derivative_of_truth._constants import (
    EVIDENCE_WEIGHTS,
    REASONING_WEIGHTS,
    TRUTH_GRADIENT_FLAG_THRESHOLD,
    UNCERTAINTY_CONFLICT,
    UNCERTAINTY_LONG_CHAIN,
    UNCERTAINTY_LOW_CREDIBILITY,
    UNCERTAINTY_SPARSE,
    _CONFLICT_PENALTY,
    _LONG_CHAIN_PENALTY,
    _LOW_CRED_PENALTY,
    _MAX_UNCERTAINTY_PENALTY,
    _SPARSE_PENALTY,
    _W_CREDIBILITY,
    _W_CREDIBILITY_OL,
    _W_EVIDENCE,
    _W_EVIDENCE_OL,
    _W_OVERLAP,
    _W_REASONING,
    _W_REASONING_OL,
)
from services.derivative_of_truth._models import EvidencePath, TruthGradientResult

logger = logging.getLogger(__name__)


def score_claim_with_truth_gradient(
    claim: str,
    evidence_paths: list[EvidencePath],
    raw_confidence: float = 0.5,
) -> TruthGradientResult:
    """Compute the truth gradient score for *claim* given its *evidence_paths*."""
    if not evidence_paths:
        result = TruthGradientResult(
            truth_gradient=0.0,
            uncertainty=1.0,
            confidence_penalty=max(0.0, raw_confidence),
            evidence_paths=[],
            uncertainty_sources=[UNCERTAINTY_SPARSE],
            flagged=True,
            explanation=(
                "No evidence paths provided. "
                "Claim cannot be supported by available knowledge."
            ),
        )
        logger.debug(
            "TruthGradient[no-evidence] claim='%s...': gradient=0.0 flagged=True",
            claim[:60],
        )
        return result

    path_scores: list[float] = []
    for path in evidence_paths:
        ev_weight = EVIDENCE_WEIGHTS.get(path.evidence_type, 0.25)
        re_weight = REASONING_WEIGHTS.get(path.reasoning_type, 0.35)
        if path.overlap > 0.0:
            path_score = (
                _W_EVIDENCE_OL * ev_weight
                + _W_REASONING_OL * re_weight
                + _W_CREDIBILITY_OL * path.credibility
                + _W_OVERLAP * path.overlap
            )
        else:
            path_score = (
                _W_EVIDENCE * ev_weight
                + _W_REASONING * re_weight
                + _W_CREDIBILITY * path.credibility
            )
        path_scores.append(path_score)

    base_gradient = sum(path_scores) / len(path_scores)

    total_penalty = 0.0
    uncertainty_sources: list[str] = []

    avg_path_uncertainty = sum(p.uncertainty for p in evidence_paths) / len(evidence_paths)
    if avg_path_uncertainty > 0.0:
        total_penalty += avg_path_uncertainty

    all_sources = {p.source for p in evidence_paths}
    has_conflicts = any(
        len(set(p.conflicts_with) & all_sources) > 0
        for p in evidence_paths
    )
    if has_conflicts:
        total_penalty += _CONFLICT_PENALTY
        uncertainty_sources.append(UNCERTAINTY_CONFLICT)

    max_chain = max(p.chain_length for p in evidence_paths)
    if max_chain > 3:
        extra_hops = max_chain - 3
        chain_penalty = _LONG_CHAIN_PENALTY * extra_hops
        total_penalty += chain_penalty
        uncertainty_sources.append(UNCERTAINTY_LONG_CHAIN)

    if len(evidence_paths) < 2:
        total_penalty += _SPARSE_PENALTY
        uncertainty_sources.append(UNCERTAINTY_SPARSE)

    low_cred_count = sum(1 for p in evidence_paths if p.credibility < 0.3)
    if low_cred_count > 0:
        total_penalty += _LOW_CRED_PENALTY * (low_cred_count / len(evidence_paths))
        uncertainty_sources.append(UNCERTAINTY_LOW_CREDIBILITY)

    clamped_penalty = min(total_penalty, _MAX_UNCERTAINTY_PENALTY)

    truth_gradient = base_gradient * (1.0 - clamped_penalty)
    truth_gradient = max(0.0, min(1.0, truth_gradient))

    confidence_penalty = max(0.0, raw_confidence - truth_gradient)

    flagged = truth_gradient < TRUTH_GRADIENT_FLAG_THRESHOLD

    explanation = _build_explanation(
        claim=claim,
        base_gradient=base_gradient,
        clamped_penalty=clamped_penalty,
        truth_gradient=truth_gradient,
        uncertainty_sources=uncertainty_sources,
        evidence_paths=evidence_paths,
        flagged=flagged,
    )

    logger.debug(
        "TruthGradient claim='%s...': base=%.3f penalty=%.3f gradient=%.3f flagged=%s",
        claim[:60],
        base_gradient,
        clamped_penalty,
        truth_gradient,
        flagged,
    )

    return TruthGradientResult(
        truth_gradient=truth_gradient,
        uncertainty=clamped_penalty,
        confidence_penalty=confidence_penalty,
        evidence_paths=evidence_paths,
        uncertainty_sources=uncertainty_sources,
        flagged=flagged,
        explanation=explanation,
    )


def _build_explanation(
    claim: str,
    base_gradient: float,
    clamped_penalty: float,
    truth_gradient: float,
    uncertainty_sources: list[str],
    evidence_paths: list[EvidencePath],
    flagged: bool,
) -> str:
    """Build a concise human-readable explanation of the truth gradient."""
    _ = claim
    n_paths = len(evidence_paths)
    ev_types = {p.evidence_type for p in evidence_paths}
    re_types = {p.reasoning_type for p in evidence_paths}
    avg_cred = (
        sum(p.credibility for p in evidence_paths) / n_paths if n_paths else 0.0
    )

    overlap_paths = [p for p in evidence_paths if p.overlap > 0.0]
    avg_overlap = (
        sum(p.overlap for p in overlap_paths) / len(overlap_paths)
        if overlap_paths else None
    )

    overlap_note = (
        f"; avg claim-evidence alignment: {avg_overlap:.2f}"
        if avg_overlap is not None
        else "; claim-evidence alignment: not computed"
    )
    parts = [
        f"Base gradient {base_gradient:.3f} from {n_paths} evidence path(s) "
        f"[types: {', '.join(sorted(ev_types))}; "
        f"reasoning: {', '.join(sorted(re_types))}; "
        f"avg credibility: {avg_cred:.2f}{overlap_note}].",
    ]
    if clamped_penalty > 0:
        parts.append(
            f"Uncertainty penalty {clamped_penalty:.3f} "
            f"({', '.join(uncertainty_sources) if uncertainty_sources else 'path uncertainty'})."
        )
    parts.append(f"Final truth gradient: {truth_gradient:.3f}.")
    if flagged:
        parts.append(
            f"Claim flagged - gradient below threshold ({TRUTH_GRADIENT_FLAG_THRESHOLD})."
        )
    return " ".join(parts)
