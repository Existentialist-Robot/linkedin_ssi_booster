"""
Ollama Local LLM Service
Generates LinkedIn posts using a locally-running Ollama model.
Drop-in replacement for ClaudeService — identical public interface.

Requires Ollama running at OLLAMA_BASE_URL (default: http://localhost:11434).
Set OLLAMA_MODEL to choose the model (default: llama3.2).

Start Ollama: ollama serve
Pull a model: ollama pull llama3.2
"""

import logging
from typing import Optional

import ollama

from services.claude_service import PERSONA_SYSTEM_PROMPT, SSI_COMPONENT_INSTRUCTIONS, X_CHAR_LIMIT, X_URL_CHARS

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.2"
DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaService:

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL):
        self.model = model
        self.base_url = base_url
        self.client = ollama.Client(host=base_url)
        logger.info(f"OllamaService initialised — model={model}, host={base_url}")

    def _chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
        """Send a chat request to Ollama and return the response text."""
        try:
            response = self.client.chat(
                model=self.model,
                options={"num_predict": max_tokens},
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

        return self._chat(system_prompt, user_prompt, max_tokens=512)

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

        prompt = f"""{format_instructions}

SSI optimisation goal for this post:
{ssi_instruction}

Article:
{article_text[:3000]}"""

        return self._chat(PERSONA_SYSTEM_PROMPT, prompt, max_tokens=512)
