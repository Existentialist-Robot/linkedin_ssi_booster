
from __future__ import annotations
"""Deterministic grounding layer for persona console mode.

This module parses PROFILE_CONTEXT project blocks, applies simple NLP-style
query intent/constraint extraction, retrieves relevant facts, and can produce
deterministic cited answers without additional model calls.
"""

from dataclasses import dataclass, field
import os
import re
from typing import TYPE_CHECKING
from colorama import Fore, Style

if TYPE_CHECKING:
    pass  # avoid circular import; avatar_intelligence imported lazily inside truth_gate

try:
    from rank_bm25 import BM25Okapi as _BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BM25_AVAILABLE = False


DEFAULT_TECH_KEYWORDS = {
    # Persona / project stack
    "java", "spring", "spring boot", "spring ai", "spring batch", "jms",
    "python", "fastapi", "scikit-learn", "gymnasium", "stable-baselines3",
    "elasticsearch", "solr", "lucene", "neo4j", "rag", "mcp", "fastmcp",
    "oracle", "weblogic", "jsf", "adf", "vaadin", "hibernate", "tomcat",
    # Domain knowledge terms
    "llm", "bm25", "knn", "k-nearest", "vector search", "embeddings",
    "semantic search", "microservices", "prompt engineering", "retrieval",
    "fine-tuning", "machine learning", "deep learning", "neural network",
    "transformer", "agent", "agentic", "api", "rest", "graphql",
    "docker", "kubernetes", "kafka", "data pipeline", "etl",
    "information retrieval", "ranking", "similarity", "reranking",
}

# Phrases that indicate the user is asking for knowledge / explanation
DOMAIN_KNOWLEDGE_PHRASES: frozenset[str] = frozenset([
    "what is", "what are", "what does", "what do",
    "explain", "how does", "how do", "how is",
    "tell me about", "know about", "what do you know",
    "expertise", "domain knowledge", "define", "describe",
    "can you explain", "teach me", "what's",
])

DEFAULT_TAG_EXPANSIONS: dict[str, set[str]] = {
    "java": {"spring", "jms", "oracle", "weblogic", "solr", "lucene", "elasticsearch"},
}



def get_truth_gate_bm25_threshold() -> float:
    """Return the minimum BM25 score threshold for truth gate validation.

    Env format:
      TRUTH_GATE_BM25_THRESHOLD=1.0 (float, defaults to 1.0)
    
    Recommended values:
      - 0.5: Permissive (allows paraphrased claims with weak evidence)
      - 1.0: Balanced (default - good for most use cases)
      - 2.0: Strict (requires strong evidence overlap)
      - 5.0: Very strict (requires very strong evidence match)
    """
    raw = os.getenv("TRUTH_GATE_BM25_THRESHOLD", "").strip()
    if not raw:
        return 1.0
    try:
        threshold = float(raw)
        # Clamp to reasonable range
        return max(0.0, min(threshold, 100.0))
    except ValueError:
        _truth_logger.warning(
            "Invalid TRUTH_GATE_BM25_THRESHOLD value: %r, using default 1.0",
            raw,
        )
        return 1.0


def get_truth_gate_spacy_sim_floor() -> float:
    """Return the minimum spaCy cosine similarity floor for numeric/org sentence validation.

    Env format:
      TRUTH_GATE_SPACY_SIM_FLOOR=0.10 (float, defaults to 0.10)

    When a sentence contains a numeric claim, year, dollar amount, or org name,
    and its spaCy cosine similarity to the article text is below this floor (and
    non-zero — zero means vectors unavailable), it is flagged as
    ``low_semantic_similarity``.  Default is very permissive (0.10) to avoid
    false positives; raise to 0.25–0.40 for stricter enforcement.
    """
    raw = os.getenv("TRUTH_GATE_SPACY_SIM_FLOOR", "").strip()
    if not raw:
        return 0.10
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        _truth_logger.warning(
            "Invalid TRUTH_GATE_SPACY_SIM_FLOOR value: %r, using default 0.10", raw
        )
        return 0.10


