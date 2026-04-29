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
import uuid
from colorama import Fore, Style
from pathlib import Path
from typing import Optional
from services.ollama_service import OllamaService
from services.shared import SSI_COMPONENT_INSTRUCTIONS, X_CHAR_LIMIT, X_URL_CHARS
from services.buffer_service import BufferQueueFullError, BufferChannelNotConnectedError
from services.console_grounding import (
    ProjectFact,
    TruthGateMeta,
    get_console_grounding_tag_expansions_from_graph,
    truth_gate_result,
)


CURATOR_MAX_PER_FEED: int = int(os.getenv("CURATOR_MAX_PER_FEED", "10"))

logger = logging.getLogger(__name__)

# Stable run identifier — shared across all candidates logged in this process.
_CURATE_RUN_ID: str = str(uuid.uuid4())

# --- Fetch relevant articles from RSS feeds ---
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
                    # Enrich summary at collection time so the AI always has text to work with
                    if len(summary.strip()) < 100 and link:
                        logger.debug(f"RSS summary empty for '{title[:50]}' — fetching URL")
                        summary = _fetch_article_text_static(link)
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
    {"name": "DeepMind Blog",               "url": "https://deepmind.com/blog/feed/basic/"},
    {"name": "OpenAI Blog",                 "url": "https://openai.com/blog/rss.xml"},
    # Search / graph / data engineering
    {"name": "Elastic Blog",                "url": "https://www.elastic.co/blog/feed"},
    {"name": "Neo4j Blog",                  "url": "https://neo4j.com/blog/feed/"},
    {"name": "TigerGraph Blog",             "url": "https://www.tigergraph.com/feed/"},
    # Java / Spring ecosystem
    {"name": "Spring Blog",                 "url": "https://spring.io/blog.atom"},
    {"name": "Vaadin Blog",                 "url": "https://vaadin.com/blog/rss.xml"},
    {"name": "Inside Java",                 "url": "https://inside.java/feed.xml"},
    {"name": "InfoQ",                       "url": "https://feed.infoq.com/"},
    {"name": "Baeldung",                    "url": "https://feeds.feedburner.com/Baeldung"},
    {"name": "JetBrains Blog",              "url": "https://blog.jetbrains.com/feed/"},
    # Event-driven / messaging / multi-agent
    {"name": "Solace Blog",                 "url": "https://solace.com/blog/feed/"},
    {"name": "Confluent Blog",              "url": "https://www.confluent.io/blog/feed/"},
    {"name": "Apache Pulsar Blog",          "url": "https://pulsar.apache.org/blog/index.xml"},
    {"name": "Temporal Blog",               "url": "https://temporal.io/blog/rss.xml"},
    {"name": "Prefect Blog",                "url": "https://www.prefect.io/blog/rss.xml"},
    # ML engineering & RL
    {"name": "Towards Data Science",        "url": "https://towardsdatascience.com/feed"},
    {"name": "PyTorch Blog",                "url": "https://pytorch.org/blog/feed.xml"},
    # Cloud / Infra
    {"name": "AWS Open Source Blog",        "url": "https://aws.amazon.com/blogs/opensource/feed/"},
    {"name": "Google Cloud Blog",           "url": "https://cloud.google.com/blog/topics/developers-practitioners/rss.xml"},
    # GovTech / broader tech
    {"name": "Apolitical",                  "url": "https://apolitical.co/en/feeds/articles"},
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


def _load_curation_grounding_keywords() -> set[str]:
    """Load keywords used specifically for curation fact retrieval.

    Falls back to CURATOR_KEYWORDS when not explicitly configured.
    """
    raw = os.getenv("CURATION_GROUNDING_TECH_KEYWORDS", "").strip()
    if raw:
        return {part.strip().lower() for part in raw.split(",") if part.strip()}
    return {kw.strip().lower() for kw in KEYWORDS if kw.strip()}



