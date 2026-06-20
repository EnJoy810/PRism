import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPORT_PATH = ROOT / "eval" / "import_swe_prbench.py"


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_swe_prbench", IMPORT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_convert_row_filters_bot_and_line_missing_comments():
    importer = _load_importer()
    row = {
        "task_id": "sqlfluff__7294",
        "repo": "sqlfluff/sqlfluff",
        "pr_url": "https://github.com/sqlfluff/sqlfluff/pull/7294",
        "language": "Python",
        "difficulty": "Type1_Direct",
        "human_review_comments": [
            {
                "author": "human-reviewer",
                "body": "This condition can cause a runtime error because the parser branch is skipped when dialect is unset.",
                "path": "src/sqlfluff/core/parser.py",
                "line": 42,
                "diffHunk": "@@ -40,3 +40,4 @@\n+result = parse_segments(raw_stack)",
            },
            {
                "author": "gemini-code-assist",
                "body": "Bot generated comment that should not be used.",
                "path": "src/sqlfluff/core/parser.py",
                "line": 43,
            },
            {
                "author": "human-reviewer",
                "body": "File-level comment without a precise target.",
                "path": "src/sqlfluff/core/parser.py",
                "line": None,
            },
        ],
    }

    sample = importer.convert_row(row, max_findings=3)

    assert sample is not None
    assert sample["id"] == "sqlfluff__7294"
    assert sample["url"] == "https://github.com/sqlfluff/sqlfluff/pull/7294"
    assert len(sample["expected_findings"]) == 1
    finding = sample["expected_findings"][0]
    assert finding["id"] == "sqlfluff__7294-c1"
    assert finding["file"] == "src/sqlfluff/core/parser.py"
    assert finding["line_range"] == [42, 42]
    assert "parser" in finding["evidence_keywords"]
    assert "parse_segments" in finding["evidence_keywords"]
    assert finding["source"] == "swe-prbench-human-review"


def test_convert_row_requires_python_and_expected_findings():
    importer = _load_importer()
    non_python = {
        "task_id": "repo__1",
        "repo": "owner/repo",
        "pr_url": "https://github.com/owner/repo/pull/1",
        "language": "TypeScript",
        "human_review_comments": [
            {"author": "human", "body": "Real comment with useful words", "path": "a.ts", "line": 1}
        ],
    }
    no_precise_comments = {
        "task_id": "repo__2",
        "repo": "owner/repo",
        "pr_url": "https://github.com/owner/repo/pull/2",
        "language": "Python",
        "human_review_comments": [
            {"author": "human", "body": "File level only", "path": "a.py", "line": None}
        ],
    }

    assert importer.convert_row(non_python, max_findings=3) is None
    assert importer.convert_row(no_precise_comments, max_findings=3) is None


def test_convert_row_filters_low_signal_human_comments():
    importer = _load_importer()
    row = {
        "task_id": "agents__4099",
        "repo": "livekit/agents",
        "pr_url": "https://github.com/livekit/agents/pull/4099",
        "language": "Python",
        "human_review_comments": [
            {"author": "human", "body": "could you add some docs for this?", "path": "a.py", "line": 1},
            {"author": "human", "body": "This is irrelevant for this PR.", "path": "b.py", "line": 2},
            {"author": "human", "body": "Why would tx_info ever be None here?", "path": "c.py", "line": 3},
            {"author": "human", "body": "Correct me if I'm wrong, but this looks redundant.", "path": "d.py", "line": 4},
            {
                "author": "human",
                "body": "This can break existing callers because None is now passed into the serializer.",
                "path": "e.py",
                "line": 5,
            },
        ],
    }

    sample = importer.convert_row(row, max_findings=3)

    assert sample is not None
    assert len(sample["expected_findings"]) == 1
    assert sample["expected_findings"][0]["file"] == "e.py"
