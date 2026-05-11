"""
LinkedIn API Service
OAuth2 authorization and post/comment fetching via LinkedIn's REST API.

Setup:
    1. Create a LinkedIn app: https://www.linkedin.com/developers/apps
    2. Under Products, request "Share on LinkedIn" and "Community Management API"
    3. Under Auth, add redirect URL: http://localhost:8080/callback
    4. Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env
    5. Run: python main.py --auth-linkedin  (one-time browser flow)

Config (via .env):
    LINKEDIN_CLIENT_ID       — LinkedIn app client ID (required)
    LINKEDIN_CLIENT_SECRET   — LinkedIn app client secret (required)
    LINKEDIN_REDIRECT_PORT   — Local OAuth callback port (default: 8080)

Token storage: data/linkedin_tokens.json (auto-refreshed, gitignored)
"""

import json
import logging
import re
import secrets
import select
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse

import requests

logger = logging.getLogger(__name__)

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_API_BASE = "https://api.linkedin.com"
TOKEN_FILE = Path("data/linkedin_tokens.json")
DEFAULT_SCOPES = ["openid", "profile", "email", "r_member_social", "w_member_social"]
AUTH_TIMEOUT_SECONDS = 120


class LinkedInAuthError(RuntimeError):
    pass


class LinkedInTokenExpiredError(LinkedInAuthError):
    pass


