"""
LinkedIn Analytics Service
===========================
Scrapes your own LinkedIn post engagement (reactions, comments) using
the joeyism/linkedin_scraper library and your li_at session cookie.

Usage:
    python main.py --analyze

Requirements:
    pip install linkedin-scraper selenium chromedriver-autoinstaller

Requires in .env:
    LINKEDIN_LI_AT=<your li_at cookie value>

How to get your li_at cookie:
  1. Log in to linkedin.com in Chrome
  2. Open DevTools → Application → Cookies → https://www.linkedin.com
  3. Copy the value of the 'li_at' cookie
  4. Add it to .env as LINKEDIN_LI_AT=<value>

ToS note: Scraping LinkedIn is against their Terms of Service.
Use this for personal insight only — not commercial data collection.
"""

import logging
import os
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


def fetch_post_analytics(li_at: str | None = None, max_posts: int = 20) -> list[PostAnalytics]:
    """Scrape engagement data from your own LinkedIn posts.

    li_at     — li_at session cookie. Falls back to LINKEDIN_LI_AT env var.
    max_posts — How many recent posts to analyse (default: 20).

    Returns a list of PostAnalytics sorted by engagement desc.
    Raises RuntimeError if the scraper or headless Chrome cannot be loaded.
    """
    li_at = li_at or os.getenv("LINKEDIN_LI_AT")
    if not li_at:
        raise ValueError(
            "LINKEDIN_LI_AT is not set. Add your li_at cookie to .env.\n"
            "See services/linkedin_analytics.py for instructions."
        )

    try:
        from linkedin_scraper import Person  # type: ignore[import]
    except ImportError:
        raise RuntimeError(
            "linkedin-scraper is not installed. Run:\n"
            "  pip install linkedin-scraper selenium chromedriver-autoinstaller"
        )

    try:
        import chromedriver_autoinstaller  # type: ignore[import]
        chromedriver_autoinstaller.install()
    except ImportError:
        logger.debug("chromedriver-autoinstaller not found — assuming chromedriver is on PATH")

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        raise RuntimeError(
            "selenium is not installed. Run:\n"
            "  pip install selenium"
        )

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    try:
        # Inject the li_at cookie so linkedin_scraper uses our session
        driver.get("https://www.linkedin.com")
        driver.add_cookie({"name": "li_at", "value": li_at, "domain": ".linkedin.com"})
        driver.refresh()

        linkedin_url = os.getenv("LINKEDIN_PROFILE_URL", "").strip()
        if not linkedin_url:
            raise ValueError(
                "LINKEDIN_PROFILE_URL is not set in .env.\n"
                "Set it to your public LinkedIn profile URL, e.g.:\n"
                "  LINKEDIN_PROFILE_URL=https://www.linkedin.com/in/shawn-jackson-dyck-52aa74358"
            )

        logger.info(f"Scraping LinkedIn profile: {linkedin_url}")
        person = Person(linkedin_url, driver=driver, scrape=True, close_on_complete=False)

        results: list[PostAnalytics] = []

        # The library exposes posts via person.posts or person.publications.
        # Field names vary by library version — fall back gracefully.
        raw_posts = getattr(person, "posts", None) or getattr(person, "activities", None) or []

        if not raw_posts:
            logger.warning(
                "No posts returned by linkedin_scraper — the page structure may have changed "
                "or your li_at cookie may be expired."
            )
            return results

        for post in raw_posts[:max_posts]:
            # Attribute names differ across joeyism/linkedin_scraper versions
            title = (
                getattr(post, "title", None)
                or getattr(post, "text", None)
                or getattr(post, "description", None)
                or ""
            )
            url = (
                getattr(post, "url", None)
                or getattr(post, "link", None)
                or ""
            )
            reactions = int(
                getattr(post, "reactions_count", None)
                or getattr(post, "likes", None)
                or getattr(post, "num_reactions", None)
                or 0
            )
            comments = int(
                getattr(post, "comments_count", None)
                or getattr(post, "num_comments", None)
                or 0
            )
            results.append(PostAnalytics(
                title=str(title)[:120],
                url=str(url),
                reactions=reactions,
                comments=comments,
            ))

        results.sort(key=lambda p: p.engagement, reverse=True)
        logger.info(f"Scraped {len(results)} posts from LinkedIn")
        return results

    finally:
        driver.quit()


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
        snippet = post.title[:50] + ("…" if len(post.title) > 50 else "")
        print(f"  {post.reactions:>9}  {post.comments:>8}  {post.engagement:>6}  {snippet}")
        if post.url:
            print(f"  {' ':>9}  {' ':>8}  {' ':>6}  {post.url}")

    print()

    # Engagement distribution hint
    high   = [p for p in posts if p.engagement >= 10]
    medium = [p for p in posts if 3 <= p.engagement < 10]
    low    = [p for p in posts if p.engagement < 3]
    print(f"  DISTRIBUTION  High(≥10): {len(high)}  Med(3-9): {len(medium)}  Low(<3): {len(low)}")
    print()
    print("  TIP: Posts with high engagement — reuse the format, topic, or opener style.")
    print("  TIP: Low-engagement posts — review the hook (first line). That's where you lose people.")
    print("\n" + "=" * 60 + "\n")
