"""Profile context parsing — converts PROFILE_CONTEXT bullet blocks into ProjectFacts."""

from __future__ import annotations

import re

from services.console_grounding._config import get_console_grounding_keywords
from services.console_grounding._models import ProjectFact


def _extract_company(title: str, details: str) -> str:
    patterns = [
        r"\bat\s+([A-Z][A-Za-z0-9&/ .\-]+?)(?:\.|,|;|$)",
        r"\bfor\s+([A-Z][A-Za-z0-9&/ .\-]+?)(?:\.|,|;|$)",
    ]
    for pat in patterns:
        m = re.search(pat, details)
        if m:
            return m.group(1).strip()
    if "/" in title:
        return title.strip()
    return title.strip()


def _extract_tags(text: str, tech_keywords: set[str]) -> set[str]:
    low = text.lower()
    return {kw for kw in tech_keywords if kw in low}


def parse_profile_project_facts(
    profile_context: str,
    tech_keywords: set[str] | None = None,
) -> list[ProjectFact]:
    """Parse '- Project (years): details' bullets from PROFILE_CONTEXT."""
    facts: list[ProjectFact] = []
    active_keywords = tech_keywords if tech_keywords is not None else get_console_grounding_keywords()
    pattern = re.compile(r"^\s*-\s+(.+?)\s*\(([^)]*)\):\s*(.+)$", re.MULTILINE)
    for m in pattern.finditer(profile_context):
        title = m.group(1).strip()
        years = m.group(2).strip()
        details = m.group(3).strip()
        company = _extract_company(title, details)
        tags = _extract_tags(f"{title} {details} {company}", active_keywords)
        source = f"PROFILE_CONTEXT: {title} ({years})"
        facts.append(
            ProjectFact(
                project=title,
                company=company,
                years=years,
                details=details,
                source=source,
                tags=tags,
            )
        )
    return facts
