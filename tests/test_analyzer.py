"""Tests para qa_uscomparer.analyzer – generación de preguntas contextuales."""

from __future__ import annotations

import pytest

from qa_uscomparer.analyzer import Question, generate_questions, _fmt, _label
from qa_uscomparer.comparator import ComparisonResult, FieldDiff
from qa_uscomparer.description_diff import DescriptionDiffResult, PointDiff


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _result(diffs: list[FieldDiff], key_a: str = "P-1", key_b: str = "P-2") -> ComparisonResult:
    return ComparisonResult(key_a=key_a, key_b=key_b, diffs=diffs)


def _diff(field: str, status: str, va=None, vb=None) -> FieldDiff:
    return FieldDiff(field_name=field, value_a=va, value_b=vb, status=status)


def _desc_result(different=0, only_a=0, only_b=0) -> DescriptionDiffResult:
    dr = DescriptionDiffResult(key_a="P-1", key_b="P-2")
    for _ in range(different):
        dr.points.append(PointDiff("different", "texto A", "texto B", 0.8))
    for _ in range(only_a):
        dr.points.append(PointDiff("only_a", "solo A", "", 0.0))
    for _ in range(only_b):
        dr.points.append(PointDiff("only_b", "", "solo B", 0.0))
    return dr


# ── _label y _fmt ──────────────────────────────────────────────────────────────

class TestHelpers:
    def test_label_known_field(self):
        assert _label("priority") == "Prioridad"

    def test_label_unknown_field(self):
        assert _label("custom_field_xyz") == "Custom Field Xyz"

    def test_fmt_none(self):
        assert _fmt(None) == "—"

    def test_fmt_empty_list(self):
        assert _fmt([]) == "—"

    def test_fmt_list(self):
        assert _fmt(["a", "b"]) == "a, b"

    def test_fmt_string(self):
        assert _fmt("hola") == "hola"

    def test_fmt_number(self):
        assert _fmt(5) == "5"


# ── generate_questions: campos distintos ──────────────────────────────────────

class TestGenerateQuestions:
    def test_returns_list_of_questions(self):
        result = _result([_diff("priority", "different", "High", "Low")])
        qs = generate_questions(result)
        assert isinstance(qs, list)
        assert all(isinstance(q, Question) for q in qs)

    def test_no_diffs_returns_empty(self):
        result = _result([_diff("status", "equal", "Open", "Open")])
        qs = generate_questions(result)
        assert qs == []

    def test_different_priority_generates_question(self):
        result = _result([_diff("priority", "different", "Alta", "Baja")])
        qs = generate_questions(result)
        assert len(qs) == 1
        assert qs[0].field == "priority"
        assert "prioridad" in qs[0].question.lower() or "priority" in qs[0].question.lower()

    def test_summary_question_is_alta_severity(self):
        result = _result([_diff("summary", "different", "Title A", "Title B")])
        qs = generate_questions(result)
        assert qs[0].severity == "alta"

    def test_labels_question_is_baja_severity(self):
        result = _result([_diff("labels", "different", ["a"], ["b"])])
        qs = generate_questions(result)
        assert qs[0].severity == "baja"

    def test_only_a_generates_presence_question(self):
        result = _result([_diff("environment", "only_a", "iOS 17", None)])
        qs = generate_questions(result)
        assert qs[0].field == "environment"
        assert "P-1" in qs[0].question

    def test_only_b_generates_presence_question(self):
        result = _result([_diff("environment", "only_b", None, "Android 14")])
        qs = generate_questions(result)
        assert qs[0].field == "environment"
        assert "P-2" in qs[0].question

    def test_sorted_by_severity_high_first(self):
        diffs = [
            _diff("labels",    "different", ["a"], ["b"]),   # baja
            _diff("priority",  "different", "H",   "L"),     # alta
            _diff("assignee",  "different", "Ana", "Bob"),   # media
        ]
        qs = generate_questions(_result(diffs))
        severities = [q.severity for q in qs]
        assert severities.index("alta") < severities.index("media")
        assert severities.index("media") < severities.index("baja")

    def test_global_question_when_many_diffs(self):
        diffs = [_diff(f"field_{i}", "different", "a", "b") for i in range(5)]
        qs = generate_questions(_result(diffs))
        assert any(q.field == "general" for q in qs)

    def test_no_global_question_when_few_diffs(self):
        diffs = [_diff("priority", "different", "H", "L")]
        qs = generate_questions(_result(diffs))
        assert not any(q.field == "general" for q in qs)

    def test_known_field_uses_specific_template(self):
        result = _result([_diff("status", "different", "Abierto", "En Progreso")])
        qs = generate_questions(result)
        q_text = qs[0].question.lower()
        # Template específico menciona "estados" o "sincronizados"
        assert "estado" in q_text or "sincroniz" in q_text

    def test_unknown_field_uses_generic_template(self):
        result = _result([_diff("customfield_99999", "different", "X", "Y")])
        qs = generate_questions(result)
        assert len(qs) == 1
        assert "diferenc" in qs[0].question.lower() or "distintos" in qs[0].question.lower()

    def test_values_appear_in_question_text(self):
        result = _result([_diff("priority", "different", "Alta", "Baja")])
        qs = generate_questions(result)
        assert "Alta" in qs[0].question
        assert "Baja" in qs[0].question

    def test_ticket_keys_appear_in_only_a_question(self):
        result = _result([_diff("duedate", "only_a", "2026-05-01", None)])
        qs = generate_questions(result)
        assert "P-1" in qs[0].question
        assert "P-2" in qs[0].question


# ── generate_questions: descripción ──────────────────────────────────────────

class TestDescriptionQuestions:
    def test_no_desc_result_no_desc_questions(self):
        result = _result([_diff("priority", "different", "H", "L")])
        qs = generate_questions(result, desc_result=None)
        assert not any(q.field == "description" for q in qs)

    def test_desc_no_diffs_no_desc_questions(self):
        result = _result([])
        desc   = _desc_result(different=0, only_a=0, only_b=0)
        qs = generate_questions(result, desc_result=desc)
        assert qs == []

    def test_desc_different_generates_question(self):
        result = _result([])
        desc   = _desc_result(different=2)
        qs = generate_questions(result, desc_result=desc)
        assert any(q.field == "description" and "2" in q.question for q in qs)

    def test_desc_only_a_generates_question(self):
        result = _result([])
        desc   = _desc_result(only_a=1)
        qs = generate_questions(result, desc_result=desc)
        assert any(q.field == "description" and "P-1" in q.question for q in qs)

    def test_desc_only_b_generates_question(self):
        result = _result([])
        desc   = _desc_result(only_b=3)
        qs = generate_questions(result, desc_result=desc)
        assert any(q.field == "description" and "P-2" in q.question for q in qs)

    def test_desc_questions_severity_alta(self):
        result = _result([])
        desc   = _desc_result(different=1)
        qs = generate_questions(result, desc_result=desc)
        desc_qs = [q for q in qs if q.field == "description"]
        assert all(q.severity == "alta" for q in desc_qs)

    def test_combined_fields_and_desc(self):
        result = _result([_diff("priority", "different", "H", "L")])
        desc   = _desc_result(different=1, only_a=1)
        qs = generate_questions(result, desc_result=desc)
        fields_in_qs = {q.field for q in qs}
        assert "priority" in fields_in_qs
        assert "description" in fields_in_qs
