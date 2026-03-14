"""
LinkedIn SSI Booster — Buffer API Integration
=============================================
Automates LinkedIn post creation and scheduling via Buffer API
to maximize Social Selling Index (SSI) across all 4 components.

Author: Shawn Jackson Dyck
Usage: python main.py [--generate | --schedule | --report | --curate]
"""

import os
import json
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

from services.claude_service import ClaudeService
from services.buffer_service import BufferService
from services.content_curator import ContentCurator
from services.ssi_tracker import SSITracker
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
    args = parser.parse_args()

    buffer  = BufferService(api_key=os.getenv("BUFFER_API_KEY"))
    claude  = ClaudeService(api_key=os.getenv("ANTHROPIC_API_KEY"))
    curator = ContentCurator(claude_service=claude)
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


# Your profile context fed into Claude for personalised post generation
PROFILE_CONTEXT = """
Name: Shawn Jackson Dyck
Role: Principal Software Engineer
Location: Ottawa/Remote
Specialties: AI-driven search, RAG, Neo4j, Elasticsearch, Java 21, Python, FastAPI
Key projects:
- G7 GovAI Grand Challenge RIA: Bilingual NLP RAG for Canadian federal law (397k docs)
- S1gnal.Zero: Winner 'Best Use of Solace Agent' hackathon, 5-agent FastMCP bot detection
- Answer42: 9-agent Spring Boot/Batch/AI academic research platform
- AI-TDD methodology: document-driven AI development workflow
Experience: 20+ years Java/J2EE, now focused on AI/ML engineering
Goal: Build LinkedIn presence as a recognized voice in AI, GovTech, and RAG systems
Tone: Technical but accessible, honest about lessons learned, not corporate-speak
"""


if __name__ == "__main__":
    main()
