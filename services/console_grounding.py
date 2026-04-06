"""Deterministic grounding layer for persona console mode.

This module parses PROFILE_CONTEXT project blocks, applies simple NLP-style
query intent/constraint extraction, retrieves relevant facts, and can produce
deterministic cited answers without additional model calls.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re


DEFAULT_TECH_KEYWORDS = {
    "java", "spring", "spring boot", "spring ai", "spring batch", "jms",
    "python", "fastapi", "scikit-learn", "gymnasium", "stable-baselines3",
    "elasticsearch", "solr", "lucene", "neo4j", "rag", "mcp", "fastmcp",
    "oracle", "weblogic", "jsf", "adf", "vaadin", "hibernate", "tomcat",
}

DEFAULT_TAG_EXPANSIONS: dict[str, set[str]] = {
    "java": {"spring", "jms", "oracle", "weblogic", "solr", "lucene", "elasticsearch"},
}


def get_console_grounding_keywords() -> set[str]:
    """Return tech keywords used by console grounding from env with defaults."""
    raw = os.getenv("CONSOLE_GROUNDING_TECH_KEYWORDS", "").strip()
    if not raw:
        return set(DEFAULT_TECH_KEYWORDS)
    parsed = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return parsed or set(DEFAULT_TECH_KEYWORDS)


def get_console_grounding_tag_expansions() -> dict[str, set[str]]:
    """Return query tag expansion map from env with sensible defaults.

    Env format:
      CONSOLE_GROUNDING_TAG_EXPANSIONS=java:spring|jms|oracle;python:fastapi|scikit-learn
    """
    raw = os.getenv("CONSOLE_GROUNDING_TAG_EXPANSIONS", "").strip()
    if not raw:
        return {k: set(v) for k, v in DEFAULT_TAG_EXPANSIONS.items()}

    expansions: dict[str, set[str]] = {}
    for block in raw.split(";"):
        block = block.strip()
        if not block or ":" not in block:
            continue
        base, values = block.split(":", 1)
        base = base.strip().lower()
        related = {v.strip().lower() for v in values.split("|") if v.strip()}
        if base and related:
            expansions[base] = related

    if expansions:
        return expansions
    return {k: set(v) for k, v in DEFAULT_TAG_EXPANSIONS.items()}


@dataclass
class ProjectFact:
    project: str
    company: str
    years: str
    details: str
    source: str
    tags: set[str]


@dataclass
class QueryConstraints:
    require_projects: bool
    require_companies: bool
    tech_tags: set[str]

    @property
    def requires_grounding(self) -> bool:
        return self.require_projects or self.require_companies or bool(self.tech_tags)


PROFILE_CLAIM_MARKERS = (
    "i built",
    "i led",
    "i implemented",
    "i shipped",
    "i delivered",
    "i worked",
    "my project",
    "my team",
    "at ",
    "for ",
)

COMMON_STOPWORDS = {
    "and", "the", "with", "from", "that", "this", "into", "about", "your", "their",
    "they", "have", "were", "been", "while", "where", "using", "across", "under", "over",
    "build", "built", "project", "projects", "system", "systems", "platform", "platforms",
}


def _extract_company(title: str, details: str) -> str:
    patterns = [
        r"\bat\s+([A-Z][A-Za-z0-9&/ .\-]+?)(?:\.|,|;|$)",
        r"\bfor\s+([A-Z][A-Za-z0-9&/ .\-]+?)(?:\.|,|;|$)",
    ]
    for pat in patterns:
        m = re.search(pat, details)
        if m:
            return m.group(1).strip()

    # Many profile bullets use the company/org as the heading.
    if "/" in title:
        return title.strip()
    return title.strip()


def _extract_tags(text: str, tech_keywords: set[str]) -> set[str]:
    low = text.lower()
    tags: set[str] = set()
    for kw in tech_keywords:
        if kw in low:
            tags.add(kw)
    return tags


def parse_profile_project_facts(profile_context: str, tech_keywords: set[str] | None = None) -> list[ProjectFact]:
    """Parse '- Project (years): details' bullets from PROFILE_CONTEXT."""
    facts: list[ProjectFact] = []
    active_keywords = tech_keywords if tech_keywords is not None else get_console_grounding_keywords()
    pattern = re.compile(r"^\s*-\s+(.+?)\s*\(([^)]*)\):\s*(.+)$", re.MULTILINE)
    for m in pattern.finditer(profile_context):
        title = m.group(1).strip()
        years = m.group(2).strip()
        details = m.group(3).strip()
        company = _extract_company(title, details)
        tags = _extract_tags(f"{title} {details} {company}", active_keywords)
        source = f"PROFILE_CONTEXT: {title} ({years})"
        facts.append(
            ProjectFact(
                project=title,
                company=company,
                years=years,
                details=details,
                source=source,
                tags=tags,
            )
        )
    return facts


def parse_query_constraints(
    query: str,
    tech_keywords: set[str] | None = None,
    tag_expansions: dict[str, set[str]] | None = None,
) -> QueryConstraints:
    q = query.lower()
    require_projects = any(w in q for w in ["project", "projects", "worked on", "built", "resume"])
    require_companies = any(w in q for w in ["company", "companies", "where", "worked at", "employer"])

    active_keywords = tech_keywords if tech_keywords is not None else get_console_grounding_keywords()
    tags: set[str] = set()
    for kw in active_keywords:
        if kw in q:
            tags.add(kw)

    # Expand detected tags into related tags for better retrieval quality.
    expansions = tag_expansions if tag_expansions is not None else get_console_grounding_tag_expansions()
    for base_tag, related in expansions.items():
        if base_tag in tags:
            tags.update(related)

    return QueryConstraints(
        require_projects=require_projects,
        require_companies=require_companies,
        tech_tags=tags,
    )


def retrieve_relevant_facts(facts: list[ProjectFact], constraints: QueryConstraints, limit: int = 8) -> list[ProjectFact]:
    if not facts:
        return []

    scored: list[tuple[int, ProjectFact]] = []
    for fact in facts:
        score = 0
        if constraints.tech_tags:
            score += len(fact.tags.intersection(constraints.tech_tags)) * 5
        if constraints.require_projects:
            score += 1
        if constraints.require_companies and fact.company:
            score += 2
        # Prefer richer, concrete entries.
        score += min(len(fact.details) // 120, 3)
        scored.append((score, fact))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [f for s, f in scored if s > 0][:limit]
    if top:
        return top
    return [f for _, f in scored[:limit]]


def build_deterministic_grounded_reply(query: str, facts: list[ProjectFact], constraints: QueryConstraints) -> str:
    """Build a deterministic cited response for fact-heavy console queries."""
    if not facts:
        return (
            "I don't have confirmed project/company records for that request in the loaded profile context. "
            "Try asking with a specific technology or company keyword."
        )

    lines = ["Here are the projects I can confirm from loaded profile context:"]
    for f in facts:
        lines.append(f"- Project: {f.project}")
        if constraints.require_companies or f.company:
            lines.append(f"  Company: {f.company}")
        lines.append(f"  Years: {f.years}")
        lines.append(f"  Why relevant: {f.details}")
        lines.append(f"  [source: {f.source}]")

    if constraints.tech_tags:
        lines.append(f"\nFilter applied: {', '.join(sorted(constraints.tech_tags))}")
    return "\n".join(lines)


def build_grounding_facts_block(facts: list[ProjectFact], limit: int = 5) -> str:
    """Build a compact deterministic facts block for generation prompts."""
    if not facts:
        return ""

    lines = ["Allowed profile facts (use these only if you reference personal experience):"]
    for fact in facts[:limit]:
        lines.append(
            f"- Project: {fact.project} | Company: {fact.company} | Years: {fact.years} | Detail: {fact.details}"
        )
    return "\n".join(lines)


def _sentence_split(text: str) -> list[str]:
    """Split text into sentence-like chunks while preserving punctuation."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _allowed_claim_tokens(facts: list[ProjectFact]) -> set[str]:
    tokens: set[str] = set()
    for fact in facts:
        combined = f"{fact.project} {fact.company}"
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9+\-/.]{2,}", combined.lower()):
            if token not in COMMON_STOPWORDS:
                tokens.add(token)
    return tokens


def enforce_profile_claim_grounding(text: str, allowed_facts: list[ProjectFact]) -> str:
    """Remove unsupported profile-claim sentences that reference unknown experience.

    This is intentionally conservative and only removes sentences that look like
    personal background claims but do not contain any allowed project/company token.
    """
    if not text or not allowed_facts:
        return text

    allowed_tokens = _allowed_claim_tokens(allowed_facts)
    if not allowed_tokens:
        return text

    sentences = _sentence_split(text)
    filtered: list[str] = []
    removed_any = False

    for sentence in sentences:
        low = sentence.lower()
        looks_like_claim = any(marker in low for marker in PROFILE_CLAIM_MARKERS)
        if looks_like_claim and not any(tok in low for tok in allowed_tokens):
            removed_any = True
            continue
        filtered.append(sentence)

    if not removed_any or not filtered:
        return text

    return " ".join(filtered).strip()
