"""Comparison logic: field-by-field diff of two normalised Jira issue dicts.

Returns a ``ComparisonResult`` that holds one ``FieldDiff`` per compared field,
classified as "equal", "different", "only_a", or "only_b".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class FieldDiff:
    """Difference (or equality) of a single field between two issues."""

    field_name: str
    value_a: Any
    value_b: Any
    status: str  # "equal" | "different" | "only_a" | "only_b"


@dataclass
class ComparisonResult:
    """Full comparison of two Jira issues."""

    key_a: str
    key_b: str
    diffs: list[FieldDiff] = field(default_factory=list)

    # ── Convenience views ────────────────────────────────────────────────────

    @property
    def equal_fields(self) -> list[FieldDiff]:
        return [d for d in self.diffs if d.status == "equal"]

    @property
    def different_fields(self) -> list[FieldDiff]:
        return [d for d in self.diffs if d.status == "different"]

    @property
    def only_in_a(self) -> list[FieldDiff]:
        return [d for d in self.diffs if d.status == "only_a"]

    @property
    def only_in_b(self) -> list[FieldDiff]:
        return [d for d in self.diffs if d.status == "only_b"]

    @property
    def has_differences(self) -> bool:
        return bool(self.different_fields or self.only_in_a or self.only_in_b)


# ── Constants ─────────────────────────────────────────────────────────────────

# Metadata fields that are inherently different between any two tickets.
_SKIP_FIELDS = {"key", "id", "self"}

# Canonical display order (most relevant first); remaining fields are sorted
# alphabetically.
_FIELD_ORDER = [
    "summary",
    "issuetype",
    "status",
    "priority",
    "assignee",
    "reporter",
    "labels",
    "components",
    "fixVersions",
    "versions",
    "description",
    "environment",
    "duedate",
    "customfield_10016",   # Story Points (Cloud)
    "customfield_10028",   # Story Points (DC)
    "customfield_10014",   # Epic Link
    "customfield_10020",   # Sprint
    "parent",
    "subtasks",
    "resolution",
    "resolutiondate",
    "created",
    "updated",
    "project",
]


# ── Public API ────────────────────────────────────────────────────────────────

def compare_tickets(
    issue_a: dict[str, Any],
    issue_b: dict[str, Any],
    fields: list[str] | None = None,
) -> ComparisonResult:
    """Compare two normalised Jira issue dicts and return a ``ComparisonResult``.

    Parameters
    ----------
    issue_a / issue_b:
        Flat ``{field: value}`` dicts as returned by ``JiraFetcher.fetch_issue()``.
    fields:
        Optional allow-list of field names to compare.  All fields are compared
        when ``None``.
    """
    result = ComparisonResult(
        key_a=issue_a.get("key", "TICKET_A"),
        key_b=issue_b.get("key", "TICKET_B"),
    )

    active_keys = (set(issue_a.keys()) | set(issue_b.keys())) - _SKIP_FIELDS
    if fields:
        active_keys = active_keys & set(fields)

    def _sort_key(k: str) -> tuple[int, str]:
        try:
            return (_FIELD_ORDER.index(k), k)
        except ValueError:
            return (len(_FIELD_ORDER), k)

    for key in sorted(active_keys, key=_sort_key):
        val_a = issue_a.get(key)
        val_b = issue_b.get(key)
        in_a = key in issue_a
        in_b = key in issue_b

        if in_a and not in_b:
            status = "only_a"
        elif in_b and not in_a:
            status = "only_b"
        elif _normalise_value(val_a) == _normalise_value(val_b):
            status = "equal"
        else:
            status = "different"

        result.diffs.append(FieldDiff(key, val_a, val_b, status))

    return result


# ── Normalisation helpers ─────────────────────────────────────────────────────

def _normalise_value(value: Any) -> Any:
    """Normalise a field value so that trivial differences do not count as diffs.

    * Strips leading / trailing whitespace from strings (empty → ``None``).
    * Sorts lists so order differences are ignored.
    * Recurses into dicts.
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    if isinstance(value, list):
        return sorted(str(_normalise_value(v)) for v in value)
    if isinstance(value, dict):
        return {k: _normalise_value(v) for k, v in sorted(value.items())}
    return value
