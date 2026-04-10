"""Avatar Intelligence and Learning Engine — Phase 1A (read-only retrieval).

Provides:
- AvatarState loader with schema validation and safe fallback.
- EvidenceFact model with stable ID assignment.
- Grounding context builder from evidence facts.
- Graph-backed retrieval path integrated into startup flow.

Learning capture (Phase 1B), confidence scoring (Phase 1C),
and narrative continuity (Phase 1D) are added in subsequent epics.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(os.getenv("AVATAR_DATA_DIR", "data/avatar"))
PERSONA_GRAPH_PATH = _DATA_DIR / "persona_graph.json"
NARRATIVE_MEMORY_PATH = _DATA_DIR / "narrative_memory.json"
LEARNING_LOG_PATH = _DATA_DIR / "learning_log.jsonl"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PersonNode:
    name: str
    title: str
    location: str
    links: list[str] = field(default_factory=list)


@dataclass
class ProjectNode:
    id: str
    name: str
    company_id: str
    years: str
    details: str
    skills: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


@dataclass
class CompanyNode:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class SkillNode:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    scope: str = "domain"  # domain | project_specific


@dataclass
class ClaimNode:
    id: str
    text: str
    project_ids: list[str] = field(default_factory=list)
    confidence_hint: str = "medium"


@dataclass
class PersonaGraph:
    schema_version: str
    person: PersonNode
    projects: list[ProjectNode]
    companies: list[CompanyNode]
    skills: list[SkillNode]
    claims: list[ClaimNode]


@dataclass
class NarrativeMemory:
    recent_themes: list[str]
    recent_claims: list[str]
    open_narrative_arcs: list[str]
    last_updated: str | None


@dataclass
class AvatarState:
    persona_graph: PersonaGraph | None
    narrative_memory: NarrativeMemory | None
    is_loaded: bool
    load_errors: list[str] = field(default_factory=list)


@dataclass
class EvidenceFact:
    """A normalized fact from the persona graph with a stable evidence ID."""

    evidence_id: str
    project: str
    company: str
    years: str
    details: str
    skills: list[str]
    source_project_id: str


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------


def _validate_persona_graph(data: dict[str, Any]) -> list[str]:
    """Return a list of validation errors; empty list means valid."""
    errors: list[str] = []
    if not isinstance(data.get("schemaVersion"), str):
        errors.append("missing or invalid 'schemaVersion'")
    if not isinstance(data.get("person"), dict):
        errors.append("missing or invalid 'person'")
    for key in ("projects", "companies", "skills", "claims"):
        if not isinstance(data.get(key), list):
            errors.append(f"missing or invalid '{key}' (must be a list)")
    return errors


def _validate_narrative_memory(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("recentThemes", "recentClaims", "openNarrativeArcs"):
        if not isinstance(data.get(key), list):
            errors.append(f"missing or invalid '{key}' (must be a list)")
    return errors


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_persona_graph(path: Path) -> tuple[PersonaGraph | None, list[str]]:
    if not path.exists():
        return None, [f"persona_graph not found at {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"persona_graph JSON parse error: {exc}"]

    errors = _validate_persona_graph(data)
    if errors:
        return None, [f"persona_graph schema error: {e}" for e in errors]

    raw_person = data.get("person", {})
    person = PersonNode(
        name=raw_person.get("name", ""),
        title=raw_person.get("title", ""),
        location=raw_person.get("location", ""),
        links=raw_person.get("links", []),
    )

    projects = [
        ProjectNode(
            id=p.get("id", ""),
            name=p.get("name", ""),
            company_id=p.get("companyId", ""),
            years=p.get("years", ""),
            details=p.get("details", ""),
            skills=p.get("skills", []),
            aliases=p.get("aliases", []),
        )
        for p in data.get("projects", [])
    ]

    companies = [
        CompanyNode(
            id=c.get("id", ""),
            name=c.get("name", ""),
            aliases=c.get("aliases", []),
        )
        for c in data.get("companies", [])
    ]

    skills = [
        SkillNode(
            id=s.get("id", ""),
            name=s.get("name", ""),
            aliases=s.get("aliases", []),
            scope=s.get("scope", "domain"),
        )
        for s in data.get("skills", [])
    ]

    claims = [
        ClaimNode(
            id=cl.get("id", ""),
            text=cl.get("text", ""),
            project_ids=cl.get("projectIds", []),
            confidence_hint=cl.get("confidenceHint", "medium"),
        )
        for cl in data.get("claims", [])
    ]

    graph = PersonaGraph(
        schema_version=data["schemaVersion"],
        person=person,
        projects=projects,
        companies=companies,
        skills=skills,
        claims=claims,
    )
    return graph, []


def _load_narrative_memory(path: Path) -> tuple[NarrativeMemory | None, list[str]]:
    if not path.exists():
        return None, [f"narrative_memory not found at {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"narrative_memory JSON parse error: {exc}"]

    errors = _validate_narrative_memory(data)
    if errors:
        return None, [f"narrative_memory schema error: {e}" for e in errors]

    memory = NarrativeMemory(
        recent_themes=data.get("recentThemes", []),
        recent_claims=data.get("recentClaims", []),
        open_narrative_arcs=data.get("openNarrativeArcs", []),
        last_updated=data.get("lastUpdated"),
    )
    return memory, []


def load_avatar_state() -> AvatarState:
    """Load persona graph and narrative memory from disk.

    Returns a fully-populated AvatarState with is_loaded=True when both
    files parse successfully.  On any error, logs a warning, sets
    is_loaded=False, and records the errors in load_errors — the caller
    continues with the existing pre-graph flow.
    """
    all_errors: list[str] = []

    graph, graph_errors = _load_persona_graph(PERSONA_GRAPH_PATH)
    all_errors.extend(graph_errors)

    memory, memory_errors = _load_narrative_memory(NARRATIVE_MEMORY_PATH)
    all_errors.extend(memory_errors)

    if all_errors:
        for err in all_errors:
            logger.warning("Avatar state load: %s", err)

    is_loaded = graph is not None and memory is not None
    return AvatarState(
        persona_graph=graph,
        narrative_memory=memory,
        is_loaded=is_loaded,
        load_errors=all_errors,
    )


# ---------------------------------------------------------------------------
# Evidence fact normalization and ID assignment (T1.7)
# ---------------------------------------------------------------------------


def _make_evidence_id(project_id: str, run_index: int) -> str:
    """Return a stable, short evidence ID based on project ID and run index.

    IDs are stable per run for the same input order:
    E{index:03d}-{6-char project hash}
    """
    project_hash = hashlib.sha256(project_id.encode()).hexdigest()[:6]
    return f"E{run_index:03d}-{project_hash}"


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


# ---------------------------------------------------------------------------
# Evidence retrieval (T1.8) — graph-backed
# ---------------------------------------------------------------------------


def retrieve_evidence(
    query: str,
    facts: list[EvidenceFact],
    limit: int = 5,
) -> list[EvidenceFact]:
    """Score and retrieve the most relevant evidence facts for a query.

    Scoring:
    - +10 per skill keyword matched in query
    - +5 for project name/alias match in query
    - +3 per query word found in details
    - +2 extra for richer detail text

    Returns up to *limit* facts; falls back to all facts when nothing scores.
    """
    if not facts:
        return []

    q_lower = query.lower()
    q_words = set(q_lower.split())

    scored: list[tuple[int, EvidenceFact]] = []
    for fact in facts:
        score = 0
        proj_lower = fact.project.lower()

        if proj_lower in q_lower or any(w in proj_lower for w in q_words):
            score += 5

        for skill in fact.skills:
            if skill.lower() in q_lower:
                score += 10

        detail_words = set(fact.details.lower().split())
        overlap = q_words & detail_words
        score += len(overlap) * 3

        score += min(len(fact.details) // 100, 2)

        scored.append((score, fact))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [f for s, f in scored if s > 0][:limit]
    if top:
        return top
    return [f for _, f in scored[:limit]]


# ---------------------------------------------------------------------------
# Grounding context builder (T1.8)
# ---------------------------------------------------------------------------


def build_grounding_context(evidence_facts: list[EvidenceFact]) -> str:
    """Build a prompt-ready grounding block from evidence facts.

    Includes evidence IDs to support --avatar-explain (Phase 1B).
    Returns an empty string when the fact list is empty.
    """
    if not evidence_facts:
        return ""

    lines = [
        "Your background — weave these in naturally when they genuinely connect to the topic:"
    ]
    for fact in evidence_facts:
        line = (
            f"- [{fact.evidence_id}] Project: {fact.project}"
            f" | Company: {fact.company}"
            f" | Years: {fact.years}"
            f" | Detail: {fact.details}"
        )
        if fact.skills:
            line += f" | Skills: {', '.join(fact.skills)}"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Startup integration helper (T1.9)
# ---------------------------------------------------------------------------


def get_grounding_context_for_query(
    query: str,
    state: AvatarState | None = None,
    limit: int = 5,
) -> str:
    """Retrieve and format grounding context for a generation query.

    When *state* is None or not loaded, returns an empty string so the
    caller can fall back to the existing PROFILE_CONTEXT-based flow.

    This is the primary integration point for ollama_service / content_curator
    to request graph-backed grounding.
    """
    if state is None or not state.is_loaded:
        return ""

    facts = normalize_evidence_facts(state)
    if not facts:
        return ""

    relevant = retrieve_evidence(query, facts, limit=limit)
    return build_grounding_context(relevant)
