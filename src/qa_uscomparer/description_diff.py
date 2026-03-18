"""Functional diff of the description field between two Jira issues.

Pipeline
--------
1. Strip HTML from raw Jira description (keeps plain text + structure).
2. Split into individual functional *points* (paragraphs / list items).
3. Match points between the two tickets using fuzzy string similarity.
4. Classify each point as:
   - ``equal``        – same concept, same (normalised) text.
   - ``different``    – same concept, different wording.
   - ``only_a``       – only present in ticket A.
   - ``only_b``       – only present in ticket B.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PointDiff:
    """Comparison result for a single functional point."""

    status: str          # "equal" | "different" | "only_a" | "only_b"
    point_a: str         # text from ticket A (empty when only_b)
    point_b: str         # text from ticket B (empty when only_a)
    similarity: float    # 0-1 similarity score (1.0 when equal)


@dataclass
class DescriptionDiffResult:
    """Full functional diff of two ticket descriptions."""

    key_a: str
    key_b: str
    points: list[PointDiff] = field(default_factory=list)

    # ── Convenience views ────────────────────────────────────────────────────

    @property
    def equal(self) -> list[PointDiff]:
        return [p for p in self.points if p.status == "equal"]

    @property
    def different(self) -> list[PointDiff]:
        return [p for p in self.points if p.status == "different"]

    @property
    def only_in_a(self) -> list[PointDiff]:
        return [p for p in self.points if p.status == "only_a"]

    @property
    def only_in_b(self) -> list[PointDiff]:
        return [p for p in self.points if p.status == "only_b"]

    @property
    def has_differences(self) -> bool:
        return bool(self.different or self.only_in_a or self.only_in_b)


# ── Public API ────────────────────────────────────────────────────────────────

# Similarity threshold – pairs above this are considered "same concept".
_MATCH_THRESHOLD = 0.72


def compare_descriptions(
    issue_a: dict[str, Any],
    issue_b: dict[str, Any],
) -> DescriptionDiffResult:
    """Extract and compare functional points from two issue descriptions.

    Parameters
    ----------
    issue_a / issue_b:
        Normalised issue dicts as returned by ``JiraFetcher.fetch_issue()``.
    """
    result = DescriptionDiffResult(
        key_a=issue_a.get("key", "TICKET_A"),
        key_b=issue_b.get("key", "TICKET_B"),
    )

    points_a = _extract_points(str(issue_a.get("description") or ""))
    points_b = _extract_points(str(issue_b.get("description") or ""))

    norm_b = [_normalise(p) for p in points_b]
    used_b: set[int] = set()

    for pa in points_a:
        na = _normalise(pa)
        best_j, best_score = _best_match(na, norm_b, used_b)

        if best_j == -1:
            result.points.append(PointDiff("only_a", pa, "", 0.0))
            continue

        pb = points_b[best_j]
        nb = norm_b[best_j]

        if na == nb:
            result.points.append(PointDiff("equal", pa, pb, 1.0))
            used_b.add(best_j)
            continue

        if best_score >= _MATCH_THRESHOLD:
            result.points.append(PointDiff("different", pa, pb, best_score))
            used_b.add(best_j)
        else:
            result.points.append(PointDiff("only_a", pa, "", 0.0))

    for j, pb in enumerate(points_b):
        if j not in used_b:
            result.points.append(PointDiff("only_b", "", pb, 0.0))

    return result


# ── HTML → plain text ─────────────────────────────────────────────────────────

def _strip_html(raw: str) -> str:
    """Convert raw Jira HTML description to structured plain text."""
    # Block-level tags → newline
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = re.sub(r"</p>|</li>|</h\d>|</pre>|</div>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities
    text = html.unescape(text)
    text = text.replace("\xa0", " ").replace("\r", "\n")
    # Collapse repeated blank lines
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


# ── Point extraction ──────────────────────────────────────────────────────────

_MIN_POINT_LEN = 14   # ignore very short fragments (section titles, labels)


def _extract_points(description: str) -> list[str]:
    """Split a description into a deduplicated list of functional points."""
    raw_lines: list[str] = []
    for line in _strip_html(description).split("\n"):
        line = line.strip(" \t-*•")
        if not line:
            continue
        # Split inline numbered / bullet sub-items
        parts = re.split(r"\s(?:\d+\.\s|-\s|•\s)", line)
        for part in parts:
            part = part.strip(" ;:-\t")
            if len(part) >= _MIN_POINT_LEN:
                raw_lines.append(part)

    seen: set[str] = set()
    unique: list[str] = []
    for line in raw_lines:
        norm = _normalise(line)
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(line)
    return unique


# ── Normalisation / matching ──────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lower-case + keep only alphanumeric + Spanish chars for comparison."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9áéíóúüñ\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _best_match(
    needle: str,
    haystack: list[str],
    excluded: set[int],
) -> tuple[int, float]:
    """Return (index, score) of the best fuzzy match in *haystack* for *needle*."""
    best_j, best_score = -1, 0.0
    for j, candidate in enumerate(haystack):
        if j in excluded:
            continue
        score = SequenceMatcher(None, needle, candidate).ratio()
        if score > best_score:
            best_j, best_score = j, score
    return best_j, best_score
