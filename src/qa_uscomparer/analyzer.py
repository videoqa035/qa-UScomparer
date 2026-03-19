"""Genera preguntas y dudas contextuales a partir de las diferencias detectadas.

Asume que ambos tickets DEBERÍAN tener descripciones coincidentes
(tickets duplicados, derivados de la misma US o espejo de distintas
plataformas/entornos). Las preguntas ayudan al equipo a clarificar si las
diferencias son intencionadas o errores antes de avanzar con el desarrollo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .comparator import ComparisonResult, FieldDiff
from .description_diff import DescriptionDiffResult


# ── Severidad y orden ─────────────────────────────────────────────────────────

_SEVERITY_ORDER: dict[str, int] = {"alta": 0, "media": 1, "baja": 2}

_FIELD_SEVERITY: dict[str, str] = {
    "summary":           "alta",
    "description":       "alta",
    "issuetype":         "alta",
    "priority":          "alta",
    "project":           "alta",
    "status":            "media",
    "assignee":          "media",
    "fixVersions":       "media",
    "customfield_10016": "media",
    "customfield_10028": "media",
    "customfield_10014": "media",
    "customfield_10020": "media",
    "parent":            "media",
    "resolution":        "media",
    "components":        "baja",
    "labels":            "baja",
    "versions":          "baja",
    "reporter":          "baja",
    "environment":       "baja",
    "duedate":           "baja",
    "subtasks":          "baja",
}

_FIELD_LABEL: dict[str, str] = {
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
    "customfield_10028": "Story Points",
    "customfield_10014": "Epic",
    "customfield_10020": "Sprint",
    "duedate":           "Fecha límite",
    "parent":            "Ticket padre",
    "subtasks":          "Subtareas",
    "resolution":        "Resolución",
    "environment":       "Entorno",
    "project":           "Proyecto",
}


# ── Modelo ────────────────────────────────────────────────────────────────────

@dataclass
class Question:
    """Una pregunta o duda contextual derivada de las diferencias detectadas."""

    field: str       # campo relacionado (o "general" / "description")
    question: str    # texto en lenguaje natural (español)
    severity: str    # "alta" | "media" | "baja"


# ── Punto de entrada ──────────────────────────────────────────────────────────

def generate_questions(
    comparison: ComparisonResult,
    desc_result: DescriptionDiffResult | None = None,
) -> list[Question]:
    """Genera preguntas contextuales ordenadas por severidad (alta → baja).

    Parameters
    ----------
    comparison:
        Resultado del diff campo a campo.
    desc_result:
        Resultado del diff funcional de la descripción (opcional).
    """
    questions: list[Question] = []
    key_a = comparison.key_a
    key_b = comparison.key_b

    # ── Pregunta introductoria si hay muchas diferencias ──────────────────
    total_diffs = (
        len(comparison.different_fields)
        + len(comparison.only_in_a)
        + len(comparison.only_in_b)
    )
    if total_diffs >= 4:
        questions.append(
            Question(
                field="general",
                severity="alta",
                question=(
                    f"Se han detectado {total_diffs} diferencias entre {key_a} y {key_b}. "
                    f"¿Estos tickets describen el mismo requisito o funcionalidad? "
                    f"Si es así, considera revisar cuál debe ser la fuente de verdad "
                    f"antes de continuar con el desarrollo."
                ),
            )
        )

    # ── Preguntas por campos distintos ─────────────────────────────────────
    for diff in comparison.different_fields:
        q = _question_for_different_field(diff, key_a, key_b)
        if q:
            questions.append(q)

    # ── Preguntas por campos que existen solo en uno de los tickets ────────
    for diff in comparison.only_in_a:
        label = _label(diff.field_name)
        questions.append(
            Question(
                field=diff.field_name,
                severity=_FIELD_SEVERITY.get(diff.field_name, "baja"),
                question=(
                    f"El campo «{label}» está informado en {key_a} pero ausente en {key_b}. "
                    f"¿Es intencionado o falta completar la información en {key_b}?"
                ),
            )
        )

    for diff in comparison.only_in_b:
        label = _label(diff.field_name)
        questions.append(
            Question(
                field=diff.field_name,
                severity=_FIELD_SEVERITY.get(diff.field_name, "baja"),
                question=(
                    f"El campo «{label}» está informado en {key_b} pero ausente en {key_a}. "
                    f"¿Es intencionado o falta completar la información en {key_a}?"
                ),
            )
        )

    # ── Preguntas por diferencias en la descripción ────────────────────────
    if desc_result and desc_result.has_differences:
        n_diff   = len(desc_result.different)
        n_only_a = len(desc_result.only_in_a)
        n_only_b = len(desc_result.only_in_b)

        if n_diff:
            questions.append(
                Question(
                    field="description",
                    severity="alta",
                    question=(
                        f"Hay {n_diff} punto(s) de la descripción que no concuerdan entre "
                        f"los dos tickets. Si ambos deberían describir el mismo requisito, "
                        f"¿las diferencias reflejan variaciones de contexto o hay "
                        f"inconsistencias reales que corregir?"
                    ),
                )
            )

        if n_only_a:
            questions.append(
                Question(
                    field="description",
                    severity="alta",
                    question=(
                        f"Hay {n_only_a} punto(s) en la descripción de {key_a} que no "
                        f"aparecen en {key_b}. ¿Son requisitos exclusivos de {key_a} "
                        f"o debería incluirlos {key_b} también?"
                    ),
                )
            )

        if n_only_b:
            questions.append(
                Question(
                    field="description",
                    severity="alta",
                    question=(
                        f"Hay {n_only_b} punto(s) en la descripción de {key_b} que no "
                        f"aparecen en {key_a}. ¿Son requisitos exclusivos de {key_b} "
                        f"o debería incluirlos {key_a} también?"
                    ),
                )
            )

    # ── Ordenar por severidad ──────────────────────────────────────────────
    questions.sort(key=lambda q: _SEVERITY_ORDER.get(q.severity, 2))
    return questions


# ── Generación por campo ──────────────────────────────────────────────────────

def _question_for_different_field(
    diff: FieldDiff, key_a: str, key_b: str
) -> Question | None:
    fn    = diff.field_name
    label = _label(fn)
    va    = _fmt(diff.value_a)
    vb    = _fmt(diff.value_b)
    sev   = _FIELD_SEVERITY.get(fn, "baja")

    _templates: dict[str, str] = {
        "summary": (
            f"Los títulos son distintos:\n"
            f"  • {key_a}: «{va}»\n"
            f"  • {key_b}: «{vb}»\n"
            f"Si ambos tickets describen el mismo requisito, ¿las diferencias son "
            f"intencionadas (p. ej. variantes por plataforma) o hay un error de redacción?"
        ),
        "issuetype": (
            f"Los tipos de incidencia son distintos: {key_a} es «{va}» y {key_b} es «{vb}». "
            f"Si describen el mismo trabajo, ¿deberían ser del mismo tipo?"
        ),
        "priority": (
            f"La prioridad no coincide: {key_a} tiene «{va}» y {key_b} tiene «{vb}». "
            f"Dado que las descripciones deberían ser equivalentes, ¿el impacto real es "
            f"distinto en cada contexto o hay un error de clasificación?"
        ),
        "status": (
            f"Los estados no coinciden: {key_a} está en «{va}» y {key_b} en «{vb}». "
            f"¿Los tickets evolucionan de forma independiente en el proceso o "
            f"deberían avanzar sincronizados?"
        ),
        "assignee": (
            f"Los responsables son distintos: {key_a} → {va} / {key_b} → {vb}. "
            f"¿Hay coordinación entre ambas personas para garantizar la coherencia "
            f"en la implementación?"
        ),
        "fixVersions": (
            f"Las versiones de entrega difieren: {va} vs {vb}. "
            f"¿Se planifican en el mismo release? Versiones distintas pueden generar "
            f"inconsistencias en la entrega del producto."
        ),
        "customfield_10016": (
            f"La estimación de esfuerzo es distinta: {va} vs {vb} puntos. "
            f"Si el trabajo es equivalente, ¿la diferencia está justificada o hay "
            f"una estimación incorrecta en uno de los tickets?"
        ),
        "customfield_10028": (
            f"La estimación de esfuerzo es distinta: {va} vs {vb} puntos. "
            f"Si el trabajo es equivalente, ¿la diferencia está justificada o hay "
            f"una estimación incorrecta en uno de los tickets?"
        ),
        "components": (
            f"Los componentes afectados difieren: {va} vs {vb}. "
            f"¿Ambos tickets impactan las mismas partes del sistema o el alcance "
            f"técnico es realmente distinto?"
        ),
        "environment": (
            f"Los entornos documentados son distintos: «{va}» vs «{vb}». "
            f"Si la descripción debería ser coincidente, ¿se ha verificado que el "
            f"problema se reproduce de igual forma en ambos entornos?"
        ),
        "customfield_10014": (
            f"Los tickets pertenecen a Epics distintas: «{va}» vs «{vb}». "
            f"¿Forman parte del mismo objetivo de negocio o son iniciativas independientes?"
        ),
        "customfield_10020": (
            f"Los tickets están planificados en sprints distintos: {va} vs {vb}. "
            f"¿El trabajo está coordinado o puede haber una desincronización en la entrega?"
        ),
        "duedate": (
            f"Las fechas límite son distintas: {va} vs {vb}. "
            f"¿Tienen dependencias entre sí que obliguen a alinear las fechas de entrega?"
        ),
        "parent": (
            f"Los tickets padre son distintos: «{va}» vs «{vb}». "
            f"¿Pertenecen a la misma historia de usuario o forman parte de épicas distintas?"
        ),
        "project": (
            f"Los tickets pertenecen a proyectos distintos: {va} vs {vb}. "
            f"¿Es una clasificación intencionada o hay un error de asignación?"
        ),
        "resolution": (
            f"Las resoluciones son distintas: «{va}» vs «{vb}». "
            f"¿Se han cerrado de la misma forma o hay inconsistencias en el cierre?"
        ),
        "labels": (
            f"Las etiquetas son distintas: {va} vs {vb}. "
            f"¿Están bien categorizados para facilitar su búsqueda y trazabilidad?"
        ),
        "reporter": (
            f"Los tickets fueron reportados por personas distintas ({va} vs {vb}). "
            f"¿Hay un origen común que debería reflejarse?"
        ),
    }

    text = _templates.get(fn) or (
        f"El campo «{label}» tiene valores distintos: «{va}» en {key_a} y «{vb}» en {key_b}. "
        f"¿Es una diferencia esperada o debería revisarse?"
    )
    return Question(field=fn, question=text, severity=sev)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _label(field: str) -> str:
    return _FIELD_LABEL.get(field, field.replace("_", " ").title())


def _fmt(value: Any, max_len: int = 120) -> str:
    """Texto plano, sin HTML, truncado a max_len caracteres."""
    import html as _html
    import re as _re
    if value is None:
        return "—"
    if isinstance(value, list):
        text = ", ".join(str(v) for v in value) if value else "—"
    else:
        text = str(value)
    # Strip HTML
    if "<" in text and ">" in text:
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _html.unescape(text)
        text = text.replace("\xa0", " ")
        text = _re.sub(r"\s+", " ", text).strip()
    return (text[:max_len - 1] + "…") if len(text) > max_len else text
