import pytest
from services import content_curator
from services.selection_learning import compute_acceptance_priors, rank_articles
from services.avatar_intelligence import ExtractedEvidenceFact

@pytest.fixture
def sample_articles():
    return [
        {"title": "AI beats humans at Go", "summary": "A new AI system defeated top Go players.", "link": "http://example.com/ai-go", "source": "Anthropic Blog", "published": "2026-04-15"},
        {"title": "Spring Boot 3.2 released", "summary": "Major update for Java devs.", "link": "http://example.com/spring-boot", "source": "Spring Blog", "published": "2026-04-14"},
        {"title": "Neo4j launches new graph DB", "summary": "Graph database gets major upgrade.", "link": "http://example.com/neo4j", "source": "Neo4j Blog", "published": "2026-04-13"},
    ]

def test_rank_articles_adaptive(sample_articles):
    priors = compute_acceptance_priors()
    ranked = rank_articles(sample_articles, priors, keywords=["AI", "Spring", "graph"])
    assert isinstance(ranked, list)
    assert all(isinstance(a, dict) for a in ranked)
    assert set(a["title"] for a in ranked) == set(a["title"] for a in sample_articles)

def test_curate_and_create_ideas_adaptive(monkeypatch, sample_articles):
    from services.ollama_service import OllamaService
    class DummyAI(OllamaService):
        pass
    curator = content_curator.ContentCurator(DummyAI())
    monkeypatch.setattr(content_curator, "fetch_relevant_articles", lambda *a, **kw: sample_articles)
    monkeypatch.setattr(curator, "_load_published_titles", lambda: set())
    monkeypatch.setattr(curator, "_save_published_title", lambda t: None)
    ideas = curator.curate_and_create_ideas(dry_run=True, max_ideas=2)
    assert isinstance(ideas, list)
    assert len(ideas) <= 2


def test_build_topic_signal_counts_tags_and_entities():
    facts = [
        ExtractedEvidenceFact(
            evidence_id="X001-aaaaaa",
            statement="Anthropic added persistent memory",
            source_url="https://example.com/a",
            source_title="A",
            tags=["anthropic", "agents"],
            entities=["persistent memory"],
            confidence="medium",
            source_fact_id="ext-1",
        ),
        ExtractedEvidenceFact(
            evidence_id="X002-bbbbbb",
            statement="Agentic AI and AIOps are converging",
            source_url="https://example.com/b",
            source_title="B",
            tags=["aiops", "anthropic"],
            entities=["agentic ai"],
            confidence="medium",
            source_fact_id="ext-2",
        ),
    ]

    signal = content_curator._build_topic_signal(facts, window=50)
    assert signal["anthropic"] == 2
    assert signal["aiops"] == 1
    assert signal["persistent memory"] == 1


def test_pick_ssi_component_applies_topic_tilt(monkeypatch):
    captured = {}

    def _fake_choices(components, weights, k):
        captured["components"] = components
        captured["weights"] = weights
        return [components[0]]

    monkeypatch.setattr(content_curator.random, "choices", _fake_choices)

    topic_signal = {"anthropic": 3, "aiops": 2, "llm": 1}
    content_curator._pick_ssi_component(topic_signal)

    idx = captured["components"].index("engage_with_insights")
    weighted = captured["weights"][idx]
    assert weighted > content_curator._SSI_WEIGHTS["engage_with_insights"]


def test_extracted_fact_to_evidence_path_sets_overlap_and_credibility():
    fact = ExtractedEvidenceFact(
        evidence_id="X003-cccccc",
        statement="Anthropic launched Claude Managed Agents with persistent memory",
        source_url="https://example.com/c",
        source_title="C",
        tags=["anthropic"],
        entities=["persistent memory"],
        confidence="high",
        source_fact_id="ext-3",
    )

    path = content_curator._extracted_fact_to_evidence_path(
        fact,
        "Claude managed agents now include persistent memory for workflows",
    )

    assert path.source.startswith("extracted_knowledge:")
    assert path.credibility == 0.85
    assert 0.0 < path.overlap <= 1.0
