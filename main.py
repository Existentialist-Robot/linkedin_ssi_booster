"""
LinkedIn SSI Booster — main entrypoint
=======================================
Generates and schedules LinkedIn posts via the Buffer API to improve
Social Selling Index (SSI) across all four components.

AI backend: Ollama (local) — requires Ollama running on OLLAMA_BASE_URL

Usage:
  python main.py --generate [--week N] [--dry-run] [--channel linkedin|x|bluesky|youtube|all]
  python main.py --schedule [--week N] [--dry-run] [--channel linkedin|x|bluesky|youtube|all]
  python main.py --curate               [--dry-run] [--channel linkedin|x|bluesky|youtube|all] [--type idea|post]
  python main.py --report
"""

import os
import json
import argparse
import logging
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from colorama import Fore, Style, init as _colorama_init

_colorama_init(autoreset=True)

from services.ollama_service import OllamaService
from services.buffer_service import BufferService, BufferQueueFullError
from services.content_curator import ContentCurator
from services.ssi_tracker import SSITracker
from services.github_service import build_github_profile_context
from scheduler import PostScheduler
from content_calendar import CONTENT_CALENDAR

load_dotenv()

# ── Coloured log formatter ─────────────────────────────────────────────────
class _ColourFormatter(logging.Formatter):
    _LEVEL = {
        logging.DEBUG:    str(Fore.CYAN)    + "DEBUG"    + str(Style.RESET_ALL),
        logging.INFO:     str(Fore.GREEN)   + "INFO"     + str(Style.RESET_ALL),
        logging.WARNING:  str(Fore.YELLOW)  + "WARN"     + str(Style.RESET_ALL),
        logging.ERROR:    str(Fore.RED)     + "ERROR"    + str(Style.RESET_ALL),
        logging.CRITICAL: str(Fore.RED) + str(Style.BRIGHT) + "CRITICAL" + str(Style.RESET_ALL),
    }
    def format(self, record: logging.LogRecord) -> str:
        record = logging.makeLogRecord(record.__dict__)
        record.levelname = self._LEVEL.get(record.levelno, record.levelname)
        return super().format(record)

