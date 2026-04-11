"""
LinkedIn SSI Booster — main entrypoint
=======================================
Generates and schedules LinkedIn posts via the Buffer API to improve
Social Selling Index (SSI) across all four components.

AI backend: Ollama (local) — requires Ollama running on OLLAMA_BASE_URL

Usage:
  python main.py --generate [--week N] [--dry-run] [--interactive] [--channel linkedin|x|bluesky|youtube|all]
  python main.py --schedule [--week N] [--dry-run] [--interactive] [--channel linkedin|x|bluesky|youtube|all]
  python main.py --curate               [--dry-run] [--interactive] [--channel linkedin|x|bluesky|youtube|all] [--type idea|post]
    python main.py --console
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
from services.buffer_service import BufferService, BufferQueueFullError, BufferRateLimitError, BufferChannelNotConnectedError
from services.content_curator import ContentCurator
from services.ssi_tracker import SSITracker
from services.console_grounding import (
    parse_query_constraints,
    retrieve_relevant_facts,
    build_deterministic_grounded_reply,
)
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


def run_console(ai: OllamaService) -> None:
    """Run interactive persona chat mode in the terminal."""
    print(str(Fore.CYAN) + str(Style.BRIGHT) + "\n🧠 Persona Console Mode" + str(Style.RESET_ALL))
    print("- No Buffer actions will be performed in this mode.")
    print("- Commands: /help, /reset, /exit")

    history: list[dict[str, str]] = []
    max_turns = 24

    # Load persona graph for deterministic grounding and persona chat context
    from services.avatar_intelligence import (
        load_avatar_state as _lav_console,
        normalize_evidence_facts,
        retrieve_evidence,
        evidence_facts_to_project_facts,
        build_grounding_context,
    )
    _avatar_state = _lav_console()
    _avatar_facts = normalize_evidence_facts(_avatar_state)
    _profile_facts = evidence_facts_to_project_facts(_avatar_facts)
    _grounding_context = build_grounding_context(_avatar_facts)

    while True:
        try:
            user_input = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting console.")
            return

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in {"/exit", "/quit"}:
            print("Exiting console.")
            return
        if cmd == "/help":
            print("Commands: /help, /reset, /exit")
            continue
        if cmd == "/reset":
            history.clear()
            print("Conversation history cleared.")
            continue

        constraints = parse_query_constraints(user_input)
        if constraints.requires_grounding:
            facts = retrieve_relevant_facts(_profile_facts, constraints, limit=8)
            reply = build_deterministic_grounded_reply(user_input, facts, constraints)
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": reply})
            if len(history) > max_turns * 2:
                history = history[-max_turns * 2 :]
            print(str(Fore.GREEN) + f"Sam> {reply}" + str(Style.RESET_ALL))
            continue

        history.append({"role": "user", "content": user_input})
        if len(history) > max_turns * 2:
            history = history[-max_turns * 2 :]

        try:
            reply = ai.chat_as_persona(history, grounding_context=_grounding_context, max_tokens=600)
        except Exception as e:
            print(str(Fore.RED) + f"Sam> Error: {e}" + str(Style.RESET_ALL))
            continue

        history.append({"role": "assistant", "content": reply})
        print(str(Fore.GREEN) + f"Sam> {reply}" + str(Style.RESET_ALL))


def main():
    parser = argparse.ArgumentParser(description="LinkedIn SSI Booster via Buffer API")
    parser.add_argument("--generate",  action="store_true", help="Generate posts from content calendar")
    parser.add_argument("--schedule",  action="store_true", help="Push scheduled posts to Buffer")
    parser.add_argument("--curate",    action="store_true", help="Curate AI news and create ideas in Buffer")
    parser.add_argument("--console",   action="store_true", help="Open interactive persona chat mode (no Buffer calls)")
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
    parser.add_argument("--interactive", action="store_true", help="Pause for user confirmation on each truth gate removal")
    parser.add_argument("--avatar-explain", action="store_true", help="Print evidence IDs and grounding summary after each generation")
    parser.add_argument("--avatar-learn-report", action="store_true", help="Print learning report from captured moderation events and exit")
    parser.add_argument("--confidence-policy", choices=["strict", "balanced", "draft-first"], default=None,
                        help="Confidence policy for curate path: strict|balanced|draft-first (default: AVATAR_CONFIDENCE_POLICY env var, else balanced)")
    parser.add_argument("--reconcile", action="store_true",
                        help="Fetch published Buffer posts and reconcile with generated candidates to build acceptance priors")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.WARNING)  # suppress noisy HTTP client logs

    ai = OllamaService(
        model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    logger.info(f"Using Ollama model: {ai.model}")
    tracker = SSITracker()

    if args.console:
        incompatible = []
        if args.generate:
            incompatible.append("--generate")
        if args.schedule:
            incompatible.append("--schedule")
        if args.curate:
            incompatible.append("--curate")
        if args.report:
            incompatible.append("--report")
        if args.save_ssi:
            incompatible.append("--save-ssi")
        if args.bsky_stats:
            incompatible.append("--bsky-stats")
        if incompatible:
            print(
                str(Fore.YELLOW)
                + f"\n⚠️  --console cannot be combined with: {', '.join(incompatible)}"
                + str(Style.RESET_ALL)
            )
            return
        run_console(ai=ai)
        return

    def build_buffer_service() -> BufferService:
        buffer_api_key = os.getenv("BUFFER_API_KEY")
        if not buffer_api_key:
            raise ValueError("BUFFER_API_KEY environment variable is required")
        return BufferService(api_key=buffer_api_key)

    if args.report:
        tracker.print_report()
        return

    if args.reconcile:
        from services.selection_learning import reconcile_published
        buffer = build_buffer_service()
        channel_ids: dict[str, str | None] = {"linkedin": buffer.get_linkedin_channel_id()}
        x_id = os.getenv("BUFFER_X_CHANNEL_ID")
        bsky_id = os.getenv("BUFFER_BLUESKY_CHANNEL_ID")
        if x_id:
            channel_ids["x"] = x_id
        if bsky_id:
            channel_ids["bluesky"] = bsky_id
        stats = reconcile_published(buffer, {k: v for k, v in channel_ids.items() if v is not None})
        print(str(Fore.GREEN) + "\n✅  Reconcile complete" + str(Style.RESET_ALL))
        for k, v in stats.items():
            print(f"   {k}: {v}")
        return

    if args.avatar_learn_report:
        from services.avatar_intelligence import build_learning_report, format_learning_report
        report = build_learning_report()
        print(format_learning_report(report))
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
        buffer = build_buffer_service()
        from services.shared import AVATAR_CONFIDENCE_POLICY
        confidence_policy = args.confidence_policy or AVATAR_CONFIDENCE_POLICY
        curator = ContentCurator(ai_service=ai, buffer_service=buffer, confidence_policy=confidence_policy)
        logger.info(f"🔍 Curating AI news sources (channel: {args.channel}, type: {args.type})...")
        try:
            ideas = curator.curate_and_create_ideas(dry_run=args.dry_run, channel=args.channel, message_type=args.type, request_delay=5.0, interactive=args.interactive)
        except BufferQueueFullError as e:
            print(str(Fore.YELLOW) + f"\n⚠️  Buffer queue is full — no new posts were scheduled.\n   {e}\n   Free up slots at https://publish.buffer.com before running again." + str(Style.RESET_ALL))
            return
        except BufferRateLimitError as e:
            print(
                str(Fore.YELLOW)
                + f"\n⚠️  Buffer API rate limit reached.\n   {e}\n"
                + "   Wait for the retry window, then run the command again."
                + str(Style.RESET_ALL)
            )
            return
        except BufferChannelNotConnectedError as e:
            print(
                str(Fore.YELLOW)
                + f"\n⚠️  Requested channel is not connected in Buffer.\n   {e}\n"
                + "   Connect the channel in Buffer or run with a different --channel value."
                + str(Style.RESET_ALL)
            )
            return
        noun = "posts" if args.type == "post" else "ideas"
        print(str(Fore.GREEN) + f"\n✅  Created {len(ideas)} {noun} in Buffer ({args.channel})" + str(Style.RESET_ALL))
        return

    if args.generate or args.schedule:
        week_topics = CONTENT_CALENDAR.get(f"week_{args.week}", [])
        if not week_topics:
            logger.error(f"No content found for week {args.week}")
            return

        # Support multi-channel dry-run for --channel all
        target_channels = [args.channel] if args.channel != "all" else ["linkedin", "x", "bluesky", "youtube"]

        for channel in target_channels:
            logger.info(f"📝 Generating {len(week_topics)} posts for week {args.week} (channel: {channel})...")
            posts = []
            from services.avatar_intelligence import (
                load_avatar_state as _lav_gen,
                normalize_evidence_facts,
                retrieve_evidence,
                evidence_facts_to_project_facts,
            )
            _gen_avatar_state = _lav_gen()
            _gen_avatar_facts = normalize_evidence_facts(_gen_avatar_state)
            if channel == "youtube" and not args.dry_run:
                Path("yt-vid-data").mkdir(exist_ok=True)
            if args.avatar_explain:
                from services.avatar_intelligence import build_explain_output, format_explain_output

            for topic in week_topics:
                logger.info(f"  Generating: {topic['title']}")
                grounding_query = f"{topic['title']}. {topic['angle']}. {topic['ssi_component']}"
                grounding_facts = evidence_facts_to_project_facts(
                    retrieve_evidence(grounding_query, _gen_avatar_facts, limit=5)
                )

                if channel == "youtube":
                    post = ai.generate_youtube_short_script(
                        title=topic["title"],
                        angle=topic["angle"],
                        ssi_component=topic["ssi_component"],
                        grounding_facts=grounding_facts,
                        interactive=args.interactive,
                    )
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
                    print(str(Fore.RED) + str(Style.BRIGHT) + f"\n🎬 YOUTUBE SHORT SCRIPT (channel: {channel}):" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + f"📄 TITLE:  {topic['title']}" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"🎯 SSI:    {topic['ssi_component']}" + str(Style.RESET_ALL))
                    print(f"\n{post}\n")
                    if not args.dry_run:
                        print(str(Fore.GREEN) + f"💾 Saved to: {script_path}" + str(Style.RESET_ALL))
                    posts.append({**topic, "generated_text": post})
                else:
                    post = ai.generate_linkedin_post(
                        title=topic["title"],
                        angle=topic["angle"],
                        ssi_component=topic["ssi_component"],
                        hashtags=topic.get("hashtags", []),
                        grounding_facts=grounding_facts,
                        channel=channel,
                        interactive=args.interactive,
                    )
                    # Hashtags are only appended for LinkedIn-style posts.
                    if channel not in ("x", "youtube"):
                        hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in topic.get("hashtags", []))
                        if hashtag_str and hashtag_str not in post:
                            post = post.rstrip() + f"\n\n{hashtag_str}"
                    posts.append({**topic, "generated_text": post})

                if channel != "youtube":
                    print(str(Fore.CYAN) + f"\n{'='*60}" + str(Style.RESET_ALL))
                    print(str(Fore.WHITE) + str(Style.BRIGHT) + f"📝 TOPIC: {topic['title']} (channel: {channel})" + str(Style.RESET_ALL))
                    print(str(Fore.CYAN) + f"🎯 SSI COMPONENT: {topic['ssi_component']}" + str(Style.RESET_ALL))
                    print(f"\n{post}\n")

                if args.avatar_explain:
                    _relevant = retrieve_evidence(grounding_query, _gen_avatar_facts)
                    _explain = build_explain_output(
                        evidence_facts=_relevant,
                        article_ref=topic.get("title", ""),
                        channel=channel,
                        ssi_component=topic.get("ssi_component", ""),
                    )
                    print(format_explain_output(_explain))

            if args.schedule and not args.dry_run:
                if channel == "youtube":
                    print(
                        str(Fore.YELLOW)
                        + "\n⚠️  YouTube scripts were generated and saved locally, but not scheduled to Buffer.\n"
                        + "   Buffer YouTube scheduling requires a video file upload (title/category/video).\n"
                        + "   Render with lipsync.video, then upload manually."
                        + str(Style.RESET_ALL)
                    )
                    continue
                buffer = build_buffer_service()
                scheduler = PostScheduler(buffer_service=buffer)
                try:
                    scheduler.schedule_week(posts, week_number=args.week, channel=channel)
                except BufferRateLimitError as e:
                    print(
                        str(Fore.YELLOW)
                        + f"\n⚠️  Buffer API rate limit reached while scheduling.\n   {e}\n"
                        + "   Wait for the retry window, then rerun the schedule command."
                        + str(Style.RESET_ALL)
                    )
                    continue
                except BufferChannelNotConnectedError as e:
                    print(
                        str(Fore.YELLOW)
                        + f"\n⚠️  Requested channel is not connected in Buffer.\n   {e}\n"
                        + "   Connect the channel in Buffer or run with a different --channel value."
                        + str(Style.RESET_ALL)
                    )
                    continue
                print(str(Fore.GREEN) + f"\n✅  Scheduled {len(posts)} posts to Buffer ({channel}) successfully" + str(Style.RESET_ALL))



if __name__ == "__main__":
    main()