def get_whitelisted_phrases() -> set[str]:
    """Return a set of whitelisted phrases (case-insensitive, stripped) from env.
    
    Env format:
      TRUTH_GATE_WHITELISTED_PHRASES=what's up — sam here,hello world (comma-separated)
    
    Sentences matching any of these phrases will always be kept by the truth gate.
    """
    raw = os.getenv("TRUTH_GATE_WHITELISTED_PHRASES", "").strip()
    if not raw:
        return set()
    return {_normalize_phrase(part) for part in raw.split(",") if part.strip()}

def _normalize_phrase(phrase: str) -> str:
        """Normalize a phrase for robust comparison: lowercase, strip, remove trailing punctuation, normalize dashes, collapse whitespace."""
        import unicodedata
        s = phrase.strip().lower()
        # Normalize unicode dashes to hyphen-minus
        s = s.replace('—', '-').replace('–', '-')
        # Remove trailing punctuation (period, exclamation, question, comma, semicolon, colon)
        s = s.rstrip('.!?;,:")')
        # Collapse multiple spaces
        s = ' '.join(s.split())
        # Remove leading/trailing quotes
        s = s.strip('"\'')
        return s



def get_console_grounding_keywords() -> set[str]:
    """Return tech keywords used by console grounding from env with defaults."""
    raw = os.getenv("CONSOLE_GROUNDING_TECH_KEYWORDS", "").strip()
    if not raw:
        return set(DEFAULT_TECH_KEYWORDS)
    parsed = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return parsed or set(DEFAULT_TECH_KEYWORDS)



def get_console_grounding_tag_expansions_from_graph(domain_knowledge=None) -> dict[str, set[str]]:
    """
    Build tag expansion relationships from the domain knowledge graph.
    Each tag in a fact is expanded to include tags from related facts (via relationships).
    If domain_knowledge is None, attempts to load it from avatar_intelligence.
    """
    if domain_knowledge is None:
        try:
            from services.avatar_intelligence import load_avatar_state
            state = load_avatar_state()
            domain_knowledge = state.domain_knowledge
        except Exception:
            domain_knowledge = None
    if not domain_knowledge or not getattr(domain_knowledge, "facts", None):
        return {}

    # Build a map from fact id to tags
    fact_tags = {f.id: set(map(str.lower, f.tags)) for f in domain_knowledge.facts}
    expansions: dict[str, set[str]] = {}

    # For each relationship, expand from source fact's tags to target fact's tags
    for rel in getattr(domain_knowledge, "relationships", []):
        from_tags = fact_tags.get(rel.from_fact_id, set())
        to_tags = fact_tags.get(rel.to_fact_id, set())
        for tag in from_tags:
            if tag not in expansions:
                expansions[tag] = set()
            expansions[tag].update(to_tags)
    return expansions


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
    reason_codes: list[str] = field(default_factory=list)  # one entry per removed sentence
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

    # Detect knowledge / explanation queries that should route to domain facts
    require_domain_knowledge = any(phrase in q for phrase in DOMAIN_KNOWLEDGE_PHRASES)

    active_keywords = tech_keywords if tech_keywords is not None else get_console_grounding_keywords()
    tags: set[str] = set()
    for kw in active_keywords:
        if kw in q:
            tags.add(kw)

    # Expand detected tags into related tags for better retrieval quality.

    # Use new graph-driven expansions
    expansions = tag_expansions if tag_expansions is not None else get_console_grounding_tag_expansions_from_graph()
    for base_tag, related in expansions.items():
        if base_tag in tags:
            tags.update(related)

    return QueryConstraints(
        require_projects=require_projects,
        require_companies=require_companies,
        require_domain_knowledge=require_domain_knowledge,
        tech_tags=tags,
    )


