"""
SSI Tracker
Tracks LinkedIn Social Selling Index targets per component
and prints a weekly action report with specific tips.
"""

import json
import os
import logging
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_bluesky_stats(handle: str | None = None, password: str | None = None) -> dict | None:
    """Fetch live Bluesky profile stats via the AT Protocol public API.

    handle   — Bluesky handle, e.g. 'samjd-zz.bsky.social'. Falls back to
               BLUESKY_HANDLE env var, then BLUESKY_IDENTIFIER.
    password — App password. Falls back to BLUESKY_APP_PASSWORD env var.

    Returns a dict with keys: handle, followers, following, posts.
    Returns None if credentials are missing or the request fails.
    """
    try:
        from atproto import Client  # optional dependency
    except ImportError:
        logger.warning("atproto package not installed — run: pip install atproto")
        return None

    handle   = handle   or os.getenv("BLUESKY_HANDLE") or os.getenv("BLUESKY_IDENTIFIER")
    password = password or os.getenv("BLUESKY_APP_PASSWORD")

    if not handle or not password:
        logger.warning("BLUESKY_HANDLE and BLUESKY_APP_PASSWORD are required for Bluesky stats")
        return None

    try:
        client = Client()
        client.login(handle, password)
        profile = client.get_profile(handle)
        return {
            "handle":    profile.handle,
            "followers": profile.followers_count or 0,
            "following": profile.follows_count   or 0,
            "posts":     profile.posts_count      or 0,
        }
    except Exception as e:
        logger.warning(f"Could not fetch Bluesky stats: {e}")
        return None

SSI_TARGETS = {
    "establish_brand":    {"current": 10.46, "target": 25.0, "max": 25.0},
    "find_right_people":  {"current": 9.465, "target": 20.0, "max": 25.0},
    "engage_with_insights": {"current": 11.0, "target": 25.0, "max": 25.0},
    "build_relationships":  {"current": 11.85, "target": 25.0, "max": 25.0},
}

SSI_ACTIONS = {
    "establish_brand": [
        "Post 3x this week (Buffer handles scheduling)",
        "Update LinkedIn headline to include 'RAG | Neo4j | AI-TDD'",
        "Add your G7 GovAI project to Featured section",
        "Complete LinkedIn Skills section with AI/ML skills",
    ],
    "find_right_people": [
        "Connect with 5 people who liked/commented your last post",
        "Search and connect with GovTech AI professionals in Ottawa",
        "Join: 'Graph Database & Neo4j', 'RAG Practitioners', 'GovAI' LinkedIn groups",
        "Follow: Anthropic, G7 GovAI Challenge, Spring AI accounts",
    ],
    "engage_with_insights": [
        "Leave 5 thoughtful comments on AI posts (not just 'Great post!')",
        "Share a curated article with your own 2-sentence take",
        "React to posts from your target connections daily",
        "Comment on a post from someone you want to connect with",
    ],
    "build_relationships": [
        "Reply to every comment on your posts within 24 hours",
        "Send a personalised message to 3 new connections",
        "Thank anyone who shares your post with a DM",
        "Endorse 5 connections for relevant skills",
    ]
}


class SSITracker:

    def __init__(self, data_file: str = "ssi_history.json"):
        self.data_file = Path(data_file)
        self.history = self._load_history()

    def _load_history(self) -> list:
        if self.data_file.exists():
            with open(self.data_file) as f:
                return json.load(f)
        return []

    def save_scores(self, establish: float, find: float, engage: float, build: float):
        """Record today's SSI scores."""
        entry = {
            "date": date.today().isoformat(),
            "establish_brand": establish,
            "find_right_people": find,
            "engage_with_insights": engage,
            "build_relationships": build,
            "total": establish + find + engage + build
        }
        self.history.append(entry)
        with open(self.data_file, "w") as f:
            json.dump(self.history, f, indent=2)
        logger.info(f"Saved SSI scores: total={entry['total']:.2f}")

    def print_report(self):
        """Print a weekly SSI action report to the console."""
        print("\n" + "="*60)
        print("  LINKEDIN SSI WEEKLY REPORT")
        print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("="*60)

        total_current = sum(v["current"] for v in SSI_TARGETS.values())
        total_target  = sum(v["target"]  for v in SSI_TARGETS.values())

        print(f"\n  OVERALL: {total_current:.1f} / 100  →  TARGET: {total_target:.0f} / 100")
        print(f"  Gap to close: {total_target - total_current:.1f} points\n")

        component_labels = {
            "establish_brand":      "Establish professional brand",
            "find_right_people":    "Find the right people",
            "engage_with_insights": "Engage with insights",
            "build_relationships":  "Build relationships",
        }

        for key, vals in SSI_TARGETS.items():
            label   = component_labels[key]
            current = vals["current"]
            target  = vals["target"]
            gap     = target - current
            bar_filled = int((current / vals["max"]) * 20)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)

            print(f"  {label}")
            print(f"  [{bar}] {current:.1f} → {target:.0f}  (gap: +{gap:.1f})")
            print(f"  Actions this week:")
            for action in SSI_ACTIONS[key]:
                print(f"    • {action}")
            print()

        print("  QUICK WINS (do these daily, 15 mins):")
        print("    1. Check Buffer queue — confirm 3 posts scheduled this week")
        print("    2. Leave 3 meaningful comments on AI/GovTech posts")
        print("    3. Accept + message 2 new connection requests")
        print("    4. Check linkedin.com/sales/ssi — track your score")
        print("\n" + "="*60 + "\n")
