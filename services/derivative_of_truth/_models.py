"""Dataclasses for the Derivative of Truth subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

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
    # PLN-enhanced fields (Phase 1)
    pln_strength: Optional[float] = None  # PLN strength [0,1]
    pln_confidence: Optional[float] = None  # PLN confidence [0,1]

    def __post_init__(self) -> None:
        self.credibility = max(0.0, min(1.0, self.credibility))
        self.uncertainty = max(0.0, min(1.0, self.uncertainty))
        self.chain_length = max(1, self.chain_length)
        self.overlap = max(0.0, min(1.0, self.overlap))
        if self.pln_strength is not None:
            self.pln_strength = max(0.0, min(1.0, self.pln_strength))
        if self.pln_confidence is not None:
            self.pln_confidence = max(0.0, min(1.0, self.pln_confidence))


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
    # Phase 2: Truth trajectory tracking
    truth_derivative: Optional[float] = None  # dT/dt - rate of change toward truth
    pln_mode: bool = False  # Whether PLN-enhanced scoring was used


@dataclass
class AnnotatedFact:
    """A knowledge-graph fact annotated with Derivative of Truth metadata."""

    fact_id: str
    evidence_type: str = EVIDENCE_TYPE_SECONDARY
    reasoning_type: str = REASONING_TYPE_LOGICAL
    source_credibility: float = 0.5
    uncertainty: float = 0.0


@dataclass
class TruthTrajectoryPoint:
    """A single point in the truth trajectory of a claim over time."""

    timestamp: datetime
    truth_gradient: float
    uncertainty: float
    evidence_count: int
    flagged: bool

    def __post_init__(self) -> None:
        self.truth_gradient = max(0.0, min(1.0, self.truth_gradient))
        self.uncertainty = max(0.0, min(1.0, self.uncertainty))
        self.evidence_count = max(0, self.evidence_count)


@dataclass
class TruthTrajectory:
    """Historical truth trajectory for a claim, tracking how truth gradient evolves.
    
    This implements Phase 2: tracking dT/dt (derivative of truth) over time
    as new evidence arrives, enabling optimization for movement toward reliable knowledge.
    """

    claim_hash: str  # Hash of the claim text for indexing
    claim_text: str
    history: list[TruthTrajectoryPoint] = field(default_factory=list)

    def add_point(
        self,
        truth_gradient: float,
        uncertainty: float,
        evidence_count: int,
        flagged: bool,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Add a new trajectory point with current timestamp."""
        point = TruthTrajectoryPoint(
            timestamp=timestamp or datetime.now(),
            truth_gradient=truth_gradient,
            uncertainty=uncertainty,
            evidence_count=evidence_count,
            flagged=flagged,
        )
        self.history.append(point)

    def compute_derivative(self) -> Optional[float]:
        """Compute dT/dt: rate of change of truth gradient.
        
        Returns:
            dT/dt over the most recent time window, or None if insufficient history.
            Positive values indicate movement toward truth, negative away from it.
        """
        if len(self.history) < 2:
            return None

        # Use last two points to compute derivative
        recent = self.history[-1]
        previous = self.history[-2]

        delta_truth = recent.truth_gradient - previous.truth_gradient
        delta_time = (recent.timestamp - previous.timestamp).total_seconds()

        if delta_time <= 0:
            return None

        # dT/dt in units of truth gradient per second
        # Normalize to per-hour for more intuitive values
        return (delta_truth / delta_time) * 3600.0

    def is_converging(self, window_size: int = 3) -> bool:
        """Check if truth gradient is converging (improving over time).
        
        Args:
            window_size: Number of recent points to examine
        
        Returns:
            True if gradient is generally increasing and uncertainty decreasing
        """
        if len(self.history) < window_size:
            return False

        window = self.history[-window_size:]
        
        # Check if truth gradient is trending upward
        gradients = [p.truth_gradient for p in window]
        gradient_improving = gradients[-1] > gradients[0]
        
        # Check if uncertainty is trending downward
        uncertainties = [p.uncertainty for p in window]
        uncertainty_decreasing = uncertainties[-1] < uncertainties[0]
        
        return gradient_improving and uncertainty_decreasing

    def current_gradient(self) -> Optional[float]:
        """Get the most recent truth gradient value."""
        return self.history[-1].truth_gradient if self.history else None

    def current_derivative(self) -> Optional[float]:
        """Get the most recent dT/dt value."""
        return self.compute_derivative()
