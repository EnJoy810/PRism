from pathlib import Path

import pytest

from app.services.sast import _extract_added_lines, _find_semgrep, _parse_results, run_sast


def test_find_semgrep():
    path = _find_semgrep()
    assert path is not None
    assert Path(path).exists()


def test_parse_results_empty():
    assert _parse_results({}) == []


def test_extract_added_lines_from_diff():
    diff = """
diff --git a/src/app.py b/src/app.py
@@ -1,2 +1,3 @@
 import os
+subprocess.run(cmd, shell=True)
 unchanged
"""

    added = _extract_added_lines(diff)

    assert added == {"src/app.py": {2: "+subprocess.run(cmd, shell=True)"}}


def test_parse_results_with_finding():
    data = {
        "results": [
            {
                "check_id": "python.lang.security.audit.test-rule",
                "path": "/tmp/test.py",
                "start": {"line": 5},
                "extra": {
                    "message": "test finding",
                    "severity": "ERROR",
                },
            }
        ]
    }
    findings = _parse_results(data)
    assert len(findings) == 1
    assert findings[0]["title"] == "test-rule"
    assert findings[0]["severity"] == "ERROR"
    assert findings[0]["file"] == "/tmp/test.py"
    assert findings[0]["line"] == 5
    assert findings[0]["source"] == "sast"


def test_parse_results_keeps_same_rule_on_different_lines():
    data = {
        "results": [
            {
                "check_id": "rule1",
                "path": "/tmp/a.py",
                "start": {"line": 1},
                "extra": {"message": "a", "severity": "WARNING"},
            },
            {
                "check_id": "rule1",
                "path": "/tmp/a.py",
                "start": {"line": 5},
                "extra": {"message": "a", "severity": "WARNING"},
            },
        ]
    }
    findings = _parse_results(data)
    assert len(findings) == 2


def test_parse_results_dedups_same_rule_same_location():
    data = {
        "results": [
            {
                "check_id": "rule1",
                "path": "/tmp/a.py",
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {"message": "a", "severity": "WARNING"},
            },
            {
                "check_id": "rule1",
                "path": "/tmp/a.py",
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {"message": "a", "severity": "WARNING"},
            },
        ]
    }

    findings = _parse_results(data)

    assert len(findings) == 1


def test_parse_results_normalizes_absolute_path_to_repo_relative(tmp_path):
    src = tmp_path / "src/app.py"
    src.parent.mkdir(parents=True)
    src.write_text("subprocess.run(cmd, shell=True)\n")
    data = {
        "results": [
            {
                "check_id": "python.lang.security.audit.subprocess-shell-true",
                "path": str(src),
                "start": {"line": 1},
                "extra": {"message": "subprocess call", "severity": "ERROR"},
            }
        ]
    }

    findings = _parse_results(data, base_path=tmp_path)

    assert findings[0]["file"] == "src/app.py"


def test_parse_results_keeps_relative_path_with_base_path(tmp_path):
    data = {
        "results": [
            {
                "check_id": "rule1",
                "path": "src/app.py",
                "start": {"line": 1},
                "extra": {"message": "issue", "severity": "WARNING"},
            }
        ]
    }

    findings = _parse_results(data, base_path=tmp_path)

    assert findings[0]["file"] == "src/app.py"


def test_parse_results_evidence_uses_added_diff_line(tmp_path):
    src = tmp_path / "src/app.py"
    src.parent.mkdir(parents=True)
    src.write_text("subprocess.run(cmd, shell=True)\n")
    diff = """
diff --git a/src/app.py b/src/app.py
@@ -0,0 +1,1 @@
+subprocess.run(cmd, shell=True)
"""
    data = {
        "results": [
            {
                "check_id": "python.lang.security.audit.subprocess-shell-true",
                "path": str(src),
                "start": {"line": 1},
                "extra": {"message": "subprocess call", "severity": "ERROR"},
            }
        ]
    }

    findings = _parse_results(data, base_path=tmp_path, diff=diff)

    assert findings[0]["evidence"] == ["+subprocess.run(cmd, shell=True)"]
    assert findings[0]["evidence"][0] in diff


def test_parse_results_filters_finding_on_unchanged_line(tmp_path):
    src = tmp_path / "src/app.py"
    src.parent.mkdir(parents=True)
    src.write_text("old()\nnew()\n")
    diff = """
diff --git a/src/app.py b/src/app.py
@@ -1,1 +1,2 @@
 old()
+new()
"""
    data = {
        "results": [
            {
                "check_id": "rule1",
                "path": str(src),
                "start": {"line": 1},
                "extra": {"message": "old issue", "severity": "ERROR"},
            }
        ]
    }

    findings = _parse_results(data, base_path=tmp_path, diff=diff)

    assert findings == []


def test_parse_results_keeps_range_that_intersects_added_line(tmp_path):
    src = tmp_path / "src/app.py"
    src.parent.mkdir(parents=True)
    src.write_text("line1\nline2\nline3\n")
    diff = """
diff --git a/src/app.py b/src/app.py
@@ -1,2 +1,3 @@
 line1
+line2
 line3
"""
    data = {
        "results": [
            {
                "check_id": "rule1",
                "path": str(src),
                "start": {"line": 1},
                "end": {"line": 3},
                "extra": {"message": "range issue", "severity": "ERROR"},
            }
        ]
    }

    findings = _parse_results(data, base_path=tmp_path, diff=diff)

    assert len(findings) == 1
    assert findings[0]["line"] == 2
    assert findings[0]["evidence"] == ["+line2"]


def test_quality_scan_sets_quality_category():
    data = {
        "results": [
            {
                "check_id": "typescript.react.best-practice.no-array-index-key",
                "path": "/tmp/app.tsx",
                "start": {"line": 1},
                "extra": {"message": "avoid array index key", "severity": "WARNING"},
            }
        ]
    }

    findings = _parse_results(data, category="quality")

    assert findings[0]["category"] == "quality"


@pytest.mark.asyncio
async def test_run_sast_security(tmp_path):
    src = tmp_path / "app.py"
    src.write_text("import subprocess\ndef run():\n    subprocess.run('ls', shell=True)\n")
    findings = await run_sast([str(src)], "security")
    assert isinstance(findings, list)


@pytest.mark.asyncio
async def test_run_sast_no_files():
    findings = await run_sast([], "security")
    assert findings == []


@pytest.mark.asyncio
async def test_run_sast_nonexistent_file():
    findings = await run_sast(["/tmp/nonexistent_file_xyz.py"], "security")
    assert findings == []
