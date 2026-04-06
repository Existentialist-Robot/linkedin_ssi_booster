"""
Ollama Local LLM Service
Generates LinkedIn posts using a locally-running Ollama model.

Requires Ollama running at OLLAMA_BASE_URL (default: http://localhost:11434).
Set OLLAMA_MODEL to choose the model (default: llama3.2).

Start Ollama: ollama serve
Pull a model: ollama pull qwen2.5:14b
"""

import os
import re

import logging
from typing import Any, Optional

import ollama

import json
from services.shared import PERSONA_SYSTEM_PROMPT, YOUTUBE_SHORT_SYSTEM_PROMPT, SSI_COMPONENT_INSTRUCTIONS, X_CHAR_LIMIT, X_URL_CHARS, clean_llm_text
from services.console_grounding import build_grounding_facts_block, ProjectFact

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.2"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_NUM_CTX = 16384


class OllamaService:

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL):
        self.model = model
        self.base_url = base_url
        raw_num_ctx = (os.getenv("OLLAMA_NUM_CTX") or str(DEFAULT_NUM_CTX)).strip()
        try:
            self.num_ctx = max(1024, int(raw_num_ctx))
        except ValueError:
            logger.warning("Invalid OLLAMA_NUM_CTX=%r; using default %d", raw_num_ctx, DEFAULT_NUM_CTX)
            self.num_ctx = DEFAULT_NUM_CTX
        self.client = ollama.Client(host=base_url)
        logger.info(
            "OllamaService initialised — model=%s, host=%s, num_ctx=%d",
            model,
            base_url,
            self.num_ctx,
        )

    def _chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        """Send a chat request to Ollama and return the response text."""
        try:
            response = self.client.chat(
                model=self.model,
                options={"num_predict": max_tokens, "num_ctx": self.num_ctx},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            return (response.message.content or "").strip()
        except ollama.ResponseError as e:
            raise RuntimeError(f"Ollama API error (model={self.model}): {e}") from e
        except Exception as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url}. "
                "Is it running? Try: ollama serve"
            ) from e

    def chat_as_persona(
        self,
        messages: list[dict[str, str]],
        profile_context: str,
        max_tokens: int = 600,
    ) -> str:
        """Run an interactive persona chat with profile context loaded."""
        system_prompt = f"""{PERSONA_SYSTEM_PROMPT}

Profile context:
{profile_context}

You are in interactive console chat mode.
- Identity lock: You MUST represent the person described in Profile context.
- Never claim to be Gemma, Google, DeepMind, a generic LLM, or an AI assistant.
- If asked who you are, introduce yourself using the profile name/title/projects from Profile context.
- Treat Profile context as the primary source of truth for biography and projects.
- If you are uncertain about a fact, say it is not confirmed in loaded profile context.
- Stay in persona and answer naturally.
- Be concrete and practical when possible.
- Output plain text only (no markdown)."""

        normalized_messages: list[dict[str, str]] = []
        for m in messages:
            role = (m.get("role") or "user").strip()
            if role not in {"user", "assistant"}:
                continue
            content = (m.get("content") or "").strip()
            if content:
                normalized_messages.append({"role": role, "content": content})

        try:
            response = self.client.chat(
                model=self.model,
                options={"num_predict": max_tokens, "num_ctx": self.num_ctx},
                messages=[{"role": "system", "content": system_prompt}, *normalized_messages],
            )
            return clean_llm_text((response.message.content or "").strip())
        except ollama.ResponseError as e:
            raise RuntimeError(f"Ollama API error (model={self.model}): {e}") from e
        except Exception as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url}. "
                "Is it running? Try: ollama serve"
            ) from e

    def generate_linkedin_post(
        self,
        title: str,
        angle: str,
        ssi_component: str,
        hashtags: list,
        profile_context: str,
        grounding_facts: Optional[list[ProjectFact]] = None,
        max_length: int = 1300,
        channel: str = "linkedin",
    ) -> str:
        """
        Generate a LinkedIn post optimised for a specific SSI component.
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
        elif channel == "youtube":
            max_length = 500
            _platform_block = f"\n{YOUTUBE_SHORT_SYSTEM_PROMPT}"
        else:
            _platform_block = ""

        grounding_block = build_grounding_facts_block(grounding_facts or [], limit=5)

        system_prompt = f"""{PERSONA_SYSTEM_PROMPT}
Maximum length: {max_length} characters including hashtags.{_platform_block}
Profile context:
{profile_context}

SSI optimisation goal:
{ssi_instruction}"""

        user_prompt = f"""Write a LinkedIn post about: {title}
Angle to take: {angle}

Truth grounding constraints:
- You may only reference personal experience that is explicitly present in "Allowed profile facts" below.
- If none of the allowed facts apply to this topic, do not mention personal project/company history.
- Never invent companies, project names, years, or implementation claims.

{grounding_block}

