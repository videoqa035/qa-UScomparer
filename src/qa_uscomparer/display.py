"""Terminal rendering for comparison results.

Supports three output formats:
* **table** (default) – colour-coded Rich table with a summary footer.
* **json** – machine-readable JSON to stdout.
* **markdown** – GitHub-flavoured Markdown table.
"""

from __future__ import annotations

import json
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .comparator import ComparisonResult, FieldDiff


# ── Display constants ─────────────────────────────────────────────────────────

_STATUS_ICON = {
    "equal":     "✅",
    "different": "⚠️ ",
    "only_a":    "◀ ",
    "only_b":    "▶ ",
}

_STATUS_COLOR = {
    "equal":     "green",
    "different": "yellow",
    "only_a":    "cyan",
    "only_b":    "magenta",
}

_FRIENDLY_NAMES: dict[str, str] = {
    "summary":           "Summary",
    "description":       "Description",
    "issuetype":         "Issue Type",
    "status":            "Status",
    "priority":          "Priority",
    "assignee":          "Assignee",
    "reporter":          "Reporter",
    "labels":            "Labels",
    "components":        "Components",
    "fixVersions":       "Fix Versions",
    "versions":          "Affects Versions",
    "customfield_10016": "Story Points",
    "customfield_10028": "Story Points (DC)",
    "customfield_10014": "Epic Link",
    "customfield_10020": "Sprint",
    "duedate":           "Due Date",
    "created":           "Created",
    "updated":           "Updated",
    "project":           "Project",
    "resolution":        "Resolution",
    "resolutiondate":    "Resolution Date",
    "environment":       "Environment",
    "parent":            "Parent",
    "subtasks":          "Subtasks",
    "comment":           "Comments",
}


# ── Public API ────────────────────────────────────────────────────────────────

def render_comparison(
    comparison: ComparisonResult,
    ticket_a: str,
    ticket_b: str,
    output_format: str,
    only_diff: bool,
    console: Console,
) -> None:
    """Render ``comparison`` to the console in the requested format."""
    if output_format == "json":
        _render_json(comparison, console)
    elif output_format == "markdown":
        _render_markdown(comparison, ticket_a, ticket_b, only_diff, console)
    else:
        _render_table(comparison, ticket_a, ticket_b, only_diff, console)


# ── Table renderer ────────────────────────────────────────────────────────────

def _render_table(
    comparison: ComparisonResult,
    ticket_a: str,
    ticket_b: str,
    only_diff: bool,
    console: Console,
) -> None:
    diffs = _select_diffs(comparison, only_diff)

    if not diffs:
        console.print(
            Panel(
                "[bold green]The two tickets are identical in all compared fields.[/bold green]",
                title="[white]qa-UScomparer[/white]",
            )
        )
        return

    title = Text()
    title.append("Jira Ticket Comparison   ", style="bold white")
    title.append(ticket_a, style="bold cyan")
    title.append("  vs  ", style="dim white")
    title.append(ticket_b, style="bold magenta")

    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white on dark_blue",
        expand=True,
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Field",                   style="bold",    min_width=18, max_width=26, no_wrap=True)
    table.add_column(f"[cyan]{ticket_a}[/cyan]",                 min_width=30, overflow="fold")
    table.add_column(f"[magenta]{ticket_b}[/magenta]",           min_width=30, overflow="fold")
    table.add_column("Δ", justify="center",     min_width=3,     max_width=3,  no_wrap=True)

    for diff in diffs:
        color = _STATUS_COLOR[diff.status]
        icon  = _STATUS_ICON[diff.status]
        row_style = "on grey7" if diff.status == "different" else None
        table.add_row(
            f"[{color}]{_friendly(diff.field_name)}[/{color}]",
            _fmt(diff.value_a),
            _fmt(diff.value_b),
            f"[{color}]{icon}[/{color}]",
            style=row_style,
        )

    console.print()
    console.print(table)
    _render_summary(comparison, console)


def _render_summary(comparison: ComparisonResult, console: Console) -> None:
    n_eq   = len(comparison.equal_fields)
    n_diff = len(comparison.different_fields)
    n_a    = len(comparison.only_in_a)
    n_b    = len(comparison.only_in_b)
    total  = len(comparison.diffs)

    console.print()
    console.print(
        f"  [bold]Summary:[/bold]  "
        f"[green]{n_eq} equal[/green]  │  "
        f"[yellow]{n_diff} different[/yellow]  │  "
        f"[cyan]{n_a} only in {comparison.key_a}[/cyan]  │  "
        f"[magenta]{n_b} only in {comparison.key_b}[/magenta]"
        f"  [dim]({total} fields compared)[/dim]"
    )
    console.print()


# ── JSON renderer ─────────────────────────────────────────────────────────────

def _render_json(comparison: ComparisonResult, console: Console) -> None:
    payload = {
        "ticket_a": comparison.key_a,
        "ticket_b": comparison.key_b,
        "summary": {
            "equal":     len(comparison.equal_fields),
            "different": len(comparison.different_fields),
            "only_in_a": len(comparison.only_in_a),
            "only_in_b": len(comparison.only_in_b),
        },
        "diffs": [
            {
                "field":   d.field_name,
                "status":  d.status,
                "value_a": d.value_a,
                "value_b": d.value_b,
            }
            for d in comparison.diffs
        ],
    }
    console.print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _render_markdown(
    comparison: ComparisonResult,
    ticket_a: str,
    ticket_b: str,
    only_diff: bool,
    console: Console,
) -> None:
    diffs = _select_diffs(comparison, only_diff)

    lines = [
        f"# Jira Comparison: {ticket_a} vs {ticket_b}",
        "",
        f"| Field | {ticket_a} | {ticket_b} | Status |",
        "|-------|-----------|-----------|--------|",
    ]
    for d in diffs:
        va = _md_cell(d.value_a)
        vb = _md_cell(d.value_b)
        lines.append(f"| **{_friendly(d.field_name)}** | {va} | {vb} | `{d.status}` |")

    lines += [
        "",
        f"**Equal:** {len(comparison.equal_fields)}  |  "
        f"**Different:** {len(comparison.different_fields)}  |  "
        f"**Only in {ticket_a}:** {len(comparison.only_in_a)}  |  "
        f"**Only in {ticket_b}:** {len(comparison.only_in_b)}",
    ]
    console.print("\n".join(lines))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _select_diffs(comparison: ComparisonResult, only_diff: bool) -> list[FieldDiff]:
    if only_diff:
        return comparison.different_fields + comparison.only_in_a + comparison.only_in_b
    return comparison.diffs


def _friendly(field_name: str) -> str:
    return _FRIENDLY_NAMES.get(field_name, field_name.replace("_", " ").title())


def _fmt(value: Any, max_len: int = 150) -> str:
    if value is None:
        return "[dim]—[/dim]"
    if isinstance(value, list):
        return "[dim](empty)[/dim]" if not value else ", ".join(str(v) for v in value)
    text = str(value)
    return text[:max_len - 1] + "…" if len(text) > max_len else text


def _md_cell(value: Any, max_len: int = 120) -> str:
    raw = str(value) if value is not None else "—"
    trimmed = (raw[:max_len - 1] + "…") if len(raw) > max_len else raw
    return trimmed.replace("|", "\\|").replace("\n", " ")
