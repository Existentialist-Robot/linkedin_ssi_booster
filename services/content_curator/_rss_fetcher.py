"""
RSS article fetching for the content curator.
Fetches and filters articles from configured RSS feeds.
"""

import feedparser
import logging
import re
import requests

from services.content_curator._config import CURATOR_MAX_PER_FEED, RSS_FEEDS, KEYWORDS

logger = logging.getLogger(__name__)


def fetch_article_text(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL and return plain text (script/style stripped).

    Used when RSS has no summary, or as a static fallback.
    """
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text
        html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        logger.debug("Could not fetch article text from %s: %s", url, exc)
        return ""


def fetch_relevant_articles(max_per_feed: int = CURATOR_MAX_PER_FEED) -> list:
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
                        summary = fetch_article_text(link)
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
