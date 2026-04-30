"""
SSI component selection logic.
Picks the LinkedIn SSI pillar to target based on configured weights and
an adaptive topic signal derived from recently extracted facts.
"""

import random
from typing import Any, Optional

from services.content_curator._config import _SSI_WEIGHTS, _SSI_TOPIC_HINTS


def build_topic_signal(extracted_facts: list[Any], window: int = 50) -> dict[str, int]:
    """Aggregate recent extracted fact tags/entities into a topic frequency map."""
    signal: dict[str, int] = {}
    recent = extracted_facts[-window:]
    for fact in recent:
        for tag in (getattr(fact, "tags", []) or []):
            key = str(tag).strip().lower()
            if key:
                signal[key] = signal.get(key, 0) + 1
        for entity in (getattr(fact, "entities", []) or []):
            key = str(entity).strip().lower()
            if key:
                signal[key] = signal.get(key, 0) + 1
    return signal


def pick_ssi_component(topic_signal: Optional[dict[str, int]] = None) -> str:
    """Pick a component proportionally to configured weights, with soft topic tilt."""
    weights = dict(_SSI_WEIGHTS)
    if topic_signal:
        for component, hints in _SSI_TOPIC_HINTS.items():
            match_score = sum(topic_signal.get(h, 0) for h in hints)
            # Soft upweight: max +50% bias so base SSI strategy remains dominant.
            weights[component] = weights[component] * (1.0 + min(match_score * 0.10, 0.50))

    components = list(weights.keys())
    weight_values = list(weights.values())
    return random.choices(components, weights=weight_values, k=1)[0]
