"""Atlassian Remote MCP – async SSE client wrapper.

Connects to the Atlassian Remote MCP server (https://mcp.atlassian.com/v1/sse)
using the official `mcp` Python SDK and exposes a simple `call_tool()` interface.

Authentication
--------------
* **Jira Cloud** – Basic auth (base64(email:api_token)).
* **Jira Data Center / Server** – Bearer PAT (email must be omitted).
"""

from __future__ import annotations

import base64
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import CallToolResult

logger = logging.getLogger(__name__)


class AtlassianMCPClient:
    """Async context manager wrapping an MCP ClientSession for Atlassian.

    Usage::

        async with AtlassianMCPClient(mcp_url, token, email) as client:
            content = await client.call_tool("jira_get_issue", {"issueIdOrKey": "PROJ-1"})
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        email: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.email = email
        self._session: ClientSession | None = None
        self._exit_stack = AsyncExitStack()

    # ── Auth ────────────────────────────────────────────────────────────────

    def _build_auth_headers(self) -> dict[str, str]:
        if self.email:
            # Jira Cloud: Basic auth  email:api_token
            credentials = base64.b64encode(
                f"{self.email}:{self.token}".encode()
            ).decode()
            return {"Authorization": f"Basic {credentials}"}
        # Jira DC / Server: Bearer personal access token
        return {"Authorization": f"Bearer {self.token}"}

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def __aenter__(self) -> "AtlassianMCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Open the SSE transport and initialise the MCP session."""
        headers = self._build_auth_headers()
        endpoint = f"{self.base_url}/v1/sse"
        logger.debug("Connecting to Atlassian MCP endpoint: %s", endpoint)

        read, write = await self._exit_stack.enter_async_context(
            sse_client(endpoint, headers=headers)
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        logger.debug("MCP session initialised successfully.")

    async def disconnect(self) -> None:
        """Close the MCP session and SSE transport."""
        await self._exit_stack.aclose()

    # ── Tool calls ──────────────────────────────────────────────────────────

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> list[Any]:
        """Call an MCP tool and return its content list.

        Raises
        ------
        RuntimeError
            If not connected or if the tool returned an error result.
        """
        if self._session is None:
            raise RuntimeError(
                "Not connected. Use 'async with AtlassianMCPClient(...)' or call connect() first."
            )
        logger.debug("MCP call_tool %r  args=%r", tool_name, arguments)
        result: CallToolResult = await self._session.call_tool(tool_name, arguments)
        if result.isError:
            raise RuntimeError(
                f"MCP tool {tool_name!r} returned an error: {result.content}"
            )
        return result.content

    async def list_tools(self) -> list[str]:
        """Return the names of all tools exposed by the MCP server."""
        if self._session is None:
            raise RuntimeError("Not connected.")
        response = await self._session.list_tools()
        return [t.name for t in response.tools]
