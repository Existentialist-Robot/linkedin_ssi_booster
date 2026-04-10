"""T6.2 — Unit tests for evidence mapping and explain output."""
import hashlib
import json
from pathlib import Path

import pytest

import services.avatar_intelligence as ai
from services.avatar_intelligence import (
    _make_evidence_id,
    normalize_evidence_facts,
    evidence_facts_to_project_facts,
    retrieve_evidence,
    build_grounding_context,
    get_grounding_context_for_query,
    build_explain_output,
    format_explain_output,
    load_avatar_state,
    EvidenceFact,
    AvatarState,
)
from tests.conftest import MINIMAL_PERSONA_GRAPH, MINIMAL_NARRATIVE_MEMORY


# ---------------------------------------------------------------------------
# _make_evidence_id
# ---------------------------------------------------------------------------


def test_make_evidence_id_stable() -> None:
    """Same inputs always produce the same ID."""
    id1 = _make_evidence_id("proj-alpha", 0)
    id2 = _make_evidence_id("proj-alpha", 0)
    assert id1 == id2


def test_make_evidence_id_format() -> None:
    """ID has the expected format: E{idx:03d}-{6hexchars}."""
    eid = _make_evidence_id("proj-alpha", 3)
    assert eid.startswith("E003-")
    assert len(eid) == 11  # "E003-" (5) + 6 hex chars


def test_make_evidence_id_different_indices() -> None:
    e0 = _make_evidence_id("proj-alpha", 0)
    e1 = _make_evidence_id("proj-alpha", 1)
    assert e0 != e1
    assert e0.startswith("E000-")
    assert e1.startswith("E001-")


def test_make_evidence_id_different_projects() -> None:
    ea = _make_evidence_id("proj-alpha", 0)
    eb = _make_evidence_id("proj-beta", 0)
    assert ea != eb


def test_make_evidence_id_hash_value() -> None:
    """Hash portion matches first 6 chars of sha256 of project_id."""
    expected_hash = hashlib.sha256("proj-alpha".encode()).hexdigest()[:6]
    eid = _make_evidence_id("proj-alpha", 0)
    assert eid == f"E000-{expected_hash}"


# ---------------------------------------------------------------------------
# normalize_evidence_facts
# ---------------------------------------------------------------------------


def _make_loaded_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AvatarState:
    """Helper: write fixtures to tmp_path and load avatar state."""
    pg = tmp_path / "persona_graph.json"
    nm = tmp_path / "narrative_memory.json"
    pg.write_text(json.dumps(MINIMAL_PERSONA_GRAPH), encoding="utf-8")
    nm.write_text(json.dumps(MINIMAL_NARRATIVE_MEMORY), encoding="utf-8")
    monkeypatch.setattr(ai, "PERSONA_GRAPH_PATH", pg)
    monkeypatch.setattr(ai, "NARRATIVE_MEMORY_PATH", nm)
    return load_avatar_state()


def test_normalize_evidence_facts_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_loaded_state(tmp_path, monkeypatch)
    facts = normalize_evidence_facts(state)
    assert len(facts) == 2  # two projects in minimal fixture


def test_normalize_evidence_facts_company_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_loaded_state(tmp_path, monkeypatch)
    facts = normalize_evidence_facts(state)
    # company_id "comp-acme" should resolve to "Acme Corp"
    assert all(f.company == "Acme Corp" for f in facts)


def test_normalize_evidence_facts_stable_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_loaded_state(tmp_path, monkeypatch)
    facts1 = normalize_evidence_facts(state)
    facts2 = normalize_evidence_facts(state)
    assert [f.evidence_id for f in facts1] == [f.evidence_id for f in facts2]


def test_normalize_evidence_facts_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_loaded_state(tmp_path, monkeypatch)
    facts = normalize_evidence_facts(state)
    first = facts[0]
    assert first.project == "Alpha Project"
    assert first.years == "2021-2023"
    assert "python" in first.skills
    assert first.source_project_id == "proj-alpha"


def test_normalize_evidence_facts_unloaded_state() -> None:
    state = AvatarState(
        persona_graph=None,
        narrative_memory=None,
        is_loaded=False,
        load_errors=["missing file"],
    )
    assert normalize_evidence_facts(state) == []


# ---------------------------------------------------------------------------
# evidence_facts_to_project_facts
# ---------------------------------------------------------------------------


def test_evidence_facts_to_project_facts_empty() -> None:
    assert evidence_facts_to_project_facts([]) == []


def test_evidence_facts_to_project_facts_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_loaded_state(tmp_path, monkeypatch)
    evidence_facts = normalize_evidence_facts(state)
    project_facts = evidence_facts_to_project_facts(evidence_facts)
    assert len(project_facts) == 2
    pf = project_facts[0]
    assert pf.project == "Alpha Project"
    assert pf.company == "Acme Corp"
    assert isinstance(pf.tags, set)
    assert "python" in pf.tags


def test_evidence_facts_to_project_facts_source_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _make_loaded_state(tmp_path, monkeypatch)
    evidence_facts = normalize_evidence_facts(state)
    project_facts = evidence_facts_to_project_facts(evidence_facts)
    assert all(pf.source.startswith("avatar:") for pf in project_facts)


