"""Evidence fact normalization and ID assignment."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from services.avatar_intelligence._models import (
    AvatarState,
    DomainEvidenceFact,
    EvidenceFact,
    ExtractedEvidenceFact,
)

logger = logging.getLogger(__name__)


def _make_evidence_id(project_id: str, run_index: int) -> str:
    """Return a stable, short evidence ID based on project ID and run index.

    IDs are stable per run for the same input order:
    E{index:03d}-{6-char project hash}
    """
    project_hash = hashlib.sha256(project_id.encode()).hexdigest()[:6]
    return f"E{run_index:03d}-{project_hash}"


def _make_domain_evidence_id(fact_id: str, run_index: int) -> str:
    """Return a stable, short evidence ID based on domain fact ID and run index.

    IDs are stable per run for the same input order:
    D{index:03d}-{6-char fact hash}
    """
    fact_hash = hashlib.sha256(fact_id.encode()).hexdigest()[:6]
    return f"D{run_index:03d}-{fact_hash}"


def normalize_evidence_facts(state: AvatarState) -> list[EvidenceFact]:
    """Convert persona graph projects into EvidenceFacts with stable IDs.

    Returns an empty list when avatar state is not loaded or has no projects.
    """
    if not state.is_loaded or state.persona_graph is None:
        return []

    graph = state.persona_graph
    company_map = {c.id: c.name for c in graph.companies}

    facts: list[EvidenceFact] = []
    for idx, project in enumerate(graph.projects):
        company_name = company_map.get(project.company_id, project.company_id)
        evidence_id = _make_evidence_id(project.id or project.name, idx)
        facts.append(
            EvidenceFact(
                evidence_id=evidence_id,
                project=project.name,
                company=company_name,
                years=project.years,
                details=project.details,
                skills=list(project.skills),
                source_project_id=project.id,
            )
        )
    return facts


def evidence_facts_to_project_facts(facts: list[EvidenceFact]) -> list[Any]:
    """Convert EvidenceFact items to ProjectFact objects for console_grounding functions.

    Uses a lazy import to avoid a circular dependency with console_grounding.
    Returns an empty list when *facts* is empty.
    """
    if not facts:
        return []
    from services.console_grounding import ProjectFact  # lazy — avoids circular import
    return [
        ProjectFact(
            project=f.project,
            company=f.company,
            years=f.years,
            details=f.details,
            source=f"avatar:{f.source_project_id}",
            tags=set(f.skills),
        )
        for f in facts
    ]


def normalize_domain_facts(state: AvatarState) -> list[DomainEvidenceFact]:
    """Convert domain knowledge facts into DomainEvidenceFacts with stable IDs.

    Returns an empty list when avatar state has no domain knowledge or facts.
    """
    if not state.domain_knowledge or not state.domain_knowledge.facts:
        return []

    knowledge = state.domain_knowledge
    domain_map = {d.id: d.name for d in knowledge.domains}

    facts: list[DomainEvidenceFact] = []
    for idx, domain_fact in enumerate(knowledge.facts):
        domain_name = domain_map.get(domain_fact.domain_id, domain_fact.domain_id)
        evidence_id = _make_domain_evidence_id(domain_fact.id, idx)
        facts.append(
            DomainEvidenceFact(
                evidence_id=evidence_id,
                domain=domain_name,
                statement=domain_fact.statement,
                tags=list(domain_fact.tags),
                confidence=domain_fact.confidence,
                source_fact_id=domain_fact.id,
            )
        )
    return facts


def domain_facts_to_project_facts(facts: list[DomainEvidenceFact]) -> list[Any]:
    """Convert DomainEvidenceFact items to ProjectFact objects for console_grounding.

    Domain facts are converted to ProjectFact format with domain name as 'project',
    'Domain Knowledge' as company, and statement as details.

    Uses a lazy import to avoid a circular dependency with console_grounding.
    Returns an empty list when *facts* is empty.
    """
    if not facts:
        return []
    from services.console_grounding import ProjectFact  # lazy — avoids circular import
    return [
        ProjectFact(
            project=f.domain,
            company="Domain Knowledge",
            years="general",
            details=f.statement,
            source=f"domain:{f.source_fact_id}",
            tags=set(f.tags),
        )
        for f in facts
    ]


def normalize_extracted_facts(state: AvatarState) -> list[ExtractedEvidenceFact]:
    """Convert extracted knowledge facts into ExtractedEvidenceFacts with stable IDs.

    Returns an empty list when avatar state has no extracted knowledge or facts.
    """
    if not state.extracted_knowledge or not state.extracted_knowledge.facts:
        return []

    facts: list[ExtractedEvidenceFact] = []
    for idx, ext_fact in enumerate(state.extracted_knowledge.facts):
        fact_hash = hashlib.sha256(ext_fact.id.encode()).hexdigest()[:6]
        evidence_id = f"X{idx:03d}-{fact_hash}"
        facts.append(
            ExtractedEvidenceFact(
                evidence_id=evidence_id,
                statement=ext_fact.statement,
                source_url=ext_fact.source_url,
                source_title=ext_fact.source_title,
                tags=list(ext_fact.tags),
                entities=list(ext_fact.entities),
                confidence=ext_fact.confidence,
                source_fact_id=ext_fact.id,
            )
        )
    return facts