class LinkedInService:

    def __init__(self, client_id: str, client_secret: str, redirect_port: int = 8080):
        if not client_id or not client_secret:
            raise ValueError(
                "LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET are required. "
                "Create an app at https://www.linkedin.com/developers/apps"
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_port = redirect_port
        self.redirect_uri = f"http://localhost:{redirect_port}/callback"
        self._tokens: dict = self._load_tokens()
        self._name_cache: dict[str, str] = {}

    def _load_tokens(self) -> dict:
        if TOKEN_FILE.exists():
            try:
                return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_tokens(self, tokens: dict) -> None:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        self._tokens = tokens
        logger.debug("LinkedIn tokens saved to %s", TOKEN_FILE)

    def _get_access_token(self) -> str:
        if not self._tokens:
            raise LinkedInAuthError(
                "Not authenticated. Run: python main.py --auth-linkedin"
            )
        expires_at = self._tokens.get("expires_at", 0)
        if time.time() < expires_at - 60:
            return self._tokens["access_token"]
        refresh_token = self._tokens.get("refresh_token", "")
        if refresh_token:
            self._refresh_token(refresh_token)
            return self._tokens["access_token"]
        raise LinkedInTokenExpiredError(
            "Access token expired and no refresh token available. "
            "Run: python main.py --auth-linkedin"
        )

    def _refresh_token(self, refresh_token: str) -> None:
        resp = requests.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._save_tokens({
            **self._tokens,
            "access_token": data["access_token"],
            "expires_at": time.time() + data.get("expires_in", 3600),
            "refresh_token": data.get("refresh_token", refresh_token),
        })
        logger.info("LinkedIn access token refreshed.")

    def authorize(self, scopes: list[str] = DEFAULT_SCOPES) -> None:
        """Run the OAuth2 authorization code flow with a local callback server."""
        state = secrets.token_urlsafe(16)
        auth_url = (
            f"{LINKEDIN_AUTH_URL}?"
            + urlencode({
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
                "scope": " ".join(scopes),
            })
        )

        code_holder: dict = {}

        class _CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                qs = parse_qs(urlparse(self.path).query)
                code_holder["code"] = qs.get("code", [""])[0]
                code_holder["state"] = qs.get("state", [""])[0]
                code_holder["error"] = qs.get("error", [""])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authorized &#10003; You can close this tab.</h2></body></html>"
                )

            def log_message(self, *args):
                pass

        server = HTTPServer(("localhost", self.redirect_port), _CallbackHandler)
        print(f"\nOpening LinkedIn authorization in your browser...")
        print(f"Waiting up to {AUTH_TIMEOUT_SECONDS}s for callback on port {self.redirect_port}.")
        print(f"\nIf the browser doesn't open, visit:\n  {auth_url}\n")
        webbrowser.open(auth_url)

        ready = select.select([server.socket], [], [], AUTH_TIMEOUT_SECONDS)[0]
        if not ready:
            server.server_close()
            raise LinkedInAuthError(
                f"Authorization timed out after {AUTH_TIMEOUT_SECONDS}s."
            )
        server.handle_request()
        server.server_close()

        if code_holder.get("error"):
            raise LinkedInAuthError(f"LinkedIn denied authorization: {code_holder['error']}")
        if not code_holder.get("code"):
            raise LinkedInAuthError("Authorization failed — no code received.")
        if code_holder.get("state") != state:
            raise LinkedInAuthError("State mismatch — possible CSRF. Try again.")

        resp = requests.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code_holder["code"],
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._save_tokens({
            "access_token": data["access_token"],
            "expires_at": time.time() + data.get("expires_in", 3600),
            "refresh_token": data.get("refresh_token", ""),
            "scopes": scopes,
        })
        print(f"LinkedIn authorized. Tokens saved to {TOKEN_FILE}")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def get_profile(self) -> dict:
        """Return the authenticated user's OpenID Connect profile."""
        resp = requests.get(
            f"{LINKEDIN_API_BASE}/v2/userinfo",
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_person_urn(self) -> str:
        """Return the authenticated user's person URN (urn:li:person:XXX)."""
        sub = self.get_profile().get("sub", "")
        return sub if sub.startswith("urn:li:person:") else f"urn:li:person:{sub}"

    def get_recent_posts(self, count: int = 10) -> list[dict]:
        """Return the authenticated user's most recent UGC posts."""
        person_urn = self.get_person_urn()
        resp = requests.get(
            f"{LINKEDIN_API_BASE}/v2/ugcPosts",
            headers=self._headers(),
            params={
                "q": "authors",
                "authors": f"List({person_urn})",
                "count": count,
                "sortBy": "LAST_MODIFIED",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("elements", [])

    def get_comments(self, post_url_or_urn: str, count: int = 50) -> list[dict]:
        """Fetch top-level comments for a LinkedIn post.

        post_url_or_urn: full LinkedIn post URL or activity/ugcPost URN.
        """
        urn = self.parse_post_url(post_url_or_urn)
        resp = requests.get(
            f"{LINKEDIN_API_BASE}/v2/socialActions/{quote(urn, safe='')}/comments",
            headers=self._headers(),
            params={"count": count},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("elements", [])

    def get_comment_replies(
        self, post_url_or_urn: str, comment_urn: str, count: int = 20
    ) -> list[dict]:
        """Fetch replies to a specific comment."""
        post_urn = self.parse_post_url(post_url_or_urn)
        resp = requests.get(
            f"{LINKEDIN_API_BASE}/v2/socialActions/{quote(post_urn, safe='')}"
            f"/comments/{quote(comment_urn, safe='')}/comments",
            headers=self._headers(),
            params={"count": count},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("elements", [])

    def resolve_person_name(self, person_urn: str) -> str:
        """Return a display name for a person URN, cached per session."""
        if person_urn in self._name_cache:
            return self._name_cache[person_urn]
        person_id = person_urn.replace("urn:li:person:", "")
        try:
            resp = requests.get(
                f"{LINKEDIN_API_BASE}/v2/people/{person_id}",
                headers=self._headers(),
                params={"fields": "localizedFirstName,localizedLastName"},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                name = f"{data.get('localizedFirstName', '')} {data.get('localizedLastName', '')}".strip()
                self._name_cache[person_urn] = name or person_urn
                return self._name_cache[person_urn]
        except Exception:
            pass
        self._name_cache[person_urn] = person_urn
        return person_urn

    @staticmethod
    def parse_post_url(url_or_urn: str) -> str:
        """Extract the activity URN from a LinkedIn post URL or pass through a URN."""
        if url_or_urn.startswith("urn:li:"):
            return url_or_urn
        match = re.search(r"activity-(\d+)", url_or_urn)
        if match:
            return f"urn:li:activity:{match.group(1)}"
        raise ValueError(f"Cannot parse activity URN from: {url_or_urn!r}")

    @staticmethod
    def format_timestamp(ms: int) -> str:
        """Convert LinkedIn epoch-milliseconds to a human-readable string."""
        try:
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
        except Exception:
            return str(ms)

    @staticmethod
    def extract_post_text(post: dict) -> str:
        """Pull the plain-text body from a UGC post element."""
        content = post.get("specificContent", {})
        share = content.get("com.linkedin.ugc.ShareContent", {})
        return share.get("shareCommentary", {}).get("text", "")

    @staticmethod
    def extract_comment_text(comment: dict) -> str:
        """Pull the plain-text body from a comment element."""
        return comment.get("message", {}).get("text", "")


def build_linkedin_service() -> LinkedInService:
    """Convenience factory used by main.py."""
    import os
    client_id = os.getenv("LINKEDIN_CLIENT_ID", "").strip()
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "").strip()
    redirect_port = int(os.getenv("LINKEDIN_REDIRECT_PORT", "8080"))
    return LinkedInService(
        client_id=client_id,
        client_secret=client_secret,
        redirect_port=redirect_port,
    )
