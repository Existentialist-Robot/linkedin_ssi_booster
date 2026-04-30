"""Continual learning — NLP extraction pipeline for avatar_intelligence."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.avatar_intelligence._loaders import _load_extracted_knowledge
from services.avatar_intelligence._models import (
    ExtractedFact,
    ExtractedKnowledgeGraph,
)
from services.avatar_intelligence._paths import EXTRACTED_KNOWLEDGE_PATH

logger = logging.getLogger(__name__)

_EXTRACTION_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "that", "this", "it", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "will", "would", "can", "could",
    "should", "may", "might", "by", "from", "as", "about", "into", "through",
})


def _make_extracted_evidence_id(fact_id: str, run_index: int) -> str:
    """Return a stable, short evidence ID based on extracted fact ID and run index.

    IDs are stable per run for the same input order:
    X{index:03d}-{6-char fact hash}
    """
    fact_hash = hashlib.sha256(fact_id.encode()).hexdigest()[:6]
    return f"X{run_index:03d}-{fact_hash}"


def _make_extracted_fact_id(source_url: str, statement: str) -> str:
    """Return a stable 12-char SHA-256 hex ID from source_url + statement.

    Used as the deduplication key for extracted facts.
    """
    raw = f"{source_url}||{statement}"
    return "ext-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def save_extracted_knowledge(
    graph: ExtractedKnowledgeGraph,
    path: Path | None = None,
) -> None:
    """Persist *graph* to *path* (defaults to ``EXTRACTED_KNOWLEDGE_PATH``).

    Failures emit a warning so the caller is never interrupted.
    """
    target = path or EXTRACTED_KNOWLEDGE_PATH
    payload: dict[str, Any] = {
        "schemaVersion": graph.schema_version,
        "facts": [asdict(f) for f in graph.facts],
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.debug(
            "Extracted knowledge saved to %s (%d facts)", target, len(graph.facts)
        )
    except OSError as exc:
        logger.warning("Extracted knowledge save failed (continuing): %s", exc)


def extract_and_append_knowledge(
    article_text: str,
    source_url: str,
    source_title: str,
    *,
    min_sentence_len: int = 40,
    max_facts_per_article: int = 5,
    confidence: str = "medium",
    path: Path | None = None,
    dry_run: bool = False,
) -> list[ExtractedFact]:
    """Extract facts from *article_text* using SpacyNLP and append them to extracted_knowledge.json.

    Pipeline:
    1. Split article_text into sentences (regex-based).
    2. For each sentence of sufficient length, attempt spaCy theme extraction.
    3. Deduplicate against existing facts using SHA-256 content hash.
    4. Append new facts to the on-disk extracted_knowledge.json.

    Args:
        article_text:          Full article text to extract from.
        source_url:            URL of the originating article.
        source_title:          Title of the originating article.
        min_sentence_len:      Minimum sentence character length to consider.
        max_facts_per_article: Maximum new facts to extract from one article.
        confidence:            Confidence level to assign: 'high' | 'medium' | 'low'.
        path:                  Override path to extracted_knowledge.json (for testing).
        dry_run:               If True, extract but do not write to disk.

    Returns:
        List of newly-appended ExtractedFact objects (empty if all were duplicates or dry_run).
    """
    target = path or EXTRACTED_KNOWLEDGE_PATH

    existing_graph, load_errors = _load_extracted_knowledge(target)
    if load_errors and "not found" in load_errors[0]:
        existing_graph = ExtractedKnowledgeGraph(schema_version="1.0", facts=[])
    elif existing_graph is None:
        logger.warning(
            "extract_and_append_knowledge: could not load existing graph — %s", load_errors
        )
        existing_graph = ExtractedKnowledgeGraph(schema_version="1.0", facts=[])

    existing_ids: set[str] = {f.id for f in existing_graph.facts}

    # Strip HTML tags and decode common entities before extracting facts.
    clean_text = re.sub(r"<[^>]+>", " ", article_text)
    clean_text = re.sub(r"&[a-zA-Z]+;", " ", clean_text)
    clean_text = re.sub(r"&#\d+;", " ", clean_text)
    clean_text = re.sub(r"\[\s*[^\]]{0,20}\s*\]", " ", clean_text)
    clean_text = re.sub(
        r"The post .+? appeared first on .+?\s*\.",
        " ",
        clean_text,
        flags=re.IGNORECASE,
    )
    clean_text = re.sub(r"\s{2,}", " ", clean_text).strip()

    if len(clean_text) < 40:
        logger.debug(
            "extract_and_append_knowledge: no usable text after HTML strip — skipping"
        )
        return []

    try:
        from services.spacy_nlp import get_spacy_nlp
        nlp_engine = get_spacy_nlp()
        spacy_available = True
    except Exception:
        nlp_engine = None
        spacy_available = False

    sentences = re.split(r"(?<=[.!?])\s+", clean_text)
    new_facts: list[ExtractedFact] = []
    extracted_at = datetime.now(timezone.utc).isoformat()

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < min_sentence_len:
            continue
        if re.search(r"[<>]|&[a-zA-Z#]", sentence):
            continue
        if re.search(
            r"appeared first on|^The post\b|^From this\b", sentence, re.IGNORECASE
        ):
            continue
        if re.match(r"^[\w\s,\-]+,\s+and\s+more\.?$", sentence, re.IGNORECASE):
            continue
        if re.match(
            r"^(Have you ever|Did you know|Are you |Do you |What if |Ever wonder)",
            sentence,
            re.IGNORECASE,
        ):
            continue
        if re.match(
            r"^(It|They|This|That|These|Those)\s+(was|were|is|are|has|have|had|added|changed|became)\b",
            sentence,
            re.IGNORECASE,
        ):
            continue
        if len(new_facts) >= max_facts_per_article:
            break

        fact_id = _make_extracted_fact_id(source_url, sentence)
        if fact_id in existing_ids:
            logger.debug(
                "extract_and_append_knowledge: skipping duplicate fact %s", fact_id
            )
            continue

        entities: list[str] = []
        tags: list[str] = []
        if spacy_available and nlp_engine is not None:
            try:
                raw_themes = nlp_engine.extract_themes(sentence)
                tags = [t for t in raw_themes if len(t.split()) == 1][:8]
                entities = [t for t in raw_themes if len(t.split()) > 1][:5]
            except Exception as exc:
                logger.debug(
                    "extract_and_append_knowledge: spaCy extraction error — %s", exc
                )
        else:
            entities = list(dict.fromkeys(
                w for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", sentence)
                if w.lower() not in _EXTRACTION_STOPWORDS
            ))[:5]
            tags = list(dict.fromkeys(
                w.lower()
                for w in re.findall(r"\b[a-zA-Z]{4,}\b", sentence.lower())
                if w.lower() not in _EXTRACTION_STOPWORDS
            ))[:8]

        fact = ExtractedFact(
            id=fact_id,
            statement=sentence,
            source_url=source_url,
            source_title=source_title,
            extracted_at=extracted_at,
            entities=entities,
            tags=tags,
            confidence=confidence,
            extraction_method="spacy_nlp" if spacy_available else "regex_fallback",
        )
        new_facts.append(fact)
        existing_ids.add(fact_id)

    if new_facts and not dry_run:
        updated_facts = existing_graph.facts + new_facts
        updated_graph = ExtractedKnowledgeGraph(
            schema_version=existing_graph.schema_version,
            facts=updated_facts,
        )
        save_extracted_knowledge(updated_graph, path=target)
        logger.debug(
            "extract_and_append_knowledge: appended %d new fact(s) to %s (total: %d)",
            len(new_facts),
            target,
            len(updated_facts),
        )
    elif not new_facts:
        logger.debug(
            "extract_and_append_knowledge: no new facts extracted from '%s'", source_title
        )

    return new_facts if not dry_run else []


def _extracted_fact_tokens(fact: "Any") -> list[str]:
    """Build the BM25 document token list for one extracted evidence fact.

    Concatenates statement, source title, tags, and entities.
    Tags and entities are repeated three times to weight them above plain
    statement words without hard-coded per-field multipliers.
    """
    base = f"{fact.statement} {fact.source_title}"
    tag_boost = " ".join(fact.tags * 3)
    entity_boost = " ".join(fact.entities * 3)
    return re.findall(
        r"[a-zA-Z0-9_+#.-]{2,}",
        (base + " " + tag_boost + " " + entity_boost).lower(),
    )
