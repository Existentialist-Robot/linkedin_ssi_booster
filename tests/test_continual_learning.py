"""Tests for continual learning — ExtractedFact, ExtractedKnowledgeGraph, and NLP pipeline.

Covers:
- Schema validation for extracted_knowledge.json
- Loader round-trip (load → save → reload)
- normalize_extracted_facts: stable IDs, correct field mapping
- _extracted_fact_tokens: BM25 tokenisation
- build_extracted_grounding_context: prompt formatting
- extract_and_append_knowledge: deduplication and dry_run flag
- AvatarState.extracted_knowledge integration via load_avatar_state
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from services.avatar_intelligence import (
    AvatarState,
    ExtractedEvidenceFact,
    ExtractedFact,
    ExtractedKnowledgeGraph,
    _extracted_fact_tokens,
    _load_extracted_knowledge,
    _make_extracted_evidence_id,
    _make_extracted_fact_id,
    _validate_extracted_knowledge,
    build_extracted_grounding_context,
    extract_and_append_knowledge,
    normalize_extracted_facts,
    save_extracted_knowledge,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph(facts: list[ExtractedFact] | None = None) -> ExtractedKnowledgeGraph:
    return ExtractedKnowledgeGraph(
        schema_version="1.0",
        facts=facts or [],
    )


def _make_fact(
    statement: str = "Transformers are state-of-the-art for NLP tasks.",
    source_url: str = "https://example.com/article",
    source_title: str = "NLP Survey 2026",
    fact_id: str | None = None,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
) -> ExtractedFact:
    fid = fact_id or _make_extracted_fact_id(source_url, statement)
    return ExtractedFact(
        id=fid,
        statement=statement,
        source_url=source_url,
        source_title=source_title,
        extracted_at="2026-04-19T16:00:00+00:00",
        entities=entities or ["Transformers"],
        tags=tags or ["nlp", "transformer", "benchmark"],
        confidence="medium",
        extraction_method="spacy_nlp",
    )


def _make_avatar_state(
    extracted_knowledge: ExtractedKnowledgeGraph | None = None,
) -> AvatarState:
    return AvatarState(
        persona_graph=None,
        narrative_memory=None,
        domain_knowledge=None,
        extracted_knowledge=extracted_knowledge,
        is_loaded=False,
    )


# ---------------------------------------------------------------------------
# _validate_extracted_knowledge
# ---------------------------------------------------------------------------

def test_validate_extracted_knowledge_valid():
    data = {"schemaVersion": "1.0", "facts": []}
    assert _validate_extracted_knowledge(data) == []


def test_validate_extracted_knowledge_missing_schema_version():
    data = {"facts": []}
    errors = _validate_extracted_knowledge(data)
    assert any("schemaVersion" in e for e in errors)


def test_validate_extracted_knowledge_missing_facts():
    data = {"schemaVersion": "1.0"}
    errors = _validate_extracted_knowledge(data)
    assert any("facts" in e for e in errors)


def test_validate_extracted_knowledge_facts_not_list():
    data = {"schemaVersion": "1.0", "facts": "not-a-list"}
    errors = _validate_extracted_knowledge(data)
    assert any("facts" in e for e in errors)


# ---------------------------------------------------------------------------
# _load_extracted_knowledge
# ---------------------------------------------------------------------------

def test_load_extracted_knowledge_missing_file(tmp_path):
    path = tmp_path / "nope.json"
    graph, errors = _load_extracted_knowledge(path)
    assert graph is None
    assert any("not found" in e for e in errors)


def test_load_extracted_knowledge_malformed_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    graph, errors = _load_extracted_knowledge(path)
    assert graph is None
    assert any("parse error" in e for e in errors)


def test_load_extracted_knowledge_schema_error(tmp_path):
    path = tmp_path / "bad_schema.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "facts": "not-a-list"}), encoding="utf-8")
    graph, errors = _load_extracted_knowledge(path)
    assert graph is None
    assert any("schema error" in e for e in errors)


def test_load_extracted_knowledge_empty_facts(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "facts": []}), encoding="utf-8")
    graph, errors = _load_extracted_knowledge(path)
    assert errors == []
    assert graph is not None
    assert graph.facts == []
    assert graph.schema_version == "1.0"


def test_load_extracted_knowledge_with_facts(tmp_path):
    fact = _make_fact()
    path = tmp_path / "graph.json"
    path.write_text(
        json.dumps({
            "schemaVersion": "1.0",
            "facts": [{
                "id": fact.id,
                "statement": fact.statement,
                "source_url": fact.source_url,
                "source_title": fact.source_title,
                "extracted_at": fact.extracted_at,
                "entities": fact.entities,
                "tags": fact.tags,
                "confidence": fact.confidence,
                "extraction_method": fact.extraction_method,
            }],
        }),
        encoding="utf-8",
    )
    graph, errors = _load_extracted_knowledge(path)
    assert errors == []
    assert graph is not None
    assert len(graph.facts) == 1
    assert graph.facts[0].id == fact.id
    assert graph.facts[0].statement == fact.statement


# ---------------------------------------------------------------------------
# save_extracted_knowledge + round-trip
# ---------------------------------------------------------------------------

def test_save_and_reload_extracted_knowledge(tmp_path):
    fact = _make_fact()
    graph = _make_graph([fact])
    path = tmp_path / "out.json"

    save_extracted_knowledge(graph, path=path)
    assert path.exists()

    reloaded, errors = _load_extracted_knowledge(path)
    assert errors == []
    assert reloaded is not None
    assert len(reloaded.facts) == 1
    assert reloaded.facts[0].statement == fact.statement
    assert reloaded.facts[0].tags == fact.tags


def test_save_extracted_knowledge_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dir" / "out.json"
    graph = _make_graph()
    save_extracted_knowledge(graph, path=path)
    assert path.exists()


# ---------------------------------------------------------------------------
# _make_extracted_fact_id
# ---------------------------------------------------------------------------

def test_make_extracted_fact_id_stable():
    id1 = _make_extracted_fact_id("https://example.com", "Some statement.")
    id2 = _make_extracted_fact_id("https://example.com", "Some statement.")
    assert id1 == id2


def test_make_extracted_fact_id_different_for_different_inputs():
    id1 = _make_extracted_fact_id("https://example.com", "Statement A.")
    id2 = _make_extracted_fact_id("https://example.com", "Statement B.")
    assert id1 != id2


def test_make_extracted_fact_id_has_ext_prefix():
    fid = _make_extracted_fact_id("https://example.com", "hello world")
    assert fid.startswith("ext-")


# ---------------------------------------------------------------------------
# _make_extracted_evidence_id
# ---------------------------------------------------------------------------

def test_make_extracted_evidence_id_prefix():
    eid = _make_extracted_evidence_id("fact-abc", 0)
    assert eid.startswith("X000-")


def test_make_extracted_evidence_id_stable():
    eid1 = _make_extracted_evidence_id("same-id", 5)
    eid2 = _make_extracted_evidence_id("same-id", 5)
    assert eid1 == eid2


def test_make_extracted_evidence_id_different_index():
    eid1 = _make_extracted_evidence_id("fact-x", 0)
    eid2 = _make_extracted_evidence_id("fact-x", 1)
    assert eid1 != eid2


# ---------------------------------------------------------------------------
# normalize_extracted_facts
# ---------------------------------------------------------------------------

def test_normalize_extracted_facts_empty_state():
    state = _make_avatar_state(extracted_knowledge=None)
    assert normalize_extracted_facts(state) == []


def test_normalize_extracted_facts_empty_graph():
    graph = _make_graph([])
    state = _make_avatar_state(extracted_knowledge=graph)
    assert normalize_extracted_facts(state) == []


def test_normalize_extracted_facts_single_fact():
    fact = _make_fact()
    graph = _make_graph([fact])
    state = _make_avatar_state(extracted_knowledge=graph)

    result = normalize_extracted_facts(state)
    assert len(result) == 1
    ef = result[0]
    assert isinstance(ef, ExtractedEvidenceFact)
    assert ef.statement == fact.statement
    assert ef.source_url == fact.source_url
    assert ef.source_title == fact.source_title
    assert ef.tags == fact.tags
    assert ef.entities == fact.entities
    assert ef.confidence == fact.confidence
    assert ef.source_fact_id == fact.id
    assert ef.evidence_id.startswith("X000-")


def test_normalize_extracted_facts_multiple_facts():
    facts = [
        _make_fact(statement=f"Fact {i}.", fact_id=f"id-{i}")
        for i in range(3)
    ]
    graph = _make_graph(facts)
    state = _make_avatar_state(extracted_knowledge=graph)
    result = normalize_extracted_facts(state)
    assert len(result) == 3
    # Evidence IDs should be different
    eids = [f.evidence_id for f in result]
    assert len(set(eids)) == 3


# ---------------------------------------------------------------------------
# _extracted_fact_tokens
# ---------------------------------------------------------------------------

def test_extracted_fact_tokens_returns_list():
    ef = ExtractedEvidenceFact(
        evidence_id="X000-abc",
        statement="Transformers are great for NLP.",
        source_url="https://example.com",
        source_title="AI Survey",
        tags=["nlp", "transformer"],
        entities=["OpenAI"],
        confidence="medium",
        source_fact_id="ext-abc",
    )
    tokens = _extracted_fact_tokens(ef)
    assert isinstance(tokens, list)
    assert len(tokens) > 0
    # Tags should appear multiple times (boost)
    assert tokens.count("nlp") >= 3
    assert tokens.count("transformer") >= 3


def test_extracted_fact_tokens_lowercased():
    ef = ExtractedEvidenceFact(
        evidence_id="X000-abc",
        statement="Python ML Models.",
        source_url="https://example.com",
        source_title="Tech News",
        tags=["Python", "ML"],
        entities=["Google"],
        confidence="high",
        source_fact_id="ext-abc",
    )
    tokens = _extracted_fact_tokens(ef)
    for tok in tokens:
        assert tok == tok.lower()


# ---------------------------------------------------------------------------
# build_extracted_grounding_context
# ---------------------------------------------------------------------------

def test_build_extracted_grounding_context_empty():
    assert build_extracted_grounding_context([]) == ""


def test_build_extracted_grounding_context_single():
    ef = ExtractedEvidenceFact(
        evidence_id="X000-abc",
        statement="RAG systems improve LLM accuracy.",
        source_url="https://example.com",
        source_title="AI Research",
        tags=["rag", "llm"],
        entities=["RAG"],
        confidence="medium",
        source_fact_id="ext-abc",
    )
    ctx = build_extracted_grounding_context([ef])
    assert "Recently learned context" in ctx
    assert "[X000-abc]" in ctx
    assert "RAG systems improve LLM accuracy" in ctx
    assert "rag" in ctx


def test_build_extracted_grounding_context_source_title():
    ef = ExtractedEvidenceFact(
        evidence_id="X001-xyz",
        statement="Agents are the future.",
        source_url="https://example.com",
        source_title="AI Trends 2026",
        tags=[],
        entities=[],
        confidence="low",
        source_fact_id="ext-xyz",
    )
    ctx = build_extracted_grounding_context([ef])
    assert "AI Trends 2026" in ctx


# ---------------------------------------------------------------------------
# extract_and_append_knowledge
# ---------------------------------------------------------------------------

ARTICLE = (
    "Large language models have transformed natural language processing. "
    "Recent benchmarks show that transformer-based models consistently outperform "
    "older RNN architectures on standard tasks. "
    "The adoption of vector search and RAG pipelines has accelerated significantly "
    "in enterprise AI systems."
)


def test_extract_and_append_knowledge_dry_run(tmp_path):
    path = tmp_path / "ek.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "facts": []}), encoding="utf-8")

    result = extract_and_append_knowledge(
        ARTICLE,
        source_url="https://example.com/article",
        source_title="Test Article",
        path=path,
        dry_run=True,
    )
    # dry_run returns empty list but should not modify disk
    assert result == []
    reloaded = json.loads(path.read_text())
    assert reloaded["facts"] == []


def test_extract_and_append_knowledge_writes_facts(tmp_path):
    path = tmp_path / "ek.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "facts": []}), encoding="utf-8")

    result = extract_and_append_knowledge(
        ARTICLE,
        source_url="https://example.com/article",
        source_title="Test Article",
        path=path,
        dry_run=False,
    )
    # Should have extracted at least one fact (sentences are long enough)
    assert len(result) >= 1
    for fact in result:
        assert isinstance(fact, ExtractedFact)
        assert fact.source_url == "https://example.com/article"
        assert fact.source_title == "Test Article"
        assert fact.id.startswith("ext-")

    # Verify on-disk file was updated
    reloaded = json.loads(path.read_text())
    assert len(reloaded["facts"]) == len(result)


def test_extract_and_append_knowledge_deduplication(tmp_path):
    path = tmp_path / "ek.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "facts": []}), encoding="utf-8")

    # First extraction
    first_run = extract_and_append_knowledge(
        ARTICLE,
        source_url="https://example.com/article",
        source_title="Test Article",
        path=path,
        dry_run=False,
    )
    count_after_first = len(first_run)

    # Second extraction of same article — all should be duplicates
    second_run = extract_and_append_knowledge(
        ARTICLE,
        source_url="https://example.com/article",
        source_title="Test Article",
        path=path,
        dry_run=False,
    )
    assert second_run == [] or len(second_run) == 0

    # Total on-disk count should not grow
    reloaded = json.loads(path.read_text())
    assert len(reloaded["facts"]) == count_after_first


def test_extract_and_append_knowledge_max_facts_per_article(tmp_path):
    path = tmp_path / "ek.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "facts": []}), encoding="utf-8")

    result = extract_and_append_knowledge(
        ARTICLE,
        source_url="https://example.com/article",
        source_title="Test Article",
        max_facts_per_article=1,
        path=path,
        dry_run=False,
    )
    assert len(result) <= 1


def test_extract_and_append_knowledge_short_sentences_skipped(tmp_path):
    path = tmp_path / "ek.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "facts": []}), encoding="utf-8")

    result = extract_and_append_knowledge(
        "Too short. Also tiny.",  # all sentences are too short
        source_url="https://example.com",
        source_title="Short",
        min_sentence_len=50,
        path=path,
        dry_run=False,
    )
    assert result == []


def test_extract_and_append_knowledge_creates_file_if_missing(tmp_path):
    path = tmp_path / "new" / "ek.json"
    # File does not exist yet
    assert not path.exists()

    result = extract_and_append_knowledge(
        ARTICLE,
        source_url="https://example.com/article",
        source_title="Test Article",
        path=path,
        dry_run=False,
    )
    assert path.exists()
    assert len(result) >= 1


def test_extract_and_append_knowledge_confidence_field(tmp_path):
    path = tmp_path / "ek.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "facts": []}), encoding="utf-8")

    result = extract_and_append_knowledge(
        ARTICLE,
        source_url="https://example.com/article",
        source_title="Test Article",
        confidence="high",
        path=path,
        dry_run=False,
    )
    for fact in result:
        assert fact.confidence == "high"


# ---------------------------------------------------------------------------
# AvatarState integration
# ---------------------------------------------------------------------------

def test_avatar_state_holds_extracted_knowledge():
    fact = _make_fact()
    graph = _make_graph([fact])
    state = _make_avatar_state(extracted_knowledge=graph)
    assert state.extracted_knowledge is not None
    assert len(state.extracted_knowledge.facts) == 1


def test_normalize_extracted_facts_ids_are_unique_across_reloads(tmp_path):
    """IDs should be deterministic across two normalize_extracted_facts calls."""
    fact = _make_fact(fact_id="stable-id")
    graph = _make_graph([fact])
    state = _make_avatar_state(extracted_knowledge=graph)

    result1 = normalize_extracted_facts(state)
    result2 = normalize_extracted_facts(state)
    assert result1[0].evidence_id == result2[0].evidence_id
