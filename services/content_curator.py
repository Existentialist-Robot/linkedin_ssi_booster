"""
Content Curator
Fetches AI/GovTech news from RSS feeds and GitHub, 
summarises with Claude, and creates Buffer ideas for review.
Targets: engage_with_insights SSI component.
"""

import feedparser
import json
import logging
import os
import random
import requests
import time
from itertools import cycle
from pathlib import Path
from typing import Optional, Union
from services.claude_service import ClaudeService, SSI_COMPONENT_INSTRUCTIONS  # noqa: E402 — run from project root
from services.gemini_service import GeminiService
from services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

CURATOR_MAX_PER_FEED: int = int(os.getenv("CURATOR_MAX_PER_FEED", "10"))
IDEAS_CACHE_PATH = Path(os.getenv("IDEAS_CACHE_PATH", "published_ideas_cache.json"))

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

    def __init__(self, claude_service: Union[ClaudeService, GeminiService, OllamaService], buffer_service=None):
        self.claude = claude_service
        self.buffer = buffer_service

    def _load_published_titles(self) -> set:
        if IDEAS_CACHE_PATH.exists():
            return set(json.loads(IDEAS_CACHE_PATH.read_text()))
        return set()

    def _save_published_title(self, title: str) -> None:
        titles = self._load_published_titles()
        titles.add(title)
        IDEAS_CACHE_PATH.write_text(json.dumps(sorted(titles), indent=2))

    def fetch_relevant_articles(self, max_per_feed: int = CURATOR_MAX_PER_FEED) -> list:
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

    def curate_and_create_ideas(self, dry_run: bool = False, max_ideas: int = 5, request_delay: float = 5.0) -> list:
        """
        Main entry point: fetch articles, generate posts with Claude,
        push as Ideas to Buffer for manual review before publishing.
        request_delay: seconds to wait between AI calls (helps with rate limits).
        Rotates through all SSI components so curated posts contribute to every pillar.
        """
        articles = self.fetch_relevant_articles()
        random.shuffle(articles)
        published = self._load_published_titles()
        created_ideas = []
        ssi_rotation = cycle(SSI_COMPONENT_INSTRUCTIONS.keys())

        for i, article in enumerate(articles[:max_ideas]):
            if article["title"] in published:
                logger.info(f"Skipping already-published idea: {article['title'][:60]}")
                continue
            if i > 0:
                time.sleep(request_delay)
            ssi_component = next(ssi_rotation)
            logger.info(f"Generating curation post [{ssi_component}] for: {article['title'][:60]}...")
            post_text = self.claude.summarise_for_curation(
                article_text=article["summary"],
                source_url=article["link"],
                ssi_component=ssi_component,
            )

            if not post_text:
                logger.info(f"Skipping article with no usable content: {article['title'][:60]}")
                continue

            # Always guarantee the source link appears in the post
            if article["link"] and article["link"] not in post_text:
                post_text = post_text.rstrip() + f"\n\n{article['link']}"

            if dry_run:
                print(f"\n{'='*60}")
                print(f"SOURCE: {article['source']}")
                print(f"ARTICLE: {article['title']}")
                print(f"SSI COMPONENT: {ssi_component}")
                print(f"\nGENERATED POST:\n{post_text}")
                created_ideas.append({"dry_run": True, "title": article["title"], "text": post_text, "ssi_component": ssi_component})
            else:
                if self.buffer:
                    idea = self.buffer.create_idea(
                        text=post_text,
                        title=f"[Curated|{ssi_component}] {article['title'][:70]}"
                    )
                    self._save_published_title(article["title"])
                    created_ideas.append(idea)
                else:
                    logger.warning("No buffer_service provided — skipping idea creation")

        return created_ideas
