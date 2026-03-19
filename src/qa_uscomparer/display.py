"""Terminal rendering for comparison results.

Formats:
* **table** (default) – informe legible: sólo diferencias + descripción + dudas sugeridas.
* **json** – JSON orientado a máquina / CI.
* **markdown** – tabla GFM para pegar en GitHub / Jira.
"""

from __future__ import annotations

import json
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .analyzer import Question
from .comparator import ComparisonResult, FieldDiff
from .description_diff import DescriptionDiffResult, PointDiff


# ── Constantes de presentación ────────────────────────────────────────────────

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

# Nombres amigables en español
_FRIENDLY_NAMES: dict[str, str] = {
    "summary":           "Título",
    "description":       "Descripción",
    "issuetype":         "Tipo de incidencia",
    "status":            "Estado",
    "priority":          "Prioridad",
    "assignee":          "Responsable",
    "reporter":          "Reportado por",
    "labels":            "Etiquetas",
    "components":        "Componentes",
    "fixVersions":       "Versión de entrega",
    "versions":          "Versiones afectadas",
    "customfield_10016": "Story Points",
    "customfield_10028": "Story Points (DC)",
    "customfield_10014": "Epic",
    "customfield_10020": "Sprint",
    "duedate":           "Fecha límite",
    "created":           "Creado",
    "updated":           "Actualizado",
    "project":           "Proyecto",
    "resolution":        "Resolución",
    "resolutiondate":    "Fecha resolución",
    "environment":       "Entorno",
    "parent":            "Ticket padre",
    "subtasks":          "Subtareas",
    "comment":           "Comentarios",
}

_SEVERITY_COLOR: dict[str, str] = {
    "alta":  "bold red",
    "media": "bold yellow",
    "baja":  "dim white",
}

_SEVERITY_LABEL: dict[str, str] = {
    "alta":  "ALTA",
    "media": "MEDIA",
    "baja":  "BAJA",
}


# ── API pública ───────────────────────────────────────────────────────────────

def render_comparison(
    comparison: ComparisonResult,
    ticket_a: str,
    ticket_b: str,
    output_format: str,
    only_diff: bool,
    console: Console,
    questions: list[Question] | None = None,
    desc_result: DescriptionDiffResult | None = None,
) -> None:
    """Renderiza el resultado de la comparación en el formato solicitado.

    Con ``output_format='table'`` (por defecto) se produce un informe legible
    en español con:
      1. Sección de diferencias encontradas (campos del ticket).
      2. Comparativa funcional de la descripción (si se pasa ``desc_result``).
      3. Panel de dudas/preguntas sugeridas (si se pasa ``questions``).
    """
    if output_format == "json":
        _render_json(comparison, console, desc_result, questions)
    elif output_format == "markdown":
        _render_markdown(comparison, ticket_a, ticket_b, only_diff, console,
                         desc_result, questions)
    else:
        _render_report(comparison, ticket_a, ticket_b, console,
                       desc_result, questions)


# ── Informe principal (formato por defecto) ───────────────────────────────────

