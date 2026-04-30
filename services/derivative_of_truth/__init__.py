"""Derivative of Truth - Truth Gradient Scoring Subsystem.

Implements the Derivative of Truth framework for AI truthfulness:
  - Evidence and reasoning annotation
  - Truth gradient scoring
  - Uncertainty tracking and penalty
  - Report generation

Public API is kept compatible with the prior single-file module.
"""

from __future__ import annotations

from services.derivative_of_truth._constants import (
    EVIDENCE_TYPE_DERIVED,
    EVIDENCE_TYPE_PATTERN,
    EVIDENCE_TYPE_PRIMARY,
    EVIDENCE_TYPE_SECONDARY,
    EVIDENCE_WEIGHTS,
    REASONING_TYPE_ANALOGY,
    REASONING_TYPE_LOGICAL,
    REASONING_TYPE_PATTERN,
    REASONING_TYPE_STATISTICAL,
    REASONING_WEIGHTS,
    TRUTH_GRADIENT_FLAG_THRESHOLD,
    UNCERTAINTY_CONFLICT,
    UNCERTAINTY_LONG_CHAIN,
    UNCERTAINTY_LOW_CREDIBILITY,
    UNCERTAINTY_SPARSE,
)
from services.derivative_of_truth._models import (
    AnnotatedFact,
    EvidencePath,
    TruthGradientResult,
)
from services.derivative_of_truth._annotation import (
    annotate_evidence_and_reasoning,
    apply_truth_gradient_to_kg_node,
    build_evidence_paths_from_kg_facts,
)
from services.derivative_of_truth._reporting import (
    format_truth_gradient_report,
    report_truth_gradient,
)
from services.derivative_of_truth._scoring import (
    score_claim_with_truth_gradient,
)

__all__ = [
    "EVIDENCE_TYPE_DERIVED",
    "EVIDENCE_TYPE_PATTERN",
    "EVIDENCE_TYPE_PRIMARY",
    "EVIDENCE_TYPE_SECONDARY",
    "EVIDENCE_WEIGHTS",
    "REASONING_TYPE_ANALOGY",
    "REASONING_TYPE_LOGICAL",
    "REASONING_TYPE_PATTERN",
    "REASONING_TYPE_STATISTICAL",
    "REASONING_WEIGHTS",
    "TRUTH_GRADIENT_FLAG_THRESHOLD",
    "UNCERTAINTY_CONFLICT",
    "UNCERTAINTY_LONG_CHAIN",
    "UNCERTAINTY_LOW_CREDIBILITY",
    "UNCERTAINTY_SPARSE",
    "AnnotatedFact",
    "EvidencePath",
    "TruthGradientResult",
    "annotate_evidence_and_reasoning",
    "apply_truth_gradient_to_kg_node",
    "build_evidence_paths_from_kg_facts",
    "format_truth_gradient_report",
    "report_truth_gradient",
    "score_claim_with_truth_gradient",
]
