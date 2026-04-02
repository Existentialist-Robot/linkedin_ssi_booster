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
from colorama import Fore, Style
from pathlib import Path
from typing import Optional
from services.ollama_service import OllamaService
from services.shared import SSI_COMPONENT_INSTRUCTIONS, X_CHAR_LIMIT, X_URL_CHARS
from services.buffer_service import BufferQueueFullError

logger = logging.getLogger(__name__)


def _truncate_at_sentence(text: str, budget: int) -> str:
    """Ensure *text* fits within *budget* chars AND ends on a complete sentence.

    If the text is already within budget, only cuts at a sentence boundary if
    one exists — never removes words from within-budget text (that would make
    a trailing incomplete sentence worse, not better).
    If the text was over budget and had to be hard-cut, finds the last sentence
    boundary; if none, removes the partial word at the cut point.
    """
    was_over_budget = len(text) > budget
    if was_over_budget:
        text = text[:budget]
    stripped = text.rstrip()
    # Already ends cleanly
    if stripped[-1:] in ".!?":
        return stripped
    # Find the last sentence-ending punctuation before any whitespace or end-of-string.
    # Using regex so we catch "sentence.\nNext" (period before newline, not space).
    last_match = None
    for m in re.finditer(r"[.!?](?=\s|$)", stripped):
        last_match = m
    if last_match and last_match.end() > len(stripped) // 4:
        return stripped[:last_match.end()]
    if was_over_budget:
        # Remove partial word at the hard-cut point — at least end on a word boundary
        return stripped.rsplit(" ", 1)[0]
    # Text was within budget but AI didn't end cleanly — return as-is.
    # The prompt is responsible for producing complete sentences.
    return stripped


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


def _extract_hashtags(text: str) -> tuple[str, str]:
    """Split the AI-generated post body from the trailing hashtag line.
    Returns (body, hashtags) where hashtags may be an empty string.
    The last non-empty line is treated as hashtags if every word starts with '#'.
    """
    lines = text.rstrip().splitlines()
    if lines and all(w.startswith('#') for w in lines[-1].split()):
        return "\n".join(lines[:-1]).rstrip(), lines[-1]
    return text, ""


def _append_url_and_hashtags(text: str, url: str) -> str:
    """Programmatically append source URL then hashtags to a LinkedIn post body.
    Hashtags are extracted from the AI output, stripped from the body, and
    re-appended after the URL so ordering is always: body → URL → hashtags.
    """
    body, hashtags = _extract_hashtags(text)
    result = body.rstrip()
    if url and url not in result:
        result += f"\n\n{url}"
    if hashtags:
        result += f"\n\n{hashtags}"
    return result

