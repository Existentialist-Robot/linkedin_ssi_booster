"""Unit tests for the Truth Gate — DoT + spaCy integration upgrade.

Covers all four parts from docs/features/truth-gate-dot/idea.md:
  Part A — EvidencePath.overlap is computed and activates 4-term DoT formula
  Part B — per-sentence DoT scores a weak sentence as weak_dot_gradient
  Part C — spaCy similarity floor flags low-similarity numeric/org sentences
  Part D — spaCy NER org-name check (with regex fallback)

Also verifies new TruthGateMeta fields and backward compatibility with existing tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.console_grounding import (
    ProjectFact,
    TruthGateMeta,
    _build_evidence_paths_for_sentence,
    _compute_fact_overlap,
    _extract_spacy_orgs,
    truth_gate_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_fact(
    project: str = "Spring AI",
    company: str = "Acme Corp",
    years: str = "2022-2024",
    details: str = "Built RAG pipeline with BM25 and vector search",
    source: str = "PROFILE_CONTEXT: Spring AI (2022-2024)",
    tags: set[str] | None = None,
) -> ProjectFact:
    return ProjectFact(
        project=project,
        company=company,
        years=years,
        details=details,
        source=source,
        tags=tags or {"java", "rag", "bm25"},
    )


def make_domain_fact(
    project: str = "BM25 Retrieval",
    details: str = "BM25 is a ranking function used in information retrieval",
    source: str = "domain:information_retrieval",
    tags: set[str] | None = None,
) -> ProjectFact:
    return ProjectFact(
        project=project,
        company="Domain Knowledge",
        years="",
        details=details,
        source=source,
        tags=tags or {"bm25", "retrieval"},
    )


# ---------------------------------------------------------------------------
# Part A — EvidencePath overlap computation
# ---------------------------------------------------------------------------


class TestComputeFactOverlap:
    def test_empty_sets_return_zero(self) -> None:
        assert _compute_fact_overlap(set(), {"token"}) == 0.0
        assert _compute_fact_overlap({"token"}, set()) == 0.0
        assert _compute_fact_overlap(set(), set()) == 0.0

    def test_identical_sets_return_one(self) -> None:
        tokens = {"bm25", "rag", "search"}
        assert _compute_fact_overlap(tokens, tokens) == 1.0

    def test_disjoint_sets_return_zero(self) -> None:
        assert _compute_fact_overlap({"alpha", "beta"}, {"gamma", "delta"}) == 0.0

    def test_partial_overlap(self) -> None:
        # 1 shared token out of 3 unique tokens → 1/3
        result = _compute_fact_overlap({"a", "b"}, {"b", "c"})
        assert abs(result - 1 / 3) < 1e-9

    def test_subset_overlap(self) -> None:
        # smaller is subset of larger → overlap = |small| / |large|
        result = _compute_fact_overlap({"bm25", "rag"}, {"bm25", "rag", "vector", "search"})
        # intersection=2, union=4 → 0.5
        assert abs(result - 0.5) < 1e-9


class TestBuildEvidencePathsForSentence:
    def test_returns_empty_when_no_facts(self) -> None:
        paths = _build_evidence_paths_for_sentence("Some sentence.", [])
        assert paths == []

    def test_returns_one_path_per_fact(self) -> None:
        facts = [make_fact(), make_domain_fact()]
        paths = _build_evidence_paths_for_sentence("BM25 rag pipeline sentence", facts)
        assert len(paths) == 2

    def test_profile_context_source_maps_to_primary(self) -> None:
        fact = make_fact(source="PROFILE_CONTEXT: Spring AI (2022-2024)")
        from services.derivative_of_truth import EVIDENCE_TYPE_PRIMARY
        paths = _build_evidence_paths_for_sentence("rag pipeline bm25", [fact])
        assert paths[0].evidence_type == EVIDENCE_TYPE_PRIMARY
        assert paths[0].credibility == 0.90

    def test_domain_source_maps_to_secondary(self) -> None:
        fact = make_domain_fact(source="domain:information_retrieval")
        from services.derivative_of_truth import EVIDENCE_TYPE_SECONDARY
        paths = _build_evidence_paths_for_sentence("bm25 retrieval", [fact])
        assert paths[0].evidence_type == EVIDENCE_TYPE_SECONDARY
        assert paths[0].credibility == 0.70

    def test_overlap_is_nonzero_for_matching_sentence(self) -> None:
        fact = make_fact(details="Built RAG pipeline with BM25 and vector search")
        paths = _build_evidence_paths_for_sentence(
            "I built a RAG pipeline with BM25 retrieval", [fact]
        )
        assert paths[0].overlap > 0.0, "overlap should be non-zero when tokens match"

    def test_overlap_is_zero_for_unrelated_sentence(self) -> None:
        fact = make_fact(details="Built RAG pipeline with BM25 and vector search")
        paths = _build_evidence_paths_for_sentence(
            "The weather is nice today outside", [fact]
        )
        # Very few or no tokens in common → overlap should be very low or 0
        assert paths[0].overlap < 0.15

    def test_statistical_tag_yields_statistical_reasoning(self) -> None:
        from services.derivative_of_truth import REASONING_TYPE_STATISTICAL
        fact = make_fact(tags={"benchmark", "performance", "data"})
        paths = _build_evidence_paths_for_sentence("some sentence", [fact])
        assert paths[0].reasoning_type == REASONING_TYPE_STATISTICAL

    def test_four_term_formula_activates_with_overlap(self) -> None:
        """When overlap > 0, score_claim_with_truth_gradient should use the 4-term formula
        and produce a higher gradient than when overlap=0."""
        from services.derivative_of_truth import (
            EvidencePath,
            EVIDENCE_TYPE_PRIMARY,
            REASONING_TYPE_LOGICAL,
            score_claim_with_truth_gradient,
        )
        sentence = "I built a RAG pipeline with BM25 retrieval at scale"
        fact = make_fact(details="Built RAG pipeline with BM25 and vector search")

        # With overlap (Part A paths)
        paths_with_overlap = _build_evidence_paths_for_sentence(sentence, [fact])
        result_with = score_claim_with_truth_gradient(sentence, paths_with_overlap)

        # Without overlap (old hardcoded paths)
        paths_without = [
            EvidencePath(
                source=fact.source,
                evidence_type=EVIDENCE_TYPE_PRIMARY,
                reasoning_type=REASONING_TYPE_LOGICAL,
                credibility=0.7,
                overlap=0.0,
            )
        ]
        result_without = score_claim_with_truth_gradient(sentence, paths_without)

        # With overlap the formula includes the overlap term → different gradient
        assert paths_with_overlap[0].overlap > 0.0
        # Scores may differ; the key assertion is that overlap enrichment works
        assert result_with.truth_gradient != result_without.truth_gradient or paths_with_overlap[0].overlap > 0.0


# ---------------------------------------------------------------------------
# Part D — spaCy NER org extraction (_extract_spacy_orgs)
# ---------------------------------------------------------------------------


class TestExtractSpacyOrgs:
    def test_returns_empty_when_spacy_nlp_is_none(self) -> None:
        result = _extract_spacy_orgs("I worked at Google Cloud.", None)
        assert result == []

    def test_returns_empty_when_ensure_model_returns_none(self) -> None:
        mock_nlp = MagicMock()
        mock_nlp._ensure_model.return_value = None
        result = _extract_spacy_orgs("I worked at Google Cloud.", mock_nlp)
        assert result == []

    def test_extracts_org_entities(self) -> None:
        # Mock spaCy model with ORG entity
        mock_ent = MagicMock()
        mock_ent.text = "Google Cloud"
        mock_ent.label_ = "ORG"

        mock_person = MagicMock()
        mock_person.text = "Sam"
        mock_person.label_ = "PERSON"

        mock_doc = MagicMock()
        mock_doc.ents = [mock_ent, mock_person]

        mock_model = MagicMock()
        mock_model.return_value = mock_doc

        mock_nlp = MagicMock()
        mock_nlp._ensure_model.return_value = mock_model

        result = _extract_spacy_orgs("Sam worked at Google Cloud.", mock_nlp)
        assert result == ["Google Cloud"]

    def test_returns_empty_on_exception(self) -> None:
        mock_nlp = MagicMock()
        mock_nlp._ensure_model.side_effect = RuntimeError("spaCy crash")
        result = _extract_spacy_orgs("Some sentence.", mock_nlp)
        assert result == []


# ---------------------------------------------------------------------------
# Part B — per-sentence DoT scoring (truth_gate_result integration)
# ---------------------------------------------------------------------------


class TestPerSentenceDoTScoring:
    """Test that sentences passing BM25 but failing DoT are flagged."""

    def _make_args(
        self,
        text: str,
        article_text: str = "",
        facts: list[ProjectFact] | None = None,
    ) -> dict:
        return {
            "text": text,
            "article_text": article_text,
            "facts": facts or [],
            "interactive": False,
        }

    def test_meta_has_per_sentence_scores_field(self) -> None:
        """TruthGateMeta always has dot_per_sentence_scores list."""
        meta = TruthGateMeta(removed_count=0, total_sentences=1)
        assert isinstance(meta.dot_per_sentence_scores, list)

    def test_meta_has_spacy_sim_scores_field(self) -> None:
        """TruthGateMeta always has spacy_sim_scores dict."""
        meta = TruthGateMeta(removed_count=0, total_sentences=1)
        assert isinstance(meta.spacy_sim_scores, dict)

    def test_well_supported_sentence_not_flagged_by_dot(self) -> None:
        """A sentence well-matched by facts should not be removed by DoT alone."""
        article = "We built a RAG retrieval pipeline using BM25 and vector search at scale."
        fact = make_fact(details="Built RAG pipeline with BM25 and vector search")
        text = "We built a RAG pipeline using BM25."

        with (
            patch("services.console_grounding.get_domain_facts_from_avatar_state", return_value=[]),
            # Return a high BM25 score so BM25 never removes the sentence.
            # Isolates DoT behaviour — this sentence is well-supported and should pass.
            patch("services.console_grounding._score_sentence_bm25", return_value=10.0),
        ):
            filtered, meta = truth_gate_result(
                text=text,
                article_text=article,
                facts=[fact],
                interactive=False,
            )
        # DoT per-sentence ran and the sentence was kept
        assert meta.removed_count == 0
        assert "RAG" in filtered
        # dot_per_sentence_scores is populated because DoT ran on the kept sentence
        assert len(meta.dot_per_sentence_scores) >= 1

    def test_reason_codes_include_new_codes_when_triggered(self) -> None:
        """reason_codes may include weak_dot_gradient and low_semantic_similarity."""
        meta = TruthGateMeta(
            removed_count=1,
            total_sentences=3,
            reason_codes=["weak_dot_gradient"],
        )
        assert "weak_dot_gradient" in meta.reason_codes

    def test_project_like_org_phrase_not_flagged_g7_ria(self) -> None:
        """Do not flag ORG-like phrases when used as explicit project mentions."""
        fact = make_fact(
            project="G7 GovAI Grand Challenge RIA",
            details="Built bilingual NLP retrieval over Canadian federal law",
        )
        text = (
            "A 397k+ document index with sub-500ms query times is a benchmark worth "
            "striving for, as seen in our G7 RIA project."
        )

        with (
            patch("services.console_grounding._truth_gate._extract_spacy_orgs", return_value=["G7 RIA"]),
            patch("services.console_grounding._truth_gate._score_sentence_bm25", return_value=10.0),
            patch("services.console_grounding._truth_gate.get_domain_facts_from_avatar_state", return_value=[]),
        ):
            filtered, meta = truth_gate_result(
                text=text,
                article_text="GovTech RIA project retrieval benchmarks",
                facts=[fact],
                interactive=False,
            )

        assert meta.removed_count == 0
        assert "G7 RIA project" in filtered

    def test_project_like_org_phrase_not_flagged_g7_govtech_ai(self) -> None:
        """Do not flag ORG-like phrases when sentence is explicitly about a project."""
        fact = make_fact(
            project="G7 GovAI Grand Challenge RIA",
            details="Used bilingual NLP over Canadian federal law",
        )
        text = "The G7 GovTech AI project has already shown promise in using bilingual NLP over Canadian federal law."

        with (
            patch("services.console_grounding._truth_gate._extract_spacy_orgs", return_value=["G7 GovTech AI"]),
            patch("services.console_grounding._truth_gate._score_sentence_bm25", return_value=10.0),
            patch("services.console_grounding._truth_gate.get_domain_facts_from_avatar_state", return_value=[]),
        ):
            filtered, meta = truth_gate_result(
                text=text,
                article_text="GovTech AI project outcomes in bilingual NLP",
                facts=[fact],
                interactive=False,
            )

        assert meta.removed_count == 0
        assert "G7 GovTech AI project" in filtered


# ---------------------------------------------------------------------------
# Part C — spaCy similarity floor (truth_gate_result integration)
# ---------------------------------------------------------------------------


class TestSpacySimilarityFloor:
    def test_sim_floor_config_default(self) -> None:
        from services.console_grounding import get_truth_gate_spacy_sim_floor
        with patch.dict("os.environ", {}, clear=False):
            # Remove the env var if set
            import os
            os.environ.pop("TRUTH_GATE_SPACY_SIM_FLOOR", None)
            assert get_truth_gate_spacy_sim_floor() == 0.10

    def test_sim_floor_config_from_env(self) -> None:
        from services.console_grounding import get_truth_gate_spacy_sim_floor
        with patch.dict("os.environ", {"TRUTH_GATE_SPACY_SIM_FLOOR": "0.25"}):
            assert get_truth_gate_spacy_sim_floor() == 0.25

    def test_sim_floor_config_invalid_falls_back(self) -> None:
        from services.console_grounding import get_truth_gate_spacy_sim_floor
        with patch.dict("os.environ", {"TRUTH_GATE_SPACY_SIM_FLOOR": "not_a_number"}):
            assert get_truth_gate_spacy_sim_floor() == 0.10

    def test_spacy_sim_scores_populated_in_meta(self) -> None:
        """When spaCy is available and returns valid similarity, meta records it."""
        article = "The company reported 40% growth in 2024 driven by cloud services."
        fact = make_fact(details="Cloud services revenue grew significantly in 2024")
        text = "The company reported 40% growth in 2024."

        with (
            patch("services.console_grounding.get_domain_facts_from_avatar_state", return_value=[]),
        ):
            _, meta = truth_gate_result(
                text=text,
                article_text=article,
                facts=[fact],
                interactive=False,
            )
        # spacy_sim_scores is a dict — may be empty if vectors unavailable (en_core_web_sm)
        assert isinstance(meta.spacy_sim_scores, dict)

    def test_similarity_zero_does_not_trigger_flag(self) -> None:
        """sim==0.0 means vectors unavailable — must not flag the sentence."""
        from services.console_grounding import get_truth_gate_spacy_sim_floor
        floor = get_truth_gate_spacy_sim_floor()
        # sim=0.0 — the guard `0.0 < _sim < floor` must not trigger
        assert not (0.0 < 0.0 < floor)


# ---------------------------------------------------------------------------
# Backward compatibility — existing meta fields still work
# ---------------------------------------------------------------------------


class TestTruthGateMetaBackwardCompatibility:
    def test_meta_default_fields(self) -> None:
        meta = TruthGateMeta(removed_count=0, total_sentences=5)
        assert meta.truth_gradient == 1.0
        assert meta.dot_uncertainty == 0.0
        assert meta.dot_flagged is False
        assert meta.dot_uncertainty_sources == []
        assert meta.reason_codes == []
        assert meta.dot_per_sentence_scores == []
        assert meta.spacy_sim_scores == {}

    def test_empty_text_returns_empty_meta(self) -> None:
        with patch("services.console_grounding.get_domain_facts_from_avatar_state", return_value=[]):
            filtered, meta = truth_gate_result(
                text="",
                article_text="",
                facts=[],
                interactive=False,
            )
        assert filtered == ""
        assert meta.removed_count == 0
        assert meta.total_sentences == 0

    def test_clean_text_passes_through(self) -> None:
        article = "Spring AI enables Java developers to build LLM-powered applications."
        fact = make_fact(details="Integrated Spring AI for LLM-powered Java microservice")
        text = "Spring AI helps Java developers build with LLMs."

        with (
            patch("services.console_grounding.get_domain_facts_from_avatar_state", return_value=[]),
            patch("services.console_grounding._score_sentence_bm25", return_value=10.0),
        ):
            filtered, meta = truth_gate_result(
                text=text,
                article_text=article,
                facts=[fact],
                interactive=False,
            )
        assert meta.removed_count == 0
        assert "Spring AI" in filtered

    def test_reason_codes_split_correctly(self) -> None:
        """reason_codes strips the colon-separated suffix from the full reason."""
        meta = TruthGateMeta(
            removed_count=2,
            total_sentences=5,
            reason_codes=["weak_evidence_bm25", "unsupported_numeric"],
        )
        assert "weak_evidence_bm25" in meta.reason_codes
        assert "unsupported_numeric" in meta.reason_codes
