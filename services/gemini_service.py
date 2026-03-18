"""
Gemini AI Service
Generates LinkedIn posts using Google's Gemini API.
Drop-in replacement for ClaudeService — identical public interface.

Requires GEMINI_API_KEY in .env.
Get a free key at: https://aistudio.google.com/apikey
Default model: gemini-2.0-flash (fast, generous free tier)
"""

import logging
import os
import time
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from services.shared import PERSONA_SYSTEM_PROMPT, SSI_COMPONENT_INSTRUCTIONS, X_CHAR_LIMIT, X_URL_CHARS, parse_xml_thread

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiService:

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required. Get one free at https://aistudio.google.com/apikey")
        self.model = model
        self.client = genai.Client(api_key=api_key)
        logger.info(f"GeminiService initialised — model={model}")

    # Retry delays longer than this indicate a quota exhaustion (daily/hourly limit),
    # not a per-minute rate limit. Fail fast rather than sleeping for hours.
    _MAX_RETRY_SLEEP = 90

    def _generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024, _retries: int = 3) -> str:
        """Send a request to Gemini and return the response text.
        Automatically retries on 429 rate-limit errors with the suggested delay.
        Raises immediately with a clear message if a daily/hourly quota is exhausted.
        """
        try:
            response = self.client.models.generate_content(
                model=self.model,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                    temperature=0.8,
                ),
                contents=user_prompt,
            )
            return (response.text or "").strip()
        except ClientError as e:
            if e.code == 429 and _retries > 0:
                # Parse retry delay from the API response, fallback to 15s
                retry_delay = 15.0
                try:
                    raw: dict = e.details  # type: ignore[assignment]
                    details = raw.get("error", {}).get("details", [])
                    for detail in details:
                        if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                            delay_str = detail.get("retryDelay", "15s").rstrip("s")
                            retry_delay = float(delay_str) + 2  # small buffer
                            break
                except Exception:
                    pass
                if retry_delay > self._MAX_RETRY_SLEEP:
                    # A long retry delay means a daily or hourly quota is exhausted —
                    # sleeping for hours would just hang the process. Fail fast instead.
                    quota_msg = getattr(e, "message", None) or str(e)
                    raise RuntimeError(
                        f"Gemini quota exhausted (retry suggested in {retry_delay:.0f}s). "
                        f"You have likely hit the free-tier daily request or token limit. "
                        f"Wait until the quota resets (usually midnight Pacific time) or "
                        f"check https://aistudio.google.com/ for your usage. "
                        f"API message: {quota_msg}"
                    ) from e
                logger.warning(f"Gemini rate limit hit — waiting {retry_delay:.0f}s then retrying ({_retries} left)")
                time.sleep(retry_delay)
                return self._generate(system_prompt, user_prompt, max_tokens, _retries - 1)
            # For non-429 errors, include the API message for easier diagnosis
            api_msg = getattr(e, "message", None) or str(e)
            raise RuntimeError(f"Gemini API error {e.code} (model={self.model}): {api_msg}") from e
        except Exception as e:
            raise RuntimeError(f"Gemini API error (model={self.model}): {e}") from e

    def generate_linkedin_post(
        self,
        title: str,
        angle: str,
        ssi_component: str,
        hashtags: list,
        profile_context: str,
        max_length: int = 1300,
        channel: str = "linkedin",
    ) -> str:
        """
        Generate a LinkedIn post optimised for a specific SSI component.
        Same signature as ClaudeService.generate_linkedin_post.
        """
        ssi_instruction = SSI_COMPONENT_INSTRUCTIONS.get(
            ssi_component, SSI_COMPONENT_INSTRUCTIONS["establish_brand"]
        )
        hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in hashtags)

        if channel == "x":
            max_length = X_CHAR_LIMIT
            _platform_block = f"""\nIMPORTANT — this post is for X (Twitter), NOT LinkedIn:
- Hard limit: {X_CHAR_LIMIT} characters total (count every character including spaces and punctuation)
- Write ONE tight paragraph only — no multi-paragraph structure
- No hashtags — they will NOT be appended for X
- No 'Read more' or filler CTAs — the post must stand completely alone
- Every word must earn its place; cut ruthlessly until it fits
"""
        else:
            _platform_block = ""

        system_prompt = f"""{PERSONA_SYSTEM_PROMPT}
Maximum length: {max_length} characters including hashtags.{_platform_block}
Profile context:
{profile_context}

SSI optimisation goal:
{ssi_instruction}"""

        user_prompt = f"""Write a LinkedIn post about: {title}
Angle to take: {angle}

The post should feel authentic to someone who actually built this, not generic AI content.
Use a hook in the first line that stops the scroll — a surprising stat, a bold claim, or a short story.
Do NOT include hashtags in your output — they will be appended automatically."""

        return self._generate(system_prompt, user_prompt, max_tokens=512)

    def generate_thread_posts(
        self,
        article_text: str,
        source_url: str,
        ssi_component: str = "engage_with_insights",
        channel: str = "x",
    ) -> "Optional[list[str]]":
        """
        Generate a 2-post thread (X or Bluesky) from an article.
        Returns a list of exactly 2 strings, or None if article_text is too short.
        Same signature as ClaudeService.generate_thread_posts.
        """
        if not article_text or len(article_text.strip()) < 100:
            logger.warning(f"Skipping thread generation — article text too short: {source_url}")
            return None

        ssi_instruction = SSI_COMPONENT_INSTRUCTIONS.get(ssi_component, SSI_COMPONENT_INSTRUCTIONS["engage_with_insights"])
        platform = "Bluesky" if channel == "bluesky" else "X (Twitter)"
        char_limit = X_CHAR_LIMIT - X_URL_CHARS  # 257 chars — safe for both X and Bluesky

        github_user = os.getenv("GITHUB_USER", "")
        github_url = f"github.com/{github_user}" if github_user else "your GitHub profile"

        prompt = f"""Generate a 2-post {platform} thread from the article below.

Return exactly two XML-tagged posts and nothing else:
<post_1>Tweet 1 text here</post_1>
<post_2>Tweet 2 text here</post_2>

Post 1 (hook) — a bold claim, surprising stat, or sharp question that stops the scroll. Max {char_limit} chars.
Post 2 (insight + close) — your technical take or personal experience, then end with your GitHub link ({github_url}) and a call to action. Max {char_limit} chars.

Rules:
- PLAIN TEXT ONLY — absolutely no asterisks, no bold (**word**), no italics (*word*), no markdown of any kind
- No hashtags in either post
- No "1/2", "2/2" thread numbering
- Count characters carefully — stay under {char_limit} per post

SSI optimisation goal:
{ssi_instruction}

Article:
{article_text[:3000]}"""

        raw = self._generate(PERSONA_SYSTEM_PROMPT, prompt, max_tokens=600)
        return parse_xml_thread(raw, source_url)

    def generate_first_comment(self, post_text: str, source_url: str) -> str:
        """
        Generate a LinkedIn first comment with hashtags and source link.
        Same signature as ClaudeService.generate_first_comment.
        """
        prompt = f"""Write a LinkedIn first comment for the post below.

The comment should contain:
- 3-5 relevant hashtags (space-separated)
- The source URL: {source_url}
- Optionally 1 short sentence that adds context or invites engagement

Keep it concise — the post body carries the main content.
Output plain text only — no Markdown.

Post:
{post_text}"""

        comment = self._generate(PERSONA_SYSTEM_PROMPT, prompt, max_tokens=200)
        if source_url and source_url not in comment:
            comment = comment.rstrip() + f"\n\n{source_url}"
        return comment

    def summarise_for_curation(self, article_text: str, source_url: str, ssi_component: str = "engage_with_insights", channel: str = "linkedin", post_mode: bool = False) -> Optional[str]:
        """
        Summarise a curated article into a LinkedIn post with personal commentary.
        Returns None if article_text is too short to be useful.
        Same signature as ClaudeService.summarise_for_curation.
        post_mode=True: omits hashtags and URL from the body — both go in the first comment instead.
        """
        if not article_text or len(article_text.strip()) < 100:
            logger.warning(f"Skipping curation — article text too short ({len(article_text.strip())} chars): {source_url}")
            return None
        ssi_instruction = SSI_COMPONENT_INSTRUCTIONS.get(ssi_component, SSI_COMPONENT_INSTRUCTIONS["engage_with_insights"])

        if channel == "x":
            _text_budget = X_CHAR_LIMIT - X_URL_CHARS
            format_instructions = f"""IMPORTANT — this post is for X (Twitter), NOT LinkedIn:
- Hard limit: {_text_budget} characters for your text (the source URL adds {X_URL_CHARS} chars, totalling {X_CHAR_LIMIT})
- One or two very short sentences only — no paragraphs, no structure
- No hashtags
- Lead with your single sharpest take on the article; skip the summary entirely
Do NOT include the article URL — it will be appended automatically."""
        elif post_mode:
            format_instructions = """Summarise this article and write a LinkedIn post sharing it with your own commentary.
Output plain text only — no Markdown, no **, no ##, no backticks. LinkedIn does not render Markdown.
Format (plain paragraphs, no dashes or bullets):
1-2 sentence hook
2-3 sentences summarising the key insight (in your own words, don't quote)
1-2 sentences of YOUR opinion or how it relates to your work in RAG/AI
3-5 relevant hashtags on the last line
Do NOT include the article URL — it will be appended automatically."""
        else:
            format_instructions = """Summarise this article and write a LinkedIn post sharing it with your own commentary.
Output plain text only — no Markdown, no **, no ##, no backticks. LinkedIn does not render Markdown.
Format (plain paragraphs, no dashes or bullets):
1-2 sentence hook
2-3 sentences summarising the key insight (in your own words, don't quote)
1-2 sentences of YOUR opinion or how it relates to your work in RAG/AI
3-5 relevant hashtags on the last line
Do NOT include the article URL in your output — it will be appended automatically."""

        system_prompt = PERSONA_SYSTEM_PROMPT
        user_prompt = f"""{format_instructions}

SSI optimisation goal for this post:
{ssi_instruction}

Article:
{article_text[:3000]}"""

        return self._generate(system_prompt, user_prompt, max_tokens=512)
