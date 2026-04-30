"""Derivative of Truth — Truth Gradient Scoring Subsystem.

Implements the Derivative of Truth framework for AI truthfulness:
  - Evidence & Reasoning Annotation (evidence_type, reasoning_type, source_credibility, uncertainty)
  - Truth Gradient Scoring (score_claim_with_truth_gradient)
  - Uncertainty Tracking & Penalty
  - Report generation (report_truth_gradient)

This subsystem augments the existing truth gate and hybrid retriever pipeline.
It computes a truth gradient metric for every generated claim/post and provides
explainability via evidence paths and uncertainty breakdown.

Integration points:
  - knowledge_graph.KnowledgeGraphManager  (annotated facts)
  - hybrid_retriever.HybridRetriever       (reranking and filtering)
  - console_grounding.truth_gate_result    (truth gate metadata)
  - content_curator / main CLI             (reporting)

Algorithm (per claim):
  1. Gather all evidence paths (evidence_type, reasoning_type, credibility, uncertainty)
  2. Compute weighted evidence strength:
       evidence_weight(type) × reasoning_weight(type) × credibility
  3. Apply uncertainty penalty:
       conflicts, long inference chains, sparse evidence
  4. Truth gradient = mean(weighted_strengths) × (1 - uncertainty_penalty)
  5. Confidence calibration penalty = max(0, truth_gradient - raw_confidence)

References:
  - docs/features/derivative-of-truth/design.md
  - docs/features/derivative-of-truth/plan.md
  - "The Derivative of Truth: A New Mathematical Framework for AI Truthfulness"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Evidence & Reasoning type constants
# ---------------------------------------------------------------------------

# Evidence type hierarchy — stronger evidence carries higher weight
EVIDENCE_TYPE_PRIMARY = "primary"       # direct first-hand experience/data
EVIDENCE_TYPE_SECONDARY = "secondary"  # peer-reviewed / well-sourced
EVIDENCE_TYPE_DERIVED = "derived"      # inferred from primary/secondary
EVIDENCE_TYPE_PATTERN = "pattern"      # pattern-based / generalisation

EVIDENCE_WEIGHTS: dict[str, float] = {
    EVIDENCE_TYPE_PRIMARY:   1.0,
    EVIDENCE_TYPE_SECONDARY: 0.75,
    EVIDENCE_TYPE_DERIVED:   0.5,
    EVIDENCE_TYPE_PATTERN:   0.25,
}

# Reasoning type hierarchy
REASONING_TYPE_LOGICAL = "logical"         # deductive / formally valid
REASONING_TYPE_STATISTICAL = "statistical" # grounded in data/probability
REASONING_TYPE_ANALOGY = "analogy"         # reasoning by similarity
REASONING_TYPE_PATTERN = "pattern"         # heuristic / recognitional

REASONING_WEIGHTS: dict[str, float] = {
    REASONING_TYPE_LOGICAL:     1.0,
    REASONING_TYPE_STATISTICAL: 0.85,
    REASONING_TYPE_ANALOGY:     0.55,
    REASONING_TYPE_PATTERN:     0.35,
}

# Uncertainty penalty sources
UNCERTAINTY_CONFLICT = "conflict"            # contradictory evidence
UNCERTAINTY_LONG_CHAIN = "long_chain"        # long inference chain (depth > 3)
UNCERTAINTY_SPARSE = "sparse"                # fewer than 2 evidence paths
UNCERTAINTY_LOW_CREDIBILITY = "low_credibility"  # credibility < 0.3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EvidencePath:
    """A single evidence path supporting (or undermining) a claim.

    Attributes
    ----------
    source:
        Human-readable source identifier (e.g. node ID, article URL, persona fact ID).
    evidence_type:
        One of primary, secondary, derived, pattern.
    reasoning_type:
        One of logical, statistical, analogy, pattern.
    credibility:
        Numeric weight ∈ [0, 1] representing source credibility
        (independence × expertise × historical accuracy).
    uncertainty:
        Numeric penalty ∈ [0, 1] for this path's uncertainty contribution.
    chain_length:
        Number of inference steps to derive this evidence (1 = direct).
    conflicts_with:
        List of other source IDs that contradict this path.
    """

    source: str
    evidence_type: str = EVIDENCE_TYPE_SECONDARY
    reasoning_type: str = REASONING_TYPE_LOGICAL
    credibility: float = 0.5
    uncertainty: float = 0.0
    chain_length: int = 1
    conflicts_with: list[str] = field(default_factory=list)
    overlap: float = 0.0
    """Token overlap ∈ [0,1] between the generated claim text and this evidence
    source's content.  0.0 means 'not computed' (e.g. KG-built paths).
    When > 0 it is included in the base_gradient formula as a direct measure
    of how much the LLM output is actually supported by the evidence text.
    """

    def __post_init__(self) -> None:
        # Clamp to valid ranges
        self.credibility = max(0.0, min(1.0, self.credibility))
        self.uncertainty = max(0.0, min(1.0, self.uncertainty))
        self.chain_length = max(1, self.chain_length)
        self.overlap = max(0.0, min(1.0, self.overlap))


@dataclass
class TruthGradientResult:
    """Output of truth gradient scoring for a single claim.

    Attributes
    ----------
    truth_gradient:
        Composite score ∈ [0, 1] — higher is more trustworthy.
    uncertainty:
        Aggregate uncertainty penalty ∈ [0, 1] applied to the gradient.
    confidence_penalty:
        How much the gradient penalises overconfidence relative to raw BM25 confidence.
    evidence_paths:
        All evidence paths used in the computation.
    uncertainty_sources:
        List of uncertainty reason codes (e.g. 'sparse', 'conflict').
    flagged:
        True when truth_gradient < TRUTH_GRADIENT_FLAG_THRESHOLD.
    explanation:
        Human-readable explanation of the score components.
    """

    truth_gradient: float
    uncertainty: float
    confidence_penalty: float
    evidence_paths: list[EvidencePath] = field(default_factory=list)
    uncertainty_sources: list[str] = field(default_factory=list)
    flagged: bool = False
    explanation: str = ""


@dataclass
class AnnotatedFact:
    """A knowledge-graph fact annotated with Derivative of Truth metadata.

    These annotations are stored in the ``metadata`` dict of each KG node
    under the key ``"dot"`` (Derivative of Truth).

    Attributes
    ----------
    fact_id:
        The knowledge graph node ID for this fact.
    evidence_type:
        Classification of the evidence quality.
    reasoning_type:
        Classification of the reasoning path.
    source_credibility:
        Numeric credibility weight ∈ [0, 1].
    uncertainty:
        Base uncertainty penalty for this fact ∈ [0, 1].
    """

    fact_id: str
    evidence_type: str = EVIDENCE_TYPE_SECONDARY
    reasoning_type: str = REASONING_TYPE_LOGICAL
    source_credibility: float = 0.5
    uncertainty: float = 0.0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Claims with truth_gradient below this threshold are flagged as weak
TRUTH_GRADIENT_FLAG_THRESHOLD: float = 0.35

# Weights for the composite truth gradient formula.
# When claim-evidence token overlap is available (overlap > 0), the 4-term
# formula is used and weights are rebalanced to give 25% to overlap —
# making the score a direct measure of LLM output support by evidence.
_W_EVIDENCE = 0.40       # fallback (no overlap)
_W_REASONING = 0.35      # fallback (no overlap)
_W_CREDIBILITY = 0.25    # fallback (no overlap)
# With overlap: 0.30*ev + 0.25*reasoning + 0.20*cred + 0.25*overlap
_W_EVIDENCE_OL = 0.30
_W_REASONING_OL = 0.25
_W_CREDIBILITY_OL = 0.20
_W_OVERLAP = 0.25

# Uncertainty penalty caps
_MAX_UNCERTAINTY_PENALTY = 0.5   # never discount gradient more than 50%
_CONFLICT_PENALTY = 0.20
_LONG_CHAIN_PENALTY = 0.10       # per extra hop beyond depth 3
_SPARSE_PENALTY = 0.15           # fewer than 2 paths
_LOW_CRED_PENALTY = 0.10


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def score_claim_with_truth_gradient(
    claim: str,
    evidence_paths: list[EvidencePath],
    raw_confidence: float = 0.5,
) -> TruthGradientResult:
    """Compute the truth gradient score for *claim* given its *evidence_paths*.

    Parameters
    ----------
    claim:
        The text of the claim / sentence being evaluated.
    evidence_paths:
        All evidence paths supporting (or contradicting) the claim.
    raw_confidence:
        The raw BM25/hybrid confidence ∈ [0, 1] from the upstream retriever,
        used to compute the confidence calibration penalty.

    Returns
    -------
    TruthGradientResult
        Full scoring result including truth_gradient, uncertainty, penalty,
        uncertainty_sources, flagged flag, and explanation.

    Algorithm
    ---------
    1. For each evidence path compute a weighted path score:
         path_score = (W_evidence × evidence_weight(type)
                       + W_reasoning × reasoning_weight(type)
                       + W_credibility × credibility)
    2. Aggregate: base_gradient = mean(path_scores) or 0 when no paths
    3. Compute uncertainty penalty from:
         - conflicts between paths
         - long inference chains (chain_length > 3)
         - sparse evidence (< 2 paths)
         - low credibility paths (credibility < 0.3)
    4. truth_gradient = base_gradient × (1 - min(total_penalty, MAX_PENALTY))
    5. confidence_penalty = max(0, raw_confidence - truth_gradient)
    6. flagged = truth_gradient < FLAG_THRESHOLD
    """
    if not evidence_paths:
        # No evidence: return near-zero gradient
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

    # ------------------------------------------------------------------
    # 1. Compute per-path weighted scores
    # ------------------------------------------------------------------
    path_scores: list[float] = []
    for path in evidence_paths:
        ev_weight = EVIDENCE_WEIGHTS.get(path.evidence_type, 0.25)
        re_weight = REASONING_WEIGHTS.get(path.reasoning_type, 0.35)
        if path.overlap > 0.0:
            # 4-term formula: includes direct claim-evidence token alignment
            path_score = (
                _W_EVIDENCE_OL * ev_weight
                + _W_REASONING_OL * re_weight
                + _W_CREDIBILITY_OL * path.credibility
                + _W_OVERLAP * path.overlap
            )
        else:
            # 3-term fallback: overlap not computed (e.g. KG-built paths)
            path_score = (
                _W_EVIDENCE * ev_weight
                + _W_REASONING * re_weight
                + _W_CREDIBILITY * path.credibility
            )
        path_scores.append(path_score)

    base_gradient = sum(path_scores) / len(path_scores)

    # ------------------------------------------------------------------
    # 2. Compute uncertainty penalty
    # ------------------------------------------------------------------
    total_penalty = 0.0
    uncertainty_sources: list[str] = []

    # Carry per-path uncertainty forward
    avg_path_uncertainty = sum(p.uncertainty for p in evidence_paths) / len(evidence_paths)
    if avg_path_uncertainty > 0.0:
        total_penalty += avg_path_uncertainty

    # Conflict detection: any path that conflicts with another source
    all_sources = {p.source for p in evidence_paths}
    has_conflicts = any(
        len(set(p.conflicts_with) & all_sources) > 0
        for p in evidence_paths
    )
    if has_conflicts:
        total_penalty += _CONFLICT_PENALTY
        uncertainty_sources.append(UNCERTAINTY_CONFLICT)

    # Long chain penalty
    max_chain = max(p.chain_length for p in evidence_paths)
    if max_chain > 3:
        extra_hops = max_chain - 3
        chain_penalty = _LONG_CHAIN_PENALTY * extra_hops
        total_penalty += chain_penalty
        uncertainty_sources.append(UNCERTAINTY_LONG_CHAIN)

    # Sparse evidence
    if len(evidence_paths) < 2:
        total_penalty += _SPARSE_PENALTY
        uncertainty_sources.append(UNCERTAINTY_SPARSE)

    # Low credibility sources
    low_cred_count = sum(1 for p in evidence_paths if p.credibility < 0.3)
    if low_cred_count > 0:
        total_penalty += _LOW_CRED_PENALTY * (low_cred_count / len(evidence_paths))
        uncertainty_sources.append(UNCERTAINTY_LOW_CREDIBILITY)

    # Cap penalty
    clamped_penalty = min(total_penalty, _MAX_UNCERTAINTY_PENALTY)

    # ------------------------------------------------------------------
    # 3. Final truth gradient
    # ------------------------------------------------------------------
    truth_gradient = base_gradient * (1.0 - clamped_penalty)
    truth_gradient = max(0.0, min(1.0, truth_gradient))

    # ------------------------------------------------------------------
    # 4. Confidence calibration penalty
    # ------------------------------------------------------------------
    confidence_penalty = max(0.0, raw_confidence - truth_gradient)

    # ------------------------------------------------------------------
    # 5. Flagging
    # ------------------------------------------------------------------
    flagged = truth_gradient < TRUTH_GRADIENT_FLAG_THRESHOLD

    # ------------------------------------------------------------------
    # 6. Human-readable explanation
    # ------------------------------------------------------------------
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


def annotate_evidence_and_reasoning(
    fact: dict[str, Any],
    default_evidence_type: str = EVIDENCE_TYPE_SECONDARY,
    default_reasoning_type: str = REASONING_TYPE_LOGICAL,
) -> AnnotatedFact:
    """Derive Derivative of Truth annotations for a knowledge-graph fact dict.

    Inspects available metadata to infer the most appropriate evidence type,
    reasoning type, and source credibility.  Falls back to safe defaults when
    fields are absent.

    Parameters
    ----------
    fact:
        A knowledge-graph node dict (as returned by KnowledgeGraphManager.query()).
        Expected keys: ``id``, ``type``, ``metadata`` (nested dict with
        ``source``, ``confidence``, ``tags``, etc.).
    default_evidence_type:
        Used when the fact's source cannot be classified.
    default_reasoning_type:
        Used when no reasoning chain is detectable.

    Returns
    -------
    AnnotatedFact
        Ready for storing back into the KG node metadata under ``"dot"``.
    """
    fact_id = fact.get("id", "")
    meta: dict[str, Any] = fact.get("metadata", {}) or {}
    source: str = str(meta.get("source", ""))
    confidence_str: str = str(meta.get("confidence", "medium"))
    node_type: str = str(fact.get("type", ""))

    # --- Evidence type inference ---
    # If source is missing or 'unknown', always use default_evidence_type
    if not source or source == "unknown":
        evidence_type = default_evidence_type
    elif source in ("persona_graph",) or node_type in ("Person", "Project", "Company"):
        evidence_type = EVIDENCE_TYPE_PRIMARY
    elif source in ("domain_knowledge",) or node_type in ("Domain", "Fact"):
        evidence_type = EVIDENCE_TYPE_SECONDARY
    elif source in ("extracted_knowledge",) or node_type == "ExtractedFact":
        evidence_type = EVIDENCE_TYPE_DERIVED
    else:
        evidence_type = default_evidence_type

    # --- Reasoning type inference ---
    tags: list[str] = meta.get("tags", []) or []
    tag_set = {t.lower() for t in tags}
    if any(t in tag_set for t in ("statistics", "benchmark", "performance", "measured", "data")):
        reasoning_type = REASONING_TYPE_STATISTICAL
    elif any(t in tag_set for t in ("pattern", "heuristic", "generalisation", "trend")):
        reasoning_type = REASONING_TYPE_PATTERN
    elif any(t in tag_set for t in ("analogy", "similar", "like", "comparable")):
        reasoning_type = REASONING_TYPE_ANALOGY
    else:
        reasoning_type = default_reasoning_type

    # --- Source credibility mapping ---
    _confidence_credibility_map: dict[str, float] = {
        "high": 0.90,
        "medium": 0.60,
        "low": 0.30,
    }
    source_credibility = _confidence_credibility_map.get(confidence_str.lower(), 0.50)

    # --- Base uncertainty ---
    # Derived/pattern evidence carries higher base uncertainty
    _evidence_base_uncertainty: dict[str, float] = {
        EVIDENCE_TYPE_PRIMARY:   0.05,
        EVIDENCE_TYPE_SECONDARY: 0.15,
        EVIDENCE_TYPE_DERIVED:   0.30,
        EVIDENCE_TYPE_PATTERN:   0.45,
    }
    uncertainty = _evidence_base_uncertainty.get(evidence_type, 0.20)

    logger.debug(
        "annotate_evidence fact_id=%s ev=%s re=%s cred=%.2f unc=%.2f",
        fact_id, evidence_type, reasoning_type, source_credibility, uncertainty,
    )

    return AnnotatedFact(
        fact_id=fact_id,
        evidence_type=evidence_type,
        reasoning_type=reasoning_type,
        source_credibility=source_credibility,
        uncertainty=uncertainty,
    )


def build_evidence_paths_from_kg_facts(
    kg_facts: list[dict[str, Any]],
) -> list[EvidencePath]:
    """Convert knowledge-graph fact dicts into EvidencePath objects.

    Uses ``annotate_evidence_and_reasoning`` to derive annotation fields.
    Pre-existing ``dot`` annotations in fact metadata take precedence over
    freshly derived values.

    Parameters
    ----------
    kg_facts:
        List of KG node dicts (from KnowledgeGraphManager.query() or find_facts()).

    Returns
    -------
    list[EvidencePath]
    """
    paths: list[EvidencePath] = []
    for fact in kg_facts:
        meta: dict[str, Any] = fact.get("metadata", {}) or {}
        existing_dot: dict[str, Any] = meta.get("dot", {}) or {}

        # Use stored annotation if present; otherwise derive it
        if existing_dot:
            ev_type = existing_dot.get("evidence_type", EVIDENCE_TYPE_SECONDARY)
            re_type = existing_dot.get("reasoning_type", REASONING_TYPE_LOGICAL)
            credibility = float(existing_dot.get("source_credibility", 0.5))
            uncertainty = float(existing_dot.get("uncertainty", 0.15))
        else:
            annotation = annotate_evidence_and_reasoning(fact)
            ev_type = annotation.evidence_type
            re_type = annotation.reasoning_type
            credibility = annotation.source_credibility
            uncertainty = annotation.uncertainty

        paths.append(
            EvidencePath(
                source=fact.get("id", "unknown"),
                evidence_type=ev_type,
                reasoning_type=re_type,
                credibility=credibility,
                uncertainty=uncertainty,
            )
        )
    return paths


def report_truth_gradient(
    claim: str,
    result: TruthGradientResult,
    verbose: bool = False,
) -> dict[str, Any]:
    """Produce a structured report dict for a truth gradient result.

    Parameters
    ----------
    claim:
        The claim / sentence that was scored.
    result:
        The TruthGradientResult from score_claim_with_truth_gradient.
    verbose:
        When True, include per-path evidence breakdown.

    Returns
    -------
    dict
        Keys: claim_snippet, truth_gradient, uncertainty, confidence_penalty,
        flagged, uncertainty_sources, explanation, [evidence_paths (verbose)].
    """
    report: dict[str, Any] = {
        "claim_snippet": claim[:120] + ("…" if len(claim) > 120 else ""),
        "truth_gradient": round(result.truth_gradient, 4),
        "uncertainty": round(result.uncertainty, 4),
        "confidence_penalty": round(result.confidence_penalty, 4),
        "flagged": result.flagged,
        "uncertainty_sources": result.uncertainty_sources,
        "explanation": result.explanation,
    }
    if verbose:
        report["evidence_paths"] = [
            {
                "source": p.source,
                "evidence_type": p.evidence_type,
                "reasoning_type": p.reasoning_type,
                "credibility": round(p.credibility, 3),
                "uncertainty": round(p.uncertainty, 3),
                "overlap": round(p.overlap, 3),
                "chain_length": p.chain_length,
                "conflicts_with": p.conflicts_with,
            }
            for p in result.evidence_paths
        ]
    return report


def format_truth_gradient_report(report: dict[str, Any]) -> str:
    """Format a truth gradient report dict as a human-readable CLI string.

    Parameters
    ----------
    report:
        A dict as returned by report_truth_gradient().

    Returns
    -------
    str
        Multi-line formatted output suitable for console display.
    """
    from colorama import Fore, Style  # lazy import — keeps module dependency soft

    tg: float = report["truth_gradient"]
    unc: float = report["uncertainty"]
    cp: float = report["confidence_penalty"]
    flagged: bool = report.get("flagged", False)

    # --- gradient bar (20 chars) ---
    bar_width = 20
    filled = round(tg * bar_width)
    if tg >= 0.70:
        bar_colour = Fore.GREEN
    elif tg >= 0.50:
        bar_colour = Fore.YELLOW
    else:
        bar_colour = Fore.RED
    gradient_bar = (
        str(bar_colour) + "█" * filled
        + str(Fore.WHITE) + "░" * (bar_width - filled)
        + str(Style.RESET_ALL)
    )

    status = (
        f"{Fore.RED}⚠️  FLAGGED{Style.RESET_ALL}"
        if flagged
        else f"{Fore.GREEN}✅ OK{Style.RESET_ALL}"
    )
    divider = f"  {Fore.CYAN}{'─' * 64}{Style.RESET_ALL}"
    C = Fore.CYAN  # label colour shorthand
    R = Style.RESET_ALL

    lines = [
        divider,
        f"  {status}  {gradient_bar}  {Fore.WHITE}{tg:.4f}{R}",
        (
            f"  {C}Uncertainty:{R} {_unc_colour(unc)}{unc:.4f}{R}   "
            f"{C}Confidence Penalty:{R} {cp:.4f}"
        ),
        f"  {C}Claim:{R} {report['claim_snippet']}",
    ]

    if report.get("uncertainty_sources"):
        src_list = ", ".join(
            f"{Fore.YELLOW}{s}{R}" for s in report["uncertainty_sources"]
        )
        lines.append(f"  {C}Uncertainty Sources:{R} {src_list}")

    if report.get("explanation"):
        lines.append(f"  {C}Explanation:{R} {report['explanation']}")

    if "evidence_paths" in report:
        lines.append(f"  {C}Evidence Paths:{R}")
        for ep in report["evidence_paths"]:
            source: str = ep["source"]
            cred: float = ep["credibility"]
            unc_ep: float = ep["uncertainty"]
            chain: int = ep["chain_length"]
            ev_type: str = ep["evidence_type"]
            re_type: str = ep["reasoning_type"]

            if source.startswith("avatar:"):
                icon, src_colour = "👤", Fore.MAGENTA
            elif source.startswith("domain:"):
                icon, src_colour = "📚", Fore.BLUE
            elif source.startswith("extracted_knowledge:"):
                icon, src_colour = "🗂️", Fore.CYAN
            else:
                icon, src_colour = "🔗", Fore.WHITE

            cred_col = Fore.GREEN if cred >= 0.80 else (Fore.YELLOW if cred >= 0.55 else Fore.RED)
            unc_col = Fore.RED if unc_ep >= 0.35 else (Fore.YELLOW if unc_ep >= 0.20 else Fore.GREEN)

            lines.append(
                f"    {icon} {src_colour}{source}{R}  "
                f"[{ev_type} / {re_type}]  "
                f"cred={cred_col}{cred:.2f}{R}  "
                f"unc={unc_col}{unc_ep:.2f}{R}  "
                f"chain={chain}"
            )
            lines.append(_explain_evidence_path_line(ep))

    lines.append(divider)

    # --- Footer: what this report means ---
    DIM = str(Style.DIM)
    evidence_paths = report.get("evidence_paths", []) if isinstance(report, dict) else []
    overlaps = [float(ep.get("overlap", 0.0)) for ep in evidence_paths if float(ep.get("overlap", 0.0)) > 0.0]
    avg_overlap = (sum(overlaps) / len(overlaps)) if overlaps else None
    unc_level = "high" if unc >= 0.35 else ("moderate" if unc >= 0.20 else "low")
    support_pct = int(round(tg * 100))

    alignment_note = (
        f"avg claim-evidence alignment {avg_overlap:.2f}"
        if avg_overlap is not None
        else "alignment unavailable (no overlap-bearing paths)"
    )

    # Dynamic support meter (same signal as the bar, expressed in plain text too)
    support_note = f"support {support_pct}/100"

    if flagged:
        footer_note = (
            f"  {DIM}⚠  Weak support ({support_note}): {alignment_note}; uncertainty {unc_level} ({unc:.2f}). "
            f"Review carefully before publishing and tighten claim-to-evidence grounding.{R}"
        )
    elif tg >= 0.70 and (avg_overlap is None or avg_overlap >= 0.45):
        footer_note = (
            f"  {DIM}ℹ  Strong support ({support_note}): {alignment_note}; uncertainty {unc_level} ({unc:.2f}). "
            f"Output is well-backed by the supplied evidence.{R}"
        )
    else:
        footer_note = (
            f"  {DIM}ℹ  Moderate support ({support_note}): {alignment_note}; uncertainty {unc_level} ({unc:.2f}). "
            f"Improve by making claims more explicit and evidence-linked.{R}"
        )
    lines.append(footer_note)
    lines.append(divider)
    return "\n".join(lines)


def _unc_colour(value: float) -> str:
    """Return a colorama colour code based on uncertainty magnitude."""
    from colorama import Fore
    if value >= 0.35:
        return str(Fore.RED)
    if value >= 0.20:
        return str(Fore.YELLOW)
    return str(Fore.GREEN)


def apply_truth_gradient_to_kg_node(
    node_data: dict[str, Any],
    annotation: Optional[AnnotatedFact] = None,
) -> dict[str, Any]:
    """Return an updated metadata dict with Derivative of Truth annotations.

    Adds or replaces the ``"dot"`` key in the node's ``metadata`` dict with
    the annotation fields.  Does not mutate the input dict — returns a copy.

    Parameters
    ----------
    node_data:
        KG node dict (from add_node / query).
    annotation:
        Pre-computed AnnotatedFact; derived fresh if None.

    Returns
    -------
    dict
        Updated node_data with ``metadata["dot"]`` populated.
    """
    import copy
    updated = copy.deepcopy(node_data)
    meta: dict[str, Any] = updated.setdefault("metadata", {})

    if annotation is None:
        annotation = annotate_evidence_and_reasoning(node_data)

    meta["dot"] = {
        "evidence_type": annotation.evidence_type,
        "reasoning_type": annotation.reasoning_type,
        "source_credibility": annotation.source_credibility,
        "uncertainty": annotation.uncertainty,
    }
    return updated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _explain_evidence_path_line(ep: dict[str, Any]) -> str:
    """Generate a one-sentence explanation for a single evidence path entry."""
    source: str = ep.get("source", "")
    ev_type: str = ep.get("evidence_type", "")
    re_type: str = ep.get("reasoning_type", "")
    cred: float = ep.get("credibility", 0.5)
    unc: float = ep.get("uncertainty", 0.2)
    chain: int = ep.get("chain_length", 1)

    if source.startswith("avatar:"):
        node = source.split(":", 1)[1]
        source_desc = f"first-hand persona fact from your avatar graph ('{node}')"
    elif source.startswith("domain:"):
        node = source.split(":", 1)[1]
        source_desc = f"domain knowledge fact ('{node}')"
    else:
        source_desc = f"knowledge source ('{source}')"

    ev_desc = {
        "primary":   "Direct",
        "secondary": "Corroborating",
        "derived":   "Inferred",
        "pattern":   "Pattern-based",
    }.get(ev_type, "Evidence from")

    re_desc = {
        "logical":     "logically reasoned",
        "statistical": "statistically supported",
        "analogy":     "reasoned by analogy",
        "pattern":     "pattern-matched",
    }.get(re_type, "reasoned")

    if cred >= 0.80:
        cred_qual = "high credibility"
    elif cred >= 0.60:
        cred_qual = "moderate-high credibility"
    elif cred >= 0.40:
        cred_qual = "moderate credibility"
    else:
        cred_qual = "lower credibility"

    if unc >= 0.35:
        unc_qual = "high uncertainty — treat with caution"
    elif unc >= 0.20:
        unc_qual = "moderate uncertainty from source variability"
    else:
        unc_qual = "low uncertainty"

    chain_note = "" if chain <= 1 else f" ({chain} inference hops to reach this fact)"

    overlap: float = ep.get("overlap", 0.0)
    if overlap >= 0.60:
        overlap_note = f", strong claim alignment ({overlap:.2f})"
    elif overlap >= 0.30:
        overlap_note = f", moderate claim alignment ({overlap:.2f})"
    elif overlap > 0.0:
        overlap_note = f", weak claim alignment ({overlap:.2f}) — output may diverge from evidence"
    else:
        overlap_note = ""

    return (
        f"      → {ev_desc} {source_desc}{chain_note}, {re_desc}. "
        f"{cred_qual.capitalize()} ({cred:.2f}), {unc_qual} ({unc:.2f}){overlap_note}."
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
            f"Claim flagged — gradient below threshold ({TRUTH_GRADIENT_FLAG_THRESHOLD})."
        )
    return " ".join(parts)
