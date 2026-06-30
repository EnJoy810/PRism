"""Tests for hunk-aware matching and miss reason classification in score_eval.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))

import pytest
from score_eval import (
    _classify_miss,
    _hunk_index,
    _line_in_same_hunk,
    _matches_expected,
    _parse_hunks_by_file,
    score_sample,
)

# ---------------------------------------------------------------------------
# Fixtures — a minimal unified diff with two files and two hunks each
# ---------------------------------------------------------------------------

SAMPLE_DIFF = """\
diff --git a/foo.py b/foo.py
index 1234567..abcdefg 100644
--- a/foo.py
+++ b/foo.py
@@ -10,6 +10,8 @@ def old():
     x = 1
+    y = 2
+    z = 3
     return x
@@ -50,4 +52,6 @@ def other():
     a = 1
+    b = 2
+    c = 3
+    d = 4
     return a
diff --git a/bar.py b/bar.py
index 0000000..1111111 100644
--- a/bar.py
+++ b/bar.py
@@ -1,3 +1,5 @@ def entry():
     pass
+    x = bad_call()
+    y = another()
     return
"""


@pytest.fixture()
def hunks():
    return _parse_hunks_by_file(SAMPLE_DIFF)


# ---------------------------------------------------------------------------
# _parse_hunks_by_file
# ---------------------------------------------------------------------------

class TestParseHunksByFile:
    def test_two_files_parsed(self, hunks):
        assert "foo.py" in hunks
        assert "bar.py" in hunks

    def test_foo_has_two_hunks(self, hunks):
        assert len(hunks["foo.py"]) == 2

    def test_bar_has_one_hunk(self, hunks):
        assert len(hunks["bar.py"]) == 1

    def test_first_hunk_start(self, hunks):
        start, _ = hunks["foo.py"][0]
        assert start == 10

    def test_second_hunk_start(self, hunks):
        start, _ = hunks["foo.py"][1]
        assert start == 52

    def test_empty_diff(self):
        assert _parse_hunks_by_file("") == {}

    def test_git_b_prefix_stripped(self, hunks):
        # Path should not contain "b/" prefix
        for key in hunks:
            assert not key.startswith("b/")


# ---------------------------------------------------------------------------
# _hunk_index
# ---------------------------------------------------------------------------

class TestHunkIndex:
    def test_line_inside_first_hunk(self, hunks):
        assert _hunk_index(11, hunks["foo.py"]) == 0

    def test_line_inside_second_hunk(self, hunks):
        assert _hunk_index(54, hunks["foo.py"]) == 1

    def test_line_between_hunks_returns_none(self, hunks):
        # Line 30 is between the two foo.py hunks
        assert _hunk_index(30, hunks["foo.py"]) is None

    def test_slack_at_boundary(self, hunks):
        # hunk 0 ends at 10+8-1=17 roughly; line just after end should still match with +1 slack
        start, end = hunks["foo.py"][0]
        assert _hunk_index(end + 1, hunks["foo.py"]) == 0

    def test_empty_hunks(self):
        assert _hunk_index(5, []) is None


# ---------------------------------------------------------------------------
# _line_in_same_hunk
# ---------------------------------------------------------------------------

class TestLineInSameHunk:
    def test_same_hunk_match(self, hunks):
        foo_hunks = hunks["foo.py"]
        start, end = foo_hunks[0]
        assert _line_in_same_hunk(start + 1, start, end, foo_hunks)

    def test_different_hunk_no_match(self, hunks):
        foo_hunks = hunks["foo.py"]
        h0_start, h0_end = foo_hunks[0]
        h1_start, h1_end = foo_hunks[1]
        assert not _line_in_same_hunk(h1_start + 1, h0_start, h0_end, foo_hunks)

    def test_pred_line_outside_any_hunk(self, hunks):
        foo_hunks = hunks["foo.py"]
        h0_start, h0_end = foo_hunks[0]
        assert not _line_in_same_hunk(999, h0_start, h0_end, foo_hunks)


# ---------------------------------------------------------------------------
# _matches_expected — hunk-aware vs ±5 fallback
# ---------------------------------------------------------------------------

class TestMatchesExpected:
    def _issue(self, file: str, line: int) -> dict:
        return {"file": file, "line": line, "severity": "ERROR",
                "title": "bug", "description": "desc", "impact_statement": ""}

    def _golden(self, file: str, line_range: list[int]) -> dict:
        return {"file": file, "line_range": line_range, "severity": "ERROR",
                "title_keywords": [], "evidence_keywords": []}

    def test_same_hunk_is_match(self, hunks):
        issue = self._issue("foo.py", 11)    # hunk 0: lines ~10-17
        golden = self._golden("foo.py", [10, 10])
        assert _matches_expected(issue, golden, hunks)

    def test_different_hunk_is_miss(self, hunks):
        issue = self._issue("foo.py", 54)    # hunk 1
        golden = self._golden("foo.py", [10, 10])  # hunk 0
        assert not _matches_expected(issue, golden, hunks)

    def test_fallback_plus_minus_5_hit(self):
        issue = self._issue("baz.py", 23)
        golden = self._golden("baz.py", [20, 22])
        assert _matches_expected(issue, golden, hunks_by_file=None)

    def test_fallback_plus_minus_5_miss(self):
        issue = self._issue("baz.py", 30)
        golden = self._golden("baz.py", [20, 22])
        assert not _matches_expected(issue, golden, hunks_by_file=None)

    def test_file_mismatch_always_fails(self, hunks):
        issue = self._issue("other.py", 11)
        golden = self._golden("foo.py", [10, 10])
        assert not _matches_expected(issue, golden, hunks)

    def test_no_line_in_issue_matches_without_line_gate(self, hunks):
        issue = {"file": "foo.py", "line": None, "severity": "ERROR",
                 "title": "bug", "description": "desc", "impact_statement": ""}
        golden = self._golden("foo.py", [10, 10])
        # No line → line gate skipped → should match on text (keywords empty = always True)
        assert _matches_expected(issue, golden, hunks)


# ---------------------------------------------------------------------------
# _classify_miss
# ---------------------------------------------------------------------------

class TestClassifyMiss:
    def _golden(self, file="foo.py", line_range=None):
        return {"file": file, "line_range": line_range or [10, 12],
                "severity": "ERROR", "title_keywords": [], "evidence_keywords": []}

    def _issue(self, file="foo.py", line=11, severity="ERROR"):
        return {"file": file, "line": line, "severity": severity,
                "title": "t", "description": "d", "impact_statement": ""}

    def test_not_detected_when_no_same_file(self, hunks):
        golden = self._golden("foo.py")
        issues = [self._issue("bar.py")]
        assert _classify_miss(golden, issues, hunks) == "not_detected"

    def test_not_detected_when_no_issues(self, hunks):
        golden = self._golden("foo.py")
        assert _classify_miss(golden, [], hunks) == "not_detected"

    def test_line_offset_same_file_wrong_hunk(self, hunks):
        # Issue in hunk 1 (line 54), golden in hunk 0
        golden = self._golden("foo.py", [10, 12])
        issues = [self._issue("foo.py", 54)]
        assert _classify_miss(golden, issues, hunks) == "line_offset"

    def test_severity_miss(self, hunks):
        # Issue on same file/hunk but INFO severity vs ERROR expected
        golden = self._golden("foo.py", [10, 12])
        issues = [self._issue("foo.py", 11, severity="INFO")]
        assert _classify_miss(golden, issues, hunks) == "severity_miss"


# ---------------------------------------------------------------------------
# score_sample integration
# ---------------------------------------------------------------------------

class TestScoreSample:
    def _make_sample(self, golden_line_range, diff=SAMPLE_DIFF):
        return {
            "id": "test-1",
            "url": "https://github.com/x/y/pull/1",
            "synthetic_diff": diff,
            "expected_findings": [
                {"id": "f1", "file": "foo.py", "line_range": golden_line_range,
                 "severity": "ERROR", "title_keywords": [], "evidence_keywords": []}
            ],
        }

    def _make_result(self, pred_line):
        return {
            "issues": [
                {"file": "foo.py", "line": pred_line, "severity": "ERROR",
                 "title": "bug", "description": "d", "impact_statement": "", "evidence": []}
            ]
        }

    def test_hit_same_hunk(self):
        sample = self._make_sample([10, 12])
        hunks = _parse_hunks_by_file(SAMPLE_DIFF)
        result = self._make_result(11)
        score = score_sample(sample, result, hunks)
        assert score["hit_count"] == 1
        assert score["miss_count"] == 0

    def test_miss_different_hunk(self):
        sample = self._make_sample([10, 12])
        hunks = _parse_hunks_by_file(SAMPLE_DIFF)
        result = self._make_result(54)  # hunk 1
        score = score_sample(sample, result, hunks)
        assert score["hit_count"] == 0
        assert score["miss_count"] == 1
        assert score["miss_reasons"]["f1"] == "line_offset"

    def test_miss_reason_not_detected(self):
        sample = self._make_sample([10, 12])
        hunks = _parse_hunks_by_file(SAMPLE_DIFF)
        result = {"issues": []}
        score = score_sample(sample, result, hunks)
        assert score["miss_reasons"]["f1"] == "not_detected"

    def test_miss_reason_counts_aggregated(self):
        sample = self._make_sample([10, 12])
        hunks = _parse_hunks_by_file(SAMPLE_DIFF)
        result = {"issues": []}
        score = score_sample(sample, result, hunks)
        assert score["miss_reason_counts"].get("not_detected", 0) == 1
