"""PLN (Probabilistic Logic Networks) inference formulas.

This module provides mathematically rigorous inference rules for deduction,
induction, and abduction, replacing DoT's fixed evidence and reasoning weights
with dynamic strength and confidence calculations based on PLN theory.

References:
- Goertzel et al., "Probabilistic Logic Networks" (2008)
- OpenCog Hyperon PLN implementation
"""

from __future__ import annotations

import logging
import math
from typing import NamedTuple

logger = logging.getLogger(__name__)

# PLN parameters
DEFAULT_CONFIDENCE_WEIGHT = 1.0  # k parameter in confidence formula
MIN_CONFIDENCE = 0.01  # Floor to avoid division by zero
MAX_CONFIDENCE = 0.99  # Cap to avoid overconfidence


class PLNTruthValue(NamedTuple):
    """PLN truth value with strength (probability) and confidence (certainty)."""
    strength: float  # Probability estimate [0,1]
    confidence: float  # Weight of evidence (certainty) [0,1]

    def __repr__(self) -> str:
        return f"<s={self.strength:.3f}, c={self.confidence:.3f}>"


def pln_deduction(
    premise_ab: PLNTruthValue,
    premise_bc: PLNTruthValue,
) -> PLNTruthValue:
    """PLN deduction rule: A→B ∧ B→C ⟹ A→C.
    
    Strength formula (simplified):
        s_AC = s_AB × s_BC
    
    Confidence formula (conjunction of independent evidence):
        c_AC = (c_AB × c_BC) / (c_AB + c_BC - c_AB × c_BC)
    
    Args:
        premise_ab: Truth value of A→B
        premise_bc: Truth value of B→C
    
    Returns:
        Truth value of A→C
    """
    strength = premise_ab.strength * premise_bc.strength
    
    # Confidence decreases through multi-hop inference
    # Using conjunction formula for independent sources
    denom = (
        premise_ab.confidence + premise_bc.confidence
        - premise_ab.confidence * premise_bc.confidence
    )
    confidence = (
        (premise_ab.confidence * premise_bc.confidence) / denom
        if denom > 0 else MIN_CONFIDENCE
    )
    confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))
    
    logger.debug(
        "PLN deduction: (%s) ∧ (%s) → %s",
        premise_ab,
        premise_bc,
        PLNTruthValue(strength, confidence),
    )
    
    return PLNTruthValue(strength, confidence)


def pln_induction(
    observations: list[PLNTruthValue],
    total_count: int,
) -> PLNTruthValue:
    """PLN induction rule: generalize from observed instances.
    
    Strength formula (empirical frequency):
        s = (positive_count + k) / (total_count + 2k)
        where k is a small constant (Laplace smoothing)
    
    Confidence formula (weight of evidence):
        c = total_count / (total_count + k)
    
    Args:
        observations: Truth values of observed instances
        total_count: Total number of instances (observed + unobserved)
    
    Returns:
        Generalized truth value
    """
    if not observations or total_count <= 0:
        return PLNTruthValue(0.5, MIN_CONFIDENCE)
    
    # Compute empirical strength (weighted average of observations)
    weighted_strength = sum(
        obs.strength * obs.confidence for obs in observations
    ) / sum(obs.confidence for obs in observations)
    
    # Laplace smoothing
    k = DEFAULT_CONFIDENCE_WEIGHT
    strength = (weighted_strength * len(observations) + k) / (total_count + 2 * k)
    
    # Confidence grows with sample size
    confidence = total_count / (total_count + k)
    confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))
    
    logger.debug(
        "PLN induction: %d observations, total=%d → <s=%.3f, c=%.3f>",
        len(observations),
        total_count,
        strength,
        confidence,
    )
    
    return PLNTruthValue(strength, confidence)


def pln_abduction(
    observation: PLNTruthValue,
    hypothesis_prior: float = 0.5,
) -> PLNTruthValue:
    """PLN abduction rule: infer hypothesis from observation.
    
    Simplified Bayesian abduction:
        s_H = P(H|E) ∝ P(E|H) × P(H)
        where P(E|H) is the observation strength, P(H) is the prior
    
    Confidence formula:
        c_H = c_E × prior_confidence
    
    Args:
        observation: Truth value of observed evidence
        hypothesis_prior: Prior probability of hypothesis [0,1]
    
    Returns:
        Truth value of inferred hypothesis
    """
    # Simplified Bayes: posterior ∝ likelihood × prior
    # Normalize assuming uniform alternative hypothesis
    posterior = observation.strength * hypothesis_prior
    normalizer = posterior + (1 - observation.strength) * (1 - hypothesis_prior)
    strength = posterior / normalizer if normalizer > 0 else hypothesis_prior
    
    # Confidence in hypothesis depends on observation confidence
    # and strength of prior (represented as confidence in prior)
    prior_confidence = 0.5  # Neutral prior confidence
    confidence = observation.confidence * prior_confidence
    confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))
    
    logger.debug(
        "PLN abduction: observation=%s, prior=%.3f → <s=%.3f, c=%.3f>",
        observation,
        hypothesis_prior,
        strength,
        confidence,
    )
    
    return PLNTruthValue(strength, confidence)


