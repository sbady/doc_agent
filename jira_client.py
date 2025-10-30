from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import json

import requests

logger = logging.getLogger(__name__)


class JiraClient:
    """Client for retrieving Jira issues via REST API."""

    def __init__(
        self,
        base_url: str,
        email: Optional[str],
        api_token: str,
        auth_type: str = "basic",
        api_version: str = "3",
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._auth_type = auth_type
        self._api_version = api_version

        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

        if auth_type == "basic":
            if not email:
                raise ValueError("Jira email is required when using basic authentication")
            self._session.auth = (email, api_token)
        elif auth_type == "pat":
            self._session.headers.update({"Authorization": f"Bearer {api_token}"})
        else:
            raise ValueError(f"Unsupported Jira auth type: {auth_type}")

        # Informational log about Jira connectivity settings (no secrets)
        logger.info(
            "Connecting to Jira: base_url=%s, auth=%s, api_version=%s, timeout=%ss",
            self._base_url,
            self._auth_type,
            self._api_version,
            self._timeout,
        )

    def get_issue_data(self, issue_key: str) -> Dict[str, Any]:
        """Fetch issue fields required for the summary prompt."""
        version_segment = self._api_version or "3"
        url = f"{self._base_url}/rest/api/{version_segment}/issue/{issue_key}"
        params = {"fields": "summary,description,comment"}

        logger.debug("Requesting issue %s from %s", issue_key, url)
        response = self._session.get(url, params=params, timeout=self._timeout)

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body_preview = response.text[:200]
            logger.error("Jira API returned error for %s: %s | Body: %s", issue_key, exc, body_preview)
            raise

        try:
            payload = response.json()
        except ValueError as exc:
            logger.error("Failed to decode Jira response for %s: %s | Body: %s", issue_key, exc, response.text[:200])
            raise
        # Log full raw JSON at DEBUG so users can inspect entire object
        if logger.isEnabledFor(logging.DEBUG):
            try:
                logger.debug("Jira raw response JSON: %s", json.dumps(payload, ensure_ascii=False))
            except Exception:
                # Fallback to raw text if JSON dump fails
                logger.debug("Jira raw response (text): %s", response.text)
        fields: Dict[str, Any] = payload.get("fields", {})

        title = fields.get("summary") or ""
        description_raw = fields.get("description")
        comments_raw = fields.get("comment", {}).get("comments", [])

        issue_data = {
            "title": title.strip(),
            "description": self._extract_text(description_raw),
            "comments": self._extract_comments(comments_raw),
        }

        # Log concise details about fetched issue
        desc = issue_data.get("description", "")
        comments = issue_data.get("comments", []) or []
        logger.info(
            "Fetched Jira issue %s: title='%s' | description_chars=%d | comments=%d",
            issue_key,
            (issue_data.get("title", "") or "").strip(),
            len(desc),
            len(comments),
        )
        # Debug previews to aid troubleshooting without flooding INFO
        if logger.isEnabledFor(logging.DEBUG):
            preview_desc = (desc[:400] + "…") if len(desc) > 400 else desc
            first_comment = comments[0] if comments else ""
            preview_comment = (first_comment[:200] + "…") if len(first_comment) > 200 else first_comment
            logger.debug("Description preview: %s", preview_desc)
            if comments:
                logger.debug("First comment preview: %s", preview_comment)
            # Also log full constructed payload for the prompt
            try:
                logger.debug(
                    "Issue payload for prompt (full): %s",
                    json.dumps(issue_data, ensure_ascii=False),
                )
            except Exception:
                logger.debug("Issue payload (repr): %r", issue_data)
        return issue_data

    # Write API: update description (Server/DC wiki markup). For Cloud ADF, this won't work.
    def update_issue_description(self, issue_key: str, description: str) -> None:
        version_segment = self._api_version or "3"
        url = f"{self._base_url}/rest/api/{version_segment}/issue/{issue_key}"
        payload = {"fields": {"description": description}}
        logger.info("Updating description for %s (length=%d)", issue_key, len(description or ""))
        response = self._session.put(url, json=payload, timeout=self._timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("Failed to update %s: %s | Body: %s", issue_key, exc, response.text[:300])
            raise

    def _extract_comments(self, comments: List[Dict[str, Any]]) -> List[str]:
        extracted: List[str] = []
        for comment in comments:
            text = self._extract_text(comment.get("body"))
            if text:
                extracted.append(text)
        return extracted

    def _extract_text(self, value: Any) -> str:
        """Convert Jira field value into plain text."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return self._extract_text_from_adf(value).strip()
        if isinstance(value, list):
            parts = [self._extract_text(item) for item in value]
            return "\n".join(filter(None, parts)).strip()
        return str(value).strip()

    def _extract_text_from_adf(self, node: Dict[str, Any]) -> str:
        node_type = node.get("type")
        content = node.get("content", [])

        if node_type == "text":
            return node.get("text", "")

        if node_type in {"paragraph", "expand", "blockquote"}:
            parts = [self._extract_text(child) for child in content]
            return " ".join(filter(None, parts))

        if node_type == "bulletList":
            lines = []
            for child in content:
                child_text = self._extract_text(child)
                if child_text:
                    lines.append(f"- {child_text}")
            return "\n".join(lines)

        if node_type == "orderedList":
            lines = []
            for index, child in enumerate(content, start=1):
                child_text = self._extract_text(child)
                if child_text:
                    lines.append(f"{index}. {child_text}")
            return "\n".join(lines)

        if node_type == "listItem":
            parts = [self._extract_text(child) for child in content]
            return " ".join(filter(None, parts))

        if node_type == "heading":
            parts = [self._extract_text(child) for child in content]
            return " ".join(filter(None, parts))

        if node_type == "codeBlock":
            text = "\n".join(child.get("text", "") for child in content if isinstance(child, dict))
            return f"`{text}`" if text else ""

        if node_type == "hardBreak":
            return "\n"

        # Fallback to flatten nested content.
        if isinstance(content, list):
            parts = [self._extract_text(child) for child in content]
            return " ".join(filter(None, parts))

        return ""