def _render_report(
    comparison: ComparisonResult,
    ticket_a: str,
    ticket_b: str,
    console: Console,
    desc_result: DescriptionDiffResult | None,
    questions: list[Question] | None,
) -> None:
    """Informe en lenguaje natural con diferencias + descripción + dudas."""
    console.print()

    # Cabecera
    header = Text(justify="center")
    header.append("Análisis de tickets  ", style="bold white")
    header.append(ticket_a, style="bold cyan")
    header.append("  vs  ", style="dim white")
    header.append(ticket_b, style="bold magenta")
    console.print(Panel(header, box=box.DOUBLE_EDGE, padding=(0, 2)))
    console.print()

    diff_fields = (
        comparison.different_fields + comparison.only_in_a + comparison.only_in_b
    )

    # ── 1. Diferencias en campos del ticket ──────────────────────────────
    console.print(Rule(
        f"[bold yellow]⚠  DIFERENCIAS EN LOS CAMPOS DEL TICKET "
        f"({len(diff_fields)} encontradas)[/bold yellow]",
        style="yellow",
    ))
    console.print()

    if not diff_fields:
        console.print(
            "  [bold green]✅  Todos los campos del ticket son idénticos.[/bold green]"
        )
    else:
        for d in diff_fields:
            _render_diff_block(d, ticket_a, ticket_b, console)

    console.print()

    # ── 2. Comparativa de descripción ────────────────────────────────────
    if desc_result is not None:
        console.print(Rule(
            "[bold blue]📝  COMPARATIVA DE DESCRIPCIÓN[/bold blue]",
            style="blue",
        ))
        console.print()
        _render_desc_blocks(desc_result, ticket_a, ticket_b, console)
        console.print()

    # ── 3. Preguntas sugeridas ────────────────────────────────────────────
    if questions:
        console.print(Rule(
            "[bold magenta]❓  DUDAS QUE PUEDEN SURGIR[/bold magenta]",
            style="magenta",
        ))
        console.print()
        for i, q in enumerate(questions, start=1):
            sev_color = _SEVERITY_COLOR.get(q.severity, "white")
            sev_label = _SEVERITY_LABEL.get(q.severity, q.severity.upper())
            # Número + severidad
            console.print(
                f"  [bold white]{i}.[/bold white]  "
                f"[{sev_color}][{sev_label}][/{sev_color}]"
            )
            # Pregunta con sangría
            for line in q.question.splitlines():
                console.print(f"       [white]{line}[/white]")
            console.print()

    # ── Pie de resumen ────────────────────────────────────────────────────
    n_eq   = len(comparison.equal_fields)
    n_diff = len(comparison.different_fields)
    n_a    = len(comparison.only_in_a)
    n_b    = len(comparison.only_in_b)
    total  = len(comparison.diffs)
    footer = (
        f"[green]✅ {n_eq} iguales[/green]  │  "
        f"[yellow]⚠ {n_diff} distintos[/yellow]  │  "
        f"[cyan]◀ {n_a} solo en {ticket_a}[/cyan]  │  "
        f"[magenta]▶ {n_b} solo en {ticket_b}[/magenta]"
        f"  [dim]({total} campos comparados)[/dim]"
    )
    console.print(Panel(footer, box=box.SIMPLE, padding=(0, 2)))
    console.print()


def _render_diff_block(
    diff: FieldDiff, ticket_a: str, ticket_b: str, console: Console
) -> None:
    """Muestra un bloque visual para una diferencia individual."""
    label  = _friendly(diff.field_name)
    color  = _STATUS_COLOR[diff.status]
    icon   = _STATUS_ICON[diff.status]

    if diff.status == "different":
        console.print(f"  [{color}]{icon} {label}[/{color}]")
        console.print(f"     [cyan]├─ {ticket_a}:[/cyan] {_fmt(diff.value_a)}")
        console.print(f"     [magenta]└─ {ticket_b}:[/magenta] {_fmt(diff.value_b)}")
    elif diff.status == "only_a":
        console.print(
            f"  [{color}]{icon} {label}[/{color}]  "
            f"[dim](solo presente en {ticket_a})[/dim]"
        )
        console.print(f"     [cyan]└─ {ticket_a}:[/cyan] {_fmt(diff.value_a)}")
    else:  # only_b
        console.print(
            f"  [{color}]{icon} {label}[/{color}]  "
            f"[dim](solo presente en {ticket_b})[/dim]"
        )
        console.print(f"     [magenta]└─ {ticket_b}:[/magenta] {_fmt(diff.value_b)}")
    console.print()


def _render_desc_blocks(
    result: DescriptionDiffResult,
    ticket_a: str,
    ticket_b: str,
    console: Console,
) -> None:
    """Muestra en bloques los puntos de la descripción que difieren."""
    diff_points = result.different + result.only_in_a + result.only_in_b

    if not diff_points:
        console.print(
            "  [bold green]✅  Las descripciones son funcionalmente idénticas.[/bold green]"
        )
        return

    _DESC_STATUS_LABEL = {
        "different": "No concuerda",
        "only_a":    f"Solo en {ticket_a}",
        "only_b":    f"Solo en {ticket_b}",
    }

    for pt in diff_points:
        color = _STATUS_COLOR[pt.status]
        icon  = _STATUS_ICON[pt.status]
        label = _DESC_STATUS_LABEL.get(pt.status, pt.status)

        console.print(f"  [{color}]{icon} {label}[/{color}]")

        if pt.status == "different":
            console.print(f"     [cyan]├─ {ticket_a}:[/cyan] {pt.point_a}")
            console.print(f"     [magenta]└─ {ticket_b}:[/magenta] {pt.point_b}")
        elif pt.status == "only_a":
            console.print(f"     [cyan]└─ {ticket_a}:[/cyan] {pt.point_a}")
        else:
            console.print(f"     [magenta]└─ {ticket_b}:[/magenta] {pt.point_b}")
        console.print()

    n   = len(result.points)
    neq = len(result.equal)
    console.print(
        f"  [dim]{neq} puntos coinciden de {n} analizados.[/dim]"
    )