def pln_revision(
    tv1: PLNTruthValue,
    tv2: PLNTruthValue,
) -> PLNTruthValue:
    """PLN revision rule: combine independent evidence for the same claim.
    
    Strength formula (weighted average by confidence):
        s = (s1×c1 + s2×c2) / (c1 + c2)
    
    Confidence formula (independent sources add evidence):
        c = (c1 + c2) / (1 + c1×c2/k)
    
    Args:
        tv1: First truth value
        tv2: Second truth value
    
    Returns:
        Revised truth value combining both sources
    """
    if tv1.confidence + tv2.confidence == 0:
        return PLNTruthValue(0.5, MIN_CONFIDENCE)
    
    # Confidence-weighted strength
    strength = (
        (tv1.strength * tv1.confidence + tv2.strength * tv2.confidence)
        / (tv1.confidence + tv2.confidence)
    )
    
    # Confidence increases with independent evidence
    k = DEFAULT_CONFIDENCE_WEIGHT
    confidence = (tv1.confidence + tv2.confidence) / (1 + tv1.confidence * tv2.confidence / k)
    confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))
    
    logger.debug(
        "PLN revision: (%s) + (%s) → <s=%.3f, c=%.3f>",
        tv1,
        tv2,
        strength,
        confidence,
    )
    
    return PLNTruthValue(strength, confidence)


def compute_evidence_weight(
    evidence_type: str,
    base_strength: float = 1.0,
    source_credibility: float = 1.0,
    chain_length: int = 1,
) -> PLNTruthValue:
    """Compute PLN truth value for evidence based on its type and metadata.
    
    Replaces DoT's fixed EVIDENCE_WEIGHTS with dynamic PLN calculation.
    
    Args:
        evidence_type: One of primary, secondary, derived, pattern
        base_strength: Initial strength estimate [0,1]
        source_credibility: Source credibility [0,1]
        chain_length: Length of inference chain (1 = direct evidence)
    
    Returns:
        PLN truth value for this evidence
    """
    # Base confidence by evidence type
    type_confidence_map = {
        "primary": 0.9,
        "secondary": 0.7,
        "derived": 0.5,
        "pattern": 0.3,
    }
    base_confidence = type_confidence_map.get(evidence_type, 0.5)
    
    # Adjust strength by source credibility
    strength = base_strength * source_credibility
    
    # Confidence degrades with chain length (each hop is a deduction)
    confidence = base_confidence
    for _ in range(chain_length - 1):
        # Simulate deduction confidence degradation
        confidence = confidence * 0.9  # 10% confidence loss per hop
    
    confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))
    
    return PLNTruthValue(strength, confidence)


def compute_reasoning_weight(
    reasoning_type: str,
    premise_confidence: float = 0.8,
) -> PLNTruthValue:
    """Compute PLN truth value for reasoning based on its type.
    
    Replaces DoT's fixed REASONING_WEIGHTS with dynamic PLN calculation.
    
    Args:
        reasoning_type: One of logical, statistical, analogy, pattern
        premise_confidence: Confidence in the premises [0,1]
    
    Returns:
        PLN truth value for this reasoning step
    """
    # Reasoning type affects both strength and confidence
    type_params = {
        "logical": (1.0, 0.95),  # (strength, confidence)
        "statistical": (0.9, 0.8),
        "analogy": (0.7, 0.6),
        "pattern": (0.5, 0.4),
    }
    base_strength, base_confidence = type_params.get(reasoning_type, (0.5, 0.5))
    
    # Confidence in conclusion depends on confidence in premises
    confidence = base_confidence * premise_confidence
    confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))
    
    return PLNTruthValue(base_strength, confidence)


def aggregate_evidence_paths(
    evidence_tvs: list[PLNTruthValue],
) -> PLNTruthValue:
    """Aggregate multiple evidence paths into a single truth value.
    
    Uses PLN revision to combine independent evidence sources.
    
    Args:
        evidence_tvs: List of truth values from different evidence paths
    
    Returns:
        Aggregated truth value
    """
    if not evidence_tvs:
        return PLNTruthValue(0.0, MIN_CONFIDENCE)
    
    if len(evidence_tvs) == 1:
        return evidence_tvs[0]
    
    # Iteratively revise with each new evidence source
    result = evidence_tvs[0]
    for tv in evidence_tvs[1:]:
        result = pln_revision(result, tv)
    
    return result