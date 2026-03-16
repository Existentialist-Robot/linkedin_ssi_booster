"""
Claude AI Service
Generates LinkedIn posts tailored to SSI components using the Anthropic API.
Each post is engineered to push a specific SSI component score.
"""

import os
import anthropic
from anthropic.types import TextBlock
import logging
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable via .env — override any of these without touching code
# ---------------------------------------------------------------------------

PERSONA_SYSTEM_PROMPT: str = os.getenv(
    "PERSONA_SYSTEM_PROMPT",
    """You are a LinkedIn content strategist and ghostwriter for a senior professional.
Your voice is technical but human: concise, direct, and occasionally contrarian. Posts feel written by someone who has actually shipped the thing.
Never use: 'In the age of AI', 'Game changer', 'Exciting to share', 'Thrilled to announce', 'Delighted to', 'I am pleased to'.
Never start a post with 'I'. Never use bullet points for the main body — write in short, punchy paragraphs.
Avoid corporate jargon, passive voice, and hollow hype. Favour specifics over generalities.
Set PERSONA_SYSTEM_PROMPT in your .env to customise this for a specific person and domain.
IMPORTANT: Output plain text only — no Markdown. Do not use **, ##, __, `, or any other Markdown syntax. LinkedIn does not render Markdown."""
)

# X (Twitter) platform limits — enforced at the prompt level, not by truncation
X_CHAR_LIMIT = 280  # Standard X character limit
X_URL_CHARS  = 23   # Every URL on X counts as exactly 23 characters regardless of real length

SSI_COMPONENT_INSTRUCTIONS: dict[str, str] = {
    "establish_brand": os.getenv(
        "SSI_ESTABLISH_BRAND",
        """This post should ESTABLISH PROFESSIONAL BRAND.
- Share something you built, learned, or solved
- Demonstrate deep expertise in AI/RAG/search
- Use specific technical details — not vague claims
- End with a clear point of view or lesson learned
- LinkedIn algorithm rewards posts that get saves and shares"""
    ),
    "find_right_people": os.getenv(
        "SSI_FIND_RIGHT_PEOPLE",
        """This post should help FIND THE RIGHT PEOPLE.
- Mention specific tools, communities, or events relevant to your industry
- Ask a question that invites replies from your target audience
- Tag relevant communities or technologies (not people)
- This drives profile visits from the right professionals"""
    ),
    "engage_with_insights": os.getenv(
        "SSI_ENGAGE_WITH_INSIGHTS",
        """This post should ENGAGE WITH INSIGHTS.
- Reference or summarize a recent AI paper, article, or trend
- Give YOUR take on it — don't just summarize
- Make a bold or counterintuitive claim based on your experience
- Invite discussion: 'What's your experience with this?'
- This component rewards thoughtful engagement on others' content too"""
    ),
    "build_relationships": os.getenv(
        "SSI_BUILD_RELATIONSHIPS",
        """This post should BUILD RELATIONSHIPS.
- Share a behind-the-scenes story or honest lesson from a project
- Be specific about challenges you faced and how you solved them
- Show personality — not just technical facts
- Make it feel like a conversation, not a press release
- End with something that invites comments and connection"""
    ),
}