def _fetch_article_text_static(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL and return plain text (script/style stripped). Used when RSS has no summary.
    
    Static version for use in module-level functions.
    """
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


def _load_curation_grounding_tag_expansions() -> dict[str, set[str]]:
    """Load curation-specific tag expansions with console defaults fallback.

    Env format:
      CURATION_GROUNDING_TAG_EXPANSIONS=llm:rag|embeddings|vector search;java:spring|jms
    """
    raw = os.getenv("CURATION_GROUNDING_TAG_EXPANSIONS", "").strip()
    if not raw:
        return get_console_grounding_tag_expansions_from_graph()

    expansions: dict[str, set[str]] = {}
    for block in raw.split(";"):
        block = block.strip()
        if not block or ":" not in block:
            continue
        base, values = block.split(":", 1)
        base = base.strip().lower()
        related = {v.strip().lower() for v in values.split("|") if v.strip()}
        if base and related:
            expansions[base] = related
    return expansions or get_console_grounding_tag_expansions_from_graph()


class ContentCurator:

    def __init__(self, ai_service: OllamaService, buffer_service=None, confidence_policy: str = "balanced", enable_spacy_summarization: bool = True, github_context: str = ""):
        self.ai = ai_service
        self.buffer = buffer_service
        self.confidence_policy = confidence_policy
        self.enable_spacy_summarization = enable_spacy_summarization
        self.github_context = github_context
        self.curation_grounding_keywords = _load_curation_grounding_keywords()
        self.curation_grounding_tag_expansions = _load_curation_grounding_tag_expansions()
        self._avatar_facts: list = []
        self._domain_facts: list = []
        self._narrative_memory = None
        self._spacy_nlp = None
        self._kg = None
        self._hybrid_retriever = None

        # Load spaCy for article summarization if enabled
        if self.enable_spacy_summarization:
            try:
                from services.spacy_nlp import get_spacy_nlp
                self._spacy_nlp = get_spacy_nlp()
            except Exception as _nlp_exc:
                logger.debug("spaCy NLP unavailable for article summarization: %s", _nlp_exc)

        try:
            from services.shared import AVATAR_LEARNING_ENABLED
            from services.avatar_intelligence import load_avatar_state, normalize_evidence_facts, normalize_domain_facts
            _state = load_avatar_state()
            self._avatar_facts = normalize_evidence_facts(_state)
            self._domain_facts = normalize_domain_facts(_state)
            if AVATAR_LEARNING_ENABLED and _state.narrative_memory is not None:
                self._narrative_memory = _state.narrative_memory
            # Bootstrap KG and HybridRetriever for graph-aware reranking
            try:
                from services.knowledge_graph import KnowledgeGraphManager
                from services.hybrid_retriever import HybridRetriever
                self._kg = KnowledgeGraphManager()
                self._kg.bootstrap_from_avatar_state(_state)
                self._hybrid_retriever = HybridRetriever(kg=self._kg)
                logger.debug("HybridRetriever initialised with KG")
            except Exception as _kg_exc:
                logger.debug("KG/HybridRetriever init skipped: %s", _kg_exc)
        except Exception as _exc:
            logger.warning("Avatar state init failed (continuing): %s", _exc)

    def _grounding_facts_for_article(self, article_title: str, article_summary: str, ssi_component: str) -> list[ProjectFact]:
        """
        Retrieve top-N persona and top-N domain facts, reranked via HybridRetriever when a
        KnowledgeGraph is available, falling back to plain BM25 retrieve_evidence otherwise.
        """
        query = f"{article_title}. {article_summary[:600]}. {ssi_component}"
        if self._avatar_facts or self._domain_facts:
            from services.avatar_intelligence import (
                retrieve_evidence,
                evidence_facts_to_project_facts,
                domain_facts_to_project_facts,
                EvidenceFact,
                DomainEvidenceFact,
                _get_evidence_split,
            )
            n_persona, n_domain = _get_evidence_split()

            if self._hybrid_retriever is not None:
                # Hybrid path: rerank all candidates together, then split by type
                all_candidates = list(self._avatar_facts) + list(self._domain_facts)
                total = n_persona + n_domain
                ranked = self._hybrid_retriever.find_facts(query, all_candidates, limit=total)
                persona_hits_typed: list[EvidenceFact] = [f for f in ranked if isinstance(f, EvidenceFact)][:n_persona]
                domain_hits_typed: list[DomainEvidenceFact] = [f for f in ranked if isinstance(f, DomainEvidenceFact)][:n_domain]
            else:
                # Pure BM25 fallback
                persona_hits = retrieve_evidence(query, self._avatar_facts, limit=n_persona) if self._avatar_facts else []
                domain_hits = retrieve_evidence(query, self._domain_facts, limit=n_domain) if self._domain_facts else []
                persona_hits_typed = [f for f in persona_hits if isinstance(f, EvidenceFact)]
                domain_hits_typed = [f for f in domain_hits if isinstance(f, DomainEvidenceFact)]

            persona_pf = evidence_facts_to_project_facts(persona_hits_typed)
            domain_pf = domain_facts_to_project_facts(domain_hits_typed)
            return persona_pf + domain_pf
        # Fallback: no avatar graph loaded — return empty (post still generated, just ungrounded)
        return []

    def _load_published_titles(self) -> set:
        if IDEAS_CACHE_PATH.exists():
            return set(json.loads(IDEAS_CACHE_PATH.read_text()))
        return set()

    def _save_published_title(self, title: str) -> None:
        titles = self._load_published_titles()
        titles.add(title)
        IDEAS_CACHE_PATH.write_text(json.dumps(sorted(titles), indent=2))

    def _fetch_article_text_with_summary(self, url: str, max_chars: int = 3000) -> str:
        """Fetch a URL and return plain text (script/style stripped), with spaCy summarization if enabled.
        
        Instance method version that uses spaCy summarization.
        """
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text
            # Remove script and style blocks entirely
            html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            
            # Use spaCy summarization if enabled and available
            if self._spacy_nlp and len(text) > 500:
                try:
                    summary = self._spacy_nlp.summarize_article(
                        article_text=text[:max_chars],
                        max_sentences=5,
                        focus_entities=True,
                    )
                    if summary:
                        logger.debug("spaCy summarized article from %d to %d chars", len(text[:max_chars]), len(summary))
                        return summary
                except Exception as _sum_exc:
                    logger.debug("spaCy summarization failed, using truncated text: %s", _sum_exc)
            
            return text[:max_chars]
        except Exception as e:
            logger.debug(f"Could not fetch article text from {url}: {e}")
            return ""

    def _score_and_route(
        self,
        post_text: str,
        article_summary: str,
        grounding_facts: list[ProjectFact],
        channel: str,
        article_ref: str,
        requested_mode: str,
    ) -> tuple[str, str]:
        """Score post_text with confidence engine and return (route, reason).

        route is 'post' | 'idea' | 'block'.  Falls back to *requested_mode* on any error.
        Also logs the decision to the learning log when AVATAR_LEARNING_ENABLED is true.
        """
        try:
            from services.avatar_intelligence import (
                extract_confidence_signals,
                score_confidence,
                decide_publish_mode,
                record_confidence_decision,
                compute_repetition_score,
            )

            from services.shared import AVATAR_LEARNING_ENABLED

            # T4.4: repetition signal from narrative memory
            rep_score = (
                compute_repetition_score(post_text, self._narrative_memory)
                if self._narrative_memory is not None
                else 0.0
            )

            # Assess the already-cleaned post against source article to get truth-gate meta.
            _assessed_text, gate_meta = truth_gate_result(
                post_text, article_summary, grounding_facts
            )
            signals = extract_confidence_signals(
                removed_count=gate_meta.removed_count,
                total_sentences=gate_meta.total_sentences,
                reason_codes=gate_meta.reason_codes,
                grounding_facts_count=len(grounding_facts),
                max_grounding_facts=5,
                channel=channel,
                post_length=len(post_text),
                narrative_repetition_score=rep_score,
            )
            result = score_confidence(signals)
            cd = decide_publish_mode(self.confidence_policy, result, requested_mode)


            if AVATAR_LEARNING_ENABLED:
                record_confidence_decision(
                    decision=cd,
                    confidence=result,
                    channel=channel,
                    article_ref=article_ref,
                )

            return cd.route, cd.reason
        except Exception as exc:
            logger.warning(
                "Confidence scoring failed (falling back to requested mode '%s'): %s",
                requested_mode,
                exc,
            )
            return requested_mode, "confidence scoring unavailable — using requested mode"

    def curate_and_create_ideas(self, dry_run: bool = False, max_ideas: int = 5, request_delay: float = 5.0, channel: str = "linkedin", message_type: str = "idea", interactive: bool = False, avatar_explain: bool = False) -> list:
        """
        Main entry point: fetch articles, generate posts with the configured AI service,
                        # --- Confidence scoring for all-channel mode (use LinkedIn post) ---
                        _conf_route, _conf_reason = self._score_and_route(
                            post_text=li_text,
                            article_summary=article["summary"],
                            grounding_facts=grounding_facts,
                            channel="linkedin",
                            article_ref=article.get("link", article["title"]),
                            requested_mode=message_type,
                        )
        and either push as Buffer Ideas (message_type='idea') or schedule directly to the
        next available queue slot (message_type='post').

        message_type='idea'  — creates Buffer Ideas for manual review before publishing.
        message_type='post'  — schedules posts directly:
            linkedin → full post + LinkedIn first comment (hashtags/link kept out of body)
            x        → 3-post thread: hook / insight / close
            bluesky  → 3-post thread: hook / insight / close
            all      → LinkedIn post + X thread + Bluesky thread per article

        request_delay: seconds to wait between AI calls (rate-limit buffer).
        avatar_explain: if True, print evidence IDs and grounding summary after each generation.
        """
        articles = fetch_relevant_articles()
        # Re-rank articles using relevance + freshness + acceptance priors.
        # Falls back to random shuffle if selection_learning data is unavailable.
        try:
            from services.selection_learning import compute_acceptance_priors, rank_articles as _rank_arts
            _priors = compute_acceptance_priors()
            articles = _rank_arts(articles, _priors, keywords=list(KEYWORDS))
        except Exception as _rank_exc:
            logger.warning("selection_learning: ranking failed, using random order: %s", _rank_exc)
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
            _candidate_id = str(uuid.uuid4())
            # Weighted random pick: components with lower scores get more posts
            ssi_component = _pick_ssi_component()
            grounding_facts = self._grounding_facts_for_article(
                article_title=article["title"],
                article_summary=article["summary"],
                ssi_component=ssi_component,
            )
            logger.info(f"Generating [{message_type}|{ssi_component}] for: {article['title'][:60]}...")

            # ----------------------------------------------------------------
            # "all" channels mode — LinkedIn + X + Bluesky + YouTube posts
            # ----------------------------------------------------------------
            if channel == "all":
                _conf_route = "n/a"
                _conf_reason = "not generated"
                li_text = self.ai.summarise_for_curation(
                    article_text=article["summary"],
                    source_url=article["link"],
                    ssi_component=ssi_component,
                    channel="linkedin",
                    post_mode=True,
                    grounding_facts=grounding_facts,
                    interactive=interactive,
                    github_context=self.github_context,
                )

                if not li_text:
                    logger.info(f"Skipping article with no usable content: {article['title'][:60]}")
                    continue

                # --- Confidence scoring for all-channel mode (use LinkedIn post) ---
                _conf_route, _conf_reason = self._score_and_route(
                    post_text=li_text,
                    article_summary=article["summary"],
                    grounding_facts=grounding_facts,
                    channel="linkedin",
                    article_ref=article.get("link", article["title"]),
                    requested_mode=message_type,
                )

                # Append URL then hashtags programmatically (order: body → URL → hashtags)
                li_text = _append_url_and_hashtags(li_text, article["link"])

                time.sleep(request_delay)
                x_post = self.ai.summarise_for_curation(
                    article["summary"],
                    article["link"],
                    ssi_component,
                    "x",
                    grounding_facts=grounding_facts,
                    interactive=interactive,
                    github_context=self.github_context,
                )
                if x_post:
                    x_budget = X_CHAR_LIMIT - X_URL_CHARS  # 257 — cap text before URL is added
                    x_post = _truncate_at_sentence(x_post, x_budget)
                    if article["link"] and article["link"] not in x_post:
                        x_post = x_post.rstrip() + f"\n\n{article['link']}"
                time.sleep(request_delay)
                bsky_post = self.ai.summarise_for_curation(
                    article["summary"],
                    article["link"],
                    ssi_component,
                    "bluesky",
                    grounding_facts=grounding_facts,
                    interactive=interactive,
                    github_context=self.github_context,
                )
                if bsky_post:
                    url_overhead = (2 + len(article["link"])) if article.get("link") else 0
                    bsky_budget = 300 - url_overhead
                    bsky_post = _truncate_at_sentence(bsky_post, bsky_budget)
                    if article["link"] and article["link"] not in bsky_post:
                        bsky_post = bsky_post.rstrip() + f"\n\n{article['link']}"

                time.sleep(request_delay)
                yt_script = self.ai.summarise_for_curation(
                    article["summary"],
                    article["link"],
                    ssi_component,
                    "youtube",
                    post_mode=True,
                    grounding_facts=grounding_facts,
                    interactive=interactive,
                    github_context=self.github_context,
                )
                if yt_script:
                    yt_script = _truncate_at_sentence(yt_script, 500)

                yt_script_path = None
                if yt_script and not dry_run:
                    yt_dir = Path("yt-vid-data")
                    yt_dir.mkdir(exist_ok=True)
                    safe_title = re.sub(r"[^\w\-]", "_", article["title"][:60]).strip("_")
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    yt_script_path = yt_dir / f"{timestamp}_{safe_title}.txt"
                    script_content = (
                        f"TITLE: {article['title']}\n"
                        f"SSI COMPONENT: {ssi_component}\n"
                        f"SOURCE: {article['link']}\n\n"
                        f"{yt_script}\n"
                    )
                    yt_script_path.write_text(script_content, encoding="utf-8")

                if dry_run:
                    print(str(Fore.CYAN) + f"\n{'='*60}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📰 SOURCE: {article['source']}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📄 ARTICLE: {article['title']}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + "📡 CHANNEL: all" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"🎯 SSI COMPONENT: {ssi_component}" + str(Style.RESET_ALL))
                    print(str(Fore.YELLOW) + f"🔒 CONFIDENCE ROUTE: {_conf_route} — {_conf_reason}" + str(Style.RESET_ALL))
                    print(str(Fore.GREEN) + f"\n🔵 LINKEDIN POST:" + str(Style.RESET_ALL) + f"\n{li_text}")
                    print(str(Fore.BLUE) + f"\n𝕏  X POST:" + str(Style.RESET_ALL) + f"\n{x_post}")
                    print(str(Fore.MAGENTA) + f"\n🦋 BLUESKY POST:" + str(Style.RESET_ALL) + f"\n{bsky_post}")
                    if yt_script:
                        print(str(Fore.RED) + str(Style.BRIGHT) + "\n🎬 YOUTUBE SHORT SCRIPT:" + str(Style.RESET_ALL) + f"\n{yt_script}\n")

                    # Print avatar explanation if requested
                    if avatar_explain:
                        try:
                            from services.avatar_intelligence import (
                                retrieve_evidence,
                                build_explain_output,
                                format_explain_output,
                            )
                            grounding_query = f"{article['title']}. {article['summary'][:600]}. {ssi_component}"
                            all_facts = self._avatar_facts + self._domain_facts
                            _relevant = retrieve_evidence(grounding_query, all_facts)
                            _explain = build_explain_output(
                                evidence_facts=_relevant,
                                article_ref=article.get("title", ""),
                                channel="all",
                                ssi_component=ssi_component,
                            )
                            print(format_explain_output(_explain))
                        except Exception as _exp_exc:
                            logger.warning("Avatar explanation failed (continuing): %s", _exp_exc)
                    
                    created_ideas.append({"dry_run": True, "title": article["title"], "ssi_component": ssi_component, "channel": "all"})
                    # Do NOT log candidates in dry_run mode. Only log when user is actually reviewing or publishing, to avoid biasing acceptance priors with unreviewed content.
                else:
                    # Log candidate before push (route=post for all-channel mode), but only if not dry_run
                    if not dry_run:
                        try:
                            from services.selection_learning import log_candidate as _log_cand_all
                            _log_cand_all(
                                candidate_id=_candidate_id,
                                article_url=article.get("link", ""),
                                article_title=article.get("title", ""),
                                article_source=article.get("source", ""),
                                ssi_component=ssi_component,
                                channel="all",
                                post_text=li_text,
                                buffer_id=None,
                                route="post",
                                run_id=_CURATE_RUN_ID,
                            )
                        except Exception as _cand_exc:
                            logger.warning("selection_learning: candidate log failed (continuing): %s", _cand_exc)
                    # Display generated posts for traceability
                    print(str(Fore.CYAN) + f"\n{'='*60}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📰 SOURCE: {article['source']}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📄 ARTICLE: {article['title']}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + "📡 CHANNEL: all" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"🎯 SSI COMPONENT: {ssi_component}" + str(Style.RESET_ALL))
                    print(str(Fore.YELLOW) + f"🔒 CONFIDENCE ROUTE: {_conf_route} — {_conf_reason}" + str(Style.RESET_ALL))
                    print(str(Fore.GREEN) + f"\n🔵 LINKEDIN POST:" + str(Style.RESET_ALL) + f"\n{li_text}")
                    if x_post:
                        print(str(Fore.BLUE) + f"\n𝕏  X POST:" + str(Style.RESET_ALL) + f"\n{x_post}")
                    if bsky_post:
                        print(str(Fore.MAGENTA) + f"\n🦋 BLUESKY POST:" + str(Style.RESET_ALL) + f"\n{bsky_post}")
                    
                    # Print avatar explanation if requested
                    if avatar_explain:
                        try:
                            from services.avatar_intelligence import (
                                retrieve_evidence,
                                build_explain_output,
                                format_explain_output,
                            )
                            grounding_query = f"{article['title']}. {article['summary'][:600]}. {ssi_component}"
                            _relevant = retrieve_evidence(grounding_query, self._avatar_facts)
                            _explain = build_explain_output(
                                evidence_facts=_relevant,
                                article_ref=article.get("title", ""),
                                channel="all",
                                ssi_component=ssi_component,
                            )
                            print(format_explain_output(_explain))
                        except Exception as _exp_exc:
                            logger.warning("Avatar explanation failed (continuing): %s", _exp_exc)
                    
                    if self.buffer:
                        try:
                            _li_post = self.buffer.create_scheduled_post(
                                self.buffer.get_linkedin_channel_id(), li_text
                            )
                            try:
                                from services.selection_learning import update_candidate_buffer_id as _upd_all
                                _upd_all(_candidate_id, _li_post.get("id", ""))
                            except Exception as _upd_exc:
                                logger.warning("selection_learning: buffer_id update failed (continuing): %s", _upd_exc)
                            if x_post:
                                try:
                                    self.buffer.create_scheduled_post(
                                        self.buffer.get_x_channel_id(), x_post, channel="x"
                                    )
                                except BufferChannelNotConnectedError as e:
                                    logger.warning(
                                        str(Fore.YELLOW)
                                        + f"⚠️  X channel is not configured — skipping X post in all-channel mode. ({e})"
                                        + str(Style.RESET_ALL)
                                    )
                            if bsky_post:
                                try:
                                    self.buffer.create_scheduled_post(
                                        self.buffer.get_bluesky_channel_id(), bsky_post, channel="bluesky"
                                    )
                                except BufferChannelNotConnectedError as e:
                                    logger.warning(
                                        str(Fore.YELLOW)
                                        + f"⚠️  Bluesky channel is not configured — skipping Bluesky post in all-channel mode. ({e})"
                                        + str(Style.RESET_ALL)
                                    )
                            if yt_script:
                                print(str(Fore.RED) + str(Style.BRIGHT) + "\n🎬 YOUTUBE SHORT SCRIPT (all-channel mode):" + str(Style.RESET_ALL))
                                print(str(Fore.WHITE) + f"📄 TITLE:  {article['title']}" + str(Style.RESET_ALL))
                                print(str(Fore.CYAN) + f"🎯 SSI:    {ssi_component}" + str(Style.RESET_ALL))
                                print(f"\n{yt_script}\n")
                                if yt_script_path:
                                    print(str(Fore.GREEN) + f"💾 Saved to: {yt_script_path}" + str(Style.RESET_ALL))
                                print(str(Fore.YELLOW) + "⚠️  YouTube script was generated locally only — Buffer YouTube requires a video upload." + str(Style.RESET_ALL))
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
                # T4.3: build continuity snippet from narrative memory (empty string if unavailable)
                try:
                    from services.avatar_intelligence import build_continuity_context
                    _continuity = (
                        build_continuity_context(self._narrative_memory)
                        if self._narrative_memory is not None
                        else ""
                    )
                except Exception:
                    _continuity = ""

                post_text = self.ai.summarise_for_curation(
                    article_text=article["summary"],
                    source_url=article["link"],
                    ssi_component=ssi_component,
                    channel=effective_channel,
                    post_mode=(message_type == "post"),
                    grounding_facts=grounding_facts,
                    interactive=interactive,
                    continuity_context=_continuity,
                    github_context=self.github_context,
                )
                if not post_text:
                    logger.info(f"Skipping article with no usable content: {article['title'][:60]}")
                    continue

                # T4.2 + T4.1: update narrative memory with themes/claims from this post
                try:
                    from services.shared import AVATAR_LEARNING_ENABLED
                    from services.avatar_intelligence import (
                        extract_narrative_updates,
                        update_narrative_memory,
                        save_narrative_memory,
                    )
                    if AVATAR_LEARNING_ENABLED and self._narrative_memory is not None:
                        _updates = extract_narrative_updates(
                            post_text, ssi_component, article["title"]
                        )
                        self._narrative_memory = update_narrative_memory(
                            self._narrative_memory,
                            themes=_updates["themes"],
                            claims=_updates["claims"],
                            arcs=_updates["arcs"],
                        )
                        save_narrative_memory(self._narrative_memory)
                except Exception as _mem_exc:
                    logger.warning("Narrative memory update failed (continuing): %s", _mem_exc)

                # Append URL then hashtags programmatically (order: body → URL → hashtags).
                # For X/Bluesky: cap the LLM text first, THEN append URL so buffer_service
                # never sees text+URL combined (which would truncate the URL).
                if effective_channel == "linkedin":
                    post_text = _append_url_and_hashtags(post_text, article["link"])
                elif effective_channel == "youtube":
                    # Hard cap — model frequently ignores char limits; enforce here
                    post_text = _truncate_at_sentence(post_text, 500)
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

                # ── Confidence scoring + policy routing (Phase 1C) ────────────────
                # Only enforce routing when actually pushing to Buffer (not dry_run).
                # In dry_run mode we display the decision for observability.
                _conf_route, _conf_reason = self._score_and_route(
                    post_text=post_text,
                    article_summary=article["summary"],
                    grounding_facts=grounding_facts,
                    channel=effective_channel,
                    article_ref=article.get("link", article["title"]),
                    requested_mode=message_type,
                )

                # Log candidate for selection learning (before any buffer push), but only if not dry_run
                if not dry_run:
                    try:
                        from services.selection_learning import log_candidate as _log_cand
                        _log_cand(
                            candidate_id=_candidate_id,
                            article_url=article.get("link", ""),
                            article_title=article.get("title", ""),
                            article_source=article.get("source", ""),
                            ssi_component=ssi_component,
                            channel=effective_channel,
                            post_text=post_text,
                            buffer_id=None,
                            route=_conf_route,
                            run_id=_CURATE_RUN_ID,
                        )
                    except Exception as _cand_exc:
                        logger.warning("selection_learning: candidate log failed (continuing): %s", _cand_exc)

                if dry_run:
                    print(str(Fore.CYAN) + f"\n{'='*60}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📰 SOURCE: {article['source']}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📄 ARTICLE: {article['title']}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"📡 CHANNEL: {channel}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"🎯 SSI COMPONENT: {ssi_component}" + str(Style.RESET_ALL))
                    print(str(Fore.YELLOW) + f"🔒 CONFIDENCE ROUTE: {_conf_route} — {_conf_reason}" + str(Style.RESET_ALL))
                    print(str(Fore.GREEN) + f"\n✍️  GENERATED POST:" + str(Style.RESET_ALL) + f"\n{post_text}")
                    
                    # Print avatar explanation if requested
                    if avatar_explain:
                        try:
                            from services.avatar_intelligence import (
                                retrieve_evidence,
                                build_explain_output,
                                format_explain_output,
                            )
                            grounding_query = f"{article['title']}. {article['summary'][:600]}. {ssi_component}"
                            _relevant = retrieve_evidence(grounding_query, self._avatar_facts)
                            _explain = build_explain_output(
                                evidence_facts=_relevant,
                                article_ref=article.get("title", ""),
                                channel=effective_channel,
                                ssi_component=ssi_component,
                            )
                            print(format_explain_output(_explain))
                        except Exception as _exp_exc:
                            logger.warning("Avatar explanation failed (continuing): %s", _exp_exc)
                    
                    created_ideas.append({"dry_run": True, "title": article["title"], "text": post_text, "ssi_component": ssi_component, "channel": channel, "confidence_route": _conf_route})
                else:
                    # Display generated post for traceability
                    print(str(Fore.CYAN) + f"\n{'='*60}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📰 SOURCE: {article['source']}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📄 ARTICLE: {article['title']}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"📡 CHANNEL: {channel}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"🎯 SSI COMPONENT: {ssi_component}" + str(Style.RESET_ALL))
                    print(str(Fore.YELLOW) + f"🔒 CONFIDENCE ROUTE: {_conf_route} — {_conf_reason}" + str(Style.RESET_ALL))
                    print(str(Fore.GREEN) + f"\n✍️  GENERATED POST:" + str(Style.RESET_ALL) + f"\n{post_text}")
                    
                    # Print avatar explanation if requested
                    if avatar_explain:
                        try:
                            from services.avatar_intelligence import (
                                retrieve_evidence,
                                build_explain_output,
                                format_explain_output,
                            )
                            grounding_query = f"{article['title']}. {article['summary'][:600]}. {ssi_component}"
                            _relevant = retrieve_evidence(grounding_query, self._avatar_facts)
                            _explain = build_explain_output(
                                evidence_facts=_relevant,
                                article_ref=article.get("title", ""),
                                channel=effective_channel,
                                ssi_component=ssi_component,
                            )
                            print(format_explain_output(_explain))
                        except Exception as _exp_exc:
                            logger.warning("Avatar explanation failed (continuing): %s", _exp_exc)

                    # Confidence policy: block → skip this article entirely
                    if _conf_route == "block":
                        logger.warning(
                            str(Fore.YELLOW)
                            + f"⚠️  Confidence policy blocked publish for: {article['title'][:60]}"
                            + str(Style.RESET_ALL)
                        )
                        continue

                    if self.buffer:
                        # Confidence policy: idea takes precedence over post when policy downgrades.
                        effective_message_type = "idea" if _conf_route == "idea" else message_type
                        if effective_message_type == "post":
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
                                try:
                                    from services.selection_learning import update_candidate_buffer_id as _upd
                                    _upd(_candidate_id, post.get("id", ""))
                                except Exception as _upd_exc:
                                    logger.warning("selection_learning: buffer_id update failed (continuing): %s", _upd_exc)
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
                            try:
                                from services.selection_learning import update_candidate_buffer_id as _upd
                                _upd(_candidate_id, idea.get("id", ""))
                            except Exception as _upd_exc:
                                logger.warning("selection_learning: buffer_id update failed (continuing): %s", _upd_exc)
                            created_ideas.append(idea)
                    else:
                        logger.warning("No buffer_service provided — skipping idea creation")

        return created_ideas