The post should feel authentic to someone who actually built this, not generic AI content.
Use a hook in the first line that stops the scroll — a surprising stat, a bold claim, or a short story.
Do NOT include hashtags in your output — they will be appended automatically."""

        text = self._chat(system_prompt, user_prompt, max_tokens=512)

        if channel == "youtube" and len(text) > 500:
            # Hard cap: truncate to last complete sentence at or before 500 chars
            truncated = text[:500]
            for sep in (".", "!", "?"):
                idx = truncated.rfind(sep)
                if idx != -1:
                    truncated = truncated[: idx + 1]
                    break
            else:
                # No sentence boundary found — cut at last word boundary
                truncated = truncated[: truncated.rfind(" ")].rstrip()
            text = truncated
            logger.debug(f"YouTube Short script truncated to {len(text)} chars")

        return text

    def generate_thread_posts(
        self,
        article_text: str,
        source_url: str,
        ssi_component: str = "engage_with_insights",
        channel: str = "x",
    ) -> "Optional[list[str]]":
        """
        Generate a 2-post thread (X or Bluesky) from an article.
        Uses Ollama structured JSON output (format schema) for reliable splitting —
        no regex parsing required.
        Returns a list of exactly 2 strings, or None if article_text is too short.
        """
        if not article_text or len(article_text.strip()) < 100:
            logger.warning(f"Skipping thread generation — article text too short: {source_url}")
            return None

        ssi_instruction = SSI_COMPONENT_INSTRUCTIONS.get(ssi_component, SSI_COMPONENT_INSTRUCTIONS["engage_with_insights"])
        platform = "Bluesky" if channel == "bluesky" else "X (Twitter)"
        char_limit = X_CHAR_LIMIT - X_URL_CHARS

        github_user = os.getenv("GITHUB_USER", "")
        github_url = f"github.com/{github_user}" if github_user else "your GitHub profile"

        prompt = f"""Generate a 2-post {platform} thread from the article below.

post_1 (hook): bold claim, surprising stat, or sharp question that stops the scroll. Max {char_limit} chars.
post_2 (insight + close): your technical take, ending with {github_url} and a CTA. Max {char_limit} chars.

Rules: plain text only, no hashtags, no markdown, no "1/2"/"2/2" numbering.

SSI goal: {ssi_instruction}

