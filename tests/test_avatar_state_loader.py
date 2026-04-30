"""T6.1 — Unit tests for avatar state loader and schema validation."""
import json
from pathlib import Path

import pytest

import services.avatar_intelligence as ai
from services.avatar_intelligence import (
    _validate_persona_graph,
    _validate_narrative_memory,
    _load_persona_graph,
    _load_narrative_memory,
    load_avatar_state,
)
from tests.conftest import MINIMAL_PERSONA_GRAPH, MINIMAL_NARRATIVE_MEMORY


# ---------------------------------------------------------------------------
# _validate_persona_graph
# ---------------------------------------------------------------------------


def test_validate_persona_graph_valid() -> None:
    errors = _validate_persona_graph(MINIMAL_PERSONA_GRAPH)
    assert errors == []


def test_validate_persona_graph_missing_schema_version() -> None:
    data = {**MINIMAL_PERSONA_GRAPH}
    del data["schemaVersion"]
    errors = _validate_persona_graph(data)
    assert any("schemaVersion" in e for e in errors)


def test_validate_persona_graph_schema_version_not_string() -> None:
    data = {**MINIMAL_PERSONA_GRAPH, "schemaVersion": 1}
    errors = _validate_persona_graph(data)
    assert any("schemaVersion" in e for e in errors)


def test_validate_persona_graph_missing_person() -> None:
    data = {k: v for k, v in MINIMAL_PERSONA_GRAPH.items() if k != "person"}
    errors = _validate_persona_graph(data)
    assert any("person" in e for e in errors)


def test_validate_persona_graph_projects_not_list() -> None:
    data = {**MINIMAL_PERSONA_GRAPH, "projects": "not a list"}
    errors = _validate_persona_graph(data)
    assert any("projects" in e for e in errors)


def test_validate_persona_graph_claims_not_list() -> None:
    data = {**MINIMAL_PERSONA_GRAPH, "claims": {"bad": "type"}}
    errors = _validate_persona_graph(data)
    assert any("claims" in e for e in errors)


# ---------------------------------------------------------------------------
# _validate_narrative_memory
# ---------------------------------------------------------------------------


def test_validate_narrative_memory_valid() -> None:
    errors = _validate_narrative_memory(MINIMAL_NARRATIVE_MEMORY)
    assert errors == []


def test_validate_narrative_memory_recent_themes_not_list() -> None:
    data = {**MINIMAL_NARRATIVE_MEMORY, "recentThemes": "bad"}
    errors = _validate_narrative_memory(data)
    assert any("recentThemes" in e for e in errors)


def test_validate_narrative_memory_missing_open_arcs() -> None:
    data = {k: v for k, v in MINIMAL_NARRATIVE_MEMORY.items() if k != "openNarrativeArcs"}
    errors = _validate_narrative_memory(data)
    assert any("openNarrativeArcs" in e for e in errors)


# ---------------------------------------------------------------------------
# _load_persona_graph — file-level tests
# ---------------------------------------------------------------------------


def test_load_persona_graph_valid(tmp_path: Path) -> None:
    p = tmp_path / "persona_graph.json"
    p.write_text(json.dumps(MINIMAL_PERSONA_GRAPH), encoding="utf-8")
    graph, errors = _load_persona_graph(p)
    assert errors == []
    assert graph is not None
    assert len(graph.projects) == 2
    assert len(graph.skills) == 5


def test_load_persona_graph_missing_file(tmp_path: Path) -> None:
    graph, errors = _load_persona_graph(tmp_path / "nonexistent.json")
    assert graph is None
    assert errors


def test_load_persona_graph_malformed_json(tmp_path: Path) -> None:
    p = tmp_path / "persona_graph.json"
    p.write_text("{not valid json", encoding="utf-8")
    graph, errors = _load_persona_graph(p)
    assert graph is None
    assert errors


def test_load_persona_graph_schema_error(tmp_path: Path) -> None:
    bad = {**MINIMAL_PERSONA_GRAPH}
    del bad["schemaVersion"]
    p = tmp_path / "persona_graph.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    graph, errors = _load_persona_graph(p)
    assert graph is None
    assert errors


# ---------------------------------------------------------------------------
# _load_narrative_memory — file-level tests
# ---------------------------------------------------------------------------


def test_load_narrative_memory_valid(tmp_path: Path) -> None:
    p = tmp_path / "narrative_memory.json"
    p.write_text(json.dumps(MINIMAL_NARRATIVE_MEMORY), encoding="utf-8")
    mem, errors = _load_narrative_memory(p)
    assert errors == []
    assert mem is not None
    assert mem.recent_themes == ["python", "api"]


def test_load_narrative_memory_missing_file(tmp_path: Path) -> None:
    mem, errors = _load_narrative_memory(Path("/nonexistent/narrative_memory.json"))
    assert mem is None
    assert errors


