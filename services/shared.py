"""
Shared constants and utilities for all LLM service backends.

Import platform limits, persona, SSI instructions, and text helpers from here.
The ollama_service module owns API logic — nothing in here should import from it.
"""

import os
import re
import logging
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform limits
# ---------------------------------------------------------------------------

X_CHAR_LIMIT = 280  # Standard X character limit
X_URL_CHARS  = 23   # Every URL on X counts as exactly 23 characters

# ---------------------------------------------------------------------------
# Persona — configurable via .env
# ---------------------------------------------------------------------------

PERSONA_SYSTEM_PROMPT: str = os.getenv(
    "PERSONA_SYSTEM_PROMPT",
    """You are a LinkedIn content strategist and ghostwriter for a senior technical professional.
Your voice is technical but human: concise, direct, and occasionally contrarian. Posts feel written by someone who has actually shipped the thing.
Never use: 'In the age of AI', 'Game changer', 'Exciting to share', 'Thrilled to announce', 'Delighted to', 'I am pleased to'.
Never start a post with 'I'. Never use bullet points for the main body — write in short, punchy paragraphs.
Avoid corporate jargon, passive voice, and hollow hype. Favour specifics over generalities.
Set PERSONA_SYSTEM_PROMPT in your .env to customise this for a specific person and domain.
IMPORTANT: Output plain text only — no Markdown. Do not use **, ##, __, `, or any other Markdown syntax. LinkedIn does not render Markdown."""
)

# ---------------------------------------------------------------------------
# SSI component instructions — configurable via .env
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Shared text utilities
# ---------------------------------------------------------------------------

def clean_llm_text(s: str) -> str:
    """Strip markdown formatting that LLMs sneak in despite instructions."""
    s = re.sub(r'\*\*(.*?)\*\*', r'\1', s)                    # **bold**
    s = re.sub(r'__(.*?)__', r'\1', s)                         # __bold__
    s = re.sub(r'\*(.*?)\*', r'\1', s)                         # *italic*
    s = re.sub(r'_(.*?)_', r'\1', s)                           # _italic_
    s = re.sub(r'`(.*?)`', r'\1', s)                           # `code`
    s = re.sub(r'^#{1,6}\s+', '', s, flags=re.MULTILINE)       # ## headings
    s = re.sub(r'^"+', '', s)                                   # leading " LLMs wrap output in
    return s.strip()


def parse_xml_thread(raw: str, source_url: str) -> Optional[list[str]]:
    """Extract a 2-post thread from <post_1>…</post_1> tagged LLM output.

    Returns exactly 2 clean strings, or None if the tags are missing/malformed.
    """
    parts = re.findall(r'<post_[12]>(.*?)</post_[12]>', raw, re.DOTALL | re.IGNORECASE)
    parts = [clean_llm_text(p) for p in parts if p.strip()]
    if len(parts) >= 2:
        return parts[:2]
    logger.warning(
        f"XML thread parse failed — expected 2 <post_N> tags, got {len(parts)} for: {source_url}"
    )
    return None
