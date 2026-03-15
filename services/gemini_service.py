"""
Gemini AI Service
Generates LinkedIn posts using Google's Gemini API.
Drop-in replacement for ClaudeService — identical public interface.

Requires GEMINI_API_KEY in .env.
Get a free key at: https://aistudio.google.com/apikey
Default model: gemini-2.0-flash (fast, generous free tier)
"""

import logging
import time
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from services.claude_service import PERSONA_SYSTEM_PROMPT, SSI_COMPONENT_INSTRUCTIONS, X_CHAR_LIMIT, X_URL_CHARS

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiService:

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required. Get one free at https://aistudio.google.com/apikey")
        self.model = model
        self.client = genai.Client(api_key=api_key)
        logger.info(f"GeminiService initialised — model={model}")

    def _generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024, _retries: int = 3) -> str:
        """Send a request to Gemini and return the response text.
        Automatically retries on 429 rate-limit errors with the suggested delay.
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
                logger.warning(f"Gemini rate limit hit — waiting {retry_delay:.0f}s then retrying ({_retries} left)")
                time.sleep(retry_delay)
                return self._generate(system_prompt, user_prompt, max_tokens, _retries - 1)
            raise RuntimeError(f"Gemini API error (model={self.model}): {e}") from e
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

    def summarise_for_curation(self, article_text: str, source_url: str, ssi_component: str = "engage_with_insights", channel: str = "linkedin") -> Optional[str]:
        """
        Summarise a curated article into a LinkedIn post with personal commentary.
        Returns None if article_text is too short to be useful.
        Same signature as ClaudeService.summarise_for_curation.
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
