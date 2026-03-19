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
from urllib.parse import urlsplit
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
        self.jira_base_url = _normalise_jira_base_url(jira_base_url)
        self._mcp_unavailable = False

    async def fetch_issue(self, issue_key: str) -> dict[str, Any]:
        """Fetch a Jira issue, preferring MCP with REST API fallback."""
        if not self._mcp_unavailable:
            try:
                logger.debug("Attempting MCP fetch for %s", issue_key)
                return await self._fetch_via_mcp(issue_key)
            except Exception as mcp_err:
                if "does not expose a Jira issue tool" in str(mcp_err):
                    self._mcp_unavailable = True
                    logger.info(
                        "MCP does not expose Jira issue tools. Using REST API fallback for %s.",
                        issue_key,
                    )
                else:
                    logger.warning(
                        "MCP fetch failed for %s (%s). Trying REST API fallback.", issue_key, mcp_err
                    )
                if not self.jira_base_url:
                    raise RuntimeError(
                        f"MCP connection failed and no --jira-url / JIRA_BASE_URL is set "
                        f"to use the REST API fallback.\nMCP error: {mcp_err}"
                    ) from mcp_err
                return await self._fetch_via_rest(issue_key)

        logger.debug("Skipping MCP for %s because Jira issue tool is unavailable.", issue_key)
        if not self.jira_base_url:
            raise RuntimeError(
                "MCP Jira issue tool is unavailable and no --jira-url / JIRA_BASE_URL is set "
                "to use the REST API fallback."
            )
        return await self._fetch_via_rest(issue_key)

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _fetch_via_mcp(self, issue_key: str) -> dict[str, Any]:
        async with AtlassianMCPClient(
            base_url=self.mcp_base_url,
            token=self.token,
            email=self.email,
        ) as client:
            tool_name = await _resolve_mcp_issue_tool(client)
            content = await client.call_tool(
                tool_name,
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
        params = {
            "fields": ",".join(JIRA_FIELDS),
            "expand": "names,renderedFields",
        }
        candidate_urls = [
            f"{base}/rest/api/3/issue/{issue_key}",
            f"{base}/rest/api/2/issue/{issue_key}",
        ]

        response: httpx.Response | None = None
        async with httpx.AsyncClient(timeout=30) as client:
            for idx, url in enumerate(candidate_urls):
                response = await client.get(
                    url,
                    headers=self._rest_auth_headers(),
                    params=params,
                )
                # Some Jira setups reject Basic auth even when email is provided.
                # Retry once with Bearer if initial request returns 401.
                if response.status_code == 401 and self.email:
                    response = await client.get(
                        url,
                        headers=self._rest_auth_headers(force_bearer=True),
                        params=params,
                    )
                # If v3 is unavailable on Server/DC, retry with v2.
                if idx == 0 and response.status_code in {400, 404, 405}:
                    continue
                # Some Server/DC instances redirect /rest/api/3 to login even with valid PAT.
                # In that case, try /rest/api/2 before surfacing an auth error.
                if idx == 0 and response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "")
                    if "login" in location.lower():
                        continue
                break

        if response is None:
            raise RuntimeError("Unexpected Jira REST error: no response received.")
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location", "")
            if "login" in location.lower():
                raise RuntimeError(
                    "Authentication failed (redirected to login). "
                    "Check token type and email usage: Jira Cloud requires email+API token; "
                    "Jira Data Center/Server requires PAT without email."
                )
            raise RuntimeError(
                "Unexpected redirect from Jira REST API. "
                "Ensure JIRA_BASE_URL points to the Jira host root (e.g. https://org.atlassian.net), "
                "not to /browse or another subpath."
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

    def _rest_auth_headers(self, force_bearer: bool = False) -> dict[str, str]:
        if self.email and not force_bearer:
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
            # ADF (JSON dict) → plain text; HTML string (REST v2) → stripped plain text
            result[field_name] = _adf_to_text(field_value)
        elif field_name == "comment":
            comments = (
                field_value.get("comments", []) if isinstance(field_value, dict) else []
            )
            # Format as readable strings: "Author: body (date)"
            result[field_name] = [
                f"{_resolve(c.get('author'))}: {_adf_to_text(c.get('body'))} ({c.get('created', '')})"
                for c in comments
            ]
        elif field_name == "subtasks":
            if isinstance(field_value, list):
                result[field_name] = [
                    _issue_ref(s) for s in field_value
                ]
            else:
                result[field_name] = _resolve(field_value)
        elif field_name == "parent":
            result[field_name] = _issue_ref(field_value) if isinstance(field_value, dict) else _resolve(field_value)
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


def _issue_ref(issue: Any) -> str:
    """Convert a Jira issue dict (subtask / parent) to 'KEY: Summary'."""
    if not isinstance(issue, dict):
        return str(issue)
    key = issue.get("key", "")
    fields = issue.get("fields", {})
    summary = ""
    if isinstance(fields, dict):
        summary = fields.get("summary", "")
    if not summary:
        summary = _resolve(issue) or ""
    return f"{key}: {summary}".strip(": ")


def _adf_to_text(node: Any, _depth: int = 0) -> str:
    """Recursively convert Atlassian Document Format (ADF) OR HTML string to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        # REST API v2 returns raw HTML — strip it to plain text
        if "<" in node:
            return _strip_html(node)
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


async def _resolve_mcp_issue_tool(client: AtlassianMCPClient) -> str:
    """Pick a Jira issue tool name supported by the connected MCP server."""
    tools = await client.list_tools()
    preferred_tools = (
        "jira_get_issue",
        "jira.getIssue",
        "getJiraIssue",
    )
    for candidate in preferred_tools:
        if candidate in tools:
            return candidate
    raise RuntimeError(
        "Connected MCP server does not expose a Jira issue tool. "
        f"Available tools: {', '.join(tools) or 'none'}"
    )


def _strip_html(raw: str) -> str:
    """Convert an HTML string to plain text (used for Jira DC/Server descriptions)."""
    import html as _html
    import re as _re
    # Block-level tags → newline
    text = _re.sub(r"<br\s*/?>", "\n", raw, flags=_re.IGNORECASE)
    text = _re.sub(r"</?(p|li|h\d|pre|div|ul|ol|blockquote)[^>]*>", "\n", text, flags=_re.IGNORECASE)
    # Strip remaining tags
    text = _re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = text.replace("\xa0", " ").replace("\r", "\n")
    # Collapse whitespace
    text = _re.sub(r" {2,}", " ", text)
    text = _re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _normalise_jira_base_url(jira_base_url: str | None) -> str | None:
    """Normalise Jira base URL to host root and strip common UI paths like /browse."""
    if not jira_base_url:
        return jira_base_url

    stripped = jira_base_url.strip().rstrip("/")
    if not stripped:
        return None

    parsed = urlsplit(stripped)
    path = parsed.path.rstrip("/")
    if path.startswith("/browse"):
        path = ""

    if not parsed.scheme or not parsed.netloc:
        return stripped

    return f"{parsed.scheme}://{parsed.netloc}{path}"
