"""Data models for console grounding."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectFact:
    project: str
    company: str
    years: str
    details: str
    source: str
    tags: set[str]


@dataclass
class TruthGateMeta:
    """Metadata about what truth_gate evaluated — used for confidence scoring (Phase 1C).

    Extended with Derivative of Truth (DoT) fields:
    - truth_gradient: composite truth gradient score ∈ [0, 1] for the full post
    - dot_uncertainty: aggregate uncertainty penalty from DoT scoring
    - dot_flagged: True if truth_gradient is below the flag threshold
    - dot_uncertainty_sources: list of uncertainty reason codes
    - dot_per_sentence_scores: DoT gradient per kept/checked sentence (Part B)
    - spacy_sim_scores: spaCy similarity scores per sentence (Part C)
    """

    removed_count: int
    total_sentences: int
    reason_codes: list[str] = field(default_factory=list)
    truth_gradient: float = 1.0
    dot_uncertainty: float = 0.0
    dot_flagged: bool = False
    dot_uncertainty_sources: list[str] = field(default_factory=list)
    dot_per_sentence_scores: list[float] = field(default_factory=list)
    spacy_sim_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class QueryConstraints:
    require_projects: bool
    require_companies: bool
    require_domain_knowledge: bool
    tech_tags: set[str]

    @property
    def requires_grounding(self) -> bool:
        return (
            self.require_projects
            or self.require_companies
            or self.require_domain_knowledge
            or bool(self.tech_tags)
        )
