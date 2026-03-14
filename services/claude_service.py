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

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-opus-4-6"

    def generate_linkedin_post(
        self,
        title: str,
        angle: str,
        ssi_component: str,
        hashtags: list,
        profile_context: str,
        max_length: int = 1300
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

        system_prompt = f"""{PERSONA_SYSTEM_PROMPT}
Maximum length: {max_length} characters including hashtags.

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

    def summarise_for_curation(self, article_text: str, source_url: str, ssi_component: str = "engage_with_insights") -> Optional[str]:
        """
        Summarise a curated article into a LinkedIn post with personal commentary.
        Returns None if article_text is too short to be useful.
        Used by the ContentCurator service.
        """
        if not article_text or len(article_text.strip()) < 100:
            logger.warning(f"Skipping curation — article text too short ({len(article_text.strip())} chars): {source_url}")
            return None
        ssi_instruction = SSI_COMPONENT_INSTRUCTIONS.get(ssi_component, SSI_COMPONENT_INSTRUCTIONS["engage_with_insights"])
        prompt = f"""Summarise this article and write a LinkedIn post sharing it with your own commentary.
Output plain text only — no Markdown, no **, no ##, no backticks. LinkedIn does not render Markdown.
Format (plain paragraphs, no dashes or bullets):
1-2 sentence hook
2-3 sentences summarising the key insight (in your own words, don't quote)
1-2 sentences of YOUR opinion or how it relates to your work in RAG/AI
3-5 relevant hashtags on the last line
Do NOT include the article URL in your output — it will be appended automatically.

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
