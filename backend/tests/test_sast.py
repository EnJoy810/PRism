from pathlib import Path

import pytest

from app.services.sast import _find_semgrep, _parse_results, run_sast


def test_find_semgrep():
    path = _find_semgrep()
    assert path is not None
    assert Path(path).exists()


def test_parse_results_empty():
    assert _parse_results({}) == []


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


def test_parse_results_dedup():
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
    assert len(findings) == 1


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