# RSS feeds — override via CURATOR_RSS_FEEDS in .env as a JSON array:
# [{"name": "My Blog", "url": "https://example.com/feed.xml"}, ...]
_DEFAULT_RSS_FEEDS = [
    # LLM / AI research
    {"name": "Anthropic Blog",              "url": "https://www.anthropic.com/rss.xml"},
    {"name": "Hugging Face Blog",           "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "The Batch (DeepLearning.AI)", "url": "https://www.deeplearning.ai/the-batch/feed/"},
    {"name": "Google AI Blog",              "url": "https://blog.research.google/atom.xml"},
    {"name": "AWS Machine Learning",        "url": "https://aws.amazon.com/blogs/machine-learning/feed/"},
    {"name": "LangChain Blog",              "url": "https://blog.langchain.dev/rss/"},
    # Search / graph / data engineering
    {"name": "Elastic Blog",                "url": "https://www.elastic.co/blog/feed"},
    {"name": "Neo4j Blog",                  "url": "https://neo4j.com/blog/feed/"},
    # Java / Spring ecosystem
    {"name": "Spring Blog",                 "url": "https://spring.io/blog.atom"},
    {"name": "Inside Java",                 "url": "https://inside.java/feed.xml"},
    {"name": "InfoQ",                       "url": "https://feed.infoq.com/"},
    # Event-driven / messaging / multi-agent
    {"name": "Solace Blog",                 "url": "https://solace.com/blog/feed/"},
    # ML engineering & RL
    {"name": "Towards Data Science",        "url": "https://towardsdatascience.com/feed"},
    {"name": "PyTorch Blog",                "url": "https://pytorch.org/blog/feed.xml"},
    # GovTech / broader tech
    {"name": "The New Stack",               "url": "https://thenewstack.io/feed/"},
]
_rss_env = os.getenv("CURATOR_RSS_FEEDS", "")
RSS_FEEDS: list = json.loads(_rss_env) if _rss_env.strip() else _DEFAULT_RSS_FEEDS

# Keywords — override via CURATOR_KEYWORDS in .env as a comma-separated list
_DEFAULT_KEYWORDS = [
    # LLM / RAG / search — core domain
    "RAG", "retrieval augmented", "LLM", "large language model", "language model",
    "vector search", "hybrid search", "semantic search", "information retrieval",
    "embeddings", "BM25", "kNN", "sentence transformer", "context engineering",
    "elasticsearch", "Solr", "Lucene",
    # Graph / knowledge
    "neo4j", "knowledge graph", "graph database", "graph traversal",
    "vector database",
    # Agents / MCP / orchestration
    "agent", "multi-agent", "MCP", "model context protocol", "FastMCP",
    "agentic", "agentic AI", "tool calling", "function calling",
    # GovTech / regulated AI
    "government AI", "GovTech", "regulatory AI", "compliance AI", "public sector AI",
    # Java / Spring ecosystem
    "Spring AI", "Spring Boot", "Spring Batch", "Java 21", "virtual thread",
    "Java AI", "JMS", "message queue",
    # Event-driven / messaging
    "Solace", "PubSub+", "event broker", "FastMCP",
    # RL / ML engineering
    "reinforcement learning", "Gymnasium", "Stable-Baselines", "reward function",
    "scikit-learn", "feature engineering", "NLP", "neural network",
    # Additional AI / ML tooling
    "Ollama", "Groq", "OpenRouter", "Perplexity AI", "Vaadin", "Supabase",
    "ElevenLabs", "text to speech", "generative media",
    "FastAPI",
]
_kw_env = os.getenv("CURATOR_KEYWORDS", "")
KEYWORDS: list = [k.strip() for k in _kw_env.split(",") if k.strip()] if _kw_env.strip() else _DEFAULT_KEYWORDS


class ContentCurator:

    def __init__(self, ai_service: OllamaService, buffer_service=None):
        self.ai = ai_service
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

    def curate_and_create_ideas(self, dry_run: bool = False, max_ideas: int = 5, request_delay: float = 5.0, channel: str = "linkedin", message_type: str = "idea") -> list:
        """
        Main entry point: fetch articles, generate posts with the configured AI service,
        and either push as Buffer Ideas (message_type='idea') or schedule directly to the
        next available queue slot (message_type='post').

        message_type='idea'  — creates Buffer Ideas for manual review before publishing.
        message_type='post'  — schedules posts directly:
            linkedin → full post + LinkedIn first comment (hashtags/link kept out of body)
            x        → 3-post thread: hook / insight / close
            bluesky  → 3-post thread: hook / insight / close
            all      → LinkedIn post + X thread + Bluesky thread per article

        request_delay: seconds to wait between AI calls (rate-limit buffer).
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
            logger.info(f"Generating [{message_type}|{ssi_component}] for: {article['title'][:60]}...")

            # ----------------------------------------------------------------
            # "all" channels post mode — LinkedIn + X + Bluesky single posts
            # ----------------------------------------------------------------
            if message_type == "post" and channel == "all":
                li_text = self.ai.summarise_for_curation(
                    article_text=article["summary"],
                    source_url=article["link"],
                    ssi_component=ssi_component,
                    channel="linkedin",
                    post_mode=True,
                )
                if not li_text:
                    logger.info(f"Skipping article with no usable content: {article['title'][:60]}")
                    continue
                # Append URL then hashtags programmatically (order: body → URL → hashtags)
                li_text = _append_url_and_hashtags(li_text, article["link"])

                time.sleep(request_delay)
                x_post = self.ai.summarise_for_curation(article["summary"], article["link"], ssi_component, "x")
                if x_post:
                    x_budget = X_CHAR_LIMIT - X_URL_CHARS  # 257 — cap text before URL is added
                    x_post = _truncate_at_sentence(x_post, x_budget)
                    if article["link"] and article["link"] not in x_post:
                        x_post = x_post.rstrip() + f"\n\n{article['link']}"
                time.sleep(request_delay)
                bsky_post = self.ai.summarise_for_curation(article["summary"], article["link"], ssi_component, "bluesky")
                if bsky_post:
                    url_overhead = (2 + len(article["link"])) if article.get("link") else 0
                    bsky_budget = 300 - url_overhead
                    bsky_post = _truncate_at_sentence(bsky_post, bsky_budget)
                    if article["link"] and article["link"] not in bsky_post:
                        bsky_post = bsky_post.rstrip() + f"\n\n{article['link']}"

                if dry_run:
                    print(str(Fore.CYAN) + f"\n{'='*60}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📰 SOURCE: {article['source']}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📄 ARTICLE: {article['title']}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + "📡 CHANNEL: all" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"🎯 SSI COMPONENT: {ssi_component}" + str(Style.RESET_ALL))
                    print(str(Fore.GREEN) + f"\n🔵 LINKEDIN POST:" + str(Style.RESET_ALL) + f"\n{li_text}")
                    print(str(Fore.BLUE) + f"\n𝕏  X POST:" + str(Style.RESET_ALL) + f"\n{x_post}")
                    print(str(Fore.MAGENTA) + f"\n🦋 BLUESKY POST:" + str(Style.RESET_ALL) + f"\n{bsky_post}")
                    created_ideas.append({"dry_run": True, "title": article["title"], "ssi_component": ssi_component, "channel": "all"})
                else:
                    if self.buffer:
                        try:
                            self.buffer.create_scheduled_post(
                                self.buffer.get_linkedin_channel_id(), li_text
                            )
                            if x_post:
                                self.buffer.create_scheduled_post(
                                    self.buffer.get_x_channel_id(), x_post, channel="x"
                                )
                            if bsky_post:
                                self.buffer.create_scheduled_post(
                                    self.buffer.get_bluesky_channel_id(), bsky_post, channel="bluesky"
                                )
                            self._save_published_title(article["title"])
                            created_ideas.append({"title": article["title"], "channel": "all", "ssi_component": ssi_component})
                        except BufferQueueFullError as e:
                            logger.warning(
                                str(Fore.YELLOW) + f"⚠️  Buffer queue is full — stopping early. "
                                f"Free up slots at https://publish.buffer.com before running again. ({e})" + str(Style.RESET_ALL)
                            )
                            break
                    else:
                        logger.warning("No buffer_service provided — skipping post creation")

            # ----------------------------------------------------------------
            # Single post mode (linkedin / x / bluesky) OR idea mode
            # ----------------------------------------------------------------
            else:
                effective_channel = "linkedin" if (message_type == "post" and channel == "linkedin") else channel
                post_text = self.ai.summarise_for_curation(
                    article_text=article["summary"],
                    source_url=article["link"],
                    ssi_component=ssi_component,
                    channel=effective_channel,
                    post_mode=(message_type == "post"),
                )
                if not post_text:
                    logger.info(f"Skipping article with no usable content: {article['title'][:60]}")
                    continue

                # Append URL then hashtags programmatically (order: body → URL → hashtags).
                # For X/Bluesky: cap the LLM text first, THEN append URL so buffer_service
                # never sees text+URL combined (which would truncate the URL).
                if effective_channel == "linkedin":
                    post_text = _append_url_and_hashtags(post_text, article["link"])
                elif effective_channel == "x":
                    x_budget = X_CHAR_LIMIT - X_URL_CHARS
                    post_text = _truncate_at_sentence(post_text, x_budget)
                    if article["link"] and article["link"] not in post_text:
                        post_text = post_text.rstrip() + f"\n\n{article['link']}"
                elif effective_channel == "bluesky":
                    url_overhead = (2 + len(article["link"])) if article.get("link") else 0
                    bsky_budget = 300 - url_overhead
                    post_text = _truncate_at_sentence(post_text, bsky_budget)
                    if article["link"] and article["link"] not in post_text:
                        post_text = post_text.rstrip() + f"\n\n{article['link']}"

                if dry_run:
                    print(str(Fore.CYAN) + f"\n{'='*60}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📰 SOURCE: {article['source']}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📄 ARTICLE: {article['title']}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"📡 CHANNEL: {channel}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"🎯 SSI COMPONENT: {ssi_component}" + str(Style.RESET_ALL))
                    print(str(Fore.GREEN) + f"\n✍️  GENERATED POST:" + str(Style.RESET_ALL) + f"\n{post_text}")
                    created_ideas.append({"dry_run": True, "title": article["title"], "text": post_text, "ssi_component": ssi_component, "channel": channel})
                else:
                    if self.buffer:
                        if message_type == "post":
                            if effective_channel == "youtube":
                                # Buffer YouTube requires a video file — can't post text-only.
                                # Write the script to yt-vid-data/ for use with lipsync.video.
                                yt_dir = Path("yt-vid-data")
                                yt_dir.mkdir(exist_ok=True)
                                safe_title = re.sub(r"[^\w\-]", "_", article["title"][:60]).strip("_")
                                from datetime import datetime as _dt
                                timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
                                script_path = yt_dir / f"{timestamp}_{safe_title}.txt"
                                script_content = f"TITLE: {article['title']}\nSSI COMPONENT: {ssi_component}\nSOURCE: {article['link']}\n\n{post_text}\n"
                                script_path.write_text(script_content, encoding="utf-8")
                                print(str(Fore.RED) + str(Style.BRIGHT) + "\n🎬 YOUTUBE SHORT SCRIPT (copy to lipsync.video):" + str(Style.RESET_ALL))
                                print(str(Fore.WHITE) + f"📄 TITLE:  {article['title']}" + str(Style.RESET_ALL))
                                print(str(Fore.CYAN) + f"🎯 SSI:    {ssi_component}" + str(Style.RESET_ALL))
                                print(f"\n{post_text}\n")
                                print(str(Fore.GREEN) + f"💾 Saved to: {script_path}" + str(Style.RESET_ALL))
                                print(str(Fore.YELLOW) + "⚠️  Buffer YouTube requires a video — script not pushed to Buffer.\n   Render with lipsync.video, then upload the video manually." + str(Style.RESET_ALL))
                                self._save_published_title(article["title"])
                                created_ideas.append({"title": article["title"], "text": post_text, "ssi_component": ssi_component, "channel": "youtube", "script_path": str(script_path)})
                                continue
                            elif effective_channel == "x":
                                channel_id = self.buffer.get_x_channel_id()
                            elif effective_channel == "bluesky":
                                channel_id = self.buffer.get_bluesky_channel_id()
                            else:
                                channel_id = self.buffer.get_linkedin_channel_id()
                            try:
                                post = self.buffer.create_scheduled_post(
                                    channel_id, post_text, channel=effective_channel
                                )
                                self._save_published_title(article["title"])
                                created_ideas.append(post)
                            except BufferQueueFullError as e:
                                logger.warning(
                                    str(Fore.YELLOW) + f"⚠️  Buffer queue is full — stopping early. "
                                    f"Free up slots at https://publish.buffer.com before running again. ({e})" + str(Style.RESET_ALL)
                                )
                                break
                        else:
                            idea = self.buffer.create_idea(
                                text=post_text,
                                title=f"[{channel}|{ssi_component}] {article['title'][:70]}"
                            )
                            self._save_published_title(article["title"])
                            created_ideas.append(idea)
                    else:
                        logger.warning("No buffer_service provided — skipping idea creation")

        return created_ideas
