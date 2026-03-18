"""
Buffer GraphQL API Service
Handles all communication with Buffer's beta GraphQL API.
Endpoint: https://api.buffer.com
Docs: https://developers.buffer.com
"""

import requests
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

BUFFER_API = "https://api.buffer.com"


class BufferService:

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("BUFFER_API_KEY is required. Get it from: https://publish.buffer.com/settings/api")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def _query(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query/mutation against Buffer API."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        response = requests.post(BUFFER_API, headers=self.headers, json=payload)
        if not response.ok:
            logger.error(f"Buffer API {response.status_code}: {response.text}")
            response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise RuntimeError(f"Buffer API error: {data['errors']}")
        return data.get("data", {})

    def get_organization_id(self) -> str:
        """Return the first organization ID from the account."""
        query = """
        query GetOrg {
          account {
            organizations {
              id
            }
          }
        }
        """
        data = self._query(query)
        orgs = data.get("account", {}).get("organizations", [])
        if not orgs:
            raise RuntimeError("No organizations found in Buffer account.")
        return orgs[0]["id"]

    def get_channels(self) -> list:
        """Get all connected social channels."""
        query = """
        query GetChannels {
          account {
            organizations {
              channels {
                id
                name
                service
              }
            }
          }
        }
        """
        data = self._query(query)
        channels = []
        for org in data.get("account", {}).get("organizations", []):
            channels.extend(org.get("channels", []))
        return channels

    def get_linkedin_channel_id(self) -> Optional[str]:
        """Find the LinkedIn personal profile channel ID."""
        channels = self.get_channels()
        for ch in channels:
            if ch.get("service") == "linkedin":
                logger.info(f"Found LinkedIn channel: {ch['name']} (id: {ch['id']})")
                return ch["id"]
        raise RuntimeError("No LinkedIn channel found in Buffer. Connect your LinkedIn profile first.")

    def get_x_channel_id(self) -> Optional[str]:
        """Find the X (Twitter) channel ID."""
        channels = self.get_channels()
        for ch in channels:
            if ch.get("service") == "twitter":
                logger.info(f"Found X channel: {ch['name']} (id: {ch['id']})")
                return ch["id"]
        raise RuntimeError("No X channel found in Buffer. Connect your X profile first.")

    def get_bluesky_channel_id(self) -> Optional[str]:
        """Find the Bluesky channel ID."""
        channels = self.get_channels()
        for ch in channels:
            if ch.get("service") == "bluesky":
                logger.info(f"Found Bluesky channel: {ch['name']} (id: {ch['id']})")
                return ch["id"]
        raise RuntimeError("No Bluesky channel found in Buffer. Connect your Bluesky profile first.")

    def create_post(self, channel_id: str, text: str, scheduled_at: Optional[str] = None) -> dict:
        """
        Create a post in Buffer.
        scheduled_at: ISO 8601 datetime string e.g. '2026-03-18T16:00:00Z'
                      If None, adds to next available queue slot.
        """
        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post {
                id
                text
                status
              }
            }
            ... on MutationError {
              message
            }
          }
        }
        """
        variables = {
            "input": {
                "channelId": channel_id,
                "text": text,
                **({"scheduledAt": scheduled_at} if scheduled_at else {})
            }
        }
        data = self._query(mutation, variables)
        result = data.get("createPost", {})
        if "message" in result:
            raise RuntimeError(f"Buffer createPost error: {result['message']}")
        post = result.get("post", {})
        logger.info(f"Post created: id={post.get('id')} status={post.get('status')}")
        return post

    def create_scheduled_post(
        self,
        channel_id: str,
        text: str,
        thread: Optional[list[str]] = None,
        first_comment: Optional[str] = None,
        channel: str = "linkedin",
    ) -> dict:
        """
        Schedule a post to the next available Buffer queue slot.
        channel: 'linkedin' | 'x' | 'bluesky' — used to route thread into the
                 correct service metadata (metadata.twitter.thread or metadata.bluesky.thread).
        thread: additional posts in the thread (X/Bluesky) — each item is the text of one reply post.
        first_comment: LinkedIn first comment text (placed in metadata.linkedin.firstComment).
        """
        mutation = """
        mutation CreateScheduledPost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post {
                id
                text
                status
              }
            }
            ... on MutationError {
              message
            }
          }
        }
        """
        # Hard-enforce per-platform character limits (LLMs don't always comply with the prompt).
        # X: 280 chars total; a Buffer-appended URL counts as 23 chars, so cap text at 257.
        # Bluesky: 300 chars total; same URL accounting → cap text at 277.
        # Thread reply items never get a URL appended, so they use the full platform limit.
        if channel == "x":
            text_limit, reply_limit = 257, 280
        elif channel == "bluesky":
            text_limit, reply_limit = 277, 300
        else:
            text_limit, reply_limit = None, None  # LinkedIn — no hard limit enforced here

        def _cap(s: str, limit: int) -> str:
            if len(s) <= limit:
                return s
            truncated = s[:limit].rsplit(" ", 1)[0]
            logger.warning(f"Truncated post from {len(s)} to {len(truncated)} chars (limit {limit})")
            return truncated

        if text_limit:
            text = _cap(text, text_limit)
        if thread and reply_limit:
            thread = [_cap(t, reply_limit) for t in thread]

        post_input: dict = {
            "channelId": channel_id,
            "text": text,
            "schedulingType": "automatic",
            "mode": "addToQueue",
        }
        metadata: dict = {}
        if thread:
            threaded = [{"text": t} for t in thread]
            if channel == "x":
                metadata["twitter"] = {"thread": threaded}
            elif channel == "bluesky":
                metadata["bluesky"] = {"thread": threaded}
        if first_comment:
            metadata["linkedin"] = {"firstComment": first_comment}
        if metadata:
            post_input["metadata"] = metadata

        data = self._query(mutation, {"input": post_input})
        result = data.get("createPost", {})
        if "message" in result:
            raise RuntimeError(f"Buffer createPost error: {result['message']}")
        post = result.get("post", {})
        logger.info(f"Scheduled post: id={post.get('id')} status={post.get('status')}")
        return post

    def create_idea(self, text: str, title: str = "") -> dict:
        """
        Create a draft idea in Buffer (for review before scheduling).
        Ideas show up in Buffer's Ideas board for manual review.
        """
        org_id = self.get_organization_id()
        mutation = """
        mutation CreateIdea($input: CreateIdeaInput!) {
          createIdea(input: $input) {
            ... on Idea {
              id
              content {
                title
                text
              }
            }
          }
        }
        """
        content: dict = {"text": text}
        if title:
            content["title"] = title
        variables = {
            "input": {
                "organizationId": org_id,
                "content": content,
            }
        }
        data = self._query(mutation, variables)
        idea = data.get("createIdea", {})
        logger.info(f"Idea created: id={idea.get('id')}")
        return idea

    def get_scheduled_posts(self, channel_id: str) -> list:
        """Get all pending scheduled posts for a channel."""
        query = """
        query GetScheduledPosts($channelId: String!) {
          channel(id: $channelId) {
            posts(status: scheduled) {
              edges {
                node {
                  id
                  text
                  dueAt
                  status
                }
              }
            }
          }
        }
        """
        data = self._query(query, {"channelId": channel_id})
        edges = data.get("channel", {}).get("posts", {}).get("edges", [])
        return [e["node"] for e in edges]
