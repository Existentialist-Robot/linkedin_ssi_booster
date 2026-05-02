"""
RSS article fetching for the content curator.
Fetches and filters articles from configured RSS feeds.
"""

import feedparser
import logging
import re
import requests

try:
    import trafilatura as _trafilatura
    _TRAFILATURA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TRAFILATURA_AVAILABLE = False

from services.content_curator._config import CURATOR_MAX_PER_FEED, RSS_FEEDS, KEYWORDS

logger = logging.getLogger(__name__)


def fetch_article_text(url: str, max_chars: int = 3000, spacy_nlp=None) -> str:
    """Fetch a URL and return the article body as plain text.

    Uses trafilatura to extract the main article body (strips nav menus,
    sidebars, cookie banners, etc.) when available.  Falls back to naive
    tag-stripping if trafilatura is not installed or returns empty.

    When spacy_nlp is provided and the article is long enough, uses extractive
    summarization (5 sentences) to surface buried key content rather than
    front-truncating. Falls back to truncation if summarization returns empty.
    Used when RSS has no summary, or as a static fallback.
    """
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text

        # --- primary: trafilatura extracts clean article body ---
        text = ""
        if _TRAFILATURA_AVAILABLE:
            text = _trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            ) or ""
            if text:
                logger.debug("trafilatura extracted %d chars from %s", len(text), url)

        # --- fallback: naive HTML tag stripping ---
        if not text:
            html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            logger.debug("trafilatura returned empty; using tag-strip fallback (%d chars) from %s", len(text), url)

        text_stripped = text.strip()
        if len(text_stripped) < 200:
            logger.info(f"[fetch_article_text] Skipping article (too short, {len(text_stripped)} chars): {url}")
            return ""
        letters = [c for c in text_stripped if c.isalpha()]
        if letters:
            upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
            if upper_ratio > 0.90:
                logger.info(f"[fetch_article_text] Skipping article (nav blob, {upper_ratio:.2%} uppercase): {url}")
                return ""

        if spacy_nlp and len(text) > 500:
            try:
                summary = spacy_nlp.summarize_article(
                    article_text=text[:max_chars],
                    max_sentences=5,
                    focus_entities=True,
                )
                if summary:
                    logger.debug("spaCy summarized fallback fetch from %d to %d chars", len(text[:max_chars]), len(summary))
                    return summary
            except Exception as _exc:
                logger.debug("spaCy summarization failed in fetch_article_text, using truncation: %s", _exc)
        return text[:max_chars]
    except Exception as exc:
        logger.debug("Could not fetch article text from %s: %s", url, exc)
        return ""


def fetch_relevant_articles(max_per_feed: int = CURATOR_MAX_PER_FEED, spacy_nlp=None) -> list:
    """Fetch recent articles matching our keyword list."""
    articles = []
    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:max_per_feed]:
                title   = str(entry.get("title") or "")
                summary = str(entry.get("summary") or "")
                link    = str(entry.get("link") or "")
                content = f"{title} {summary}".lower()

                if any(kw.lower() in content for kw in KEYWORDS):
                    if len(summary.strip()) < 100 and link:
                        logger.debug("RSS summary empty for '%s' — fetching URL", title[:50])
                        summary = fetch_article_text(link, spacy_nlp=spacy_nlp)
                    articles.append({
                        "source":    feed_info["name"],
                        "title":     title,
                        "summary":   summary,
                        "link":      link,
                        "published": entry.get("published", ""),
                    })
                    logger.info("  🧲 Matched: [%s] %s", feed_info["name"], title[:60])
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", feed_info["name"], exc)
    logger.info("🗞️  Found %d relevant articles across %d feeds", len(articles), len(RSS_FEEDS))
    return articles
