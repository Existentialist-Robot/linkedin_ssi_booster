"""
GitHub Service
Fetches public repository metadata for a GitHub user and formats it as a
compact profile context block suitable for LLM prompt injection.

Responses are cached to github_repos_cache.json for 24 hours to avoid
hammering the API on every run.

Config (via .env):
    GITHUB_USER          — GitHub username (required to enable)
    GITHUB_TOKEN         — Optional personal access token (avoids 60 req/hr limit)
    GITHUB_REPO_FILTER   — Comma-separated list of repo names to include.
                           If empty, all non-fork repos are included.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CACHE_FILE = Path("github_repos_cache.json")
CACHE_TTL_SECONDS = 86400  # 24 hours
GITHUB_API_BASE = "https://api.github.com"


class GitHubService:

    def __init__(
        self,
        username: str,
        token: Optional[str] = None,
        repo_filter: Optional[list[str]] = None,
    ):
        self.username = username
        self.repo_filter = [r.strip().lower() for r in repo_filter] if repo_filter else []
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def _fetch_repos(self) -> list[dict]:
        """Fetch all non-fork public repos, paginating as needed."""
        repos: list[dict] = []
        page = 1
        while True:
            resp = self._session.get(
                f"{GITHUB_API_BASE}/users/{self.username}/repos",
                params={"type": "public", "sort": "updated", "per_page": 100, "page": page},
                timeout=10,
            )
            if resp.status_code == 404:
                raise ValueError(f"GitHub user not found: {self.username}")
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return [r for r in repos if not r.get("fork")]

    def _load_cache(self) -> Optional[list[dict]]:
        if not CACHE_FILE.exists():
            return None
        try:
            data = json.loads(CACHE_FILE.read_text())
            if time.time() - data.get("fetched_at", 0) < CACHE_TTL_SECONDS:
                return data["repos"]
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def _save_cache(self, repos: list[dict]) -> None:
        CACHE_FILE.write_text(json.dumps({"fetched_at": time.time(), "repos": repos}))

    def get_repos(self) -> list[dict]:
        """Return repos from cache if fresh, otherwise fetch from API."""
        cached = self._load_cache()
        if cached is not None:
            logger.debug("GitHub repos loaded from cache")
            return cached
        logger.info(f"Fetching public repos for GitHub user: {self.username}")
        repos = self._fetch_repos()
        self._save_cache(repos)
        return repos

    def build_profile_context_block(self) -> str:
        """Return a compact multi-line string listing relevant repos for prompt injection."""
        try:
            repos = self.get_repos()
        except Exception as e:
            logger.warning(f"GitHub fetch failed — skipping repo context: {e}")
            return ""

        if self.repo_filter:
            repos = [r for r in repos if r["name"].lower() in self.repo_filter]

        if not repos:
            return ""

        lines = ["GitHub projects (use these as real reference points when relevant):"]
        for repo in repos:
            name = repo["name"]
            desc = (repo.get("description") or "").strip()
            lang = repo.get("language") or ""
            topics = ", ".join(repo.get("topics") or [])
            stars = repo.get("stargazers_count", 0)

            parts = [f"- {name}"]
            if desc:
                parts.append(desc)
            meta: list[str] = []
            if lang:
                meta.append(lang)
            if topics:
                meta.append(f"topics: {topics}")
            if stars:
                meta.append(f"{stars} stars")
            if meta:
                parts.append(f"[{' | '.join(meta)}]")
            lines.append("  ".join(parts))

        return "\n".join(lines)


def build_github_profile_context() -> str:
    """
    Convenience function called from main.py.
    Returns an empty string if GITHUB_USER is not set.
    """
    username = os.getenv("GITHUB_USER", "").strip()
    if not username:
        return ""

    token = os.getenv("GITHUB_TOKEN", "").strip() or None
    raw_filter = os.getenv("GITHUB_REPO_FILTER", "").strip()
    repo_filter = [r for r in raw_filter.split(",") if r.strip()] if raw_filter else []

    svc = GitHubService(username=username, token=token, repo_filter=repo_filter or None)
    return svc.build_profile_context_block()
