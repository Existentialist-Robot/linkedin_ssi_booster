import pytest
from services import content_curator
from services.selection_learning import compute_acceptance_priors, rank_articles

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
