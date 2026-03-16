"""
Post Scheduler
Pushes generated posts to Buffer with optimal scheduling.
Targets: Tue/Wed/Fri 4:00 PM EST — matching your Buffer posting windows.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import pytz

logger = logging.getLogger(__name__)

# Your Buffer posting schedule (from setup)
POSTING_SCHEDULE = {
    "tuesday":   {"hour": 16, "minute": 0},
    "wednesday": {"hour": 16, "minute": 0},
    "friday":    {"hour": 16, "minute": 0},
}

WEEKDAY_MAP = {
    "tuesday":   1,
    "wednesday": 2,
    "friday":    4,
}

TIMEZONE = pytz.timezone("America/Toronto")  # Ottawa EST


class PostScheduler:

    def __init__(self, buffer_service):
        self.buffer = buffer_service

    def _resolve_channel_ids(self, channel: str) -> list[str]:
        """Return a list of Buffer channel IDs for the given channel selector."""
        if channel == "linkedin":
            return [self.buffer.get_linkedin_channel_id()]
        elif channel == "x":
            return [self.buffer.get_x_channel_id()]
        elif channel == "bluesky":
            return [self.buffer.get_bluesky_channel_id()]
        elif channel == "all":
            ids = [self.buffer.get_linkedin_channel_id()]
            ids.append(self.buffer.get_x_channel_id())
            ids.append(self.buffer.get_bluesky_channel_id())
            return ids
        else:
            raise ValueError(f"Unknown channel {channel!r}. Use 'linkedin', 'x', 'bluesky', or 'all'.")

    def _next_slot(self, day_name: str, reference: Optional[datetime] = None) -> str:
        """Calculate the next occurrence of a given weekday posting slot."""
        if reference is None:
            reference = datetime.now(TIMEZONE)

        target_weekday = WEEKDAY_MAP[day_name]
        slot = POSTING_SCHEDULE[day_name]

        days_ahead = target_weekday - reference.weekday()
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0:
            # Same day — check if slot has passed
            slot_today = reference.replace(hour=slot["hour"], minute=slot["minute"], second=0, microsecond=0)
            if reference >= slot_today:
                days_ahead = 7

        post_date = reference + timedelta(days=days_ahead)
        post_dt = post_date.replace(hour=slot["hour"], minute=slot["minute"], second=0, microsecond=0)
        return post_dt.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def schedule_week(self, posts: list, week_number: int = 1, channel: str = "linkedin"):
        """
        Schedule a week of posts to Buffer.
        Posts are distributed Tue/Wed/Fri at 4 PM EST.
        Max 3 posts per week per channel (matches your free plan queue rhythm).
        channel: 'linkedin' | 'x' | 'all'
        """
        channel_ids = self._resolve_channel_ids(channel)
        days = ["tuesday", "wednesday", "friday"]
        reference = datetime.now(TIMEZONE)

        # Advance reference by (week_number - 1) weeks
        if week_number > 1:
            reference = reference + timedelta(weeks=week_number - 1)

        scheduled = []
        for channel_id in channel_ids:
            for i, post in enumerate(posts[:3]):
                day_name     = days[i % 3]
                scheduled_at = self._next_slot(day_name, reference=reference)
                text         = post.get("generated_text", "")

                if not text:
                    logger.warning(f"Post {i+1} has no generated text — skipping")
                    continue

                result = self.buffer.create_post(
                    channel_id=channel_id,
                    text=text,
                    scheduled_at=scheduled_at
                )
                logger.info(f"[{channel_id}] Scheduled post {i+1}/{len(posts[:3])} → {day_name} {scheduled_at}")
                scheduled.append(result)

        logger.info(f"Week {week_number}: {len(scheduled)} posts scheduled to Buffer ({channel})")
        return scheduled
