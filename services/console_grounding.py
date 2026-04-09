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

    lines = ["Your background — weave these in naturally when they genuinely connect to the topic:"]
    for fact in facts[:limit]:
        lines.append(
            f"- Project: {fact.project} | Company: {fact.company} | Years: {fact.years} | Detail: {fact.details}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lightweight truth gate — post-generation claim check
# ---------------------------------------------------------------------------

# Regex to find sentences containing numeric claims (percentages, specific
# numbers with units, dollar amounts) or year references that might be
# hallucinated.
_NUMERIC_CLAIM_RE = re.compile(
    r"\d+(?:\.\d+)?(?:\s*[%x×]"           # 40%, 3x, 2×
    r"|\s*(?:percent|million|billion|thousand|ms|seconds?|minutes?|hours?)"
    r"|\s*(?:faster|slower|reduction|improvement|increase|decrease)"
    r")",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_DOLLAR_RE = re.compile(r"\$\s?\d")

# Company-name heuristic: two+ capitalised words that look like an org name
# but are NOT common English phrases.
_ORG_NAME_RE = re.compile(
    r"\b(?:at|for|with|from|joined)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

import logging as _logging
_truth_logger = _logging.getLogger(__name__)


def _build_allowed_tokens(article_text: str, facts: list[ProjectFact]) -> set[str]:
    """Build a set of lowercased tokens that are considered 'allowed' evidence.

    Includes all words, numbers, and short phrases from the article text and
    the grounding facts.  The truth gate checks whether a claim's specific
    numeric/company token appears somewhere in this allowed set.
    """
    allowed: set[str] = set()

    # Extract all number-like tokens and lowercased words from sources.
    sources = [article_text]
    for f in facts:
        sources.append(f"{f.project} {f.company} {f.years} {f.details}")

    for src in sources:
        # Numbers (with optional decimal): "397k", "500ms", "40%", "2024"
        for m in re.finditer(r"\d[\d,.*]*\w*", src):
            allowed.add(m.group(0).lower().rstrip("."))
        # Year ranges like "2014-2023"
        for m in re.finditer(r"(19|20)\d{2}(?:\s*[-–]\s*(19|20)?\d{2})?", src):
            allowed.add(m.group(0).replace(" ", "").lower())
        # Capitalised multi-word names (potential orgs)
        for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", src):
            allowed.add(m.group(0).lower())
        # Individual words ≥3 chars
        for w in re.findall(r"\b\w{3,}\b", src):
            allowed.add(w.lower())

    return allowed


def _build_project_tech_map(
    facts: list[ProjectFact],
    article_text: str,
) -> dict[str, str]:
    """Map each project name (lowercased) to its allowed evidence text.

    The evidence text is the lowercased concatenation of the project's own
    title + details and the article text.  Keyword matching uses substring
    search against this text, which naturally handles:
    - Multi-word phrases (e.g. 'hybrid search' found in detail prose)
    - Compound-word aliases (e.g. 'mcp' found inside 'fastmcp')
    """
    article_lower = article_text.lower()

    project_map: dict[str, str] = {}
    for fact in facts:
        detail_lower = f"{fact.project} {fact.details}".lower()
        project_map[fact.project.lower()] = f"{detail_lower} {article_lower}"
    return project_map


def _check_project_claim(
    sentence: str,
    project_map: dict[str, str],
    tech_keywords: set[str],
) -> str | None:
    """Return the reason string if the sentence falsely links a tech to a project.

    Returns None when the sentence is fine to keep.
    """
    sent_lower = sentence.lower()
    for project_name, evidence_text in project_map.items():
        if project_name not in sent_lower:
            continue
        # This sentence mentions a known project — check tech keywords in it.
        for kw in tech_keywords:
            if kw in sent_lower and kw not in evidence_text:
                return (
                    f"project_claim: '{kw}' attributed to "
                    f"'{project_name}' but not in its detail or article"
                )
    return None


def truth_gate(
    text: str,
    article_text: str,
    facts: list[ProjectFact],
) -> str:
    """Lightweight post-generation truth gate.

    Scans each sentence in *text* for:
    1. Numeric claims, year references, dollar amounts, and company-name
       patterns whose key token does NOT appear in the article or facts.
    2. Project-technology misattributions — when a sentence names a known
       project but pairs it with a tech keyword that does not appear in
       that project's detail or the article text.

    Flagged sentences are silently removed.  The rest of the post is left
    intact — no rewriting.

    Returns the filtered text (may be identical to input if nothing was stripped).
    """
    if not text:
        return text

    allowed = _build_allowed_tokens(article_text, facts)
    tech_keywords = get_console_grounding_keywords()
    project_map = _build_project_tech_map(facts, article_text)
    sentences = _SENTENCE_SPLIT_RE.split(text)
    kept: list[str] = []
    removed: list[tuple[str, str]] = []  # (sentence_fragment, reason)

    for sentence in sentences:
        reason: str | None = None

        # Check numeric claims
        for m in _NUMERIC_CLAIM_RE.finditer(sentence):
            num_token = re.match(r"[\d,.]+", m.group(0))
            if num_token and num_token.group(0).lower().rstrip(".") not in allowed:
                reason = f"unsupported_numeric: '{m.group(0)}'"
                break

        # Check year references
        if not reason:
            for m in _YEAR_RE.finditer(sentence):
                if m.group(0) not in allowed:
                    reason = f"unsupported_year: '{m.group(0)}'"
                    break

        # Check dollar amounts
        if not reason:
            for m in _DOLLAR_RE.finditer(sentence):
                nearby = sentence[m.start():m.start()+20]
                num = re.search(r"\d[\d,.]*", nearby)
                if num and num.group(0).lower().rstrip(".") not in allowed:
                    reason = f"unsupported_dollar: '{nearby.strip()}'"
                    break

        # Check org-name patterns ("at SomeCompany", "for BigCorp")
        if not reason:
            for m in _ORG_NAME_RE.finditer(sentence):
                if m.group(1).lower() not in allowed:
                    reason = f"unsupported_org: '{m.group(1)}'"
                    break

        # Semantic project-claim check
        if not reason:
            reason = _check_project_claim(sentence, project_map, tech_keywords)

        if reason:
            removed.append((sentence[:80], reason))
        else:
            kept.append(sentence)

    # Log each removed sentence with its reason code
    if removed:
        for fragment, reason in removed:
            _truth_logger.info(
                "Truth gate removed [%s]: ...%s...",
                reason,
                fragment,
            )
        _truth_logger.info(
            "Truth gate summary: removed %d of %d sentences",
            len(removed),
            len(sentences),
        )

    return " ".join(kept).strip()