# ── JSON ──────────────────────────────────────────────────────────────────────

def _render_json(
    comparison: ComparisonResult,
    console: Console,
    desc_result: DescriptionDiffResult | None,
    questions: list[Question] | None,
) -> None:
    payload: dict[str, Any] = {
        "ticket_a": comparison.key_a,
        "ticket_b": comparison.key_b,
        "resumen": {
            "iguales":     len(comparison.equal_fields),
            "distintos":   len(comparison.different_fields),
            "solo_en_a":   len(comparison.only_in_a),
            "solo_en_b":   len(comparison.only_in_b),
        },
        "diferencias": [
            {
                "campo":    d.field_name,
                "etiqueta": _friendly(d.field_name),
                "estado":   d.status,
                "valor_a":  d.value_a,
                "valor_b":  d.value_b,
            }
            for d in (
                comparison.different_fields + comparison.only_in_a + comparison.only_in_b
            )
        ],
    }

    if desc_result is not None:
        payload["descripcion"] = {
            "iguales":      len(desc_result.equal),
            "no_concuerdan": len(desc_result.different),
            "solo_en_a":    len(desc_result.only_in_a),
            "solo_en_b":    len(desc_result.only_in_b),
            "puntos": [
                {
                    "estado":   p.status,
                    "punto_a":  p.point_a,
                    "punto_b":  p.point_b,
                    "similitud": round(p.similarity, 3),
                }
                for p in desc_result.points
                if p.status != "equal"
            ],
        }

    if questions:
        payload["dudas_sugeridas"] = [
            {
                "campo":     q.field,
                "severidad": q.severity,
                "pregunta":  q.question,
            }
            for q in questions
        ]

    console.print(json.dumps(payload, indent=2, ensure_ascii=False, default=str), highlight=False, soft_wrap=True)


# ── Markdown ──────────────────────────────────────────────────────────────────

def _render_markdown(
    comparison: ComparisonResult,
    ticket_a: str,
    ticket_b: str,
    only_diff: bool,
    console: Console,
    desc_result: DescriptionDiffResult | None,
    questions: list[Question] | None,
) -> None:
    diff_fields = (
        comparison.different_fields + comparison.only_in_a + comparison.only_in_b
    )
    diffs = diff_fields if only_diff else comparison.diffs

    lines: list[str] = [
        f"# Análisis de tickets: {ticket_a} vs {ticket_b}",
        "",
        "## Diferencias en campos",
        "",
        f"| Campo | {ticket_a} | {ticket_b} | Estado |",
        "|-------|-----------|-----------|--------|",
    ]
    for d in diffs:
        va = _md_cell(d.value_a)
        vb = _md_cell(d.value_b)
        estado = {
            "equal":     "✅ Igual",
            "different": "⚠️ Distinto",
            "only_a":    f"◀ Solo en {ticket_a}",
            "only_b":    f"▶ Solo en {ticket_b}",
        }.get(d.status, d.status)
        lines.append(
            f"| **{_friendly(d.field_name)}** | {va} | {vb} | {estado} |"
        )

    lines += [
        "",
        f"**Iguales:** {len(comparison.equal_fields)}  |  "
        f"**Distintos:** {len(comparison.different_fields)}  |  "
        f"**Solo en {ticket_a}:** {len(comparison.only_in_a)}  |  "
        f"**Solo en {ticket_b}:** {len(comparison.only_in_b)}",
    ]

    if desc_result is not None:
        diff_pts = desc_result.different + desc_result.only_in_a + desc_result.only_in_b
        lines += [
            "",
            "## Comparativa de descripción",
            "",
            f"| Estado | {ticket_a} | {ticket_b} |",
            "|--------|-----------|-----------|",
        ]
        for pt in diff_pts:
            tag = {
                "different": "⚠️ No concuerda",
                "only_a":    f"◀ Solo en {ticket_a}",
                "only_b":    f"▶ Solo en {ticket_b}",
            }.get(pt.status, pt.status)
            lines.append(
                f"| {tag} | {_md_cell(pt.point_a or '—')} "
                f"| {_md_cell(pt.point_b or '—')} |"
            )

    if questions:
        lines += ["", "## Dudas que pueden surgir", ""]
        for i, q in enumerate(questions, start=1):
            sev = q.severity.upper()
            lines.append(f"{i}. **[{sev}]** {q.question.replace(chr(10), ' ')}")

    console.print("\n".join(lines))


# ── Helpers compartidos ───────────────────────────────────────────────────────

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
        return "[dim](vacío)[/dim]" if not value else ", ".join(str(v) for v in value)
    text = str(value)
    return text[: max_len - 1] + "…" if len(text) > max_len else text


