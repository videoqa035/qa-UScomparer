"""Tests for qa_uscomparer.description_diff module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qa_uscomparer.description_diff import (
    DescriptionDiffResult,
    PointDiff,
    _extract_points,
    _normalise,
    _strip_html,
    compare_descriptions,
)


# ── _strip_html ───────────────────────────────────────────────────────────────

class TestStripHtml:
    def test_removes_tags(self):
        assert "<p>" not in _strip_html("<p>Hello world</p>")

    def test_converts_br_to_newline(self):
        result = _strip_html("Line one<br/>Line two")
        assert "\n" in result
        assert "Line one" in result
        assert "Line two" in result

    def test_decodes_html_entities(self):
        result = _strip_html("&lt;item&gt; &amp; more &nbsp;text")
        assert "&lt;" not in result
        assert "<item>" in result
        assert "&" in result

    def test_handles_empty_string(self):
        assert _strip_html("") == ""

    def test_collapses_repeated_newlines(self):
        result = _strip_html("<p>A</p><p></p><p>B</p>")
        assert "\n\n" not in result


# ── _extract_points ───────────────────────────────────────────────────────────

class TestExtractPoints:
    def test_returns_list_of_strings(self):
        raw = "<p>El usuario puede ir al directo pulsando el botón ACEPTAR.</p>"
        pts = _extract_points(raw)
        assert isinstance(pts, list)
        assert len(pts) >= 1

    def test_deduplicates(self):
        raw = "<p>Mismo punto relevante aquí.</p><p>Mismo punto relevante aquí.</p>"
        pts = _extract_points(raw)
        assert len(pts) == 1

    def test_ignores_very_short_lines(self):
        raw = "<p>OK</p><p>Un punto largo y relevante con más de catorce caracteres.</p>"
        pts = _extract_points(raw)
        assert all(len(p) >= 14 for p in pts)

    def test_empty_description(self):
        assert _extract_points("") == []

    def test_none_like_string(self):
        assert _extract_points("None") == []


# ── _normalise ────────────────────────────────────────────────────────────────

class TestNormalise:
    def test_lowercases(self):
        assert _normalise("HELLO World") == "hello world"

    def test_strips_punctuation(self):
        result = _normalise("Hello, World!")
        assert "hello" in result
        assert "world" in result
        assert "," not in result
        assert "!" not in result

    def test_collapses_whitespace(self):
        assert "  " not in _normalise("a   b   c")


# ── compare_descriptions ──────────────────────────────────────────────────────

class TestCompareDescriptions:
    def _issue(self, key: str, description: str) -> dict:
        return {"key": key, "description": description}

    def test_returns_description_diff_result(self):
        a = self._issue("A-1", "<p>El usuario pulsa ACEPTAR para ir al directo.</p>")
        b = self._issue("B-1", "<p>El usuario pulsa ACEPTAR para ir al directo.</p>")
        result = compare_descriptions(a, b)
        assert isinstance(result, DescriptionDiffResult)

    def test_equal_descriptions_have_no_differences(self):
        desc = "<p>El usuario puede ver el pop-up de confirmación al finalizar el programa.</p>"
        a = self._issue("A-1", desc)
        b = self._issue("B-1", desc)
        result = compare_descriptions(a, b)
        assert not result.has_differences
        assert len(result.equal) >= 1

    def test_detects_only_a(self):
        a = self._issue(
            "A-1",
            "<p>Comportamiento exclusivo de CORE: mostrar toast con temporizador.</p>",
        )
        b = self._issue("B-1", "<p>Otro contenido completamente diferente sin relación.</p>")
        result = compare_descriptions(a, b)
        assert result.has_differences

    def test_detects_only_b(self):
        a = self._issue("A-1", "<p>Contenido distinto para la plataforma CORE sin más.</p>")
        b = self._issue(
            "B-1",
            "<p>Funcionalidad exclusiva de GO: pop-up no activable ni desactivable.</p>",
        )
        result = compare_descriptions(a, b)
        assert any(p.status == "only_b" for p in result.points)

    def test_detects_similar_but_different(self):
        a = self._issue(
            "A-1",
            "<p>Si el usuario no interactúa, se va al directo automáticamente tras el timeout.</p>",
        )
        b = self._issue(
            "B-1",
            "<p>Si el usuario no interactúa, se queda en timeshift automáticamente tras el timeout.</p>",
        )
        result = compare_descriptions(a, b)
        statuses = {p.status for p in result.points}
        assert "different" in statuses or "only_a" in statuses

    def test_empty_descriptions(self):
        result = compare_descriptions(
            self._issue("A-1", ""),
            self._issue("B-1", ""),
        )
        assert result.points == []

    def test_keys_are_preserved(self):
        result = compare_descriptions(
            self._issue("STV-999", "<p>Un punto funcional relevante para el sistema.</p>"),
            self._issue("GOSPECS-999", "<p>Otro punto funcional relevante para el sistema.</p>"),
        )
        assert result.key_a == "STV-999"
        assert result.key_b == "GOSPECS-999"


# ── DescriptionDiffResult convenience properties ──────────────────────────────

class TestDescriptionDiffResult:
    def _make(self, statuses: list[str]) -> DescriptionDiffResult:
        r = DescriptionDiffResult(key_a="A-1", key_b="B-1")
        for s in statuses:
            r.points.append(PointDiff(s, "text a", "text b", 0.9))
        return r

    def test_equal_property(self):
        r = self._make(["equal", "different", "only_a"])
        assert len(r.equal) == 1

    def test_different_property(self):
        r = self._make(["equal", "different", "only_b"])
        assert len(r.different) == 1

    def test_only_in_a(self):
        r = self._make(["only_a", "only_a", "equal"])
        assert len(r.only_in_a) == 2

    def test_only_in_b(self):
        r = self._make(["only_b", "equal"])
        assert len(r.only_in_b) == 1

    def test_has_differences_false_when_all_equal(self):
        r = self._make(["equal", "equal"])
        assert not r.has_differences

    def test_has_differences_true(self):
        r = self._make(["equal", "different"])
        assert r.has_differences
