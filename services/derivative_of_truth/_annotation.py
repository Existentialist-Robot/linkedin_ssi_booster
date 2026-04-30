"""Knowledge-graph annotation helpers for Derivative of Truth."""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from services.derivative_of_truth._constants import (
    EVIDENCE_TYPE_DERIVED,
    EVIDENCE_TYPE_PATTERN,
    EVIDENCE_TYPE_PRIMARY,
    EVIDENCE_TYPE_SECONDARY,
    REASONING_TYPE_ANALOGY,
    REASONING_TYPE_LOGICAL,
    REASONING_TYPE_PATTERN,
    REASONING_TYPE_STATISTICAL,
)
from services.derivative_of_truth._models import AnnotatedFact, EvidencePath

logger = logging.getLogger(__name__)


def annotate_evidence_and_reasoning(
    fact: dict[str, Any],
    default_evidence_type: str = EVIDENCE_TYPE_SECONDARY,
    default_reasoning_type: str = REASONING_TYPE_LOGICAL,
) -> AnnotatedFact:
    """Derive Derivative of Truth annotations for a knowledge-graph fact dict."""
    fact_id = fact.get("id", "")
    meta: dict[str, Any] = fact.get("metadata", {}) or {}
    source: str = str(meta.get("source", ""))
    confidence_str: str = str(meta.get("confidence", "medium"))
    node_type: str = str(fact.get("type", ""))

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

    _confidence_credibility_map: dict[str, float] = {
        "high": 0.90,
        "medium": 0.60,
        "low": 0.30,
    }
    source_credibility = _confidence_credibility_map.get(confidence_str.lower(), 0.50)

    _evidence_base_uncertainty: dict[str, float] = {
        EVIDENCE_TYPE_PRIMARY: 0.05,
        EVIDENCE_TYPE_SECONDARY: 0.15,
        EVIDENCE_TYPE_DERIVED: 0.30,
        EVIDENCE_TYPE_PATTERN: 0.45,
    }
    uncertainty = _evidence_base_uncertainty.get(evidence_type, 0.20)

    logger.debug(
        "annotate_evidence fact_id=%s ev=%s re=%s cred=%.2f unc=%.2f",
        fact_id,
        evidence_type,
        reasoning_type,
        source_credibility,
        uncertainty,
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
    """Convert knowledge-graph fact dicts into EvidencePath objects."""
    paths: list[EvidencePath] = []
    for fact in kg_facts:
        meta: dict[str, Any] = fact.get("metadata", {}) or {}
        existing_dot: dict[str, Any] = meta.get("dot", {}) or {}

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


def apply_truth_gradient_to_kg_node(
    node_data: dict[str, Any],
    annotation: Optional[AnnotatedFact] = None,
) -> dict[str, Any]:
    """Return an updated metadata dict with Derivative of Truth annotations."""
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
