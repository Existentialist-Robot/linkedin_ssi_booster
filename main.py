"""
LinkedIn SSI Booster — main entrypoint
=======================================
Generates and schedules LinkedIn posts via the Buffer API to improve
Social Selling Index (SSI) across all four components.

AI backends (mutually exclusive flags):
  (default)  Anthropic Claude  — requires ANTHROPIC_API_KEY
  --gemini   Google Gemini     — requires GEMINI_API_KEY
  --local    Ollama (local)    — requires Ollama running on OLLAMA_BASE_URL

Usage:
  python main.py --generate [--week N] [--dry-run] [--local | --gemini]
  python main.py --schedule [--week N] [--dry-run] [--local | --gemini]
  python main.py --curate               [--dry-run] [--local | --gemini]
  python main.py --report
"""

import os
import json
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

from services.claude_service import ClaudeService
from services.gemini_service import GeminiService
from services.ollama_service import OllamaService
from services.buffer_service import BufferService
from services.content_curator import ContentCurator
from services.ssi_tracker import SSITracker
from services.github_service import build_github_profile_context
from scheduler import PostScheduler
from content_calendar import CONTENT_CALENDAR

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="LinkedIn SSI Booster via Buffer API")
    parser.add_argument("--generate",  action="store_true", help="Generate posts from content calendar")
    parser.add_argument("--schedule",  action="store_true", help="Push scheduled posts to Buffer")
    parser.add_argument("--curate",    action="store_true", help="Curate AI news and create ideas in Buffer")
    parser.add_argument("--report",    action="store_true", help="Print SSI component report")
    parser.add_argument("--week",      type=int, default=1, help="Week number from content calendar (1-4)")
    parser.add_argument("--dry-run",   action="store_true", help="Preview posts without pushing to Buffer")
    parser.add_argument("--local",     action="store_true", help="Use local Ollama instead of Claude")
    parser.add_argument("--gemini",    action="store_true", help="Use Google Gemini instead of Claude")
    args = parser.parse_args()

    buffer_api_key = os.getenv("BUFFER_API_KEY")
    if not buffer_api_key:
        raise ValueError("BUFFER_API_KEY environment variable is required")
    buffer = BufferService(api_key=buffer_api_key)

    if args.local:
        ai = OllamaService(
            model=os.getenv("OLLAMA_MODEL", "llama3.2"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
        logger.info(f"Using local Ollama model: {ai.model}")
    elif args.gemini:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        ai = GeminiService(
            api_key=gemini_api_key,
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        )
        logger.info(f"Using Gemini model: {ai.model}")
    else:
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        ai = ClaudeService(api_key=anthropic_api_key)
    claude  = ai  # keep existing variable name for compatibility
    curator = ContentCurator(claude_service=ai)
    tracker = SSITracker()

    if args.report:
        tracker.print_report()
        return

    if args.curate:
        logger.info("Curating AI news sources...")
        ideas = curator.curate_and_create_ideas(dry_run=args.dry_run)
        logger.info(f"Created {len(ideas)} ideas in Buffer")
        return

    if args.generate or args.schedule:
        week_topics = CONTENT_CALENDAR.get(f"week_{args.week}", [])
        if not week_topics:
            logger.error(f"No content found for week {args.week}")
            return

        logger.info(f"Generating {len(week_topics)} posts for week {args.week}...")
        posts = []

        for topic in week_topics:
            logger.info(f"  Generating: {topic['title']}")
            post = claude.generate_linkedin_post(
                title=topic["title"],
                angle=topic["angle"],
                ssi_component=topic["ssi_component"],
                hashtags=topic.get("hashtags", []),
                profile_context=PROFILE_CONTEXT
            )
            hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in topic.get("hashtags", []))
            if hashtag_str and hashtag_str not in post:
                post = post.rstrip() + f"\n\n{hashtag_str}"
            posts.append({**topic, "generated_text": post})

            if args.dry_run:
                print(f"\n{'='*60}")
                print(f"TOPIC: {topic['title']}")
                print(f"SSI COMPONENT: {topic['ssi_component']}")
                print(f"\n{post}\n")

        if args.schedule and not args.dry_run:
            scheduler = PostScheduler(buffer_service=buffer)
            scheduler.schedule_week(posts, week_number=args.week)
            logger.info(f"Scheduled {len(posts)} posts to Buffer successfully")


# ---------------------------------------------------------------------------
# Profile context — static base, extended at module load with live GitHub data
# if GITHUB_USER is set in .env (cached 24h to github_repos_cache.json).
# ---------------------------------------------------------------------------
_PROFILE_CONTEXT_BASE = """
Name: Shawn Jackson Dyck
Title: Principal Software Engineer
Location: Ottawa/Remote
Links: github.com/samjd-zz | samjd-zz.github.io | linkedin.com/in/shawn-jackson-dyck-52aa74358

Core expertise: AI-driven search, RAG pipelines, multi-agent orchestration, hybrid search, GovTech AI
Languages & frameworks: Java 21 (Virtual Threads, Spring Boot/Batch/AI), Python (FastAPI, scikit-learn, Gymnasium), Vaadin 24
Search stack: Elasticsearch (BM25+vector, sharding, kNN, translog), Apache Solr/Lucene, Neo4j graph traversal
AI/ML: RAG architecture, multi-agent orchestration, NLP (GateNLP, SentenceTransformers), reinforcement learning, feature engineering
Messaging: Solace PubSub+ Agent Mesh, JMS (millions of events/day), FastMCP, event-driven architecture

Key projects (use these for specifics — never fabricate numbers):
- G7 GovAI Grand Challenge RIA (2025): Led 3-person team. Bilingual NLP hybrid search over 397k Canadian federal law docs. Neo4j graph + Elasticsearch BM25+vector → sub-500ms Gemini RAG Q&A. Tech: Python, FastAPI, Elasticsearch, Neo4j, SentenceTransformers, React/TypeScript, Docker
- S1gnal.Zero (2025): Winner "Best Use of Solace Agent" hackathon. 5-agent FastMCP bot/fake-review detection with real-time Vaadin UI on Solace PubSub+ Agent Mesh. Tech: Java 17, Python FastMCP, Solace PubSub+, Spring Boot, Vaadin, PostgreSQL
- Answer42 (2025): 9-agent Spring Batch pipeline for academic paper analysis. Multi-source discovery (Crossref, Semantic Scholar, Perplexity), three-mode AI chat (Claude/GPT-4/Perplexity). Tech: Java 21, Spring Boot/Batch/AI, Vaadin 24, PostgreSQL/Supabase, Ollama
- TPG/USPS (2014–2023): 9-year JMS lead processing millions of USPS shipment tracking events/day. Tech: Java 6/8, JMS, JAXB, WebSphere, Oracle
- RL Environments (2025): Gymnasium-compliant RL env for B2B SaaS support ticket routing by agent expertise and workload. Tech: Python, scikit-learn, Stable-Baselines3, Streamlit
- Grizz-AI (2024): Multi-model GenAI creative media studio orchestrating OpenAI, ElevenLabs TTS, Groq, Flux image models. Tech: Python, Flask/FastAPI, SQLite

Experience: 20+ years Java/J2EE; since 2024 focused full-time on AI engineering (search, RAG, multi-agent, GovTech)
Goal: Recognized voice in AI-driven search, RAG architecture, GovTech AI, and multi-agent systems on LinkedIn
Tone: Technical but human — concise, direct, occasionally contrarian. Written by someone who has shipped these systems.
"""

_github_block = build_github_profile_context()
PROFILE_CONTEXT = _PROFILE_CONTEXT_BASE.rstrip() + (
    f"\n\n{_github_block}" if _github_block else ""
)


if __name__ == "__main__":
    main()
