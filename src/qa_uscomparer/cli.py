"""CLI entry point for qa-UScomparer.

Usage
-----
    qa-uscomparer TICKET_A TICKET_B [OPTIONS]

Environment variables (all can also be passed as flags):
    ATLASSIAN_TOKEN     – API token or PAT.
    ATLASSIAN_EMAIL     – Account email (Jira Cloud only).
    ATLASSIAN_BASE_URL  – Atlassian Remote MCP base URL.
    JIRA_BASE_URL       – Jira instance URL (REST API fallback).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console

from .comparator import compare_tickets
from .display import render_comparison
from .jira_fetcher import JiraFetcher

load_dotenv()

console = Console(stderr=False)


# ── CLI definition ─────────────────────────────────────────────────────────────

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("ticket_a")
@click.argument("ticket_b")
@click.option(
    "--token",
    envvar="ATLASSIAN_TOKEN",
    prompt="Atlassian Personal Access Token (or API Token)",
    hide_input=True,
    help="Atlassian personal access token or API token.",
)
@click.option(
    "--email",
    envvar="ATLASSIAN_EMAIL",
    default=None,
    show_default=False,
    help="Atlassian account email – required for Jira Cloud (Basic auth).",
)
@click.option(
    "--base-url",
    envvar="ATLASSIAN_BASE_URL",
    default="https://mcp.atlassian.com",
    show_default=True,
    help="Atlassian Remote MCP base URL.",
)
@click.option(
    "--jira-url",
    envvar="JIRA_BASE_URL",
    default=None,
    help="Jira instance base URL for REST API fallback (e.g. https://org.atlassian.net).",
)
@click.option(
    "--output",
    type=click.Choice(["table", "json", "markdown"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--fields",
    default=None,
    metavar="FIELD1,FIELD2,…",
    help="Comma-separated list of fields to compare (all fields if omitted).",
)
@click.option(
    "--only-diff",
    is_flag=True,
    default=False,
    help="Show only fields that differ between the two tickets.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
@click.version_option("0.1.0", prog_name="qa-uscomparer")
def main(
    ticket_a: str,
    ticket_b: str,
    token: str,
    email: Optional[str],
    base_url: str,
    jira_url: Optional[str],
    output: str,
    fields: Optional[str],
    only_diff: bool,
    verbose: bool,
) -> None:
    """Compare the definitions of two Jira tickets using the Atlassian MCP server.

    \b
    TICKET_A  First  Jira issue key  (e.g. PROJ-101)
    TICKET_B  Second Jira issue key  (e.g. PROJ-102)

    \b
    Examples:

      qa-uscomparer PROJ-101 PROJ-102
      qa-uscomparer PROJ-101 PROJ-102 --only-diff
      qa-uscomparer PROJ-101 PROJ-102 --output json
      qa-uscomparer PROJ-101 PROJ-102 --output markdown
      qa-uscomparer PROJ-101 PROJ-102 --fields summary,status,priority
      ATLASSIAN_TOKEN=xxxx ATLASSIAN_EMAIL=you@org.com qa-uscomparer PROJ-101 PROJ-102
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    field_list = [f.strip() for f in fields.split(",")] if fields else None

    asyncio.run(
        _run(
            ticket_a=ticket_a,
            ticket_b=ticket_b,
            token=token,
            email=email,
            base_url=base_url,
            jira_url=jira_url,
            output=output.lower(),
            fields=field_list,
            only_diff=only_diff,
        )
    )


# ── Async runner ───────────────────────────────────────────────────────────────

async def _run(
    ticket_a: str,
    ticket_b: str,
    token: str,
    email: Optional[str],
    base_url: str,
    jira_url: Optional[str],
    output: str,
    fields: Optional[list[str]],
    only_diff: bool,
) -> None:
    fetcher = JiraFetcher(
        token=token,
        email=email,
        mcp_base_url=base_url,
        jira_base_url=jira_url,
    )

    try:
        with console.status(f"[bold cyan]Fetching [yellow]{ticket_a}[/yellow]…"):
            issue_a = await fetcher.fetch_issue(ticket_a)
        with console.status(f"[bold cyan]Fetching [yellow]{ticket_b}[/yellow]…"):
            issue_b = await fetcher.fetch_issue(ticket_b)
    except Exception as exc:  # noqa: BLE001
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    comparison = compare_tickets(issue_a, issue_b, fields=fields)

    render_comparison(
        comparison=comparison,
        ticket_a=ticket_a,
        ticket_b=ticket_b,
        output_format=output,
        only_diff=only_diff,
        console=console,
    )