def test_load_narrative_memory_malformed_json(tmp_path: Path) -> None:
    p = tmp_path / "narrative_memory.json"
    p.write_text("[broken", encoding="utf-8")
    mem, errors = _load_narrative_memory(p)
    assert mem is None
    assert errors


# ---------------------------------------------------------------------------
# load_avatar_state — integration via monkeypatched module constants
# ---------------------------------------------------------------------------


def test_load_avatar_state_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pg = tmp_path / "persona_graph.json"
    nm = tmp_path / "narrative_memory.json"
    pg.write_text(json.dumps(MINIMAL_PERSONA_GRAPH), encoding="utf-8")
    nm.write_text(json.dumps(MINIMAL_NARRATIVE_MEMORY), encoding="utf-8")

    monkeypatch.setattr(ai, "PERSONA_GRAPH_PATH", pg)
    monkeypatch.setattr(ai, "NARRATIVE_MEMORY_PATH", nm)

    state = load_avatar_state()
    assert state.is_loaded is True
    assert state.load_errors == []
    assert state.persona_graph is not None
    assert len(state.persona_graph.projects) == 2


def test_load_avatar_state_missing_persona_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nm = tmp_path / "narrative_memory.json"
    nm.write_text(json.dumps(MINIMAL_NARRATIVE_MEMORY), encoding="utf-8")

    monkeypatch.setattr(ai, "PERSONA_GRAPH_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(ai, "NARRATIVE_MEMORY_PATH", nm)

    state = load_avatar_state()
    assert state.is_loaded is False
    assert state.load_errors


def test_load_avatar_state_missing_narrative_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pg = tmp_path / "persona_graph.json"
    pg.write_text(json.dumps(MINIMAL_PERSONA_GRAPH), encoding="utf-8")

    monkeypatch.setattr(ai, "PERSONA_GRAPH_PATH", pg)
    monkeypatch.setattr(ai, "NARRATIVE_MEMORY_PATH", tmp_path / "missing.json")

    state = load_avatar_state()
    assert state.is_loaded is False
    assert state.load_errors


def test_load_avatar_state_malformed_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pg = tmp_path / "persona_graph.json"
    nm = tmp_path / "narrative_memory.json"
    pg.write_text("{broken", encoding="utf-8")
    nm.write_text(json.dumps(MINIMAL_NARRATIVE_MEMORY), encoding="utf-8")

    monkeypatch.setattr(ai, "PERSONA_GRAPH_PATH", pg)
    monkeypatch.setattr(ai, "NARRATIVE_MEMORY_PATH", nm)

    state = load_avatar_state()
    assert state.is_loaded is False
    assert state.load_errors


_MINIMAL_DOMAIN_KNOWLEDGE = {
    "schemaVersion": "1.0",
    "domains": [{"id": "d1", "name": "Domain A", "description": "Desc"}],
    "facts": [{"id": "f1", "domainId": "d1", "statement": "Fact one.", "tags": ["tag1"]}],
    "relationships": [],
}

_EXTRA_DOMAIN_KNOWLEDGE = {
    "schemaVersion": "1.0",
    "domains": [{"id": "d2", "name": "Domain B", "description": "Desc B"}],
    "facts": [
        {"id": "f2", "domainId": "d2", "statement": "Java is statically typed.", "tags": ["java"]},
        {"id": "f3", "domainId": "d2", "statement": "S3 is an AWS storage service.", "tags": ["s3", "aws"]},
    ],
    "relationships": [],
}


def test_load_avatar_state_merges_extra_domain_knowledge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extra domain_knowledge_*.json files in the same dir are merged automatically."""
    pg = tmp_path / "persona_graph.json"
    nm = tmp_path / "narrative_memory.json"
    dk = tmp_path / "domain_knowledge.json"
    dk_extra = tmp_path / "domain_knowledge_extra.json"

    pg.write_text(json.dumps(MINIMAL_PERSONA_GRAPH), encoding="utf-8")
    nm.write_text(json.dumps(MINIMAL_NARRATIVE_MEMORY), encoding="utf-8")
    dk.write_text(json.dumps(_MINIMAL_DOMAIN_KNOWLEDGE), encoding="utf-8")
    dk_extra.write_text(json.dumps(_EXTRA_DOMAIN_KNOWLEDGE), encoding="utf-8")

    monkeypatch.setattr(ai, "PERSONA_GRAPH_PATH", pg)
    monkeypatch.setattr(ai, "NARRATIVE_MEMORY_PATH", nm)
    monkeypatch.setattr(ai, "DOMAIN_KNOWLEDGE_PATH", dk)

    state = load_avatar_state()
    assert state.is_loaded is True
    assert state.domain_knowledge is not None
    # Primary (1 fact) + extra (2 facts) = 3 total
    assert len(state.domain_knowledge.facts) == 3
    all_statements = {f.statement for f in state.domain_knowledge.facts}
    assert "Java is statically typed." in all_statements
    assert "S3 is an AWS storage service." in all_statements
