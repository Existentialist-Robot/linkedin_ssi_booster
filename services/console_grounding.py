
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
    """Metadata about what truth_gate evaluated — used for confidence scoring (Phase 1C)."""

    removed_count: int
    total_sentences: int
    reason_codes: list[str] = field(default_factory=list)  # one entry per removed sentence


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
    
    # Lazy import spaCy NLP for fact suggestion
    spacy_nlp = None
    if suggest_facts and facts:
        try:
            from services.spacy_nlp import get_spacy_nlp
            spacy_nlp = get_spacy_nlp()
        except Exception as _nlp_exc:
            _truth_logger.debug("spaCy NLP unavailable for fact suggestion: %s", _nlp_exc)

    # Get BM25 threshold for weak evidence detection
    bm25_threshold = get_truth_gate_bm25_threshold()
    
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

        if reason:
            if interactive:
                print(f"\n⚠️  Truth gate flagged sentence:")
                print(f"    Reason : {reason}")
                print(f"    Sentence: {sentence}")
                
                # Suggest matching facts using spaCy if enabled
                if spacy_nlp and all_facts:
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
            _truth_logger.info("Truth gate removed [channel=%s] [%s]: %s", channel, reason, full_sentence)
        _truth_logger.info(
            "Truth gate summary [channel=%s]: removed %d of %d sentences",
            channel,
            len(removed),
            len(sentences),
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
    )
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
