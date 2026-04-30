"""Dataclasses for the Derivative of Truth subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field

from services.derivative_of_truth._constants import (
    EVIDENCE_TYPE_SECONDARY,
    REASONING_TYPE_LOGICAL,
)


@dataclass
class EvidencePath:
    """A single evidence path supporting (or undermining) a claim."""

    source: str
    evidence_type: str = EVIDENCE_TYPE_SECONDARY
    reasoning_type: str = REASONING_TYPE_LOGICAL
    credibility: float = 0.5
    uncertainty: float = 0.0
    chain_length: int = 1
    conflicts_with: list[str] = field(default_factory=list)
    overlap: float = 0.0

    def __post_init__(self) -> None:
        self.credibility = max(0.0, min(1.0, self.credibility))
        self.uncertainty = max(0.0, min(1.0, self.uncertainty))
        self.chain_length = max(1, self.chain_length)
        self.overlap = max(0.0, min(1.0, self.overlap))


@dataclass
class TruthGradientResult:
    """Output of truth gradient scoring for a single claim."""

    truth_gradient: float
    uncertainty: float
    confidence_penalty: float
    evidence_paths: list[EvidencePath] = field(default_factory=list)
    uncertainty_sources: list[str] = field(default_factory=list)
    flagged: bool = False
    explanation: str = ""


@dataclass
class AnnotatedFact:
    """A knowledge-graph fact annotated with Derivative of Truth metadata."""

    fact_id: str
    evidence_type: str = EVIDENCE_TYPE_SECONDARY
    reasoning_type: str = REASONING_TYPE_LOGICAL
    source_credibility: float = 0.5
    uncertainty: float = 0.0
