"""Unit tests for services/selection_learning.py"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.selection_learning import (
    CandidateRecord,
    FeaturePrior,
    _jaccard,
    _match_candidate,
    compute_acceptance_priors,
    get_acceptance_rate,
    log_candidate,
    rank_articles,
    reconcile_published,
    update_candidate_buffer_id,
    upsert_published_record,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate_id() -> str:
    return str(uuid.uuid4())


def _make_run_id() -> str:
    return str(uuid.uuid4())


def _write_candidates(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _read_candidates(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _old_iso(days: int = 20) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# log_candidate
# ---------------------------------------------------------------------------

class TestLogCandidate:
    def test_writes_record_to_file(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        cid = _make_candidate_id()
        run_id = _make_run_id()
        rec = log_candidate(
            candidate_id=cid,
            article_url="https://example.com/article",
            article_title="Test Article",
            article_source="Test Source",
            ssi_component="establish_brand",
            channel="linkedin",
            post_text="A generated LinkedIn post about AI.",
            buffer_id=None,
            route="idea",
            run_id=run_id,
            path=path,
        )
        assert isinstance(rec, CandidateRecord)
        assert rec.candidate_id == cid
        assert rec.route == "idea"
        assert rec.selected is None

        rows = _read_candidates(path)
        assert len(rows) == 1
        assert rows[0]["candidate_id"] == cid
        assert rows[0]["article_source"] == "Test Source"
        assert rows[0]["ssi_component"] == "establish_brand"
        assert rows[0]["selected"] is None
        assert rows[0]["run_id"] == run_id

    def test_text_hash_is_16_hex_chars(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        rec = log_candidate(
            candidate_id=_make_candidate_id(),
            article_url="",
            article_title="",
            article_source="",
            ssi_component="engage_with_insights",
            channel="linkedin",
            post_text="Hello world this is a test post.",
            buffer_id=None,
            route="post",
            run_id=_make_run_id(),
            path=path,
        )
        assert len(rec.text_hash) == 16
        assert all(c in "0123456789abcdef" for c in rec.text_hash)

    def test_snippet_truncated_to_200_chars(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        long_text = "x" * 500
        rec = log_candidate(
            candidate_id=_make_candidate_id(),
            article_url="",
            article_title="",
            article_source="",
            ssi_component="build_relationships",
            channel="linkedin",
            post_text=long_text,
            buffer_id=None,
            route="idea",
            run_id=_make_run_id(),
            path=path,
        )
        assert len(rec.text_snippet) == 200


# ---------------------------------------------------------------------------
# update_candidate_buffer_id
# ---------------------------------------------------------------------------

class TestUpdateCandidateBufferId:
    def test_updates_buffer_id_when_found(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        cid = _make_candidate_id()
        _write_candidates(path, [{
            "candidate_id": cid,
            "buffer_id": None,
            "selected": None,
        }])
        result = update_candidate_buffer_id(cid, "buf_abc123", path=path)
        assert result is True
        rows = _read_candidates(path)
        assert rows[0]["buffer_id"] == "buf_abc123"

    def test_returns_false_when_not_found(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        _write_candidates(path, [{"candidate_id": "other-id", "buffer_id": None}])
        result = update_candidate_buffer_id("nonexistent-id", "buf_xyz", path=path)
        assert result is False

    def test_updates_only_matching_record(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        cid1 = _make_candidate_id()
        cid2 = _make_candidate_id()
        _write_candidates(path, [
            {"candidate_id": cid1, "buffer_id": None},
            {"candidate_id": cid2, "buffer_id": None},
        ])
        update_candidate_buffer_id(cid1, "buf_first", path=path)
        rows = _read_candidates(path)
        cid1_row = next(r for r in rows if r["candidate_id"] == cid1)
        cid2_row = next(r for r in rows if r["candidate_id"] == cid2)
        assert cid1_row["buffer_id"] == "buf_first"
        assert cid2_row["buffer_id"] is None


# ---------------------------------------------------------------------------
# _match_candidate
# ---------------------------------------------------------------------------

class TestMatchCandidate:
    def test_exact_buffer_id_wins(self):
        cid = _make_candidate_id()
        candidates = [
            {"candidate_id": cid, "buffer_id": "buf_123", "text_snippet": "hello world test", "article_url": ""},
            {"candidate_id": "other", "buffer_id": "buf_999", "text_snippet": "completely different", "article_url": ""},
        ]
        result = _match_candidate({"buffer_id": "buf_123", "text_snippet": "something else"}, candidates)
        assert result == cid

    def test_url_token_match_second_priority(self):
        cid = _make_candidate_id()
        article_url = "https://news.ycombinator.com/item?id=12345"
        candidates = [
            {"candidate_id": cid, "buffer_id": None, "text_snippet": "some post", "article_url": article_url},
        ]
        # Published text contains the URL
        published = {"buffer_id": "newid", "text_snippet": f"Check this out: {article_url}"}
        result = _match_candidate(published, candidates)
        assert result == cid

    def test_jaccard_match_third_priority(self):
        cid = _make_candidate_id()
        # High-overlap text (Jaccard >> 0.25)
        candidate_text = "large language models revolutionizing natural language processing applications"
        published_text = "large language models transforming natural language processing deployment scenarios"
        candidates = [{"candidate_id": cid, "buffer_id": None, "text_snippet": candidate_text, "article_url": ""}]
        result = _match_candidate({"buffer_id": "", "text_snippet": published_text}, candidates)
        assert result == cid

    def test_no_match_returns_none(self):
        candidates = [
            {"candidate_id": "abc", "buffer_id": "buf_000", "text_snippet": "hello world", "article_url": ""},
        ]
        result = _match_candidate(
            {"buffer_id": "completely-different", "text_snippet": "xyz qrs nothing overlapping here substantially"},
            candidates,
        )
        assert result is None


# ---------------------------------------------------------------------------
# reconcile_published
# ---------------------------------------------------------------------------

class TestReconcilePublished:
    def _make_buffer_service(self, posts_by_channel: dict) -> MagicMock:
        svc = MagicMock()
        svc.get_published_posts.side_effect = lambda channel_id, limit=50: posts_by_channel.get(channel_id, [])
        return svc

    def test_labels_matching_candidate_as_selected(self, tmp_path):
        c_path = tmp_path / "candidates.jsonl"
        p_path = tmp_path / "published.jsonl"
        cid = _make_candidate_id()
        _write_candidates(c_path, [{
            "candidate_id": cid,
            "buffer_id": "buf_match",
            "text_snippet": "ai tools for developers boost productivity",
            "article_url": "https://example.com/a1",
            "article_source": "HN",
            "ssi_component": "establish_brand",
            "timestamp": _now_iso(),
            "selected": None,
            "selected_at": None,
        }])
        svc = self._make_buffer_service({
            "li_ch": [{"id": "buf_match", "text": "ai tools content", "dueAt": _now_iso()}]
        })
        stats = reconcile_published(
            svc,
            {"linkedin": "li_ch"},
            candidates_path=c_path,
            published_path=p_path,
            acceptance_window_days=14,
        )
        assert stats["labelled_selected"] == 1
        assert stats["labelled_rejected"] == 0
        rows = _read_candidates(c_path)
        assert rows[0]["selected"] is True

    def test_labels_old_unmatched_candidate_as_rejected(self, tmp_path):
        c_path = tmp_path / "candidates.jsonl"
        p_path = tmp_path / "published.jsonl"
        cid = _make_candidate_id()
        _write_candidates(c_path, [{
            "candidate_id": cid,
            "buffer_id": None,
            "text_snippet": "some old post nobody published",
            "article_url": "https://example.com/old",
            "article_source": "OldSource",
            "ssi_component": "find_right_people",
            "timestamp": _old_iso(days=20),  # 20 days old > 14-day window
            "selected": None,
            "selected_at": None,
        }])
        svc = self._make_buffer_service({"li_ch": []})  # no published posts
        stats = reconcile_published(
            svc,
            {"linkedin": "li_ch"},
            candidates_path=c_path,
            published_path=p_path,
            acceptance_window_days=14,
        )
        assert stats["labelled_rejected"] == 1
        rows = _read_candidates(c_path)
        assert rows[0]["selected"] is False

    def test_recent_unmatched_candidate_stays_pending(self, tmp_path):
        c_path = tmp_path / "candidates.jsonl"
        p_path = tmp_path / "published.jsonl"
        cid = _make_candidate_id()
        _write_candidates(c_path, [{
            "candidate_id": cid,
            "buffer_id": None,
            "text_snippet": "brand new post from yesterday",
            "article_url": "https://example.com/new",
            "article_source": "NewSource",
            "ssi_component": "build_relationships",
            "timestamp": _now_iso(),  # just created
            "selected": None,
            "selected_at": None,
        }])
        svc = self._make_buffer_service({"li_ch": []})
        stats = reconcile_published(
            svc,
            {"linkedin": "li_ch"},
            candidates_path=c_path,
            published_path=p_path,
            acceptance_window_days=14,
        )
        assert stats["labelled_selected"] == 0
        assert stats["labelled_rejected"] == 0
        rows = _read_candidates(c_path)
        assert rows[0]["selected"] is None

    def test_already_labelled_candidates_are_skipped(self, tmp_path):
        c_path = tmp_path / "candidates.jsonl"
        p_path = tmp_path / "published.jsonl"
        cid = _make_candidate_id()
        _write_candidates(c_path, [{
            "candidate_id": cid,
            "buffer_id": "buf_abc",
            "text_snippet": "already labelled post",
            "article_url": "",
            "article_source": "Src",
            "ssi_component": "establish_brand",
            "timestamp": _old_iso(30),
            "selected": False,  # already labelled
            "selected_at": _old_iso(10),
        }])
        svc = self._make_buffer_service({"li_ch": [{"id": "buf_abc", "text": "already labelled post", "dueAt": _now_iso()}]})
        stats = reconcile_published(
            svc,
            {"linkedin": "li_ch"},
            candidates_path=c_path,
            published_path=p_path,
        )
        # labelled_selected counts newly labelled — should be 0
        assert stats["labelled_selected"] == 0
        # The record's existing label should be unchanged
        rows = _read_candidates(c_path)
        assert rows[0]["selected"] is False


# ---------------------------------------------------------------------------
# compute_acceptance_priors
# ---------------------------------------------------------------------------

class TestComputeAcceptancePriors:
    def test_beta_smoothing_math(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        _write_candidates(path, [
            {"article_source": "SrcA", "ssi_component": "establish_brand", "selected": True},
            {"article_source": "SrcA", "ssi_component": "establish_brand", "selected": True},
            {"article_source": "SrcA", "ssi_component": "establish_brand", "selected": False},
            # n_sel=2, n_tot=3 -> rate = (2+1)/(3+2) = 3/5 = 0.60
        ])
        priors = compute_acceptance_priors(path=path)
        key = ("SrcA", "establish_brand")
        assert key in priors
        p = priors[key]
        assert p.n_selected == 2
        assert p.n_total == 3
        assert abs(p.acceptance_rate - 0.60) < 1e-9

    def test_uninformative_prior_with_no_data(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.touch()
        priors = compute_acceptance_priors(path=path)
        assert priors == {}

    def test_pending_candidates_excluded(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        _write_candidates(path, [
            {"article_source": "SrcB", "ssi_component": "build_relationships", "selected": True},
            # pending — should not count
            {"article_source": "SrcB", "ssi_component": "build_relationships", "selected": None},
        ])
        priors = compute_acceptance_priors(path=path)
        key = ("SrcB", "build_relationships")
        assert priors[key].n_total == 1  # only the labelled one

    def test_multiple_sources(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        _write_candidates(path, [
            {"article_source": "FeedA", "ssi_component": "engage_with_insights", "selected": True},
            {"article_source": "FeedB", "ssi_component": "engage_with_insights", "selected": False},
        ])
        priors = compute_acceptance_priors(path=path)
        assert ("FeedA", "engage_with_insights") in priors
        assert ("FeedB", "engage_with_insights") in priors


# ---------------------------------------------------------------------------
# get_acceptance_rate
# ---------------------------------------------------------------------------

class TestGetAcceptanceRate:
    def _make_priors(self) -> dict:
        return {
            ("SrcA", "establish_brand"): FeaturePrior("SrcA", "establish_brand", 4, 5, (4 + 1) / (5 + 2)),
            ("SrcA", "build_relationships"): FeaturePrior("SrcA", "build_relationships", 1, 5, (1 + 1) / (5 + 2)),
        }

    def test_exact_key_match(self):
        priors = self._make_priors()
        rate = get_acceptance_rate("SrcA", "establish_brand", priors)
        assert abs(rate - (5 / 7)) < 1e-9

    def test_source_only_fallback(self):
        priors = self._make_priors()
        rate = get_acceptance_rate("SrcA", "find_right_people", priors)
        # Average of (5/7, 2/7) = 7/14 = 0.5
        expected = ((5 / 7) + (2 / 7)) / 2
        assert abs(rate - expected) < 1e-9

    def test_global_fallback_returns_0_5(self):
        priors = self._make_priors()
        rate = get_acceptance_rate("UnknownSource", "establish_brand", priors)
        assert rate == 0.5

    def test_empty_priors_returns_0_5(self):
        assert get_acceptance_rate("Any", "Any", {}) == 0.5


# ---------------------------------------------------------------------------
# rank_articles
# ---------------------------------------------------------------------------

class TestRankArticles:
    def _make_article(self, source: str, age_days: int = 1, title: str = "AI news") -> dict:
        pub = (datetime.now(timezone.utc) - timedelta(days=age_days)).strftime(
            "%a, %d %b %Y %H:%M:%S +0000"
        )
        return {
            "title": title,
            "summary": "summary text",
            "link": "https://example.com/article",
            "source": source,
            "published": pub,
        }

    def test_high_acceptance_source_ranked_first(self):
        # SrcGood: acceptance_rate close to 1.0; SrcBad: rate close to 0.0
        priors = {
            ("SrcGood", "establish_brand"): FeaturePrior("SrcGood", "establish_brand", 9, 10, 10 / 12),
            ("SrcBad", "establish_brand"): FeaturePrior("SrcBad", "establish_brand", 0, 10, 1 / 12),
        }
        articles = [
            self._make_article("SrcBad", age_days=1),
            self._make_article("SrcGood", age_days=1),
        ]
        ranked = rank_articles(articles, priors, ssi_component="establish_brand", keywords=["ai"])
        assert ranked[0]["source"] == "SrcGood"

    def test_fresh_article_ranked_above_stale(self):
        # Same source → freshness decides
        priors: dict = {}  # no priors — equal acceptance (0.5)
        articles = [
            self._make_article("SrcA", age_days=30, title="Old news"),
            self._make_article("SrcA", age_days=1, title="Fresh news"),
        ]
        ranked = rank_articles(articles, priors, ssi_component="establish_brand", keywords=["ai"])
        assert ranked[0]["title"] == "Fresh news"

    def test_returns_all_articles(self):
        articles = [self._make_article("Src", age_days=i) for i in range(5)]
        ranked = rank_articles(articles, {}, ssi_component="establish_brand", keywords=[])
        assert len(ranked) == len(articles)

    def test_empty_articles_returns_empty(self):
        result = rank_articles([], {}, ssi_component="establish_brand", keywords=["ai"])
        assert result == []


# ---------------------------------------------------------------------------
# Jaccard helper (sanity checks)
# ---------------------------------------------------------------------------

class TestJaccard:
    def test_identical_strings_return_1(self):
        assert _jaccard("machine learning model training", "machine learning model training") == 1.0

    def test_disjoint_strings_return_0(self):
        assert _jaccard("apple orange fruit", "planet galaxy universe") == 0.0

    def test_partial_overlap(self):
        score = _jaccard("deep learning research papers", "deep learning applications industry")
        assert 0 < score < 1
