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
from .description_diff import DescriptionDiffResult, PointDiff


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


# ── Description functional-diff renderer ─────────────────────────────────────

_DESC_STATUS_ICON = {
    "equal":     "✅",
    "different": "⚠️ ",
    "only_a":    "◀ ",
    "only_b":    "▶ ",
}

_DESC_STATUS_COLOR = {
    "equal":     "green",
    "different": "yellow",
    "only_a":    "cyan",
    "only_b":    "magenta",
}

_DESC_STATUS_LABEL = {
    "equal":     "Igual",
    "different": "No concuerda",
    "only_a":    "Solo en A",
    "only_b":    "Solo en B",
}


def render_description_diff(
    result: DescriptionDiffResult,
    output_format: str,
    only_diff: bool,
    console: Console,
) -> None:
    """Render a :class:`DescriptionDiffResult` in the requested format."""
    if output_format == "json":
        _render_desc_json(result, console)
    elif output_format == "markdown":
        _render_desc_markdown(result, only_diff, console)
    else:
        _render_desc_table(result, only_diff, console)


def _select_desc_points(
    result: DescriptionDiffResult,
    only_diff: bool,
) -> list[PointDiff]:
    if only_diff:
        return result.different + result.only_in_a + result.only_in_b
    return result.points


def _render_desc_table(
    result: DescriptionDiffResult,
    only_diff: bool,
    console: Console,
) -> None:
    points = _select_desc_points(result, only_diff)

    if not points:
        console.print(
            Panel(
                "[bold green]Las descripciones son funcionalmente idénticas.[/bold green]",
                title="[white]qa-UScomparer · Descripción[/white]",
            )
        )
        return

    title = Text()
    title.append("Comparativa funcional de descripción   ", style="bold white")
    title.append(result.key_a, style="bold cyan")
    title.append("  vs  ", style="dim white")
    title.append(result.key_b, style="bold magenta")

    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white on dark_blue",
        expand=True,
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Estado", style="bold", min_width=14, max_width=14, no_wrap=True)
    table.add_column(
        f"[cyan]{result.key_a}[/cyan]",
        min_width=36,
        overflow="fold",
    )
    table.add_column(
        f"[magenta]{result.key_b}[/magenta]",
        min_width=36,
        overflow="fold",
    )

    for pt in points:
        color = _DESC_STATUS_COLOR[pt.status]
        icon  = _DESC_STATUS_ICON[pt.status]
        label = _DESC_STATUS_LABEL[pt.status]
        text_a = pt.point_a or "[dim]—[/dim]"
        text_b = pt.point_b or "[dim]—[/dim]"
        row_style = "on grey7" if pt.status == "different" else None
        table.add_row(
            f"[{color}]{icon} {label}[/{color}]",
            text_a,
            text_b,
            style=row_style,
        )

    console.print()
    console.print(table)

    n_eq   = len(result.equal)
    n_diff = len(result.different)
    n_a    = len(result.only_in_a)
    n_b    = len(result.only_in_b)
    total  = len(result.points)
    console.print()
    console.print(
        f"  [bold]Resumen:[/bold]  "
        f"[green]{n_eq} iguales[/green]  │  "
        f"[yellow]{n_diff} no concuerdan[/yellow]  │  "
        f"[cyan]{n_a} solo en {result.key_a}[/cyan]  │  "
        f"[magenta]{n_b} solo en {result.key_b}[/magenta]"
        f"  [dim]({total} puntos analizados)[/dim]"
    )
    console.print()


def _render_desc_json(result: DescriptionDiffResult, console: Console) -> None:
    import json as _json

    payload = {
        "ticket_a": result.key_a,
        "ticket_b": result.key_b,
        "resumen": {
            "iguales":        len(result.equal),
            "no_concuerdan":  len(result.different),
            "solo_en_a":      len(result.only_in_a),
            "solo_en_b":      len(result.only_in_b),
        },
        "puntos": [
            {
                "estado":     p.status,
                "punto_a":    p.point_a,
                "punto_b":    p.point_b,
                "similitud":  p.similarity,
            }
            for p in result.points
        ],
    }
    console.print(_json.dumps(payload, indent=2, ensure_ascii=False))


def _render_desc_markdown(
    result: DescriptionDiffResult,
    only_diff: bool,
    console: Console,
) -> None:
    points = _select_desc_points(result, only_diff)
    lines = [
        f"# Comparativa funcional de descripción: {result.key_a} vs {result.key_b}",
        "",
        f"| Estado | {result.key_a} | {result.key_b} |",
        "|--------|-----------|-----------|" ,
    ]
    for pt in points:
        icon  = _DESC_STATUS_ICON[pt.status]
        label = _DESC_STATUS_LABEL[pt.status]
        a = _md_cell(pt.point_a or "—")
        b = _md_cell(pt.point_b or "—")
        lines.append(f"| {icon} **{label}** | {a} | {b} |")

    lines += [
        "",
        f"**Iguales:** {len(result.equal)}  |  "
        f"**No concuerdan:** {len(result.different)}  |  "
        f"**Solo en {result.key_a}:** {len(result.only_in_a)}  |  "
        f"**Solo en {result.key_b}:** {len(result.only_in_b)}",
    ]
    console.print("\n".join(lines))
