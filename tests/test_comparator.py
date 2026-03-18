"""Tests for qa_uscomparer.comparator module."""

import pytest

from qa_uscomparer.comparator import (
    ComparisonResult,
    FieldDiff,
    _normalise_value,
    compare_tickets,
)


class TestNormaliseValue:
    def test_none_returns_none(self):
        assert _normalise_value(None) is None

    def test_blank_string_returns_none(self):
        assert _normalise_value("   ") is None

    def test_string_stripped(self):
        assert _normalise_value("  hello  ") == "hello"

    def test_list_sorted(self):
        assert _normalise_value(["z", "a", "m"]) == ["a", "m", "z"]

    def test_nested_dict(self):
        result = _normalise_value({"b": "2", "a": "1"})
        assert result == {"a": "1", "b": "2"}

    def test_scalar_unchanged(self):
        assert _normalise_value(42) == 42


class TestCompareTickets:
    def test_equal_fields_detected(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b)
        equal = {d.field_name for d in result.equal_fields}
        # These are the same in both fixtures
        assert "issuetype" in equal
        assert "assignee" in equal
        assert "resolution" in equal
        assert "fixVersions" in equal

    def test_different_fields_detected(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b)
        diff_fields = {d.field_name for d in result.different_fields}
        assert "summary" in diff_fields
        assert "status" in diff_fields
        assert "priority" in diff_fields
        assert "description" in diff_fields
        assert "environment" in diff_fields

    def test_comparison_keys(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b)
        assert result.key_a == "PROJ-101"
        assert result.key_b == "PROJ-102"

    def test_has_differences_true(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b)
        assert result.has_differences is True

    def test_identical_issues_no_diff(self):
        issue = {
            "key": "X-1", "id": "1", "self": "",
            "summary": "Test", "status": "Open",
        }
        result = compare_tickets(issue, dict(issue) | {"key": "X-2"})
        assert result.has_differences is False
        assert result.equal_fields

    def test_field_filter(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b, fields=["status", "summary"])
        compared_names = {d.field_name for d in result.diffs}
        assert compared_names == {"status", "summary"}

    def test_only_in_a(self):
        a = {"key": "A-1", "id": "1", "self": "", "unique_a": "only here"}
        b = {"key": "B-1", "id": "2", "self": ""}
        result = compare_tickets(a, b)
        only_a = {d.field_name for d in result.only_in_a}
        assert "unique_a" in only_a

    def test_only_in_b(self):
        a = {"key": "A-1", "id": "1", "self": ""}
        b = {"key": "B-1", "id": "2", "self": "", "unique_b": "only here"}
        result = compare_tickets(a, b)
        only_b = {d.field_name for d in result.only_in_b}
        assert "unique_b" in only_b

    def test_skip_metadata_fields(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b)
        compared_names = {d.field_name for d in result.diffs}
        # These internal fields should be excluded
        for meta in ("key", "id", "self"):
            assert meta not in compared_names

    def test_result_is_comparison_result(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b)
        assert isinstance(result, ComparisonResult)

    def test_field_diff_structure(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b)
        for d in result.diffs:
            assert isinstance(d, FieldDiff)
            assert d.status in {"equal", "different", "only_a", "only_b"}

    def test_whitespace_insensitive(self):
        a = {"key": "A-1", "id": "1", "self": "", "summary": "  Hello World  "}
        b = {"key": "B-1", "id": "2", "self": "", "summary": "Hello World"}
        result = compare_tickets(a, b)
        eq = {d.field_name for d in result.equal_fields}
        assert "summary" in eq

    def test_list_order_insensitive(self):
        a = {"key": "A-1", "id": "1", "self": "", "labels": ["b", "a", "c"]}
        b = {"key": "B-1", "id": "2", "self": "", "labels": ["a", "b", "c"]}
        result = compare_tickets(a, b)
        eq = {d.field_name for d in result.equal_fields}
        assert "labels" in eq

    def test_story_points_differ(self, sample_issue_a, sample_issue_b):
        result = compare_tickets(sample_issue_a, sample_issue_b)
        diff_fields = {d.field_name for d in result.different_fields}
        assert "customfield_10016" in diff_fields
