"""Path constants for the avatar_intelligence package."""

from __future__ import annotations

import os
from pathlib import Path

_DATA_DIR = Path(os.getenv("AVATAR_DATA_DIR", "data/avatar"))

PERSONA_GRAPH_PATH = _DATA_DIR / "persona_graph.json"
NARRATIVE_MEMORY_PATH = _DATA_DIR / "narrative_memory.json"
DOMAIN_KNOWLEDGE_PATH = _DATA_DIR / "domain_knowledge.json"
LEARNING_LOG_PATH = _DATA_DIR / "learning_log.jsonl"
EXTRACTED_KNOWLEDGE_PATH = _DATA_DIR / "extracted_knowledge.json"
