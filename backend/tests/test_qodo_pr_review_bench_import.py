import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = ROOT / "eval" / "import_qodo_pr_review_bench.py"


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_qodo_pr_review_bench", IMPORTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_convert_row_keeps_functional_issues_and_filters_style():
    importer = _load_importer()
    row = {
        "repo": "Ghost",
        "pr_url_to_review": "https://github.com/agentic-review-benchmarks/Ghost/pull/1",
        "issues": [
            {
                "title": "Missing semicolon",
                "description": "The rule requires semicolons.",
                "file_path": "a.ts",
                "start_line": 1,
                "end_line": 1,
                "problematic_code_snippet": "const x = 1",
                "rule_name": "Code Must Always Use Semicolons",
            },
            {
                "title": "Missing optional chaining causes runtime error",
                "description": "The component can crash when openForm is undefined.",
                "file_path": "form.tsx",
                "start_line": 311,
                "end_line": 315,
                "problematic_code_snippet": "openForm.in_reply_to_snippet",
            },
        ],
    }

    sample = importer.convert_row(row, max_findings=2)

    assert sample is not None
    assert sample["id"] == "qodo-ghost-1"
    assert sample["repo"] == "agentic-review-benchmarks/Ghost"
    assert len(sample["expected_findings"]) == 1
    finding = sample["expected_findings"][0]
    assert finding["file"] == "form.tsx"
    assert finding["line_range"] == [311, 315]
    assert finding["source"] == "qodo-pr-review-bench-injected-issue"
