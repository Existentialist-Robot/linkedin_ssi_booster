"""
LinkedIn Analytics Service
==========================
Scrapes your own LinkedIn post engagement using joeyism/linkedin_scraper.

This uses the current v3 Playwright-based API from the library:
  - BrowserManager
  - login_with_cookie

Usage:
    python main.py --analyze

Requirements:
    pip install -r requirements.txt
    playwright install chromium

Requires in .env:
    LINKEDIN_LI_AT=<your li_at cookie value>
    LINKEDIN_PROFILE_URL=https://www.linkedin.com/in/your-profile-slug

ToS note: Scraping LinkedIn is against their Terms of Service.
Use this for personal insight only.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PostAnalytics:
    title: str
    url: str
    reactions: int
    comments: int
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def engagement(self) -> int:
        return self.reactions + self.comments


def _parse_count(value: object) -> int:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0

    match = re.search(r"(\d+(?:\.\d+)?)([KkMm]?)", text)
    if not match:
        return 0

    number = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "k":
        number *= 1000
    elif suffix == "m":
        number *= 1_000_000
    return int(number)


async def _fetch_post_analytics_async(li_at: str, linkedin_url: str, max_posts: int) -> list[PostAnalytics]:
    try:
        from linkedin_scraper import BrowserManager, login_with_cookie  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "linkedin-scraper is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    activity_url = linkedin_url.rstrip("/") + "/recent-activity/all/"
    results: list[PostAnalytics] = []

    # The upstream project recommends non-headless mode for LinkedIn compatibility.
    async with BrowserManager(headless=False) as browser:
        await login_with_cookie(browser.page, li_at)
        await browser.page.goto(activity_url, wait_until="domcontentloaded")
        await browser.page.wait_for_timeout(3000)

        for _ in range(4):
            await browser.page.mouse.wheel(0, 2500)
            await browser.page.wait_for_timeout(1200)

        posts_data = await browser.page.evaluate(
            """(limit) => {
                const nodes = Array.from(document.querySelectorAll('[data-urn^="urn:li:activity:"]'));
                const seen = new Set();
                const posts = [];

                for (const el of nodes) {
                    const urn = el.getAttribute('data-urn');
                    if (!urn || seen.has(urn)) continue;
                    seen.add(urn);

                    const textEl = el.querySelector(
                        '.feed-shared-update-v2__description, .update-components-text, .feed-shared-text, [data-test-id="main-feed-activity-card__commentary"]'
                    );
                    const text = (textEl?.innerText || '').trim();
                    if (!text) continue;

                    const reactionsEl = el.querySelector(
                        'button[aria-label*="reaction"], [class*="social-details-social-counts__reactions"]'
                    );
                    const commentsEl = el.querySelector('button[aria-label*="comment"]');

                    posts.push({
                        urn,
                        text,
                        reactions: reactionsEl?.innerText || '',
                        comments: commentsEl?.innerText || '',
                    });

                    if (posts.length >= limit) break;
                }

                return posts;
            }""",
            max_posts,
        )

        for post in posts_data:
            urn = str(post.get("urn") or "")
            activity_id = urn.replace("urn:li:activity:", "")
            results.append(
                PostAnalytics(
                    title=str(post.get("text") or "")[:120],
                    url=(
                        f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}/"
                        if activity_id
                        else ""
                    ),
                    reactions=_parse_count(post.get("reactions")),
                    comments=_parse_count(post.get("comments")),
                )
            )

    results.sort(key=lambda item: item.engagement, reverse=True)
    logger.info("Scraped %s LinkedIn posts", len(results))
    return results


def fetch_post_analytics(li_at: str | None = None, max_posts: int = 20) -> list[PostAnalytics]:
    """Scrape engagement data from your own LinkedIn posts."""
    li_at = li_at or os.getenv("LINKEDIN_LI_AT")
    if not li_at:
        raise ValueError(
            "LINKEDIN_LI_AT is not set. Add your li_at cookie to .env.\n"
            "See services/linkedin_analytics.py for instructions."
        )

    linkedin_url = os.getenv("LINKEDIN_PROFILE_URL", "").strip()
    if not linkedin_url:
        raise ValueError(
            "LINKEDIN_PROFILE_URL is not set in .env.\n"
            "Set it to your public LinkedIn profile URL, e.g.:\n"
            "  LINKEDIN_PROFILE_URL=https://www.linkedin.com/in/shawn-jackson-dyck-52aa74358"
        )

    try:
        return asyncio.run(_fetch_post_analytics_async(li_at, linkedin_url, max_posts))
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" in str(exc):
            raise RuntimeError(
                "LinkedIn analytics must be run from the CLI, not from an active event loop."
            ) from exc
        raise


def print_analytics_report(posts: list[PostAnalytics], top_n: int = 10) -> None:
    """Print a formatted engagement report to stdout."""
    print("\n" + "=" * 60)
    print("  LINKEDIN POST ENGAGEMENT REPORT")
    print(f"  Scraped: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    if not posts:
        print("\n  No posts found.\n")
        print("=" * 60 + "\n")
        return

    total_reactions = sum(p.reactions for p in posts)
    total_comments  = sum(p.comments  for p in posts)
    total_posts     = len(posts)
    avg_reactions   = total_reactions / total_posts if total_posts else 0
    avg_comments    = total_comments  / total_posts if total_posts else 0

    print(f"\n  Posts analysed : {total_posts}")
    print(f"  Total reactions: {total_reactions}  (avg {avg_reactions:.1f}/post)")
    print(f"  Total comments : {total_comments}   (avg {avg_comments:.1f}/post)")
    print()

    print(f"  TOP {min(top_n, total_posts)} POSTS BY ENGAGEMENT")
    print(f"  {'Reactions':>9}  {'Comments':>8}  {'Total':>6}  Title")
    print("  " + "-" * 56)

    for post in posts[:top_n]:
        snippet = post.title[:50] + ("..." if len(post.title) > 50 else "")
        print(f"  {post.reactions:>9}  {post.comments:>8}  {post.engagement:>6}  {snippet}")
        if post.url:
            print(f"  {' ':>9}  {' ':>8}  {' ':>6}  {post.url}")

    print()

    # Engagement distribution hint
    high   = [p for p in posts if p.engagement >= 10]
    medium = [p for p in posts if 3 <= p.engagement < 10]
    low    = [p for p in posts if p.engagement < 3]
    print(f"  DISTRIBUTION  High(>=10): {len(high)}  Med(3-9): {len(medium)}  Low(<3): {len(low)}")
    print()
    print("  TIP: Posts with high engagement - reuse the format, topic, or opener style.")
    print("  TIP: Low-engagement posts - review the hook (first line). That's where you lose people.")
    print("\n" + "=" * 60 + "\n")
