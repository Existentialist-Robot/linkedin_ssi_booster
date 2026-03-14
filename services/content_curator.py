"""
Content Curator
Fetches AI/GovTech news from RSS feeds and GitHub, 
summarises with Claude, and creates Buffer ideas for review.
Targets: engage_with_insights SSI component.
"""

import feedparser
import requests
import logging
from typing import Optional
from services.claude_service import ClaudeService  # noqa: E402 — run from project root

logger = logging.getLogger(__name__)

# RSS feeds relevant to Shawn's niche
RSS_FEEDS = [
    {"name": "Anthropic Blog",        "url": "https://www.anthropic.com/rss.xml"},
    {"name": "Hugging Face Blog",     "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "Towards Data Science",  "url": "https://towardsdatascience.com/feed"},
    {"name": "The Batch (DeepLearning.AI)", "url": "https://www.deeplearning.ai/the-batch/feed/"},
    {"name": "AWS Machine Learning",  "url": "https://aws.amazon.com/blogs/machine-learning/feed/"},
    {"name": "Google AI Blog",        "url": "https://blog.research.google/atom.xml"},
]

KEYWORDS = [
    "RAG", "retrieval augmented", "LLM", "language model",
    "neo4j", "graph", "elasticsearch", "vector search",
    "agent", "multi-agent", "MCP", "model context protocol",
    "government AI", "GovTech", "regulatory", "compliance AI",
    "Java AI", "Spring AI", "FastAPI"
]


class ContentCurator:

    def __init__(self, claude_service: ClaudeService, buffer_service=None):
        self.claude = claude_service
        self.buffer = buffer_service

    def fetch_relevant_articles(self, max_per_feed: int = 3) -> list:
        """Fetch recent articles matching our keyword list."""
        articles = []
        for feed_info in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_info["url"])
                for entry in feed.entries[:max_per_feed]:
                    title   = entry.get("title") or ""
                    summary = entry.get("summary") or ""
                    link    = entry.get("link") or ""
                    content = f"{title} {summary}".lower()

                    if any(kw.lower() in content for kw in KEYWORDS):
                        articles.append({
                            "source": feed_info["name"],
                            "title":  title,
                            "summary": summary,
                            "link":   link,
                            "published": entry.get("published", "")
                        })
                        logger.info(f"  Matched: [{feed_info['name']}] {title[:60]}")
            except Exception as e:
                logger.warning(f"Failed to fetch {feed_info['name']}: {e}")
        logger.info(f"Found {len(articles)} relevant articles across {len(RSS_FEEDS)} feeds")
        return articles

    def curate_and_create_ideas(self, dry_run: bool = False, max_ideas: int = 5) -> list:
        """
        Main entry point: fetch articles, generate posts with Claude,
        push as Ideas to Buffer for manual review before publishing.
        """
        articles = self.fetch_relevant_articles()
        created_ideas = []

        for article in articles[:max_ideas]:
            logger.info(f"Generating curation post for: {article['title'][:60]}...")
            post_text = self.claude.summarise_for_curation(
                article_text=article["summary"],
                source_url=article["link"]
            )

            if dry_run:
                print(f"\n{'='*60}")
                print(f"SOURCE: {article['source']}")
                print(f"ARTICLE: {article['title']}")
                print(f"\nGENERATED POST:\n{post_text}")
                created_ideas.append({"dry_run": True, "title": article["title"], "text": post_text})
            else:
                if self.buffer:
                    idea = self.buffer.create_idea(
                        text=post_text,
                        title=f"[Curated] {article['title'][:80]}"
                    )
                    created_ideas.append(idea)
                else:
                    logger.warning("No buffer_service provided — skipping idea creation")

        return created_ideas