def retrieve_relevant_facts(facts: list[ProjectFact], constraints: QueryConstraints, limit: int = 8) -> list[ProjectFact]:
    if not facts:
        return []

    _is_domain = lambda f: f.source.startswith("domain:") or f.company == "Domain Knowledge"

    scored: list[tuple[int, ProjectFact]] = []
    for fact in facts:
        score = 0
        if constraints.tech_tags:
            score += len(fact.tags.intersection(constraints.tech_tags)) * 5
        if constraints.require_projects and not _is_domain(fact):
            score += 1
        if constraints.require_companies and fact.company and not _is_domain(fact):
            score += 2
        # Boost domain-knowledge facts when the query is knowledge-seeking
        if constraints.require_domain_knowledge and _is_domain(fact):
            score += 4
        # Suppress domain facts when the query is strictly project/company-focused
        if (constraints.require_projects or constraints.require_companies) and not constraints.require_domain_knowledge and _is_domain(fact):
            score -= 2
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
        if constraints.require_domain_knowledge:
            return (
                "I don't have confirmed domain knowledge records for that topic. "
                "Try asking about a specific technology (e.g. RAG, BM25, microservices, LLM)."
            )
        return (
            "I don't have confirmed project/company records for that request in the loaded profile context. "
            "Try asking with a specific technology or company keyword."
        )

    _is_domain = lambda f: f.source.startswith("domain:") or f.company == "Domain Knowledge"

    domain_facts = [f for f in facts if _is_domain(f)]
    project_facts = [f for f in facts if not _is_domain(f)]

    lines: list[str] = []

    if project_facts:
        lines.append("Here are the projects I can confirm from loaded profile context:")
        for f in project_facts:
            lines.append(f"- Project: {f.project}")
            if constraints.require_companies or f.company:
                lines.append(f"  Company: {f.company}")
            lines.append(f"  Years: {f.years}")
            lines.append(f"  Why relevant: {f.details}")
            lines.append(f"  [source: {f.source}]")

    if domain_facts:
        if project_facts:
            lines.append("")
        lines.append("Here is what I know from domain knowledge:")
        for f in domain_facts:
            lines.append(f"- Topic: {f.project}")
            lines.append(f"  Fact: {f.details}")
            lines.append(f"  Tags: {', '.join(sorted(f.tags)) if f.tags else 'n/a'}")
            lines.append(f"  [source: {f.source}]")

    if constraints.tech_tags:
        lines.append(f"\nFilter applied: {', '.join(sorted(constraints.tech_tags))}")
    return "\n".join(lines)


def build_grounding_facts_block(facts: list[ProjectFact], limit: int | None = None) -> str:
    """Build a compact deterministic facts block for generation prompts.

    ``limit`` defaults to EVIDENCE_PROJECT_COUNT + EVIDENCE_DOMAIN_COUNT from .env
    (falling back to 5) so the display cap always matches the retrieval split.
    """
    if limit is None:
        try:
            limit = int(os.getenv("EVIDENCE_PROJECT_COUNT", "3")) + int(os.getenv("EVIDENCE_DOMAIN_COUNT", "2"))
        except Exception:
            limit = 5
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


def get_domain_facts_from_avatar_state() -> list[ProjectFact]:
    """Load domain facts from avatar state if available.
    
    Returns a list of ProjectFact objects representing domain knowledge.
    Uses lazy import to avoid circular dependency.
    Returns empty list if avatar state is not loaded or has no domain knowledge.
    """
    try:
        from services.avatar_intelligence import (
            load_avatar_state,
            normalize_domain_facts,
            domain_facts_to_project_facts,
        )
        state = load_avatar_state()
        if not state.domain_knowledge:
            return []
        domain_evidence_facts = normalize_domain_facts(state)
        return domain_facts_to_project_facts(domain_evidence_facts)
    except Exception as exc:
        _truth_logger.debug("Failed to load domain facts: %s", exc)
        return []


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
    Domain-wide terms (e.g. 'llm', 'ai') are always allowed — they apply
    broadly across all projects and should not trigger misattribution.
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


