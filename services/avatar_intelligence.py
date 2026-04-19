"""Avatar Intelligence and Learning Engine — Phase 1A + 1B.

Provides:
- AvatarState loader with schema validation and safe fallback.
- EvidenceFact model with stable ID assignment.
- Grounding context builder from evidence facts.
- Graph-backed retrieval path integrated into startup flow.
- Moderation event model and append-only learning log writer (1B).
- Learning report aggregation and advisory heuristics (1B).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from rank_bm25 import BM25Okapi as _BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BM25_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(os.getenv("AVATAR_DATA_DIR", "data/avatar"))
PERSONA_GRAPH_PATH = _DATA_DIR / "persona_graph.json"
NARRATIVE_MEMORY_PATH = _DATA_DIR / "narrative_memory.json"
DOMAIN_KNOWLEDGE_PATH = _DATA_DIR / "domain_knowledge.json"
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
class DomainNode:
    """A domain area (e.g., 'AI & Machine Learning', 'Software Engineering')."""
    id: str
    name: str
    description: str


@dataclass
class DomainFact:
    """A general domain-level truth not tied to a specific project."""
    id: str
    domain_id: str
    statement: str
    tags: list[str] = field(default_factory=list)
    confidence: str = "medium"
    scope: str = "general"


@dataclass
class DomainRelationship:
    """Relationship between domain facts."""
    id: str
    from_fact_id: str
    to_fact_id: str
    relation_type: str
    description: str = ""


@dataclass
class DomainKnowledge:
    """Domain knowledge graph containing general professional expertise."""
    schema_version: str
    domains: list[DomainNode]
    facts: list[DomainFact]
    relationships: list[DomainRelationship]


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
    domain_knowledge: DomainKnowledge | None
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


@dataclass
class DomainEvidenceFact:
    """A normalized fact from the domain knowledge graph with a stable evidence ID."""

    evidence_id: str
    domain: str
    statement: str
    tags: list[str]
    confidence: str
    source_fact_id: str


@dataclass
class ModerationEvent:
    """One interactive truth-gate decision captured in the learning log.

    Fields:
    - timestamp:     ISO-8601 UTC string.
    - channel:       linkedin | x | bluesky | youtube | all.
    - reason_code:   truth-gate reason string (e.g. unsupported_numeric).
    - decision:      'kept' (user overrode removal) or 'removed'.
    - sentence_hash: SHA-256[:16] of the flagged sentence (privacy-preserving).
    - article_ref:   URL or title of the source article.
    - project_refs:  project IDs or names referenced in the sentence.
    - run_id:        UUID identifying the current tool run.
    """

    timestamp: str
    channel: str
    reason_code: str
    decision: str          # 'kept' | 'removed'
    sentence_hash: str
    article_ref: str
    project_refs: list[str]
    run_id: str


@dataclass
class ExplainOutput:
    """Explain-mode summary of evidence used and confidence for one generation."""

    evidence_ids: list[str]
    evidence_summaries: list[str]   # one human-readable line per fact
    article_ref: str
    channel: str
    ssi_component: str


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


def _validate_domain_knowledge(data: dict[str, Any]) -> list[str]:
    """Return a list of validation errors; empty list means valid."""
    errors: list[str] = []
    if not isinstance(data.get("schemaVersion"), str):
        errors.append("missing or invalid 'schemaVersion'")
    for key in ("domains", "facts", "relationships"):
        if not isinstance(data.get(key), list):
            errors.append(f"missing or invalid '{key}' (must be a list)")
    return errors


def _load_domain_knowledge(path: Path) -> tuple[DomainKnowledge | None, list[str]]:
    """Load domain knowledge graph from disk."""
    if not path.exists():
        return None, [f"domain_knowledge not found at {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"domain_knowledge JSON parse error: {exc}"]

    errors = _validate_domain_knowledge(data)
    if errors:
        return None, [f"domain_knowledge schema error: {e}" for e in errors]

    domains = [
        DomainNode(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
        )
        for d in data.get("domains", [])
    ]

    facts = [
        DomainFact(
            id=f.get("id", ""),
            domain_id=f.get("domainId", ""),
            statement=f.get("statement", ""),
            tags=f.get("tags", []),
            confidence=f.get("confidence", "medium"),
            scope=f.get("scope", "general"),
        )
        for f in data.get("facts", [])
    ]

    relationships = [
        DomainRelationship(
            id=r.get("id", ""),
            from_fact_id=r.get("fromFactId", ""),
            to_fact_id=r.get("toFactId", ""),
            relation_type=r.get("relationType", ""),
            description=r.get("description", ""),
        )
        for r in data.get("relationships", [])
    ]

    knowledge = DomainKnowledge(
        schema_version=data["schemaVersion"],
        domains=domains,
        facts=facts,
        relationships=relationships,
    )
    return knowledge, []


def load_avatar_state() -> AvatarState:
    """Load persona graph, narrative memory, and domain knowledge from disk.

    Returns a fully-populated AvatarState with is_loaded=True when all
    required files parse successfully. Domain knowledge is optional; if missing,
    the system continues without it. On any error, logs a warning, sets
    is_loaded=False, and records the errors in load_errors — the caller
    continues with the existing pre-graph flow.
    """
    all_errors: list[str] = []

    graph, graph_errors = _load_persona_graph(PERSONA_GRAPH_PATH)
    all_errors.extend(graph_errors)

    memory, memory_errors = _load_narrative_memory(NARRATIVE_MEMORY_PATH)
    all_errors.extend(memory_errors)

    # Domain knowledge is optional - log as info if missing, not an error
    knowledge, knowledge_errors = _load_domain_knowledge(DOMAIN_KNOWLEDGE_PATH)
    if knowledge_errors and "not found" not in knowledge_errors[0]:
        # Only treat as error if it's not just missing, but actually malformed
        all_errors.extend(knowledge_errors)
    elif knowledge_errors:
        logger.info("Domain knowledge not found (optional): %s", knowledge_errors[0])

    if all_errors:
        for err in all_errors:
            logger.warning("Avatar state load: %s", err)

    # is_loaded requires persona graph and narrative memory; domain knowledge is optional
    is_loaded = graph is not None and memory is not None
    return AvatarState(
        persona_graph=graph,
        narrative_memory=memory,
        domain_knowledge=knowledge,
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


def _make_domain_evidence_id(fact_id: str, run_index: int) -> str:
    """Return a stable, short evidence ID based on domain fact ID and run index.

    IDs are stable per run for the same input order:
    D{index:03d}-{6-char fact hash}
    """
    fact_hash = hashlib.sha256(fact_id.encode()).hexdigest()[:6]
    return f"D{run_index:03d}-{fact_hash}"


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


# ---------------------------------------------------------------------------
# Evidence retrieval (T1.8) — graph-backed
# ---------------------------------------------------------------------------


def _fact_tokens(fact: EvidenceFact) -> list[str]:
    """Build the BM25 document token list for one evidence fact.

    Concatenates project name, company, years, detail text, and skill names
    so the corpus field reflects everything the fact can match against.
    Skill tokens are repeated three times to weight them above plain detail
    words without hard-coded per-field multipliers.
    """
    base = f"{fact.project} {fact.company} {fact.years} {fact.details}"
    skill_boost = " ".join(fact.skills * 3)  # repeat for IDF weight boost
    return re.findall(r"[a-zA-Z0-9_+#.-]{2,}", (base + " " + skill_boost).lower())


def _domain_fact_tokens(fact: DomainEvidenceFact) -> list[str]:
    """Build the BM25 document token list for one domain fact.

    Concatenates domain name, statement, and tags.
    Tags are repeated three times to weight them above plain statement words.
    """
    base = f"{fact.domain} {fact.statement}"
    tag_boost = " ".join(fact.tags * 3)  # repeat for IDF weight boost
    return re.findall(r"[a-zA-Z0-9_+#.-]{2,}", (base + " " + tag_boost).lower())

def _retrieve_domain_evidence_fallback(
    query: str,
    facts: list[DomainEvidenceFact],
    limit: int,
) -> list[DomainEvidenceFact]:
    """Hand-weighted keyword fallback for domain facts when rank_bm25 is not installed."""
    q_lower = query.lower()
    q_words = set(q_lower.split())

    scored: list[tuple[int, DomainEvidenceFact]] = []
    for fact in facts:
        score = 0
        domain_lower = fact.domain.lower()
        if domain_lower in q_lower or any(w in domain_lower for w in q_words):
            score += 5
        for tag in fact.tags:
            if tag.lower() in q_lower:
                score += 10
        statement = fact.statement
        statement_words = set(statement.lower().split())
        overlap = q_words & statement_words
        score += len(overlap) * 3
        score += min(len(statement) // 100, 2)
        scored.append((score, fact))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [f for s, f in scored if s > 0][:limit]
    if top:
        return top
    return [f for _, f in scored[:limit]]

def retrieve_domain_evidence(
    query: str,
    facts: list[DomainEvidenceFact],
    limit: int = 5,
) -> list[DomainEvidenceFact]:
    """Score and retrieve the most relevant domain evidence facts for a query.

    Uses BM25Okapi (rank_bm25) when available — with domain-specific tokenization.
    Falls back to hand-weighted keyword overlap when rank_bm25 is not installed.
    Returns up to *limit* facts; falls back to all facts when nothing scores.
    """
    if not facts:
        return []

    if _BM25_AVAILABLE:
        return _retrieve_domain_evidence_bm25(query, facts, limit)
    return _retrieve_domain_evidence_fallback(query, facts, limit)


def _retrieve_domain_evidence_bm25(
    query: str,
    facts: list[DomainEvidenceFact],
    limit: int,
) -> list[DomainEvidenceFact]:
    """BM25Okapi-backed retrieval path for domain evidence facts."""
    corpus = [_domain_fact_tokens(f) for f in facts]
    bm25 = _BM25Okapi(corpus)
    q_tokens = re.findall(r"[a-zA-Z0-9_+#.-]{2,}", query.lower())
    scores: list[float] = bm25.get_scores(q_tokens).tolist()

    ranked = sorted(zip(scores, facts), key=lambda x: x[0], reverse=True)
    top = [f for s, f in ranked if s > 0.0][:limit]
    if top:
        return top
    # nothing scored — return top-N by raw order (all facts are equally unknown)
    return [f for _, f in ranked[:limit]]
    """Build the BM25 document token list for one domain fact.

    Concatenates domain name, statement, and tags.
    Tags are repeated three times to weight them above plain statement words.
    """
    base = f"{fact.domain} {fact.statement}"
    tag_boost = " ".join(fact.tags * 3)  # repeat for IDF weight boost
    return re.findall(r"[a-zA-Z0-9_+#.-]{2,}", (base + " " + tag_boost).lower())


def retrieve_evidence(
    query: str,
    facts: list[EvidenceFact],
    limit: int = 5,
) -> list[EvidenceFact]:
    """Score and retrieve the most relevant evidence facts for a query.

    Uses BM25Okapi (rank_bm25) when available — accounts for term-frequency
    saturation and corpus-level IDF so rare skills score higher than common
    words like 'python'.  Falls back to hand-weighted keyword overlap when
    rank_bm25 is not installed.

    Returns up to *limit* facts; falls back to all facts when nothing scores.
    """
    if not facts:
        return []

    if _BM25_AVAILABLE:
        return _retrieve_evidence_bm25(query, facts, limit)
    return _retrieve_evidence_fallback(query, facts, limit)


def _retrieve_evidence_bm25(
    query: str,
    facts: list[EvidenceFact],
    limit: int,
) -> list[EvidenceFact]:
    """BM25Okapi-backed retrieval path."""
    corpus = [_fact_tokens(f) for f in facts]
    bm25 = _BM25Okapi(corpus)
    q_tokens = re.findall(r"[a-zA-Z0-9_+#.-]{2,}", query.lower())
    scores: list[float] = bm25.get_scores(q_tokens).tolist()

    ranked = sorted(zip(scores, facts), key=lambda x: x[0], reverse=True)
    top = [f for s, f in ranked if s > 0.0][:limit]
    if top:
        return top
    # nothing scored — return top-N by raw order (all facts are equally unknown)
    return [f for _, f in ranked[:limit]]


def _retrieve_evidence_fallback(
    query: str,
    facts: list[EvidenceFact],
    limit: int,
) -> list[EvidenceFact]:
    """Hand-weighted keyword fallback used when rank_bm25 is not installed."""
    q_lower = query.lower()
    q_words = set(q_lower.split())


    scored: list[tuple[int, Any]] = []
    for fact in facts:
        score = 0
        # EvidenceFact: project, skills, details
        # DomainEvidenceFact: domain, tags, statement
        if hasattr(fact, "project") and hasattr(fact, "skills") and hasattr(fact, "details"):
            proj_lower = getattr(fact, "project", "").lower()
            if proj_lower in q_lower or any(w in proj_lower for w in q_words):
                score += 5
            for skill in getattr(fact, "skills", []):
                if skill.lower() in q_lower:
                    score += 10
            detail = getattr(fact, "details", "")
            detail_words = set(detail.lower().split())
            overlap = q_words & detail_words
            score += len(overlap) * 3
            score += min(len(detail) // 100, 2)
        elif hasattr(fact, "domain") and hasattr(fact, "tags") and hasattr(fact, "statement"):
            domain_lower = getattr(fact, "domain", "").lower()
            if domain_lower in q_lower or any(w in domain_lower for w in q_words):
                score += 5
            for tag in getattr(fact, "tags", []):
                if tag.lower() in q_lower:
                    score += 10
            statement = getattr(fact, "statement", "")
            statement_words = set(statement.lower().split())
            overlap = q_words & statement_words
            score += len(overlap) * 3
            score += min(len(statement) // 100, 2)
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
    include_domain_facts: bool = True,
) -> str:
    """Retrieve and format grounding context for a generation query.

    When *state* is None or not loaded, returns an empty string so the
    caller can fall back to the existing PROFILE_CONTEXT-based flow.

    When *include_domain_facts* is True (default), domain knowledge facts
    are included in the retrieval corpus alongside project facts.

    This is the primary integration point for ollama_service / content_curator
    to request graph-backed grounding.
    """
    if state is None or not state.is_loaded:
        return ""

    facts = normalize_evidence_facts(state)
    domain_facts = normalize_domain_facts(state) if include_domain_facts else []
    
    if not facts and not domain_facts:
        return ""

    # Combine both types of facts for retrieval
    # We'll use a unified approach by converting domain facts to EvidenceFact-like structure
    all_facts = facts[:]
    
    # If we have domain facts, we need to retrieve from both corpora
    if domain_facts:
        # Build combined BM25 corpus with both project and domain facts
        if _BM25_AVAILABLE:
            project_corpus = [_fact_tokens(f) for f in facts]
            domain_corpus = [_domain_fact_tokens(f) for f in domain_facts]
            combined_corpus = project_corpus + domain_corpus
            
            bm25 = _BM25Okapi(combined_corpus)
            q_tokens = re.findall(r"[a-zA-Z0-9_+#.-]{2,}", query.lower())
            scores: list[float] = bm25.get_scores(q_tokens).tolist()
            
            # Separate scores back into project and domain
            project_scores = scores[:len(facts)]
            domain_scores = scores[len(facts):]
            
            # Get top results from each
            project_ranked = sorted(zip(project_scores, facts), key=lambda x: x[0], reverse=True)
            domain_ranked = sorted(zip(domain_scores, domain_facts), key=lambda x: x[0], reverse=True)
            
            # Take top scoring from each pool (roughly equal split)
            project_limit = limit // 2 if domain_facts else limit
            domain_limit = limit - project_limit
            
            top_projects = [f for s, f in project_ranked if s > 0.0][:project_limit]
            top_domains = [f for s, f in domain_ranked if s > 0.0][:domain_limit]
            
            # Build combined context
            context_parts = []
            if top_projects:
                context_parts.append(build_grounding_context(top_projects))
            if top_domains:
                context_parts.append(build_domain_grounding_context(top_domains))
            
            return "\n\n".join(context_parts) if context_parts else ""
        else:
            # Fallback: just use project facts if BM25 not available
            relevant = retrieve_evidence(query, facts, limit=limit)
            return build_grounding_context(relevant)
    else:
        # No domain facts, use original flow
        relevant = retrieve_evidence(query, facts, limit=limit)
        return build_grounding_context(relevant)


def build_domain_grounding_context(domain_facts: list[DomainEvidenceFact]) -> str:
    """Build a prompt-ready grounding block from domain evidence facts.

    Returns an empty string when the fact list is empty.
    """
    if not domain_facts:
        return ""

    lines = [
        "Domain expertise — general knowledge you can reference when relevant:"
    ]
    for fact in domain_facts:
        line = (
            f"- [{fact.evidence_id}] {fact.statement}"
        )
        if fact.tags:
            line += f" (Tags: {', '.join(fact.tags)})"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 1B: Learning log writer (T2.1, T2.2)
# ---------------------------------------------------------------------------

# Module-level run ID — stable for the lifetime of one process invocation.
_RUN_ID: str = str(uuid.uuid4())


def _sentence_hash(sentence: str) -> str:
    """Return a 16-char SHA-256 hex digest of the sentence (privacy-preserving)."""
    return hashlib.sha256(sentence.encode("utf-8")).hexdigest()[:16]


def record_moderation_event(
    *,
    sentence: str,
    reason_code: str,
    decision: str,
    channel: str,
    article_ref: str,
    project_refs: list[str] | None = None,
) -> None:
    """Append one ModerationEvent to learning_log.jsonl.

    Failures emit a warning and do not interrupt the generation/publish path.

    Args:
        sentence:     The flagged sentence (hashed before storage).
        reason_code:  Truth-gate reason string (e.g. 'unsupported_numeric').
        decision:     'kept' or 'removed'.
        channel:      Publication channel (linkedin, x, bluesky, youtube, all).
        article_ref:  URL or title of the source article.
        project_refs: Project IDs or names referenced in the sentence.
    """
    if decision not in ("kept", "removed"):
        logger.warning("record_moderation_event: invalid decision '%s'; must be 'kept' or 'removed'", decision)
        return

    event = ModerationEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        channel=channel,
        reason_code=reason_code,
        decision=decision,
        sentence_hash=_sentence_hash(sentence),
        article_ref=article_ref,
        project_refs=project_refs or [],
        run_id=_RUN_ID,
    )
    try:
        LEARNING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEARNING_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event)) + "\n")
    except OSError as exc:
        logger.warning("Learning log write failed (continuing): %s", exc)


# ---------------------------------------------------------------------------
# Phase 1B: Explain output builder (T2.4)
# ---------------------------------------------------------------------------


def build_explain_output(
    evidence_facts: list[EvidenceFact],
    article_ref: str,
    channel: str,
    ssi_component: str,
) -> ExplainOutput:
    """Build an ExplainOutput summary from the evidence facts used in a generation."""
    ids = [f.evidence_id for f in evidence_facts]
    summaries = []
    for f in evidence_facts:
        # Use type checks for robust attribute access
        if type(f).__name__ == "EvidenceFact":
            project = getattr(f, "project", "")
            years = getattr(f, "years", "")
            details = getattr(f, "details", "")
            summaries.append(
                f"[{f.evidence_id}] {project} ({years}) — {details[:80]}{'...' if len(details) > 80 else ''}"
            )
        elif type(f).__name__ == "DomainEvidenceFact":
            domain = getattr(f, "domain", "")
            statement = getattr(f, "statement", "")
            tags = getattr(f, "tags", [])
            summaries.append(
                f"[{f.evidence_id}] {domain} — {statement[:80]}{'...' if len(statement) > 80 else ''} (Tags: {', '.join(tags)})"
            )
        else:
            summaries.append(f"[{getattr(f, 'evidence_id', '?')}] Unknown evidence type")
    return ExplainOutput(
        evidence_ids=ids,
        evidence_summaries=summaries,
        article_ref=article_ref,
        channel=channel,
        ssi_component=ssi_component,
    )


def format_explain_output(explain: ExplainOutput) -> str:
    """Format an ExplainOutput as a human-readable plain-text block."""
    lines = [
        "── Avatar Explain ──────────────────────────────────────",
        f"Article  : {explain.article_ref}",
        f"Channel  : {explain.channel}",
        f"SSI      : {explain.ssi_component}",
        f"Evidence : {', '.join(explain.evidence_ids) if explain.evidence_ids else 'none (empty persona graph)'}",
        "",
    ]
    if explain.evidence_summaries:
        lines.append("Evidence details:")
        lines.extend(f"  {s}" for s in explain.evidence_summaries)
    else:
        lines.append("  No persona graph facts were used (graph is empty or not loaded).")
    lines.append("────────────────────────────────────────────────────────")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 1B: Learning report (T2.5, T2.6, T2.7)
# ---------------------------------------------------------------------------

# Minimum event count for a pattern to be included in recommendations.
_HEURISTIC_MIN_COUNT = 2


@dataclass
class LearningRecommendation:
    category: str       # 'domain_term' | 'retrieval_expansion' | 'prompt_length'
    suggestion: str
    confidence: str     # 'high' | 'medium' | 'low'
    evidence_count: int


@dataclass
class LearningReport:
    total_events: int
    kept_count: int
    removed_count: int
    top_reason_codes: list[tuple[str, int]]       # (reason_code, count), sorted desc
    kept_vs_removed: list[tuple[str, int, int]]   # (reason_code, kept, removed)
    recommendations: list[LearningRecommendation]


def _load_learning_events() -> list[dict[str, Any]]:
    """Read all events from learning_log.jsonl; skip malformed lines."""
    if not LEARNING_LOG_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    for i, line in enumerate(LEARNING_LOG_PATH.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Learning log line %d is not valid JSON — skipping", i)
    return events


def _apply_heuristics(
    events: list[dict[str, Any]],
) -> list[LearningRecommendation]:
    """Apply rule-based heuristics to produce advisory-only recommendations.

    Rules:
    1. project_claim kept repeatedly for same term → suggest domain-term candidate.
    2. Numeric removals on known sources repeatedly → suggest retrieval keyword review.
    3. Repeated low-confidence due to length pressure → suggest channel prompt adjustment.
       (Length pressure heuristic uses unsupported_numeric removals as a proxy until
        Phase 1C confidence scoring is available.)
    """
    recs: list[LearningRecommendation] = []

    # Rule 1: project_claim — kept decisions (user overrode removal)
    project_claim_kept = [e for e in events if "project_claim" in e.get("reason_code", "") and e.get("decision") == "kept"]
    if len(project_claim_kept) >= _HEURISTIC_MIN_COUNT:
        recs.append(LearningRecommendation(
            category="domain_term",
            suggestion=(
                f"You overrode {len(project_claim_kept)} 'project_claim' removals. "
                "Consider adding the repeatedly-kept tech keywords to domain knowledge "
                "or CONSOLE_GROUNDING_TECH_KEYWORDS in your .env."
            ),
            confidence="high" if len(project_claim_kept) >= 5 else "medium",
            evidence_count=len(project_claim_kept),
        ))

    # Rule 2: numeric removals — suggest retrieval keyword expansion
    numeric_removed = [e for e in events if "unsupported_numeric" in e.get("reason_code", "") and e.get("decision") == "removed"]
    if len(numeric_removed) >= _HEURISTIC_MIN_COUNT:
        recs.append(LearningRecommendation(
            category="retrieval_expansion",
            suggestion=(
                f"{len(numeric_removed)} numeric claims were removed. "
                "Review whether source articles provide supporting stats, and consider "
                "adjusting retrieval tags so richer articles are prioritised."
            ),
            confidence="medium",
            evidence_count=len(numeric_removed),
        ))

    # Rule 3: high removal rate per channel → suggest prompt length adjustment
    channel_removals: Counter[str] = Counter(
        e.get("channel", "unknown")
        for e in events
        if e.get("decision") == "removed"
    )
    for channel, count in channel_removals.items():
        if count >= _HEURISTIC_MIN_COUNT * 2:
            recs.append(LearningRecommendation(
                category="prompt_length",
                suggestion=(
                    f"High removal rate on '{channel}' ({count} removed sentences). "
                    "Consider adjusting the channel prompt or instruction length to "
                    "reduce hallucination pressure."
                ),
                confidence="low" if count < 10 else "medium",
                evidence_count=count,
            ))

    return recs


def build_learning_report() -> LearningReport:
    """Aggregate events from learning_log.jsonl into a structured report.

    Returns a LearningReport with zero counts when the log is empty.
    Recommendations are advisory only — this function never mutates config files.
    """
    events = _load_learning_events()

    if not events:
        return LearningReport(
            total_events=0,
            kept_count=0,
            removed_count=0,
            top_reason_codes=[],
            kept_vs_removed=[],
            recommendations=[],
        )

    kept_count = sum(1 for e in events if e.get("decision") == "kept")
    removed_count = sum(1 for e in events if e.get("decision") == "removed")

    reason_counter: Counter[str] = Counter(e.get("reason_code", "unknown") for e in events)
    top_reason_codes = reason_counter.most_common(10)

    # kept vs removed per reason code
    kept_by_reason: Counter[str] = Counter(
        e.get("reason_code", "unknown") for e in events if e.get("decision") == "kept"
    )
    removed_by_reason: Counter[str] = Counter(
        e.get("reason_code", "unknown") for e in events if e.get("decision") == "removed"
    )
    all_reasons = set(kept_by_reason) | set(removed_by_reason)
    kept_vs_removed = sorted(
        [(r, kept_by_reason[r], removed_by_reason[r]) for r in all_reasons],
        key=lambda x: x[1] + x[2],
        reverse=True,
    )

    recommendations = _apply_heuristics(events)

    return LearningReport(
        total_events=len(events),
        kept_count=kept_count,
        removed_count=removed_count,
        top_reason_codes=top_reason_codes,
        kept_vs_removed=kept_vs_removed,
        recommendations=recommendations,
    )


def format_learning_report(report: LearningReport) -> str:
    """Format a LearningReport as a human-readable plain-text block."""
    lines = [
        "── Avatar Learning Report ──────────────────────────────",
        f"Total events : {report.total_events}",
        f"Kept         : {report.kept_count}",
        f"Removed      : {report.removed_count}",
        "",
    ]

    if report.top_reason_codes:
        lines.append("Top reason codes:")
        for code, count in report.top_reason_codes:
            lines.append(f"  {code:<40} {count:>4}")
        lines.append("")

    if report.kept_vs_removed:
        lines.append("Kept vs removed by reason:")
        lines.append(f"  {'Reason':<40} {'Kept':>6} {'Removed':>8}")
        lines.append(f"  {'-'*40} {'------':>6} {'--------':>8}")
        for reason, kept, removed in report.kept_vs_removed:
            lines.append(f"  {reason:<40} {kept:>6} {removed:>8}")
        lines.append("")

    if report.recommendations:
        lines.append("Recommendations (advisory only — no config files modified):")
        for rec in report.recommendations:
            lines.append(f"  [{rec.confidence.upper()}] [{rec.category}] {rec.suggestion}")
        lines.append("")
    else:
        lines.append("No recommendations (insufficient data or no patterns detected).")

    lines.append("────────────────────────────────────────────────────────")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 1C: Confidence Scoring and Policy (T3.1–T3.3, T3.6)
# ---------------------------------------------------------------------------

# Severity weights per reason code — higher means more concern.
_REASON_SEVERITY: dict[str, float] = {
    "fabricated_detail":    0.90,
    "unsupported_numeric":  0.80,
    "unsupported_claim":    0.70,
    "unsupported_dollar":   0.75,
    "unsupported_year":     0.65,
    "speculative":          0.50,
    "unsupported_org":      0.55,
    "project_claim":        0.40,
    "out_of_scope":         0.30,
}
_DEFAULT_REASON_SEVERITY = 0.50

# Per-channel character budgets used for length-pressure normalization.
_CHANNEL_LENGTH_BUDGETS: dict[str, int] = {
    "linkedin": 3000,
    "x":        257,   # 280 - 23 URL chars
    "bluesky":  300,
    "youtube":  500,
    "all":      3000,
}


@dataclass
class ConfidenceSignals:
    """Normalized input signals for confidence scoring (all values 0.0–1.0 unless noted)."""

    truth_gate_removed_count: int      # raw count of sentences removed by truth gate
    truth_gate_reason_severity: float  # max severity of removal reason codes (0–1)
    grounding_coverage_ratio: float    # evidence facts used / max available (0–1)
    unsupported_claim_pressure: float  # removed / total_sentences ratio (0–1)
    channel_length_pressure: float     # post_length / channel_budget, capped at 1.0
    narrative_repetition_score: float  # reserved for Phase 1D; always 0.0 until then


@dataclass
class ConfidenceResult:
    """Scored confidence output for one generation."""

    score: float                    # 0.0–1.0
    level: str                      # 'high' | 'medium' | 'low'
    signals: ConfidenceSignals
    dominant_signal: str | None     # name of the signal with largest negative contribution


@dataclass
class ConfidenceDecision:
    """Output of decide_publish_mode — publish route + human-readable reason."""

    route: str              # 'post' | 'idea' | 'block'
    reason: str
    policy: str
    confidence_level: str   # mirrors ConfidenceResult.level


@dataclass
class ConfidenceDecisionEvent:
    """One confidence-policy decision captured in the learning log (T3.6)."""

    timestamp: str
    channel: str
    route: str
    policy: str
    confidence_score: float
    confidence_level: str
    dominant_signal: str | None
    reason: str
    article_ref: str
    run_id: str


def extract_confidence_signals(
    *,
    removed_count: int,
    total_sentences: int,
    reason_codes: list[str],
    grounding_facts_count: int,
    max_grounding_facts: int = 5,
    channel: str = "linkedin",
    post_length: int = 0,
    narrative_repetition_score: float = 0.0,
) -> ConfidenceSignals:
    """Extract normalized confidence signals from generation + truth-gate metadata.

    All output values are normalized to [0.0, 1.0].

    Args:
        removed_count:              Sentences removed by truth gate.
        total_sentences:            Total sentences in the draft.
        reason_codes:               Reason codes from removed sentences.
        grounding_facts_count:      Number of evidence facts used in grounding.
        max_grounding_facts:        Upper bound for grounding coverage ratio.
        channel:                    Target channel (used for length-budget lookup).
        post_length:                Final post character count.
        narrative_repetition_score: Phase 1D signal; pass 0.0 until implemented.
    """
    # truth_gate_removed_count: normalize against a soft cap of 10 sentences
    removed_norm = min(removed_count / 10.0, 1.0)  # stored as-is for transparency

    # truth_gate_reason_severity: worst-case severity across all reason codes
    severities = [_REASON_SEVERITY.get(rc, _DEFAULT_REASON_SEVERITY) for rc in reason_codes]
    max_severity = max(severities, default=0.0)

    # grounding_coverage_ratio
    if max_grounding_facts > 0:
        coverage = min(grounding_facts_count / max_grounding_facts, 1.0)
    else:
        coverage = 0.0

    # unsupported_claim_pressure
    claim_pressure = min(removed_count / total_sentences, 1.0) if total_sentences > 0 else 0.0

    # channel_length_pressure
    budget = _CHANNEL_LENGTH_BUDGETS.get(channel, 3000)
    length_pressure = min(post_length / budget, 1.0) if budget > 0 else 0.0

    return ConfidenceSignals(
        truth_gate_removed_count=removed_count,
        truth_gate_reason_severity=max_severity,
        grounding_coverage_ratio=coverage,
        unsupported_claim_pressure=claim_pressure,
        channel_length_pressure=length_pressure,
        narrative_repetition_score=narrative_repetition_score,
    )


def score_confidence(signals: ConfidenceSignals) -> ConfidenceResult:
    """Compute a deterministic confidence score from normalized signals.

    Scoring formula (contributions sum against base 1.0):
    - truth_gate_reason_severity   : up to -0.35
    - unsupported_claim_pressure   : up to -0.30
    - truth_gate_removed_count     : up to -0.15 (normalized /10)
    - channel_length_pressure      : up to -0.10
    - narrative_repetition_score   : up to -0.10
    - grounding_coverage_ratio     : up to +0.10 (bonus)

    Level thresholds: high ≥ 0.70, medium ≥ 0.40, low < 0.40.

    The function is deterministic: same signals always produce the same output.
    """
    contributions: dict[str, float] = {
        "truth_gate_reason_severity":  -signals.truth_gate_reason_severity  * 0.35,
        "unsupported_claim_pressure":  -signals.unsupported_claim_pressure  * 0.30,
        "truth_gate_removed_count":    -min(signals.truth_gate_removed_count / 10.0, 1.0) * 0.15,
        "grounding_coverage_ratio":    +signals.grounding_coverage_ratio    * 0.10,
        "channel_length_pressure":     -signals.channel_length_pressure     * 0.10,
        "narrative_repetition_score":  -signals.narrative_repetition_score  * 0.10,
    }

    raw = 1.0 + sum(contributions.values())
    score = round(max(0.0, min(1.0, raw)), 4)

    if score >= 0.70:
        level = "high"
    elif score >= 0.40:
        level = "medium"
    else:
        level = "low"

    # Dominant negative contributor
    negative = {k: v for k, v in contributions.items() if v < 0}
    dominant = min(negative, key=lambda k: negative[k]) if negative else None

    return ConfidenceResult(score=score, level=level, signals=signals, dominant_signal=dominant)


def decide_publish_mode(
    policy: str,
    confidence: ConfidenceResult,
    requested_mode: str,
) -> ConfidenceDecision:
    """Apply config §7.2 policy matrix to produce a publish route decision.

    Policy matrix:
    - strict:       high → post; medium → idea; low → block
    - balanced:     high/medium → post; low → idea
    - draft-first:  all → idea

    *requested_mode* ('post' or 'idea') is the caller's intent and is
    recorded in the reason string for traceability but does not override
    the policy decision.

    Falls back to 'balanced' behaviour for unrecognised policy values.
    """
    level = confidence.level

    if policy == "draft-first":
        return ConfidenceDecision(
            route="idea",
            reason=f"draft-first policy: all outputs buffered as ideas (score={confidence.score:.2f})",
            policy=policy,
            confidence_level=level,
        )

    if policy == "strict":
        if level == "high":
            return ConfidenceDecision(
                route="post",
                reason=f"strict policy: high confidence ({confidence.score:.2f}) → direct post",
                policy=policy,
                confidence_level=level,
            )
        elif level == "medium":
            return ConfidenceDecision(
                route="idea",
                reason=f"strict policy: medium confidence ({confidence.score:.2f}) → idea for review",
                policy=policy,
                confidence_level=level,
            )
        else:
            return ConfidenceDecision(
                route="block",
                reason=f"strict policy: low confidence ({confidence.score:.2f}) → blocked",
                policy=policy,
                confidence_level=level,
            )

    # balanced (default — also catches unknown policy values)
    if policy not in ("strict", "balanced", "draft-first"):
        logger.warning("Unknown confidence policy '%s'; falling back to 'balanced'", policy)

    if level in ("high", "medium"):
        return ConfidenceDecision(
            route="post",
            reason=f"balanced policy: {level} confidence ({confidence.score:.2f}) → direct post",
            policy="balanced",
            confidence_level=level,
        )
    return ConfidenceDecision(
        route="idea",
        reason=f"balanced policy: low confidence ({confidence.score:.2f}) → idea for review",
        policy="balanced",
        confidence_level=level,
    )


def record_confidence_decision(
    *,
    decision: ConfidenceDecision,
    confidence: ConfidenceResult,
    channel: str,
    article_ref: str,
) -> None:
    """Append one ConfidenceDecisionEvent to learning_log.jsonl (T3.6).

    Failures emit a warning and do not interrupt the publish path.
    """
    event = ConfidenceDecisionEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        channel=channel,
        route=decision.route,
        policy=decision.policy,
        confidence_score=confidence.score,
        confidence_level=confidence.level,
        dominant_signal=confidence.dominant_signal,
        reason=decision.reason,
        article_ref=article_ref,
        run_id=_RUN_ID,
    )
    try:
        LEARNING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEARNING_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event)) + "\n")
    except OSError as exc:
        logger.warning("Learning log write failed (confidence event, continuing): %s", exc)


# ── Epic 1D: Narrative Continuity Memory ─────────────────────────────────────

_CLAIM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(you can|you should|you must|always|never|every|the key|the trick|the secret|the best way)\b", re.IGNORECASE),
    re.compile(r"\b(is (the|a) (major|critical|key|core|main|primary))\b", re.IGNORECASE),
    re.compile(r"\b(more (important|effective|efficient|scalable) than)\b", re.IGNORECASE),
    re.compile(r"\b(will (replace|change|transform|disrupt))\b", re.IGNORECASE),
]

_THEME_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "that", "this", "it", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "will", "would", "can", "could",
    "should", "may", "might", "by", "from", "as", "about", "into", "through",
})


def update_narrative_memory(
    memory: NarrativeMemory,
    themes: list[str],
    claims: list[str],
    arcs: list[str],
    max_items: int | None = None,
) -> NarrativeMemory:
    """Append new items to narrative memory and trim to *max_items* (FIFO).

    Each list is trimmed independently so no category starves another.
    When *max_items* is None, falls back to ``AVATAR_MAX_MEMORY_ITEMS``.
    """
    from services.shared import AVATAR_MAX_MEMORY_ITEMS as _DEFAULT_MAX  # lazy to avoid circular

    limit = max_items if max_items is not None else _DEFAULT_MAX

    def _merge_trim(existing: list[str], new: list[str]) -> list[str]:
        merged = existing + [item for item in new if item not in existing]
        return merged[-limit:]  # keep most-recent up to limit

    return NarrativeMemory(
        recent_themes=_merge_trim(memory.recent_themes, themes),
        recent_claims=_merge_trim(memory.recent_claims, claims),
        open_narrative_arcs=_merge_trim(memory.open_narrative_arcs, arcs),
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


def save_narrative_memory(memory: NarrativeMemory, path: Path | None = None) -> None:
    """Persist *memory* to *path* (defaults to ``NARRATIVE_MEMORY_PATH``).

    Failures emit a warning so the publish path is never interrupted.
    """
    target = path or NARRATIVE_MEMORY_PATH
    payload = {
        "recentThemes": memory.recent_themes,
        "recentClaims": memory.recent_claims,
        "openNarrativeArcs": memory.open_narrative_arcs,
        "lastUpdated": memory.last_updated,
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug(
            "Narrative memory saved to %s (%d themes, %d claims)",
            target,
            len(memory.recent_themes),
            len(memory.recent_claims),
        )
    except OSError as exc:
        logger.warning("Narrative memory save failed (continuing): %s", exc)


def extract_narrative_updates(
    post_text: str,
    ssi_component: str,
    article_title: str = "",
) -> dict[str, list[str]]:
    """Extract themes, claims, and open arcs from a successfully-generated post.

    Returns a dict with keys ``themes``, ``claims``, ``arcs``.  Rule-based,
    no LLM call — deterministic and fast.

    Themes: top non-stopword tokens from ssi_component + article_title.
    Claims: sentences matching known claim patterns.
    Arcs:   empty list in v1 (reserved for future turn-taking signals).
    """
    raw_tokens = re.findall(r"[a-zA-Z]{3,}", f"{ssi_component} {article_title}".lower())
    themes = list(dict.fromkeys(t for t in raw_tokens if t not in _THEME_STOPWORDS))[:10]

    sentences = re.split(r"(?<=[.!?])\s+", post_text.strip())
    claims: list[str] = []
    for sent in sentences:
        sent_stripped = sent.strip()
        if any(p.search(sent_stripped) for p in _CLAIM_PATTERNS):
            norm = sent_stripped.rstrip(".!?,;").lower()
            if len(norm) >= 20 and norm not in claims:
                claims.append(norm)
    claims = claims[:5]

    return {"themes": themes, "claims": claims, "arcs": []}


def build_continuity_context(memory: NarrativeMemory, max_chars: int = 300) -> str:
    """Build a prompt-ready continuity snippet from narrative memory.

    Returns an empty string when memory has no useful content.  The output
    is trimmed to *max_chars* and is safe to include verbatim in any prompt.
    """
    parts: list[str] = []
    if memory.recent_themes:
        top_themes = memory.recent_themes[-5:]
        parts.append("Recent topics you have written about: " + ", ".join(top_themes) + ".")
    if memory.open_narrative_arcs:
        top_arcs = memory.open_narrative_arcs[-3:]
        parts.append("Open narrative threads to vary or continue: " + "; ".join(top_arcs) + ".")
    if not parts:
        return ""
    snippet = " ".join(parts)
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rsplit(" ", 1)[0].rstrip(",;") + "..."
    return snippet


def compute_repetition_score(post_text: str, memory: NarrativeMemory) -> float:
    """Return a [0.0, 1.0] score representing how much *post_text* repeats recent claims.

    Score is the fraction of recent claims whose key tokens overlap ≥ 50 %
    with *post_text*, capped at 1.0.  Score of 0.0 = no repetition.
    """
    if not memory.recent_claims:
        return 0.0

    post_tokens: frozenset[str] = frozenset(
        t.lower()
        for t in re.findall(r"[a-zA-Z]{3,}", post_text)
        if t.lower() not in _THEME_STOPWORDS
    )
    if not post_tokens:
        return 0.0

    overlap_count = 0
    for claim in memory.recent_claims:
        claim_tokens = frozenset(
            t.lower()
            for t in re.findall(r"[a-zA-Z]{3,}", claim)
            if t.lower() not in _THEME_STOPWORDS
        )
        if not claim_tokens:
            continue
        overlap = len(post_tokens & claim_tokens) / len(claim_tokens)
        if overlap >= 0.5:
            overlap_count += 1

    return round(min(overlap_count / len(memory.recent_claims), 1.0), 4)

