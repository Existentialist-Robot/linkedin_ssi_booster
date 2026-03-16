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
import re
import requests
import time
from pathlib import Path
from typing import Optional, Union
from services.claude_service import ClaudeService, SSI_COMPONENT_INSTRUCTIONS  # noqa: E402 — run from project root
from services.gemini_service import GeminiService
from services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

CURATOR_MAX_PER_FEED: int = int(os.getenv("CURATOR_MAX_PER_FEED", "10"))
IDEAS_CACHE_PATH = Path(os.getenv("IDEAS_CACHE_PATH", "published_ideas_cache.json"))

# ---------------------------------------------------------------------------
# SSI post-type focus — how often each pillar gets a post (should add up to 100).
# Bump a pillar up when it's lagging; dial it back when it improves.
# ---------------------------------------------------------------------------
_SSI_WEIGHTS: dict[str, float] = {
    "establish_brand":      float(os.getenv("SSI_FOCUS_ESTABLISH_BRAND",      "25")),
    "find_right_people":    float(os.getenv("SSI_FOCUS_FIND_RIGHT_PEOPLE",    "27")),
    "engage_with_insights": float(os.getenv("SSI_FOCUS_ENGAGE_WITH_INSIGHTS", "24")),
    "build_relationships":  float(os.getenv("SSI_FOCUS_BUILD_RELATIONSHIPS",  "24")),
}


def _pick_ssi_component() -> str:
    """Pick a component proportionally to its configured focus percentage."""
    components = list(_SSI_WEIGHTS.keys())
    weights    = list(_SSI_WEIGHTS.values())
    return random.choices(components, weights=weights, k=1)[0]

# RSS feeds — override via CURATOR_RSS_FEEDS in .env as a JSON array:
# [{"name": "My Blog", "url": "https://example.com/feed.xml"}, ...]
_DEFAULT_RSS_FEEDS = [
    {"name": "Anthropic Blog",              "url": "https://www.anthropic.com/rss.xml"},
    {"name": "Hugging Face Blog",           "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "Towards Data Science",        "url": "https://towardsdatascience.com/feed"},
    {"name": "The Batch (DeepLearning.AI)", "url": "https://www.deeplearning.ai/the-batch/feed/"},
    {"name": "AWS Machine Learning",        "url": "https://aws.amazon.com/blogs/machine-learning/feed/"},
    {"name": "Google AI Blog",              "url": "https://blog.research.google/atom.xml"},
    {"name": "Spring Blog",                 "url": "https://spring.io/blog.atom"},
    {"name": "Elastic Blog",                "url": "https://www.elastic.co/blog/feed"},
    {"name": "Neo4j Blog",                  "url": "https://neo4j.com/blog/feed/"},
    {"name": "Inside Java",                 "url": "https://inside.java/feed.xml"},
    {"name": "LangChain Blog",              "url": "https://blog.langchain.dev/rss/"},
    {"name": "The New Stack",               "url": "https://thenewstack.io/feed/"},
]
_rss_env = os.getenv("CURATOR_RSS_FEEDS", "")
RSS_FEEDS: list = json.loads(_rss_env) if _rss_env.strip() else _DEFAULT_RSS_FEEDS

# Keywords — override via CURATOR_KEYWORDS in .env as a comma-separated list
_DEFAULT_KEYWORDS = [
    "RAG", "retrieval augmented", "LLM", "language model",
    "neo4j", "graph", "elasticsearch", "vector search",
    "agent", "multi-agent", "MCP", "model context protocol",
    "government AI", "GovTech", "regulatory", "compliance AI",
    "Java AI", "Spring AI", "FastAPI",
    "Spring Boot", "Spring Batch", "Java 21", "virtual thread",
    "reinforcement learning", "scikit-learn", "embeddings", "BM25",
    "Solr", "Lucene", "NLP", "sentence transformer", "context engineering",
    "event-driven", "event broker", "Solace", "PubSub", "streaming",
    "microservices", "Docker", "Groq", "OpenRouter", "Perplexity AI",
    "Ollama", "Vaadin", "FastMCP", "kNN", "feature engineering",
    "neural network", "agentic", "agentic AI", "Supabase",
    "vector database", "knowledge graph",
]
_kw_env = os.getenv("CURATOR_KEYWORDS", "")
KEYWORDS: list = [k.strip() for k in _kw_env.split(",") if k.strip()] if _kw_env.strip() else _DEFAULT_KEYWORDS


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

    def _fetch_article_text(self, url: str, max_chars: int = 3000) -> str:
        """Fetch a URL and return plain text (script/style stripped). Used when RSS has no summary."""
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text
            # Remove script and style blocks entirely
            html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:max_chars]
        except Exception as e:
            logger.debug(f"Could not fetch article text from {url}: {e}")
            return ""

    def fetch_relevant_articles(self, max_per_feed: int = CURATOR_MAX_PER_FEED) -> list:
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
                        # Enrich summary at collection time so the AI always has text to work with
                        if len(summary.strip()) < 100 and link:
                            logger.debug(f"RSS summary empty for '{title[:50]}' — fetching URL")
                            summary = self._fetch_article_text(link)
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

    def curate_and_create_ideas(self, dry_run: bool = False, max_ideas: int = 5, request_delay: float = 5.0, channel: str = "linkedin") -> list:
        """
        Main entry point: fetch articles, generate posts with Claude,
        push as Ideas to Buffer for manual review before publishing.
        request_delay: seconds to wait between AI calls (helps with rate limits).
        Rotates through all SSI components so curated posts contribute to every pillar.
        channel: 'linkedin' | 'x' | 'all' — included in the Buffer idea title for easy filtering.
        """
        articles = self.fetch_relevant_articles()
        random.shuffle(articles)
        published = set() if dry_run else self._load_published_titles()
        created_ideas = []

        for article in articles:
            if len(created_ideas) >= max_ideas:
                break
            if article["title"] in published:
                logger.info(f"Skipping already-published idea: {article['title'][:60]}")
                continue
            if created_ideas:
                time.sleep(request_delay)
            # Weighted random pick: components with lower scores get more posts
            ssi_component = _pick_ssi_component()
            logger.info(f"Generating curation post [{ssi_component}] for: {article['title'][:60]}...")
            post_text = self.claude.summarise_for_curation(
                article_text=article["summary"],
                source_url=article["link"],
                ssi_component=ssi_component,
                channel=channel,
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
                print(f"CHANNEL: {channel}")
                print(f"SSI COMPONENT: {ssi_component}")
                print(f"\nGENERATED POST:\n{post_text}")
                created_ideas.append({"dry_run": True, "title": article["title"], "text": post_text, "ssi_component": ssi_component, "channel": channel})
            else:
                if self.buffer:
                    idea = self.buffer.create_idea(
                        text=post_text,
                        title=f"[{channel}|{ssi_component}] {article['title'][:70]}"
                    )
                    self._save_published_title(article["title"])
                    created_ideas.append(idea)
                else:
                    logger.warning("No buffer_service provided — skipping idea creation")

        return created_ideas