def _tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize text for BM25 scoring.
    
    Uses the same tokenization pattern as avatar_intelligence.py for consistency.
    Returns lowercased tokens of 2+ alphanumeric characters.
    """
    return re.findall(r"[a-zA-Z0-9_+#.-]{2,}", text.lower())


def _score_sentence_bm25(
    sentence: str,
    article_text: str,
    facts: list[ProjectFact],
) -> float:
    """Score a sentence against article text and persona facts using BM25.
    
    Returns the BM25 score for the sentence. Higher scores indicate stronger
    evidence support. Returns 0.0 if BM25 is unavailable or corpus is empty.
    """
    if not _BM25_AVAILABLE:
        return 0.0
    
    # Build corpus from article text and facts
    corpus_docs: list[str] = [article_text]
    for fact in facts:
        corpus_docs.append(f"{fact.project} {fact.company} {fact.years} {fact.details}")
    
    if not corpus_docs:
        return 0.0
    
    try:
        # Tokenize corpus
        tokenized_corpus = [_tokenize_for_bm25(doc) for doc in corpus_docs]
        
        # Build BM25 index
        bm25 = _BM25Okapi(tokenized_corpus)
        
        # Tokenize and score the sentence
        sentence_tokens = _tokenize_for_bm25(sentence)
        if not sentence_tokens:
            return 0.0
        
        # Get scores for all documents and return the max score
        # (we want to know if the sentence matches ANY document in the corpus)
        scores = bm25.get_scores(sentence_tokens)
        return float(max(scores)) if len(scores) > 0 else 0.0
    except Exception as exc:
        _truth_logger.debug("BM25 scoring failed for sentence: %s", exc)
        return 0.0


def _compute_fact_overlap(sentence_tokens: set[str], fact_tokens: set[str]) -> float:
    """Compute Jaccard token overlap between sentence and fact token sets.

    Returns a value in [0, 1].  Returns 0.0 when either set is empty, which is
    also the sentinel value used when overlap is not computed (overlap=0.0 on
    EvidencePath triggers the 3-term DoT fallback formula instead of the richer
    4-term formula).
    """
    if not sentence_tokens or not fact_tokens:
        return 0.0
    intersection = len(sentence_tokens & fact_tokens)
    union = len(sentence_tokens | fact_tokens)
    return intersection / union if union > 0 else 0.0


def _build_evidence_paths_for_sentence(
    sentence: str,
    all_facts: list[ProjectFact],
) -> list["EvidencePath"]:  # type: ignore[name-defined]
    """Build EvidencePath objects for a sentence with proper source annotation and overlap.

    Part A implementation: computes Jaccard token overlap between the sentence
    and each fact's text, and infers evidence_type / credibility from the fact's
    source prefix so the 4-term DoT formula activates when overlap > 0.

    Returns an empty list when DoT is not importable or no facts are provided.
    """
    if not all_facts:
        return []
    try:
        from services.derivative_of_truth import (
            EvidencePath,
            EVIDENCE_TYPE_PRIMARY,
            EVIDENCE_TYPE_SECONDARY,
            REASONING_TYPE_LOGICAL,
            REASONING_TYPE_STATISTICAL,
        )
    except ImportError:
        return []

    sent_tokens = set(_tokenize_for_bm25(sentence))
    paths: list[EvidencePath] = []

    for fact in all_facts:
        fact_text = f"{fact.project} {fact.details}"
        fact_tokens = set(_tokenize_for_bm25(fact_text))
        overlap = _compute_fact_overlap(sent_tokens, fact_tokens)

        # Infer evidence type and credibility from the fact source prefix.
        src_lower = fact.source.lower()
        if src_lower.startswith("profile_context") or src_lower.startswith("avatar:"):
            evidence_type = EVIDENCE_TYPE_PRIMARY
            credibility = 0.90
        elif src_lower.startswith("domain:"):
            evidence_type = EVIDENCE_TYPE_SECONDARY
            credibility = 0.70
        else:
            evidence_type = EVIDENCE_TYPE_SECONDARY
            credibility = 0.60

        # Infer reasoning type from tags.
        tag_set = {t.lower() for t in fact.tags}
        if any(t in tag_set for t in ("statistics", "benchmark", "performance", "measured", "data")):
            reasoning_type = REASONING_TYPE_STATISTICAL
        else:
            reasoning_type = REASONING_TYPE_LOGICAL

        paths.append(
            EvidencePath(
                source=fact.source,
                evidence_type=evidence_type,
                reasoning_type=reasoning_type,
                credibility=credibility,
                overlap=overlap,
            )
        )

    return paths


def _extract_spacy_orgs(sentence: str, spacy_nlp: object) -> list[str]:
    """Extract ORG named entities from a sentence using spaCy NER.

    Part D implementation: returns a list of org-name strings (original case).
    Returns an empty list when spaCy is unavailable or the model has no NER.
    Callers fall back to the ``_ORG_NAME_RE`` regex when this returns [].
    """
    try:
        nlp = spacy_nlp._ensure_model()  # type: ignore[union-attr]
        if nlp is None:
            return []
        doc = nlp(sentence)
        return [ent.text for ent in doc.ents if ent.label_ == "ORG"]
    except Exception as exc:
        _truth_logger.debug("spaCy org extraction failed: %s", exc)
        return []


def truth_gate_result(
    text: str,
    article_text: str,
    facts: list[ProjectFact],
    interactive: bool = False,
    article_ref: str = "",
    channel: str = "linkedin",
    suggest_facts: bool = True,
) -> tuple[str, TruthGateMeta]:
    """Truth gate that returns both the filtered text and scoring metadata.

    Identical logic to :func:`truth_gate` but also returns a :class:`TruthGateMeta`
    with removed_count, total_sentences, and reason_codes so callers can feed
    the metadata into confidence scoring (Phase 1C).

    When *interactive* is True, user decisions are still recorded to the
    learning log exactly as in :func:`truth_gate`.
    
    When *suggest_facts* is True, uses spaCy to suggest matching facts from the
    persona graph for sentences that are dropped by the truth gate.
    """
    if not text:
        return text, TruthGateMeta(removed_count=0, total_sentences=0)

    _truth_logger.debug("Truth gate called for channel=%s", channel)
    
    # Include domain facts as evidence sources alongside project facts
    domain_facts = get_domain_facts_from_avatar_state()
    all_facts = facts + domain_facts
    _truth_logger.debug("Truth gate using %d project facts + %d domain facts", len(facts), len(domain_facts))
    
    allowed = _build_allowed_tokens(article_text, all_facts)
    tech_keywords = get_console_grounding_keywords()
    project_map = _build_project_tech_map(all_facts, article_text)
    sentences = _SENTENCE_SPLIT_RE.split(text)
    kept: list[str] = []
    removed: list[tuple[str, str]] = []  # (full_sentence, reason)

    # Load spaCy NLP — used for org NER (Part D), semantic similarity (Part C),
    # and interactive fact suggestions.  Loaded unconditionally so Parts C and D
    # always get the chance to run regardless of the suggest_facts flag.
    spacy_nlp = None
    try:
        from services.spacy_nlp import get_spacy_nlp
        spacy_nlp = get_spacy_nlp()
    except Exception as _nlp_exc:
        _truth_logger.debug("spaCy NLP unavailable: %s", _nlp_exc)

    # Get BM25 threshold for weak evidence detection
    bm25_threshold = get_truth_gate_bm25_threshold()
    # spaCy similarity floor for numeric/org sentence semantic check (Part C)
    spacy_sim_floor = get_truth_gate_spacy_sim_floor()

    # Per-sentence DoT state (Parts A + B)
    dot_per_sentence_scores: list[float] = []
    spacy_sim_scores: dict[str, float] = {}

    # Pre-import DoT scoring function once for reuse in the sentence loop (Part B)
    # and the full-post post-hoc scoring block (Part A).
    _dot_score_fn = None
    try:
        from services.derivative_of_truth import score_claim_with_truth_gradient as _dot_score_fn
    except ImportError:
        _truth_logger.debug("DoT unavailable — per-sentence and full-post scoring skipped")

    whitelisted_phrases = get_whitelisted_phrases()
    for sentence in sentences:
        # Always keep sentences that are only hashtags, only URLs, empty/whitespace, questions, or whitelisted phrases
        stripped = sentence.strip()
        if not stripped:
            kept.append(sentence)
            continue
        # Whitelisted phrases (case-insensitive, stripped)
        if _normalize_phrase(stripped) in whitelisted_phrases:
            kept.append(sentence)
            continue
        # Only hashtags (e.g., '#Tag #AnotherTag')
        if all(word.startswith('#') for word in stripped.split()):
            kept.append(sentence)
            continue
        # Only URL(s)
        import re as _re
        url_pattern = _re.compile(r'^(https?://\S+)$')
        if all(url_pattern.match(word) for word in stripped.split()):
            kept.append(sentence)
            continue
        # Any sentence containing a URL should be preserved (CTA/source links)
        if _re.search(r"https?://\S+", stripped):
            kept.append(sentence)
            continue
        # Questions (ending with '?')
        if stripped.endswith('?'):
            kept.append(sentence)
            continue
        reason: str | None = None
        # BM25 evidence strength check (if available)
        # This provides a flexible, context-aware validation that catches
        # paraphrased or weakly supported claims that strict token matching might miss
        if _BM25_AVAILABLE and (article_text or all_facts):
            bm25_score = _score_sentence_bm25(sentence, article_text, all_facts)
            if bm25_score < bm25_threshold:
                reason = f"weak_evidence_bm25: score={bm25_score:.2f} < threshold={bm25_threshold}"

        # Part C: spaCy semantic similarity floor.
        # Only fires for sentences containing numeric/org-like claims (reduces false positives).
        # sim==0.0 means spaCy vectors are unavailable — skip the check in that case.
        if not reason and spacy_nlp and article_text:
            _has_specific_claim = (
                _NUMERIC_CLAIM_RE.search(stripped)
                or _YEAR_RE.search(stripped)
                or _DOLLAR_RE.search(stripped)
                or _ORG_NAME_RE.search(stripped)
            )
            if _has_specific_claim:
                _sim = spacy_nlp.compute_similarity(sentence, article_text)
                spacy_sim_scores[sentence] = _sim
                if 0.0 < _sim < spacy_sim_floor:
                    reason = f"low_semantic_similarity: sim={_sim:.3f} < floor={spacy_sim_floor:.2f}"

        # Strict token-matching checks for specific claim types
        # These complement BM25 by catching exact numeric/org mismatches
        if not reason:
            for m in _NUMERIC_CLAIM_RE.finditer(sentence):
                full_token = m.group(0).lower().strip()
                num_token = re.match(r"[\d,.]+", m.group(0))
                if num_token and full_token not in allowed and num_token.group(0).lower().rstrip(".") not in allowed:
                    reason = f"unsupported_numeric: '{m.group(0)}'"
                    break

        if not reason:
            for m in _YEAR_RE.finditer(sentence):
                if m.group(0) not in allowed:
                    reason = f"unsupported_year: '{m.group(0)}'"
                    break

        if not reason:
            for m in _DOLLAR_RE.finditer(sentence):
                nearby = sentence[m.start():m.start()+20]
                num = re.search(r"\d[\d,.]*", nearby)
                if num and num.group(0).lower().rstrip(".") not in allowed:
                    reason = f"unsupported_dollar: '{nearby.strip()}'"
                    break

        if not reason:
            # Part D: spaCy NER org-name check (falls back to _ORG_NAME_RE regex).
            # spaCy NER has higher recall for single-word brands, all-caps names,
            # and abbreviations that the regex misses.
            _spacy_orgs = _extract_spacy_orgs(sentence, spacy_nlp) if spacy_nlp else []
            if _spacy_orgs:
                for _org in _spacy_orgs:
                    _org_lower = _org.lower()
                    if _org_lower not in allowed:
                        _org_words = [w for w in re.findall(r"\w+", _org_lower) if len(w) > 1]
                        if not all(word in allowed for word in _org_words):
                            reason = f"unsupported_org: '{_org}'"
                            break
            else:
                # Fallback: regex when spaCy unavailable or finds no ORG entities
                for m in _ORG_NAME_RE.finditer(sentence):
                    org_phrase = m.group(1).lower()
                    if org_phrase not in allowed:
                        # Allow if all words in org name are present in allowed evidence
                        org_words = [w for w in re.findall(r"\w+", org_phrase) if len(w) > 1]
                        if not all(word in allowed for word in org_words):
                            reason = f"unsupported_org: '{m.group(1)}'"
                            break

        if not reason:
            reason = _check_project_claim(sentence, project_map, tech_keywords)

        # Part B: per-sentence DoT scoring — active filter for weakly-supported claims.
        # Runs only when a sentence would otherwise be kept; flags it with
        # 'weak_dot_gradient' when the truth gradient falls below the threshold.
        if not reason and all_facts and _dot_score_fn is not None:
            try:
                _sent_paths = _build_evidence_paths_for_sentence(sentence, all_facts)
                if _sent_paths:
                    _sent_dot = _dot_score_fn(sentence, _sent_paths)
                    dot_per_sentence_scores.append(_sent_dot.truth_gradient)
                    if _sent_dot.flagged:
                        reason = (
                            f"weak_dot_gradient: gradient={_sent_dot.truth_gradient:.3f}"
                        )
                        _truth_logger.debug(
                            "DoT per-sentence flagged: gradient=%.3f sentence='%s...'",
                            _sent_dot.truth_gradient,
                            sentence[:60],
                        )
            except Exception as _dot_sent_exc:
                _truth_logger.debug("Per-sentence DoT failed: %s", _dot_sent_exc)

        if reason:
            if interactive:
                print(f"\n⚠️  Truth gate flagged sentence:")
                print(f"    Reason : {reason}")
                print(f"    Sentence: {sentence}")
                
                # Suggest matching facts using spaCy if enabled
                if suggest_facts and spacy_nlp and all_facts:
                    try:
                        fact_texts = [f"{f.project} | {f.details}" for f in all_facts]
                        suggestions = spacy_nlp.suggest_matching_facts(
                            dropped_sentence=sentence,
                            available_facts=fact_texts,
                            top_n=3,
                        )
                        if suggestions:
                            print(f"\n    💡 Suggested facts to support this claim:")
                            for i, sugg in enumerate(suggestions, 1):
                                print(f"       {i}. [{sugg['similarity']:.2f}] {sugg['fact'][:80]}...")
                                print(f"          → {sugg['suggestion']}")
                    except Exception as _sugg_exc:
                        _truth_logger.debug("Fact suggestion failed: %s", _sugg_exc)
                
                try:
                    answer = input("    Remove this sentence? [y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = "n"
                user_removed = answer in ("y", "yes")
                if user_removed:
                    removed.append((sentence, reason))
                else:
                    kept.append(sentence)
                decision = "removed" if user_removed else "kept"
                try:
                    from services.avatar_intelligence import record_moderation_event
                    record_moderation_event(
                        sentence=sentence,
                        reason_code=reason.split(":")[0],
                        decision=decision,
                        channel=channel,
                        article_ref=article_ref,
                    )
                except Exception as _log_exc:  # noqa: BLE001
                    _truth_logger.warning("Failed to record moderation event: %s", _log_exc)
            else:
                removed.append((sentence, reason))
        else:
            kept.append(sentence)

    if removed:
        for full_sentence, reason in removed:
            _truth_logger.info(
                "%s🛑 Truth gate removed [channel=%s] [%s]: %s%s",
                str(Fore.RED),
                channel,
                reason,
                full_sentence,
                str(Style.RESET_ALL),
            )
        _truth_logger.info(
            "%s⚖️  Truth gate summary [channel=%s]: removed %d of %d sentences%s",
            str(Fore.YELLOW),
            channel,
            len(removed),
            len(sentences),
            str(Style.RESET_ALL),
        )
    else:
        _truth_logger.debug(
            "Truth gate [channel=%s]: no sentences removed (%d total sentences)",
            channel,
            len(sentences),
        )

    meta = TruthGateMeta(
        removed_count=len(removed),
        total_sentences=len(sentences),
        reason_codes=[r.split(":")[0] for _, r in removed],
        dot_per_sentence_scores=dot_per_sentence_scores,
        spacy_sim_scores=spacy_sim_scores,
    )

    # --- Derivative of Truth scoring on the kept post text (Part A) ---
    # Uses _build_evidence_paths_for_sentence so that EvidencePath.overlap is
    # populated, activating the 4-term DoT formula instead of the 3-term fallback.
    try:
        if _dot_score_fn is None:
            raise ImportError("DoT not imported")
        kept_text = " ".join(kept).strip()
        ev_paths = _build_evidence_paths_for_sentence(kept_text, all_facts) if all_facts else []
        _dot = _dot_score_fn(kept_text, ev_paths)
        meta.truth_gradient = _dot.truth_gradient
        meta.dot_uncertainty = _dot.uncertainty
        meta.dot_flagged = _dot.flagged
        meta.dot_uncertainty_sources = _dot.uncertainty_sources
        if _dot.flagged:
            _truth_logger.warning(
                "DoT: truth gradient %.3f below threshold — post flagged (channel=%s)",
                _dot.truth_gradient,
                channel,
            )
        else:
            _truth_logger.debug(
                "DoT: truth gradient=%.3f uncertainty=%.3f (channel=%s)",
                _dot.truth_gradient,
                _dot.uncertainty,
                channel,
            )
    except Exception as _dot_exc:
        _truth_logger.debug("DoT scoring unavailable: %s", _dot_exc)

    return " ".join(kept).strip(), meta


def truth_gate(
    text: str,
    article_text: str,
    facts: list[ProjectFact],
    interactive: bool = False,
    article_ref: str = "",
    channel: str = "linkedin",
    suggest_facts: bool = True,
) -> str:
    """Lightweight post-generation truth gate.

    Scans each sentence in *text* for:
    1. Numeric claims, year references, dollar amounts, and company-name
       patterns whose key token does NOT appear in the article or facts.
    2. Project-technology misattributions — when a sentence names a known
       project but pairs it with a tech keyword that does not appear in
       that project's detail or the article text.

    When *interactive* is True, each flagged sentence is presented to the
    user for confirmation before removal.  Interactive decisions are recorded
    in the avatar learning log when the avatar module is available.

    *article_ref* and *channel* are forwarded to the learning log for context.

    Returns the filtered text (may be identical to input if nothing was stripped).
    
    When *suggest_facts* is True, uses spaCy to suggest matching facts from the
    persona graph for sentences that are dropped by the truth gate (interactive mode only).
    """
    filtered, _ = truth_gate_result(
        text=text,
        article_text=article_text,
        facts=facts,
        interactive=interactive,
        article_ref=article_ref,
        channel=channel,
        suggest_facts=suggest_facts,
    )
    return filtered
