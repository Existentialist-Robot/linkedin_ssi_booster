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
  python main.py --generate [--week N] [--dry-run] [--local | --gemini] [--channel linkedin|x|bluesky|all]
  python main.py --schedule [--week N] [--dry-run] [--local | --gemini] [--channel linkedin|x|bluesky|all]
  python main.py --curate               [--dry-run] [--local | --gemini] [--channel linkedin|x|bluesky|all] [--type idea|post]
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
    parser.add_argument("--save-ssi",  nargs=4, metavar=("BRAND", "FIND", "ENGAGE", "BUILD"),
                        type=float, help="Record today's SSI scores: --save-ssi 10.49 9.69 11.0 12.15")
    parser.add_argument("--bsky-stats", action="store_true", help="Fetch and display live Bluesky profile stats")
    parser.add_argument("--week",      type=int, default=1, help="Week number from content calendar (1-4)")
    parser.add_argument("--dry-run",   action="store_true", help="Preview posts without pushing to Buffer")
    parser.add_argument("--local",     action="store_true", help="Use local Ollama instead of Claude")
    parser.add_argument("--gemini",    action="store_true", help="Use Google Gemini instead of Claude")
    parser.add_argument("--channel",   choices=["linkedin", "x", "bluesky", "all"], default="linkedin",
                        help="Target channel(s) for scheduling/curation (default: linkedin)")
    parser.add_argument("--type",      choices=["idea", "post"], default="idea",
                        help="idea: add to Buffer Ideas board; post: schedule directly to next available queue slot (default: idea)")
    parser.add_argument("--debug",     action="store_true", help="Enable DEBUG-level logging (shows raw API payloads and responses)")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.WARNING)  # suppress noisy HTTP client logs

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
        ai = ClaudeService(
            api_key=anthropic_api_key,
            model=os.getenv("CLAUDE_MODEL", "claude-opus-4-6"),
        )
        logger.info(f"Using Claude model: {ai.model}")
    claude  = ai  # keep existing variable name for compatibility
    curator = ContentCurator(claude_service=ai, buffer_service=buffer)
    tracker = SSITracker()

    if args.report:
        tracker.print_report()
        return

    if args.save_ssi:
        brand, find, engage, build = args.save_ssi
        tracker.save_scores(establish=brand, find=find, engage=engage, build=build)
        total = brand + find + engage + build
        print(f"Saved SSI scores: brand={brand} find={find} engage={engage} build={build} total={total:.2f}")
        return

    if args.bsky_stats:
        from services.ssi_tracker import fetch_bluesky_stats
        stats = fetch_bluesky_stats()
        if stats:
            print(f"\nBluesky stats for @{stats['handle']}")
            print(f"  Followers    : {stats['followers']}")
            print(f"  Following    : {stats['following']}")
            print(f"  Total posts  : {stats['posts']}")
            print(f"\n  Last {stats['analysed']} posts (engagement)")
            print(f"  Likes        : {stats['total_likes']}")
            print(f"  Replies      : {stats['total_replies']}")
            print(f"  Reposts      : {stats['total_reposts']}")
            print(f"  Quotes       : {stats['total_quotes']}")
            print(f"  Avg / post   : {stats['avg_engagement']}")
            if stats.get("top_post"):
                tp = stats["top_post"]
                print(f"\n  Top post ({tp['likes']}L {tp['replies']}R {tp['reposts']}RT)")
                print(f"  '{tp['text']}'")
                if tp["url"]:
                    print(f"  {tp['url']}")
        return

    if args.curate:
        logger.info(f"Curating AI news sources (channel: {args.channel}, type: {args.type})...")
        # Gemini free tier = 15 RPM. Use a longer inter-call delay to avoid 429s.
        # 'all' channel makes 3 calls per article, so needs even more breathing room.
        if args.gemini:
            if args.channel == "all":
                _request_delay = 20.0
            else:
                _request_delay = 8.0
        else:
            _request_delay = 5.0
        ideas = curator.curate_and_create_ideas(dry_run=args.dry_run, channel=args.channel, message_type=args.type, request_delay=_request_delay)
        logger.info(f"Created {len(ideas)} {'posts' if args.type == 'post' else 'ideas'} in Buffer")
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
                profile_context=PROFILE_CONTEXT,
                channel=args.channel,
            )
            # Hashtags eat too many chars on X — only append for LinkedIn
            if args.channel != "x":
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
            scheduler.schedule_week(posts, week_number=args.week, channel=args.channel)
            logger.info(f"Scheduled {len(posts)} posts to Buffer ({args.channel}) successfully")


# ---------------------------------------------------------------------------
# Profile context — loaded from PROFILE_CONTEXT in .env (gitignored).
# Extended at module load with live GitHub data if GITHUB_USER is set.
# ---------------------------------------------------------------------------
_PROFILE_CONTEXT_BASE = os.getenv("PROFILE_CONTEXT", "").strip()
if not _PROFILE_CONTEXT_BASE:
    raise ValueError(
        "PROFILE_CONTEXT is not set in .env. "
        "Copy the example from .env.example and fill in your details."
    )

_github_block = build_github_profile_context()
PROFILE_CONTEXT = _PROFILE_CONTEXT_BASE + (
    f"\n\n{_github_block}" if _github_block else ""
)


if __name__ == "__main__":
    main()
