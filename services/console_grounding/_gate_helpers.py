"""Internal helpers for the truth gate: regex constants, BM25/token scoring,
Jaccard overlap, EvidencePath builders, spaCy org extraction, and avatar
state loaders."""

from __future__ import annotations

import logging
import re

from services.console_grounding._models import ProjectFact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BM25 optional import
# ---------------------------------------------------------------------------

try:
    from rank_bm25 import BM25Okapi as _BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BM25_AVAILABLE = False

# ---------------------------------------------------------------------------
# Regex constants for claim detection
# ---------------------------------------------------------------------------

_NUMERIC_CLAIM_RE = re.compile(
    r"\d+(?:\.\d+)?(?:\s*[%x×]"
    r"|\s*(?:percent|million|billion|thousand|ms|seconds?|minutes?|hours?)"
    r"|\s*(?:faster|slower|reduction|improvement|increase|decrease)"
    r")",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_DOLLAR_RE = re.compile(r"\$\s?\d")

# Company-name heuristic: two+ capitalised words preceded by a preposition.
# spaCy NER (Part D) supersedes this when available.
_ORG_NAME_RE = re.compile(
    r"\b(?:at|for|with|from|joined)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# ---------------------------------------------------------------------------
# Avatar state loaders (lazy — avoids circular import)
# ---------------------------------------------------------------------------

def get_domain_facts_from_avatar_state() -> list[ProjectFact]:
    """Load domain facts from avatar state for use as evidence in the truth gate."""
    try:
        from services.avatar_intelligence import (
            load_avatar_state,
            normalize_domain_facts,
            domain_facts_to_project_facts,
        )
        state = load_avatar_state()
        if not state.domain_knowledge:
            return []
        return domain_facts_to_project_facts(normalize_domain_facts(state))
    except Exception as exc:
        logger.debug("Failed to load domain facts: %s", exc)
        return []


def get_all_persona_facts_from_avatar_state() -> list[ProjectFact]:
    """Load *all* persona/evidence facts for token allowlisting.

    Used so that numeric claims established anywhere in the persona are never
    blocked by the truth gate, regardless of the top-N retrieved for the article.
    """
    try:
        from services.avatar_intelligence import (
            load_avatar_state,
            normalize_evidence_facts,
            evidence_facts_to_project_facts,
        )
        state = load_avatar_state()
        return evidence_facts_to_project_facts(normalize_evidence_facts(state))
    except Exception as exc:
        logger.debug("Failed to load all persona facts for allowlist: %s", exc)
        return []

# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _tokenize_for_bm25(text: str) -> list[str]:
    """Return lowercased tokens of 2+ alphanumeric characters."""
    return re.findall(r"[a-zA-Z0-9_+#.-]{2,}", text.lower())


def _build_allowed_tokens(article_text: str, facts: list[ProjectFact]) -> set[str]:
    """Build a set of lowercased tokens considered 'allowed' evidence."""
    allowed: set[str] = set()
    sources = [article_text]
    for f in facts:
        sources.append(f"{f.project} {f.company} {f.years} {f.details}")
    for src in sources:
        for m in re.finditer(r"\d[\d,.*]*\w*", src):
            allowed.add(m.group(0).lower().rstrip("."))
        for m in re.finditer(r"(19|20)\d{2}(?:\s*[-–]\s*(19|20)?\d{2})?", src):
            allowed.add(m.group(0).replace(" ", "").lower())
        for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", src):
            allowed.add(m.group(0).lower())
        for w in re.findall(r"\b\w{3,}\b", src):
            allowed.add(w.lower())
    return allowed


def _build_project_tech_map(
    facts: list[ProjectFact],
    article_text: str,
) -> dict[str, str]:
    """Map each project name (lowercased) to its concatenated evidence text."""
    article_lower = article_text.lower()
    return {
        fact.project.lower(): f"{fact.project} {fact.details}".lower() + " " + article_lower
        for fact in facts
    }


def _check_project_claim(
    sentence: str,
    project_map: dict[str, str],
    tech_keywords: set[str],
) -> str | None:
    """Return a reason string if the sentence falsely links a tech to a project."""
    sent_lower = sentence.lower()
    for project_name, evidence_text in project_map.items():
        if project_name not in sent_lower:
            continue
        for kw in tech_keywords:
            if kw in sent_lower and kw not in evidence_text:
                return (
                    f"project_claim: '{kw}' attributed to "
                    f"'{project_name}' but not in its detail or article"
                )
    return None

# ---------------------------------------------------------------------------
# BM25 sentence scoring
# ---------------------------------------------------------------------------

def _score_sentence_bm25(
    sentence: str,
    article_text: str,
    facts: list[ProjectFact],
) -> float:
    """Score a sentence against article text and persona facts using BM25."""
    if not _BM25_AVAILABLE:
        return 0.0
    corpus_docs: list[str] = [article_text] + [
        f"{f.project} {f.company} {f.years} {f.details}" for f in facts
    ]
    try:
        tokenized_corpus = [_tokenize_for_bm25(doc) for doc in corpus_docs]
        bm25 = _BM25Okapi(tokenized_corpus)
        sentence_tokens = _tokenize_for_bm25(sentence)
        if not sentence_tokens:
            return 0.0
        scores = bm25.get_scores(sentence_tokens)
        return float(max(scores)) if len(scores) > 0 else 0.0
    except Exception as exc:
        logger.debug("BM25 scoring failed for sentence: %s", exc)
        return 0.0

# ---------------------------------------------------------------------------
# Jaccard overlap + EvidencePath builder
# ---------------------------------------------------------------------------

def _compute_fact_overlap(sentence_tokens: set[str], fact_tokens: set[str]) -> float:
    """Compute Jaccard token overlap between sentence and fact token sets.

    Returns a value in [0, 1].  Returns 0.0 when either set is empty.  A
    non-zero overlap activates the 4-term DoT formula instead of the 3-term
    fallback.
    """
    if not sentence_tokens or not fact_tokens:
        return 0.0
    intersection = len(sentence_tokens & fact_tokens)
    union = len(sentence_tokens | fact_tokens)
    return intersection / union if union > 0 else 0.0


def _build_evidence_paths_for_sentence(
    sentence: str,
    all_facts: list[ProjectFact],
) -> list:  # list[EvidencePath] — type not imported at module level to avoid circular deps
    """Build EvidencePath objects for a sentence with overlap and source annotation.

    Part A implementation: computes Jaccard token overlap between the sentence and
    each fact's text so the 4-term DoT formula activates when overlap > 0.

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
    paths = []
    for fact in all_facts:
        fact_tokens = set(_tokenize_for_bm25(f"{fact.project} {fact.details}"))
        overlap = _compute_fact_overlap(sent_tokens, fact_tokens)
        src_lower = fact.source.lower()
        if src_lower.startswith("profile_context") or src_lower.startswith("avatar:"):
            evidence_type, credibility = EVIDENCE_TYPE_PRIMARY, 0.90
        elif src_lower.startswith("domain:"):
            evidence_type, credibility = EVIDENCE_TYPE_SECONDARY, 0.70
        else:
            evidence_type, credibility = EVIDENCE_TYPE_SECONDARY, 0.60
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

# ---------------------------------------------------------------------------
# spaCy ORG extraction
# ---------------------------------------------------------------------------

# Abbreviations that are concepts/fields, not company names.
_CONCEPT_ABBREVS: frozenset[str] = frozenset({
    "AGI", "AI", "ML", "DL", "NLP", "LLM", "LLMs", "RAG", "RL", "RLHF",
    "API", "APIs", "SDK", "CLI", "UI", "UX", "DB", "SQL", "NoSQL",
    "CI", "CD", "DevOps", "SRE", "SLA", "SLO",
    "IoT", "AR", "VR", "XR",
})


def _extract_spacy_orgs(sentence: str, spacy_nlp: object) -> list[str]:
    """Extract ORG named entities from a sentence using spaCy NER.

    Part D implementation: returns a list of org-name strings (original case).
    Returns an empty list when spaCy is unavailable or the model has no NER.
    Callers fall back to ``_ORG_NAME_RE`` regex when this returns [].

    Known AI/tech concept abbreviations (AGI, LLM, NLP, etc.) are excluded even
    when spaCy mistakenly tags them as ORG entities.
    """
    try:
        nlp = spacy_nlp._ensure_model()  # type: ignore[union-attr]
        if nlp is None:
            return []
        doc = nlp(sentence)
        return [
            ent.text for ent in doc.ents
            if ent.label_ == "ORG" and ent.text not in _CONCEPT_ABBREVS
        ]
    except Exception as exc:
        logger.debug("spaCy org extraction failed: %s", exc)
        return []
