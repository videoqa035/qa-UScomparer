"""Tests for qa_uscomparer.jira_fetcher module (normalisation + REST fallback)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qa_uscomparer.jira_fetcher import (
    JiraFetcher,
    _adf_to_text,
    _normalise_jira_base_url,
    _normalise_issue,
    _resolve,
)


# ── _adf_to_text ─────────────────────────────────────────────────────────────

class TestAdfToText:
    def test_none_returns_empty(self):
        assert _adf_to_text(None) == ""

    def test_plain_string_passthrough(self):
        assert _adf_to_text("hello") == "hello"

    def test_simple_text_node(self):
        node = {"type": "text", "text": "Hello world"}
        assert _adf_to_text(node) == "Hello world"

    def test_paragraph_node(self):
        node = {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Line one"}],
        }
        assert _adf_to_text(node) == "Line one"

    def test_nested_structure(self):
        node = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "First"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Second"}],
                },
            ],
        }
        result = _adf_to_text(node)
        assert "First" in result
        assert "Second" in result

    def test_list_of_nodes(self):
        nodes = [
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
        ]
        assert _adf_to_text(nodes) == "a\nb"


# ── _resolve ─────────────────────────────────────────────────────────────────

class TestResolve:
    def test_none_passthrough(self):
        assert _resolve(None) is None

    def test_string_passthrough(self):
        assert _resolve("hello") == "hello"

    def test_dict_with_display_name(self):
        assert _resolve({"displayName": "John Doe", "accountId": "abc"}) == "John Doe"

    def test_dict_with_name(self):
        assert _resolve({"name": "High", "id": "2"}) == "High"

    def test_dict_with_value(self):
        assert _resolve({"value": "Done"}) == "Done"

    def test_list_of_dicts(self):
        result = _resolve([{"name": "Frontend"}, {"name": "Mobile"}])
        assert result == ["Frontend", "Mobile"]

    def test_scalar_passthrough(self):
        assert _resolve(42) == 42


# ── _normalise_issue ─────────────────────────────────────────────────────────

class TestNormaliseIssue:
    def _raw_issue(self, **extra_fields):
        base = {
            "id":   "10001",
            "key":  "PROJ-1",
            "self": "https://org.atlassian.net/rest/api/3/issue/10001",
            "fields": {
                "summary":    "Test summary",
                "issuetype":  {"name": "Bug", "id": "1"},
                "status":     {"name": "Open", "id": "1"},
                "description": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Desc text"}],
                        }
                    ],
                },
                **extra_fields,
            },
        }
        return base

    def test_top_level_fields_extracted(self):
        norm = _normalise_issue(self._raw_issue())
        assert norm["key"] == "PROJ-1"
        assert norm["id"] == "10001"

    def test_summary_preserved(self):
        norm = _normalise_issue(self._raw_issue())
        assert norm["summary"] == "Test summary"

    def test_description_converted_to_text(self):
        norm = _normalise_issue(self._raw_issue())
        assert isinstance(norm["description"], str)
        assert "Desc text" in norm["description"]

    def test_issuetype_resolved(self):
        norm = _normalise_issue(self._raw_issue())
        assert norm["issuetype"] == "Bug"

    def test_empty_dict_returns_empty(self):
        assert _normalise_issue({}) == {}

    def test_comments_normalised(self):
        raw = self._raw_issue(
            comment={
                "comments": [
                    {
                        "author": {"displayName": "John"},
                        "body": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "A comment"}]}]},
                        "created": "2026-03-01T09:00:00.000Z",
                    }
                ]
            }
        )
        norm = _normalise_issue(raw)
        assert isinstance(norm["comment"], list)
        # New format: "Author: body (date)"
        assert norm["comment"][0].startswith("John:")
        assert "A comment" in norm["comment"][0]


# ── JiraFetcher ───────────────────────────────────────────────────────────────

class TestJiraFetcher:
    def _make_fetcher(self, jira_url="https://org.atlassian.net"):
        return JiraFetcher(
            token="fake-token",
            email="user@org.com",
            mcp_base_url="https://mcp.atlassian.com",
            jira_base_url=jira_url,
        )

    @pytest.mark.asyncio
    async def test_fetch_via_mcp_success(self):
        fetcher = self._make_fetcher()
        mock_content = MagicMock()
        mock_content.text = '{"id": "1", "key": "PROJ-1", "fields": {"summary": "MCP ticket"}}'

        with patch("qa_uscomparer.jira_fetcher.AtlassianMCPClient") as MockClient:
            instance = AsyncMock()
            instance.list_tools.return_value = ["jira_get_issue"]
            instance.call_tool.return_value = [mock_content]
            MockClient.return_value.__aenter__.return_value = instance
            MockClient.return_value.__aexit__.return_value = None

            result = await fetcher.fetch_issue("PROJ-1")

        assert result["key"] == "PROJ-1"
        assert result["summary"] == "MCP ticket"

    @pytest.mark.asyncio
    async def test_fetch_falls_back_to_rest_on_mcp_error(self):
        fetcher = self._make_fetcher()
        fake_response_json = {
            "id": "10001",
            "key": "PROJ-1",
            "self": "https://org.atlassian.net/rest/api/3/issue/10001",
            "fields": {
                "summary": "REST fallback ticket",
                "issuetype": {"name": "Story"},
                "status": {"name": "Open"},
                "description": None,
            },
        }

        with patch("qa_uscomparer.jira_fetcher.AtlassianMCPClient") as MockClient:
            instance = AsyncMock()
            instance.list_tools.return_value = ["jira_get_issue"]
            instance.call_tool.side_effect = RuntimeError("MCP unreachable")
            MockClient.return_value.__aenter__.return_value = instance
            MockClient.return_value.__aexit__.return_value = None

            with patch("httpx.AsyncClient") as MockHttpx:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = fake_response_json
                mock_response.raise_for_status = MagicMock()
                http_instance = AsyncMock()
                http_instance.get.return_value = mock_response
                MockHttpx.return_value.__aenter__.return_value = http_instance
                MockHttpx.return_value.__aexit__.return_value = None

                result = await fetcher.fetch_issue("PROJ-1")

        assert result["key"] == "PROJ-1"
        assert result["summary"] == "REST fallback ticket"

    @pytest.mark.asyncio
    async def test_fetch_raises_when_no_jira_url_and_mcp_fails(self):
        fetcher = self._make_fetcher(jira_url=None)

        with patch("qa_uscomparer.jira_fetcher.AtlassianMCPClient") as MockClient:
            instance = AsyncMock()
            instance.list_tools.return_value = ["jira_get_issue"]
            instance.call_tool.side_effect = RuntimeError("MCP unreachable")
            MockClient.return_value.__aenter__.return_value = instance
            MockClient.return_value.__aexit__.return_value = None

            with pytest.raises(RuntimeError, match="JIRA_BASE_URL"):
                await fetcher.fetch_issue("PROJ-1")

    @pytest.mark.asyncio
    async def test_fetch_falls_back_when_mcp_has_no_jira_issue_tool(self):
        fetcher = self._make_fetcher()
        fake_response_json = {
            "id": "10001",
            "key": "PROJ-1",
            "self": "https://org.atlassian.net/rest/api/3/issue/10001",
            "fields": {
                "summary": "REST fallback ticket",
                "issuetype": {"name": "Story"},
                "status": {"name": "Open"},
                "description": None,
            },
        }

        with patch("qa_uscomparer.jira_fetcher.AtlassianMCPClient") as MockClient:
            instance = AsyncMock()
            instance.list_tools.return_value = ["getTeamworkGraphContext"]
            MockClient.return_value.__aenter__.return_value = instance
            MockClient.return_value.__aexit__.return_value = None

            with patch("httpx.AsyncClient") as MockHttpx:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = fake_response_json
                mock_response.raise_for_status = MagicMock()
                http_instance = AsyncMock()
                http_instance.get.return_value = mock_response
                MockHttpx.return_value.__aenter__.return_value = http_instance
                MockHttpx.return_value.__aexit__.return_value = None

                result = await fetcher.fetch_issue("PROJ-1")

        assert result["key"] == "PROJ-1"
        assert result["summary"] == "REST fallback ticket"

    @pytest.mark.asyncio
    async def test_fetch_skips_mcp_after_tool_unavailable_once(self):
        fetcher = self._make_fetcher()
        fake_response_json = {
            "id": "10001",
            "key": "PROJ-1",
            "self": "https://org.atlassian.net/rest/api/3/issue/10001",
            "fields": {
                "summary": "REST fallback ticket",
                "issuetype": {"name": "Story"},
                "status": {"name": "Open"},
                "description": None,
            },
        }

        with patch("qa_uscomparer.jira_fetcher.AtlassianMCPClient") as MockClient:
            instance = AsyncMock()
            instance.list_tools.return_value = ["getTeamworkGraphContext"]
            MockClient.return_value.__aenter__.return_value = instance
            MockClient.return_value.__aexit__.return_value = None

            with patch("httpx.AsyncClient") as MockHttpx:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = fake_response_json
                mock_response.raise_for_status = MagicMock()
                http_instance = AsyncMock()
                http_instance.get.return_value = mock_response
                MockHttpx.return_value.__aenter__.return_value = http_instance
                MockHttpx.return_value.__aexit__.return_value = None

                await fetcher.fetch_issue("PROJ-1")
                await fetcher.fetch_issue("PROJ-2")

        assert MockClient.call_count == 1

    @pytest.mark.asyncio
    async def test_rest_redirect_to_login_raises_auth_error(self):
        fetcher = self._make_fetcher(jira_url="https://jira.example.com")

        with patch("httpx.AsyncClient") as MockHttpx:
            mock_response = MagicMock()
            mock_response.status_code = 302
            mock_response.headers = {"location": "/login.jsp"}
            http_instance = AsyncMock()
            http_instance.get.return_value = mock_response
            MockHttpx.return_value.__aenter__.return_value = http_instance
            MockHttpx.return_value.__aexit__.return_value = None

            with pytest.raises(RuntimeError, match="redirected to login"):
                await fetcher._fetch_via_rest("PROJ-1")

    @pytest.mark.asyncio
    async def test_rest_retries_with_bearer_after_401(self):
        fetcher = self._make_fetcher(jira_url="https://jira.example.com")
        fake_response_json = {
            "id": "10001",
            "key": "PROJ-1",
            "self": "https://jira.example.com/rest/api/3/issue/10001",
            "fields": {
                "summary": "Recovered via bearer",
                "issuetype": {"name": "Task"},
                "status": {"name": "Open"},
                "description": None,
            },
        }

        with patch("httpx.AsyncClient") as MockHttpx:
            first_response = MagicMock()
            first_response.status_code = 401
            first_response.headers = {}

            second_response = MagicMock()
            second_response.status_code = 200
            second_response.headers = {}
            second_response.json.return_value = fake_response_json
            second_response.raise_for_status = MagicMock()

            http_instance = AsyncMock()
            http_instance.get.side_effect = [first_response, second_response]
            MockHttpx.return_value.__aenter__.return_value = http_instance
            MockHttpx.return_value.__aexit__.return_value = None

            result = await fetcher._fetch_via_rest("PROJ-1")

        assert result["summary"] == "Recovered via bearer"
        assert http_instance.get.await_count == 2

    @pytest.mark.asyncio
    async def test_rest_falls_back_to_api_v2_when_v3_unavailable(self):
        fetcher = self._make_fetcher(jira_url="https://jira.example.com")
        fake_response_json = {
            "id": "10001",
            "key": "PROJ-1",
            "self": "https://jira.example.com/rest/api/2/issue/10001",
            "fields": {
                "summary": "Fetched via api v2",
                "issuetype": {"name": "Task"},
                "status": {"name": "Open"},
                "description": None,
            },
        }

        with patch("httpx.AsyncClient") as MockHttpx:
            v3_response = MagicMock()
            v3_response.status_code = 404
            v3_response.headers = {}

            v2_response = MagicMock()
            v2_response.status_code = 200
            v2_response.headers = {}
            v2_response.json.return_value = fake_response_json
            v2_response.raise_for_status = MagicMock()

            http_instance = AsyncMock()
            http_instance.get.side_effect = [v3_response, v2_response]
            MockHttpx.return_value.__aenter__.return_value = http_instance
            MockHttpx.return_value.__aexit__.return_value = None

            result = await fetcher._fetch_via_rest("PROJ-1")

        assert result["summary"] == "Fetched via api v2"
        assert http_instance.get.await_count == 2

    @pytest.mark.asyncio
    async def test_rest_falls_back_to_api_v2_when_v3_redirects_to_login(self):
        fetcher = self._make_fetcher(jira_url="https://jira.example.com")
        fake_response_json = {
            "id": "10001",
            "key": "PROJ-1",
            "self": "https://jira.example.com/rest/api/2/issue/10001",
            "fields": {
                "summary": "Fetched via api v2 after v3 redirect",
                "issuetype": {"name": "Task"},
                "status": {"name": "Open"},
                "description": None,
            },
        }

        with patch("httpx.AsyncClient") as MockHttpx:
            v3_response = MagicMock()
            v3_response.status_code = 302
            v3_response.headers = {"location": "/login.jsp"}

            v2_response = MagicMock()
            v2_response.status_code = 200
            v2_response.headers = {}
            v2_response.json.return_value = fake_response_json
            v2_response.raise_for_status = MagicMock()

            http_instance = AsyncMock()
            http_instance.get.side_effect = [v3_response, v2_response]
            MockHttpx.return_value.__aenter__.return_value = http_instance
            MockHttpx.return_value.__aexit__.return_value = None

            result = await fetcher._fetch_via_rest("PROJ-1")

        assert result["summary"] == "Fetched via api v2 after v3 redirect"
        assert http_instance.get.await_count == 2


class TestNormaliseJiraBaseUrl:
    def test_none_passthrough(self):
        assert _normalise_jira_base_url(None) is None

    def test_strips_browse_path(self):
        assert _normalise_jira_base_url("https://jira.tid.es/browse/") == "https://jira.tid.es"

    def test_keeps_root_url(self):
        assert _normalise_jira_base_url("https://org.atlassian.net") == "https://org.atlassian.net"