_handler = logging.StreamHandler()
_handler.setFormatter(_ColourFormatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
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
    parser.add_argument("--channel",   choices=["linkedin", "x", "bluesky", "youtube", "all"], default="linkedin",
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

    ai = OllamaService(
        model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    logger.info(f"Using Ollama model: {ai.model}")
    curator = ContentCurator(ai_service=ai, buffer_service=buffer)
    tracker = SSITracker()

    if args.report:
        tracker.print_report()
        return

    if args.save_ssi:
        brand, find, engage, build = args.save_ssi
        tracker.save_scores(establish=brand, find=find, engage=engage, build=build)
        total = brand + find + engage + build
        print(str(Fore.GREEN) + f"✅  Saved SSI scores: brand={brand} find={find} engage={engage} build={build} total={total:.2f}" + str(Style.RESET_ALL))
        return

    if args.bsky_stats:
        from services.ssi_tracker import fetch_bluesky_stats
        stats = fetch_bluesky_stats()
        if stats:
            print(str(Fore.CYAN) + str(Style.BRIGHT) + f"\n📊 Bluesky stats for @{stats['handle']}" + str(Style.RESET_ALL))
            print(f"  👥 Followers    : {str(Fore.WHITE)}{stats['followers']}{str(Style.RESET_ALL)}")
            print(f"  ➡️  Following    : {stats['following']}")
            print(f"  📝 Total posts  : {stats['posts']}")
            print(str(Fore.CYAN) + f"\n  Last {stats['analysed']} posts (engagement)" + str(Style.RESET_ALL))
            print(f"  ❤️  Likes        : {stats['total_likes']}")
            print(f"  💬 Replies      : {stats['total_replies']}")
            print(f"  🔁 Reposts      : {stats['total_reposts']}")
            print(f"  🗨️  Quotes       : {stats['total_quotes']}")
            print(f"  📈 Avg / post   : {stats['avg_engagement']}")
            if stats.get("top_post"):
                tp = stats["top_post"]
                print(str(Fore.YELLOW) + f"\n  🏆 Top post ({tp['likes']}L {tp['replies']}R {tp['reposts']}RT)" + str(Style.RESET_ALL))
                print(f"  '{tp['text']}'")
                if tp["url"]:
                    print(f"  {tp['url']}")
        return

    if args.curate:
        logger.info(f"🔍 Curating AI news sources (channel: {args.channel}, type: {args.type})...")
        try:
            ideas = curator.curate_and_create_ideas(dry_run=args.dry_run, channel=args.channel, message_type=args.type, request_delay=5.0)
        except BufferQueueFullError as e:
            print(str(Fore.YELLOW) + f"\n⚠️  Buffer queue is full — no new posts were scheduled.\n   {e}\n   Free up slots at https://publish.buffer.com before running again." + str(Style.RESET_ALL))
            return
        noun = "posts" if args.type == "post" else "ideas"
        print(str(Fore.GREEN) + f"\n✅  Created {len(ideas)} {noun} in Buffer ({args.channel})" + str(Style.RESET_ALL))
        return

    if args.generate or args.schedule:
        week_topics = CONTENT_CALENDAR.get(f"week_{args.week}", [])
        if not week_topics:
            logger.error(f"No content found for week {args.week}")
            return

        logger.info(f"📝 Generating {len(week_topics)} posts for week {args.week}...")
        posts = []
        if args.channel == "youtube" and not args.dry_run:
            Path("yt-vid-data").mkdir(exist_ok=True)

        for topic in week_topics:
            logger.info(f"  Generating: {topic['title']}")
            post = ai.generate_linkedin_post(
                title=topic["title"],
                angle=topic["angle"],
                ssi_component=topic["ssi_component"],
                hashtags=topic.get("hashtags", []),
                profile_context=PROFILE_CONTEXT,
                channel=args.channel,
            )
            # Hashtags are only appended for LinkedIn-style posts.
            if args.channel not in ("x", "youtube"):
                hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in topic.get("hashtags", []))
                if hashtag_str and hashtag_str not in post:
                    post = post.rstrip() + f"\n\n{hashtag_str}"

            if args.channel == "youtube":
                if len(post) > 500:
                    # Absolute safety cap for YouTube scripts.
                    truncated = post[:500]
                    for sep in (".", "!", "?"):
                        idx = truncated.rfind(sep)
                        if idx != -1:
                            truncated = truncated[: idx + 1]
                            break
                    else:
                        truncated = truncated[: truncated.rfind(" ")].rstrip()
                    post = truncated
                    logger.warning(f"YouTube generate script exceeded 500 chars; truncated to {len(post)}")

                safe_title = re.sub(r"[^\w\-]", "_", topic["title"][:60]).strip("_")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                script_path = Path("yt-vid-data") / f"{timestamp}_{safe_title}.txt"
                script_content = (
                    f"TITLE: {topic['title']}\n"
                    f"SSI COMPONENT: {topic['ssi_component']}\n\n"
                    f"{post}\n"
                )
                if not args.dry_run:
                    script_path.write_text(script_content, encoding="utf-8")
                print(str(Fore.RED) + str(Style.BRIGHT) + "\n🎬 YOUTUBE SHORT SCRIPT:" + str(Style.RESET_ALL))
                print(str(Fore.WHITE) + f"📄 TITLE:  {topic['title']}" + str(Style.RESET_ALL))
                print(str(Fore.CYAN) + f"🎯 SSI:    {topic['ssi_component']}" + str(Style.RESET_ALL))
                print(f"\n{post}\n")
                if not args.dry_run:
                    print(str(Fore.GREEN) + f"💾 Saved to: {script_path}" + str(Style.RESET_ALL))
            posts.append({**topic, "generated_text": post})

            if args.dry_run and args.channel != "youtube":
                print(str(Fore.CYAN) + f"\n{'='*60}" + str(Style.RESET_ALL))
                print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📝 TOPIC: {topic['title']}" + str(Style.RESET_ALL))
                print(str(Fore.CYAN) + f"🎯 SSI COMPONENT: {topic['ssi_component']}" + str(Style.RESET_ALL))
                print(f"\n{post}\n")

        if args.schedule and not args.dry_run:
            if args.channel == "youtube":
                print(
                    str(Fore.YELLOW)
                    + "\n⚠️  YouTube scripts were generated and saved locally, but not scheduled to Buffer.\n"
                    + "   Buffer YouTube scheduling requires a video file upload (title/category/video).\n"
                    + "   Render with lipsync.video, then upload manually."
                    + str(Style.RESET_ALL)
                )
                return
            scheduler = PostScheduler(buffer_service=buffer)
            scheduler.schedule_week(posts, week_number=args.week, channel=args.channel)
            print(str(Fore.GREEN) + f"\n✅  Scheduled {len(posts)} posts to Buffer ({args.channel}) successfully" + str(Style.RESET_ALL))


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