class ClaudeService:

    def __init__(self, api_key: str, model: str = "claude-opus-4-6"):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

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
        
        Args:
            title: Topic title (e.g. 'What is AI-TDD')
            angle: Specific angle to take (e.g. 'contrast with vibe coding')
            ssi_component: One of: establish_brand, find_right_people, engage_with_insights, build_relationships
            hashtags: List of hashtags to include
            profile_context: Shawn's profile summary for personalisation
            max_length: Target character length (LinkedIn limit is ~3000)
        """
        ssi_instruction = SSI_COMPONENT_INSTRUCTIONS.get(ssi_component, SSI_COMPONENT_INSTRUCTIONS["establish_brand"])
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
{ssi_instruction}
"""

        user_prompt = f"""Write a LinkedIn post about: {title}
Angle to take: {angle}

The post should feel authentic to someone who actually built this, not generic AI content.
Use a hook in the first line that stops the scroll — a surprising stat, a bold claim, or a short story.
Do NOT include hashtags in your output — they will be appended automatically.
"""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt
        )
        text_block = next(b for b in message.content if isinstance(b, TextBlock))
        return text_block.text.strip()

    def generate_thread_posts(
        self,
        article_text: str,
        source_url: str,
        ssi_component: str = "engage_with_insights",
        channel: str = "x",
    ) -> Optional[list[str]]:
        """
        Generate a 3-post thread (X or Bluesky) from an article.
        Returns a list of exactly 3 strings:
          [0] Post 1: hook — bold claim or question
          [1] Post 2: insight — technical take or experience
          [2] Post 3: close — call to action (source URL appended by Buffer, not included here)
        Returns None if article_text is too short.
        """
        if not article_text or len(article_text.strip()) < 100:
            logger.warning(f"Skipping thread generation — article text too short: {source_url}")
            return None

        ssi_instruction = SSI_COMPONENT_INSTRUCTIONS.get(ssi_component, SSI_COMPONENT_INSTRUCTIONS["engage_with_insights"])
        platform = "Bluesky" if channel == "bluesky" else "X (Twitter)"
        char_limit = X_CHAR_LIMIT - X_URL_CHARS  # 257 — safe for both X and Bluesky

        prompt = f"""Generate a 3-post {platform} thread from the article below.
Output ONLY the three posts separated by "---" on its own line. No labels, no numbering.

Post 1 (hook): A bold claim, surprising stat, or sharp question that stops the scroll. Max {char_limit} chars.
---
Post 2 (insight): Your technical take or the key finding. Concrete details — no vague generalities. Max {char_limit} chars.
---
Post 3 (close): A clear call to action or key takeaway. Do NOT include the source URL. Max {char_limit} chars.

Rules:
- No hashtags in any post
- No "1/3", "2/3", "3/3" thread numbering
- No Markdown formatting — plain text only
- Count characters carefully — stay under {char_limit} per post

SSI optimisation goal:
{ssi_instruction}

Article:
{article_text[:3000]}"""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            system=PERSONA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        text_block = next(b for b in message.content if isinstance(b, TextBlock))
        raw = text_block.text.strip()

        parts = [p.strip() for p in raw.split("---") if p.strip()]
        if len(parts) < 3:
            logger.warning(f"Thread generation returned {len(parts)} parts (expected 3) for: {source_url}")
            return None
        return parts[:3]

    def generate_first_comment(self, post_text: str, source_url: str) -> str:
        """
        Generate a LinkedIn first comment with hashtags and source link.
        Keeps the main post body clean for LinkedIn algorithm reach
        (LinkedIn de-ranks posts with links in the body).
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

        message = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=PERSONA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        text_block = next(b for b in message.content if isinstance(b, TextBlock))
        comment = text_block.text.strip()
        # Guarantee source URL is present
        if source_url and source_url not in comment:
            comment = comment.rstrip() + f"\n\n{source_url}"
        return comment

    def summarise_for_curation(self, article_text: str, source_url: str, ssi_component: str = "engage_with_insights", channel: str = "linkedin", post_mode: bool = False) -> Optional[str]:
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
            _text_budget = X_CHAR_LIMIT - X_URL_CHARS  # reserve 23 chars for the URL Buffer appends
            format_instructions = f"""IMPORTANT — this post is for X (Twitter), NOT LinkedIn:
- Hard limit: {_text_budget} characters for your text (the source URL adds {X_URL_CHARS} chars, totalling {X_CHAR_LIMIT})
- One or two very short sentences only — no paragraphs, no structure
- No hashtags
- Lead with your single sharpest take on the article; skip the summary entirely
Do NOT include the article URL — it will be appended automatically."""
        elif post_mode:
            # LinkedIn direct-post: keep body clean — hashtags + link go in the first comment
            format_instructions = """Summarise this article and write a LinkedIn post sharing it with your own commentary.
Output plain text only — no Markdown, no **, no ##, no backticks. LinkedIn does not render Markdown.
Format (plain paragraphs, no dashes or bullets):
1-2 sentence hook
2-3 sentences summarising the key insight (in your own words, don't quote)
1-2 sentences of YOUR opinion or how it relates to your work in RAG/AI
Do NOT include hashtags — they will be added in the first comment.
Do NOT include the article URL — it will be added in the first comment."""
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
{article_text[:3000]}
"""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=PERSONA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        text_block = next(b for b in message.content if isinstance(b, TextBlock))
        return text_block.text.strip()