def _md_cell(value: Any, max_len: int = 120) -> str:
    raw = str(value) if value is not None else "—"
    trimmed = (raw[: max_len - 1] + "…") if len(raw) > max_len else raw
    return trimmed.replace("|", "\\|").replace("\n", " ")


# ── Compatibilidad hacia atrás: render_description_diff ──────────────────────
# Mantenida para que el flag --description-diff siga funcionando en solitario.

_DESC_STATUS_ICON = _STATUS_ICON
_DESC_STATUS_COLOR = _STATUS_COLOR
_DESC_STATUS_LABEL_COMPAT = {
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
    """Renderiza un DescriptionDiffResult de forma independiente."""
    if output_format == "json":
        _render_desc_json(result, console)
    elif output_format == "markdown":
        _render_desc_markdown_compat(result, only_diff, console)
    else:
        _render_desc_table_compat(result, only_diff, console)


def _select_desc_points(
    result: DescriptionDiffResult, only_diff: bool
) -> list[PointDiff]:
    if only_diff:
        return result.different + result.only_in_a + result.only_in_b
    return result.points


def _render_desc_table_compat(
    result: DescriptionDiffResult, only_diff: bool, console: Console
) -> None:
    points = _select_desc_points(result, only_diff)
    if not points:
        console.print(Panel(
            "[bold green]Las descripciones son funcionalmente idénticas.[/bold green]",
            title="[white]qa-UScomparer · Descripción[/white]",
        ))
        return

    title = Text()
    title.append("Comparativa de descripción   ", style="bold white")
    title.append(result.key_a, style="bold cyan")
    title.append("  vs  ", style="dim white")
    title.append(result.key_b, style="bold magenta")

    table = Table(
        title=title, box=box.ROUNDED, show_header=True,
        header_style="bold white on dark_blue", expand=True,
        show_lines=True, padding=(0, 1),
    )
    table.add_column("Estado", style="bold", min_width=14, max_width=16, no_wrap=True)
    table.add_column(f"[cyan]{result.key_a}[/cyan]", min_width=36, overflow="fold")
    table.add_column(f"[magenta]{result.key_b}[/magenta]", min_width=36, overflow="fold")

    for pt in points:
        color = _DESC_STATUS_COLOR[pt.status]
        icon  = _DESC_STATUS_ICON[pt.status]
        label = _DESC_STATUS_LABEL_COMPAT[pt.status]
        row_style = "on grey7" if pt.status == "different" else None
        table.add_row(
            f"[{color}]{icon} {label}[/{color}]",
            pt.point_a or "[dim]—[/dim]",
            pt.point_b or "[dim]—[/dim]",
            style=row_style,
        )

    console.print()
    console.print(table)
    console.print()
    console.print(
        f"  [bold]Resumen:[/bold]  "
        f"[green]{len(result.equal)} iguales[/green]  │  "
        f"[yellow]{len(result.different)} no concuerdan[/yellow]  │  "
        f"[cyan]{len(result.only_in_a)} solo en {result.key_a}[/cyan]  │  "
        f"[magenta]{len(result.only_in_b)} solo en {result.key_b}[/magenta]"
        f"  [dim]({len(result.points)} puntos)[/dim]"
    )
    console.print()


def _render_desc_json(result: DescriptionDiffResult, console: Console) -> None:
    payload = {
        "ticket_a": result.key_a,
        "ticket_b": result.key_b,
        "resumen": {
            "iguales":       len(result.equal),
            "no_concuerdan": len(result.different),
            "solo_en_a":     len(result.only_in_a),
            "solo_en_b":     len(result.only_in_b),
        },
        "puntos": [
            {
                "estado":    p.status,
                "punto_a":   p.point_a,
                "punto_b":   p.point_b,
                "similitud": p.similarity,
            }
            for p in result.points
        ],
    }
    console.print(json.dumps(payload, indent=2, ensure_ascii=False), highlight=False, soft_wrap=True)


def _render_desc_markdown_compat(
    result: DescriptionDiffResult, only_diff: bool, console: Console
) -> None:
    points = _select_desc_points(result, only_diff)
    lines = [
        f"# Comparativa de descripción: {result.key_a} vs {result.key_b}",
        "",
        f"| Estado | {result.key_a} | {result.key_b} |",
        "|--------|-----------|-----------|",
    ]
    for pt in points:
        icon  = _DESC_STATUS_ICON[pt.status]
        label = _DESC_STATUS_LABEL_COMPAT[pt.status]
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

