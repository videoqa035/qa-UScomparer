"""Tests for the CLI entry point (qa_uscomparer.cli)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from qa_uscomparer.cli import main
from qa_uscomparer.comparator import ComparisonResult, FieldDiff


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_result(key_a="PROJ-101", key_b="PROJ-102") -> ComparisonResult:
    return ComparisonResult(
        key_a=key_a,
        key_b=key_b,
        diffs=[
            FieldDiff("summary",  "Login bug iOS",     "Login bug Android",   "different"),
            FieldDiff("status",   "In Progress",        "Open",                "different"),
            FieldDiff("issuetype","Bug",                "Bug",                 "equal"),
            FieldDiff("priority", "High",               None,                  "only_a"),
            FieldDiff("labels",   None,                 ["android", "mobile"], "only_b"),
        ],
    )


def _invoke(args: list[str]) -> object:
    runner = CliRunner()
    return runner.invoke(
        main,
        args,
        catch_exceptions=False,
    )


def _mock_run(result: ComparisonResult):
    """Context manager that stubs both fetch_issue calls."""
    issue_a = {"key": result.key_a, "id": "1", "self": "", "summary": "Login bug iOS"}
    issue_b = {"key": result.key_b, "id": "2", "self": "", "summary": "Login bug Android"}

    async def fake_fetch(self, key: str):  # 'self' = JiraFetcher instance
        return issue_a if key == result.key_a else issue_b

    return patch("qa_uscomparer.cli.JiraFetcher.fetch_issue", new=fake_fetch)


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestCLI:
    def test_help_exits_zero(self):
        result = _invoke(["--help"])
        assert result.exit_code == 0
        assert "TICKET_A" in result.output

    def test_version_flag(self):
        result = _invoke(["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_table_output(self):
        with _mock_run(_make_result()):
            result = _invoke([
                "PROJ-101", "PROJ-102",
                "--token", "fake-token",
                "--email", "user@org.com",
                "--jira-url", "https://org.atlassian.net",
            ])
        assert result.exit_code == 0

    def test_json_output_valid_json(self):
        with _mock_run(_make_result()):
            result = _invoke([
                "PROJ-101", "PROJ-102",
                "--token", "fake-token",
                "--email", "user@org.com",
                "--jira-url", "https://org.atlassian.net",
                "--output", "json",
            ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ticket_a"] == "PROJ-101"
        assert data["ticket_b"] == "PROJ-102"
        assert "diffs" in data

    def test_markdown_output_contains_table(self):
        with _mock_run(_make_result()):
            result = _invoke([
                "PROJ-101", "PROJ-102",
                "--token", "fake-token",
                "--email", "user@org.com",
                "--jira-url", "https://org.atlassian.net",
                "--output", "markdown",
            ])
        assert result.exit_code == 0
        assert "| Field |" in result.output
        assert "PROJ-101" in result.output
        assert "PROJ-102" in result.output

    def test_only_diff_flag_filters(self):
        with _mock_run(_make_result()):
            result = _invoke([
                "PROJ-101", "PROJ-102",
                "--token", "fake-token",
                "--email", "user@org.com",
                "--jira-url", "https://org.atlassian.net",
                "--output", "json",
                "--only-diff",
            ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        statuses = {d["status"] for d in data["diffs"]}
        assert "equal" not in statuses

    def test_error_exits_nonzero_on_fetch_failure(self):
        async def fail_fetch(self, key: str):
            raise RuntimeError("Network error")

        with patch("qa_uscomparer.cli.JiraFetcher.fetch_issue", new=fail_fetch):
            result = _invoke([
                "PROJ-101", "PROJ-102",
                "--token", "fake-token",
                "--jira-url", "https://org.atlassian.net",
            ])
        assert result.exit_code != 0
