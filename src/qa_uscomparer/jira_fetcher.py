"""Jira issue fetcher: MCP-first with Jira REST API v3 fallback.

Flow
----
1. Open an ``AtlassianMCPClient`` session and call ``jira_get_issue``.
2. If that fails (auth error, network, unsupported server), fall back to
   a direct ``httpx`` call against the Jira REST API v3.
3. Normalise the raw API response into a flat ``{field: value}`` dict so
   the comparator can work with a consistent structure.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from .mcp_client import AtlassianMCPClient

logger = logging.getLogger(__name__)

# ── Fields requested from Jira ──────────────────────────────────────────────
# Add any custom field IDs your instance uses (e.g. customfield_10030).
JIRA_FIELDS = [
    "summary",
    "description",
    "issuetype",
    "status",
    "priority",
    "assignee",
    "reporter",
    "labels",
    "components",
    "fixVersions",
    "versions",           # Affects Versions
    "customfield_10016",  # Story Points  (Jira Cloud)
    "customfield_10028",  # Story Points  (Jira DC / next-gen)
    "customfield_10014",  # Epic Link
    "customfield_10020",  # Sprint
    "duedate",
    "created",
    "updated",
    "comment",
    "subtasks",
    "parent",
    "project",
    "resolution",
    "resolutiondate",
    "environment",
]


class JiraFetcher:
    """Fetches and normalises Jira issue data.

    Parameters
    ----------
    token:
        Atlassian API token (Cloud) or Personal Access Token (DC/Server).
    email:
        Atlassian account email – required for Jira Cloud Basic auth.
        Leave ``None`` for Jira DC/Server Bearer auth.
    mcp_base_url:
        Base URL of the Atlassian Remote MCP server.
    jira_base_url:
        Base URL of the Jira instance used as REST API fallback.
    """

    def __init__(
        self,
        token: str,
        email: str | None,
        mcp_base_url: str,
        jira_base_url: str | None,
    ) -> None:
        self.token = token
        self.email = email
        self.mcp_base_url = mcp_base_url
        self.jira_base_url = jira_base_url

    async def fetch_issue(self, issue_key: str) -> dict[str, Any]:
        """Fetch a Jira issue, preferring MCP with REST API fallback."""
        try:
            logger.debug("Attempting MCP fetch for %s", issue_key)
            return await self._fetch_via_mcp(issue_key)
        except Exception as mcp_err:
            logger.warning(
                "MCP fetch failed for %s (%s). Trying REST API fallback.", issue_key, mcp_err
            )
            if not self.jira_base_url:
                raise RuntimeError(
                    f"MCP connection failed and no --jira-url / JIRA_BASE_URL is set "
                    f"to use the REST API fallback.\nMCP error: {mcp_err}"
                ) from mcp_err
            return await self._fetch_via_rest(issue_key)

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _fetch_via_mcp(self, issue_key: str) -> dict[str, Any]:
        async with AtlassianMCPClient(
            base_url=self.mcp_base_url,
            token=self.token,
            email=self.email,
        ) as client:
            content = await client.call_tool(
                "jira_get_issue",
                {"issueIdOrKey": issue_key, "fields": JIRA_FIELDS},
            )

        # content is a list of TextContent / ImageContent objects.
        # The Atlassian MCP server returns JSON text inside TextContent.
        if not content:
            raise ValueError(f"Empty response from MCP for issue {issue_key!r}")

        raw_text = content[0].text  # type: ignore[union-attr]
        data: dict[str, Any] = json.loads(raw_text) if isinstance(raw_text, str) else raw_text
        return _normalise_issue(data)

    async def _fetch_via_rest(self, issue_key: str) -> dict[str, Any]:
        """Direct Jira REST API v3 call."""
        base = (self.jira_base_url or "").rstrip("/")
        url = f"{base}/rest/api/3/issue/{issue_key}"
        params = {
            "fields": ",".join(JIRA_FIELDS),
            "expand": "names,renderedFields",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                url, headers=self._rest_auth_headers(), params=params
            )
        if response.status_code == 401:
            raise RuntimeError(
                "Authentication failed (401). Check your token and email."
            )
        if response.status_code == 404:
            raise RuntimeError(
                f"Issue {issue_key!r} not found (404). "
                "Check the issue key and that your account has access."
            )
        response.raise_for_status()
        return _normalise_issue(response.json())

    def _rest_auth_headers(self) -> dict[str, str]:
        if self.email:
            credentials = base64.b64encode(
                f"{self.email}:{self.token}".encode()
            ).decode()
            return {"Authorization": f"Basic {credentials}", "Accept": "application/json"}
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise_issue(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Jira REST API / MCP response into a simple ``{field: value}`` dict."""
    if not raw:
        return {}

    fields: dict[str, Any] = raw.get("fields", raw)
    result: dict[str, Any] = {
        "key": raw.get("key", ""),
        "id": raw.get("id", ""),
        "self": raw.get("self", ""),
    }

    for field_name, field_value in fields.items():
        if field_name == "description":
            # Atlassian Document Format → plain text
            result[field_name] = _adf_to_text(field_value)
        elif field_name == "comment":
            comments = (
                field_value.get("comments", []) if isinstance(field_value, dict) else []
            )
            result[field_name] = [
                {
                    "author": _resolve(c.get("author")),
                    "body": _adf_to_text(c.get("body")),
                    "created": c.get("created"),
                }
                for c in comments
            ]
        else:
            result[field_name] = _resolve(field_value)

    return result


def _resolve(value: Any) -> Any:
    """Recursively reduce Jira nested objects to their human-readable values."""
    if isinstance(value, dict):
        return (
            value.get("displayName")
            or value.get("name")
            or value.get("value")
            or value.get("accountId")
            or str(value)
        )
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    return value


def _adf_to_text(node: Any, _depth: int = 0) -> str:
    """Recursively convert Atlassian Document Format (ADF) to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        node_type = node.get("type", "")
        if node_type == "text":
            return node.get("text", "")
        children = node.get("content", [])
        block_types = {
            "paragraph", "heading", "bulletList", "orderedList",
            "listItem", "blockquote", "codeBlock", "rule",
        }
        sep = "\n" if node_type in block_types else ""
        return sep.join(_adf_to_text(c, _depth + 1) for c in children)
    if isinstance(node, list):
        return "\n".join(_adf_to_text(n, _depth) for n in node)
    return str(node)