# ---------------------------------------------------------------------------
# retrieve_evidence — scoring
# ---------------------------------------------------------------------------


def _make_facts() -> list[EvidenceFact]:
    return [
        EvidenceFact(
            evidence_id="E000-aaa111",
            project="Alpha Project",
            company="Acme Corp",
            years="2021-2023",
            details="Built a scalable API with Python and FastAPI.",
            skills=["python", "fastapi", "api"],
            source_project_id="proj-alpha",
        ),
        EvidenceFact(
            evidence_id="E001-bbb222",
            project="Beta Project",
            company="Acme Corp",
            years="2023-2024",
            details="Machine learning pipeline using scikit-learn and pandas.",
            skills=["ml", "scikit-learn"],
            source_project_id="proj-beta",
        ),
        EvidenceFact(
            evidence_id="E002-ccc333",
            project="Gamma Project",
            company="Other Corp",
            years="2020-2021",
            details="Frontend development with React and TypeScript.",
            skills=["react", "typescript"],
            source_project_id="proj-gamma",
        ),
    ]


def test_retrieve_evidence_skill_match_scores_highest() -> None:
    facts = _make_facts()
    # "fastapi" is a skill of Alpha — should rank first
    results = retrieve_evidence("fastapi framework exploration", facts, limit=3)
    assert results[0].project == "Alpha Project"


def test_retrieve_evidence_ml_skill_ranks_beta() -> None:
    facts = _make_facts()
    results = retrieve_evidence("machine learning ml scikit-learn", facts, limit=3)
    assert results[0].project == "Beta Project"


def test_retrieve_evidence_empty_facts() -> None:
    assert retrieve_evidence("anything", [], limit=5) == []


def test_retrieve_evidence_fallback_when_no_match() -> None:
    """When no fact scores, falls back to first `limit` facts."""
    facts = _make_facts()
    results = retrieve_evidence("zzzzzzz totally unrelated query xyz", facts, limit=2)
    assert len(results) == 2


def test_retrieve_evidence_limit_respected() -> None:
    facts = _make_facts()
    results = retrieve_evidence("python fastapi ml scikit react typescript", facts, limit=2)
    assert len(results) <= 2


# ---------------------------------------------------------------------------
# build_explain_output / format_explain_output
# ---------------------------------------------------------------------------


def test_build_explain_output_fields() -> None:
    facts = _make_facts()[:2]
    explain = build_explain_output(facts, "http://example.com", "linkedin", "engage_with_insights")
    assert explain.article_ref == "http://example.com"
    assert explain.channel == "linkedin"
    assert explain.ssi_component == "engage_with_insights"
    assert len(explain.evidence_ids) == 2
    assert explain.evidence_ids[0] == "E000-aaa111"


def test_build_explain_output_summary_truncation() -> None:
    long_detail = "A" * 200
    fact = EvidenceFact(
        evidence_id="E000-aaa111",
        project="Big Project",
        company="Corp",
        years="2020-2024",
        details=long_detail,
        skills=[],
        source_project_id="big-proj",
    )
    explain = build_explain_output([fact], "ref", "x", "establish_brand")
    assert explain.evidence_summaries[0].endswith("...")
    # summary should reference only up to 80 chars of details
    summary_detail_part = explain.evidence_summaries[0].split(" — ", 1)[1]
    assert len(summary_detail_part) <= 83  # 80 chars + "..." = 83


def test_format_explain_output_contains_evidence_id() -> None:
    facts = _make_facts()[:1]
    explain = build_explain_output(facts, "http://example.com", "linkedin", "establish_brand")
    formatted = format_explain_output(explain)
    assert "E000-aaa111" in formatted
    assert "http://example.com" in formatted


def test_format_explain_output_empty_facts() -> None:
    explain = build_explain_output([], "", "linkedin", "establish_brand")
    formatted = format_explain_output(explain)
    assert "none" in formatted.lower() or "no persona" in formatted.lower()


# ---------------------------------------------------------------------------
# build_grounding_context
# ---------------------------------------------------------------------------


def test_build_grounding_context_empty() -> None:
    assert build_grounding_context([]) == ""


def test_build_grounding_context_contains_evidence_id() -> None:
    facts = _make_facts()[:1]
    ctx = build_grounding_context(facts)
    assert "E000-aaa111" in ctx
    assert "Alpha Project" in ctx


# ---------------------------------------------------------------------------
# get_grounding_context_for_query
# ---------------------------------------------------------------------------


def test_get_grounding_context_none_state() -> None:
    assert get_grounding_context_for_query("query", None) == ""


def test_get_grounding_context_unloaded_state() -> None:
    state = AvatarState(
        persona_graph=None, narrative_memory=None, is_loaded=False, load_errors=[]
    )
    assert get_grounding_context_for_query("query", state) == ""


def test_get_grounding_context_loaded_returns_nonempty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _make_loaded_state(tmp_path, monkeypatch)
    ctx = get_grounding_context_for_query("python fastapi", state, limit=5)
    assert ctx != ""
    assert "Alpha Project" in ctx
