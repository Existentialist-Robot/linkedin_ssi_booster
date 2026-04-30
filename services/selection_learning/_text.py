"""Text hashing, tokenization, and candidate matching helpers."""

from __future__ import annotations

import hashlib
import re

from services.selection_learning._constants import JACCARD_THRESHOLD


class TextMatcher:
    """Text-level utilities used by logging and reconciliation."""

    @staticmethod
    def text_hash(text: str) -> str:
        """Return first 16 hex chars of SHA-256 of *text* (normalized)."""
        return hashlib.sha256(text.lower().strip().encode()).hexdigest()[:16]

    @staticmethod
    def tokenize(text: str) -> set[str]:
        """Lowercase word tokens from *text*, 3+ chars, excluding stopwords."""
        stop = frozenset({
            "the", "and", "for", "that", "this", "with", "are", "was", "were",
            "you", "your", "our", "has", "have", "had", "not", "its", "but",
            "about", "from", "they", "than", "when", "what", "how",
        })
        return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in stop}

    @staticmethod
    def jaccard(a: str, b: str) -> float:
        """Jaccard similarity of word tokens between two strings."""
        ta, tb = TextMatcher.tokenize(a), TextMatcher.tokenize(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    @staticmethod
    def match_candidate(
        published: dict[str, object],
        candidates: list[dict[str, object]],
    ) -> str | None:
        """Return best-matching candidate id for *published*, or None.

        Matching priority:
        1. buffer_id equality (exact)
        2. article URL appears in published text snippet
        3. Jaccard token similarity of text snippets >= threshold
        """
        pub_text = str(published.get("text_snippet", ""))
        pub_buffer_id = str(published.get("buffer_id", ""))

        for cand in candidates:
            cbuf = cand.get("buffer_id")
            if cbuf and str(cbuf) == pub_buffer_id:
                return str(cand["candidate_id"])

        for cand in candidates:
            url = str(cand.get("article_url", ""))
            if url and url in pub_text:
                return str(cand["candidate_id"])

        best_score = JACCARD_THRESHOLD
        best_id: str | None = None
        for cand in candidates:
            score = TextMatcher.jaccard(str(cand.get("text_snippet", "")), pub_text)
            if score > best_score:
                best_score = score
                best_id = str(cand["candidate_id"])
        return best_id