Article: {article_text[:3000]}"""

        try:
            response = self.client.chat(
                model=self.model,
                options={"num_predict": 600, "num_ctx": self.num_ctx},
                format={
                    "type": "object",
                    "properties": {
                        "post_1": {"type": "string"},
                        "post_2": {"type": "string"},
                    },
                    "required": ["post_1", "post_2"],
                },
                messages=[
                    {"role": "system", "content": PERSONA_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
            )
            data = json.loads(response.message.content or "{}")
            return [clean_llm_text(data["post_1"]), clean_llm_text(data["post_2"])]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Ollama structured output parse failed ({e}): {source_url}")
            return None

    def generate_first_comment(self, post_text: str, source_url: str) -> str:
        """
        Generate a LinkedIn first comment with hashtags and source link.
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

        comment = self._chat(PERSONA_SYSTEM_PROMPT, prompt, max_tokens=200)
        if source_url and source_url not in comment:
            comment = comment.rstrip() + f"\n\n{source_url}"
        return comment

    def summarise_for_curation(
        self,
        article_text: str,
        source_url: str,
        ssi_component: str = "engage_with_insights",
        channel: str = "linkedin",
        post_mode: bool = False,
        grounding_facts: Optional[list[ProjectFact]] = None,
    ) -> Optional[str]:
        """
        Summarise a curated article into a LinkedIn post with personal commentary.
        Returns None if article_text is too short to be useful.
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
- Write 1-3 tight sentences — no paragraphs, no structure, no hashtags
- Ground your take in something SPECIFIC from this article: a number, a technique, a concrete claim, or a decision. Do NOT write a generic AI observation.
- Forbidden openers: "Everyone thinks", "Scaling AI", "AI is", "The future of", "Everyone knows" — be specific to what this article actually covers
- Sound like someone who shipped it: direct, technical, occasionally contrarian
- Do NOT start with a quotation mark character
Do NOT include the article URL — it will be appended automatically."""
        elif channel == "bluesky":
            _url_overhead = 2 + len(source_url)
            _text_budget = 300 - _url_overhead
            format_instructions = f"""IMPORTANT — this post is for Bluesky, NOT LinkedIn:
- Hard character limit: {_text_budget} characters for your text ({_url_overhead} chars reserved for the URL, total max = 300)
- Write 1-2 short complete sentences. Target under {_text_budget - 40} characters — leave margin so nothing gets cut.
- ONE RULE ABOVE ALL: every sentence MUST end with a period, exclamation mark, or question mark. Never end mid-thought.
- Ground your take in something SPECIFIC from this article — no generic AI observations
- No hashtags, no bullet points, do NOT start with a quotation mark character
Do NOT include the article URL — it will be appended automatically."""
        elif channel == "youtube":
            format_instructions = f"""{YOUTUBE_SHORT_SYSTEM_PROMPT}
CRITICAL HARD LIMIT: your entire response MUST be 500 characters or fewer — count every character before you output.
Do NOT include hashtags, URLs, or any markdown.
If you are close to 500 characters, stop at the last complete sentence that fits."""
        elif post_mode:
            format_instructions = """Summarise this article and write a LinkedIn post sharing it with your own commentary.
Output plain text only — no Markdown, no **, no ##, no backticks. LinkedIn does not render Markdown.
Format (plain paragraphs, no dashes or bullets):

Hook (1-2 sentences): Open with the most specific, surprising, or counterintuitive claim FROM THIS ARTICLE — name the actual thing: a model name, a number, a named technique, a decision the team actually made. Not a generic AI observation.
Summary (2-3 sentences): Explain the article's core insight in your own words. Include at least one concrete detail from the article (a number, a benchmark result, a named technique, a specific decision). Do not pad with generalities.
Opinion (1-2 sentences): Give your take as an engineer who builds production AI systems. Stay exactly on-topic — your opinion must be about the SAME subject as the article, not a tangentially related subject. Include at most ONE grounded personal reference from Allowed profile facts when it is clearly relevant; otherwise keep your opinion article-focused.

CRITICAL: All claims must be grounded in what THIS specific article covers. If the article is about fine-tuning, write about fine-tuning. If it is about agent safety, write about agent safety. Do NOT pivot topics under any circumstances.
3-5 relevant hashtags on the last line
Do NOT include the article URL — it will be appended automatically."""
        else:
            format_instructions = """Summarise this article and write a LinkedIn post sharing it with your own commentary.
Output plain text only — no Markdown, no **, no ##, no backticks. LinkedIn does not render Markdown.
Format (plain paragraphs, no dashes or bullets):

Hook (1-2 sentences): Open with the most specific, surprising, or counterintuitive claim FROM THIS ARTICLE — name the actual thing: a model name, a number, a named technique, a decision the team actually made. Not a generic AI observation.
Summary (2-3 sentences): Explain the article's core insight in your own words. Include at least one concrete detail from the article (a number, a benchmark result, a named technique, a specific decision). Do not pad with generalities.
Opinion (1-2 sentences): Give your take as an engineer who builds production AI systems. Stay exactly on-topic — your opinion must be about the SAME subject as the article, not a tangentially related subject. Include at most ONE grounded personal reference from Allowed profile facts when it is clearly relevant; otherwise keep your opinion article-focused.

CRITICAL: All claims must be grounded in what THIS specific article covers. If the article is about fine-tuning, write about fine-tuning. If it is about agent safety, write about agent safety. Do NOT pivot topics under any circumstances.
3-5 relevant hashtags on the last line
Do NOT include the article URL in your output — it will be appended automatically."""

        grounding_block = build_grounding_facts_block(grounding_facts or [], limit=5)

        prompt = f"""READ THIS ARTICLE CAREFULLY — your post must be grounded in it, not in your profile:
---
{article_text[:3000]}
---

{format_instructions}

Truth grounding constraints for any personal references:
- You may only reference personal experience that appears in "Allowed profile facts" below.
- If none of these facts fit this article, keep your commentary general and article-focused.
- Never invent project/company names, years, or claims.

{grounding_block}

SSI optimisation goal for this post:
{ssi_instruction}"""

        first_pass = clean_llm_text(self._chat(PERSONA_SYSTEM_PROMPT, prompt, max_tokens=512))
        if first_pass:
            return first_pass

        logger.warning(
            "Curation first-pass output was empty after cleanup; retrying with simplified prompt"
        )
        retry_prompt = f"""Write a concise {channel} post grounded in this article.

Article:
{article_text[:2500]}

Requirements:
- 3-5 sentences, plain text only.
- Include one specific detail from the article.
- Include at most one grounded personal reference from Allowed profile facts if clearly relevant.
- Do not invent project/company names, years, or claims.

Allowed profile facts:
{grounding_block}
"""
        retry_pass = clean_llm_text(self._chat(PERSONA_SYSTEM_PROMPT, retry_prompt, max_tokens=384))
        if retry_pass:
            return retry_pass

        logger.warning(
            "Curation retry output was empty after cleanup; using deterministic article-only fallback"
        )
        clean_article = re.sub(r"<[^>]+>", " ", article_text)
        clean_article = re.sub(r"\s+", " ", clean_article).strip()
        detail = ""
        if clean_article:
            parts = re.split(r"(?<=[.!?])\s+", clean_article)
            detail = (parts[0] if parts else clean_article).strip()

        hook = "Worth a read for teams building production AI and search systems."
        if channel == "x":
            fallback = f"{hook} {detail}".strip()
            return fallback[: max(1, X_CHAR_LIMIT - X_URL_CHARS)].rstrip()
        if channel == "bluesky":
            bsky_budget = 300 - (2 + len(source_url) if source_url else 0)
            fallback = f"{hook} {detail}".strip()
            return fallback[: max(1, bsky_budget)].rstrip()
        if channel == "youtube":
            fallback = f"{hook} {detail}".strip()
            return fallback[:500].rstrip()

        fallback_lines = [hook]
        if detail:
            fallback_lines.append(detail)
        fallback_lines.append("What stands out most to you from this approach in real deployments?")
        if post_mode:
            fallback_lines.append("#AI #MachineLearning #LLM")
        return "\n\n".join(fallback_lines)
