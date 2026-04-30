"""JSONL persistence helpers for selection learning."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JsonlStore:
    """Utility class for reading/appending/rewriting JSONL files."""

    @staticmethod
    def read(path: Path) -> list[dict[str, Any]]:
        """Read a newline-delimited JSON file; return empty list if missing."""
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "selection_learning: skipping malformed line %d in %s: %s",
                        lineno,
                        path,
                        exc,
                    )
        return records

    @staticmethod
    def append(path: Path, record: dict[str, Any]) -> None:
        """Append one JSON object to a JSONL file, creating it if needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    @staticmethod
    def rewrite(path: Path, records: list[dict[str, Any]]) -> None:
        """Atomically overwrite a JSONL file with *records*."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")
        tmp.replace(path)

    @staticmethod
    def load_published_ids(path: Path) -> set[str]:
        """Return the set of buffer_ids already in the published cache."""
        return {r["buffer_id"] for r in JsonlStore.read(path) if r.get("buffer_id")}
