"""Tests for classify_hunk and filter_mechanical_hunks in diff.py."""

from app.services.diff import classify_hunk, filter_mechanical_hunks

# ---------------------------------------------------------------------------
# classify_hunk
# ---------------------------------------------------------------------------

class TestClassifyHunk:
    def test_pure_whitespace_change_is_mechanical(self):
        hunk = [
            "@@ -1,2 +1,2 @@",
            "    x = 1",
            "-  y = 2",
            "+    y = 2",
        ]
        assert classify_hunk(hunk) == "mechanical"

    def test_logical_change_is_not_mechanical(self):
        hunk = [
            "@@ -1,2 +1,2 @@",
            "    x = 1",
            "-  y = 2",
            "+    y = 3",
        ]
        assert classify_hunk(hunk) == "logical"

    def test_pure_rename_is_mechanical(self):
        """Renaming an identifier (same skeleton) is mechanical."""
        hunk = [
            "@@ -1,2 +1,2 @@",
            "-def old_name():",
            "+def new_name():",
        ]
        assert classify_hunk(hunk) == "mechanical"

    def test_pure_import_block_is_mechanical(self):
        hunk = [
            "@@ -1,3 +1,4 @@",
            " import os",
            "+import sys",
            " import re",
        ]
        assert classify_hunk(hunk) == "mechanical"

    def test_import_with_non_import_removed_is_logical(self):
        """If removed lines include non-import code, it's logical."""
        hunk = [
            "@@ -1,3 +1,3 @@",
            "-x = 1",
            "+import sys",
            " import re",
        ]
        assert classify_hunk(hunk) == "logical"

    def test_addition_only_logical(self):
        hunk = [
            "@@ -1,1 +1,2 @@",
            " x = 1",
            "+y = dangerous_call()",
        ]
        assert classify_hunk(hunk) == "logical"

    def test_empty_hunk_is_mechanical(self):
        assert classify_hunk(["@@ -1,1 +1,1 @@"]) == "mechanical"

    def test_jsdoc_comment_rename_is_mechanical(self):
        """Renaming inside a comment block — skeleton matches → mechanical."""
        hunk = [
            "@@ -1,3 +1,3 @@",
            " /**",
            "- * TODO(old): fix later",
            "+ * TODO(new): fix later",
            " */",
        ]
        assert classify_hunk(hunk) == "mechanical"

    def test_require_import_is_mechanical(self):
        hunk = [
            "@@ -1,2 +1,3 @@",
            " const fs = require('fs')",
            "+const path = require('path')",
            " module.exports = fs",
        ]
        assert classify_hunk(hunk) == "mechanical"

    def test_real_logic_change_not_mechanical_even_with_similar_structure(self):
        """Changing a value (not just identifier) is logical."""
        hunk = [
            "@@ -1,1 +1,1 @@",
            "-MAX_RETRIES = 3",
            "+MAX_RETRIES = 10",
        ]
        assert classify_hunk(hunk) == "logical"


# ---------------------------------------------------------------------------
# filter_mechanical_hunks
# ---------------------------------------------------------------------------

def _file_item(file: str, hunks_body: str) -> dict:
    """Build a file item with standard header."""
    header = f"diff --git a/{file} b/{file}\n--- a/{file}\n+++ b/{file}"
    return {"file": file, "diff": header + "\n" + hunks_body}


class TestFilterMechanicalHunks:
    def test_all_mechanical_file_is_skipped(self):
        items = [
            _file_item("a.py", "@@ -1,1 +1,1 @@\n-old_name()\n+new_name()"),
        ]
        result, skipped = filter_mechanical_hunks(items)
        assert result == []
        assert skipped == ["a.py"]

    def test_all_logical_file_is_kept(self):
        body = "@@ -1,1 +1,1 @@\n-x = 1\n+x = 2"
        items = [_file_item("a.py", body)]
        result, skipped = filter_mechanical_hunks(items)
        assert len(result) == 1
        assert result[0]["file"] == "a.py"
        assert skipped == []

    def test_mixed_hunks_keeps_logical_drops_mechanical(self):
        body = (
            "@@ -1,1 +1,1 @@\n"
            "-old_name()\n"
            "+new_name()\n"
            "@@ -10,1 +10,1 @@\n"
            "-x = 1\n"
            "+x = 2"
        )
        items = [_file_item("a.py", body)]
        result, skipped = filter_mechanical_hunks(items)
        assert len(result) == 1
        # Only the logical hunk should remain
        assert "x = 2" in result[0]["diff"]
        assert "new_name()" not in result[0]["diff"]
        assert skipped == []

    def test_multiple_files_partial_skip(self):
        items = [
            _file_item("a.py", "@@ -1,1 +1,1 @@\n-x = 1\n+x = 2"),
            _file_item("b.py", "@@ -1,1 +1,1 @@\n-old()\n+new()"),
        ]
        result, skipped = filter_mechanical_hunks(items)
        assert len(result) == 1
        assert result[0]["file"] == "a.py"
        assert skipped == ["b.py"]

    def test_no_hunks_passes_through(self):
        """A diff with no @@ hunks is kept as-is."""
        items = [{"file": "a.py", "diff": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"}]
        result, skipped = filter_mechanical_hunks(items)
        assert len(result) == 1
        assert skipped == []

    def test_empty_input(self):
        result, skipped = filter_mechanical_hunks([])
        assert result == []
        assert skipped == []

    def test_whitespace_only_hunk_dropped(self):
        body = "@@ -1,1 +1,1 @@\n-  x = 1\n+    x = 1"
        items = [_file_item("a.py", body)]
        result, skipped = filter_mechanical_hunks(items)
        assert result == []
        assert skipped == ["a.py"]
