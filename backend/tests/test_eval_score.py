import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCORE_EVAL_PATH = ROOT / "eval" / "score_eval.py"


def _load_score_eval():
    spec = importlib.util.spec_from_file_location("score_eval", SCORE_EVAL_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_score_sample_matches_expected_finding_once():
    score_eval = _load_score_eval()
    sample = {
        "id": "pydantic-10500",
        "expected_findings": [
            {
                "id": "duplicate-test-name",
                "file": "tests/test_types.py",
                "line_range": [7015, 7025],
                "title_keywords": ["命名冲突"],
                "evidence_keywords": ["test_base64_with_invalid_min_length"],
                "severity": "ERROR",
            }
        ],
    }
    result = {
        "issues": [
            {
                "file": "tests/test_types.py",
                "line": 7020,
                "title": "测试函数命名冲突导致现有参数化测试被覆盖",
                "severity": "ERROR",
                "evidence": ["def test_base64_with_invalid_min_length() -> None:"],
            }
        ]
    }

    score = score_eval.score_sample(sample, result)

    assert score["expected_total"] == 1
    assert score["hit_count"] == 1
    assert score["miss_count"] == 0
    assert score["noise_count"] == 0
    assert score["duplicate_count"] == 0
    assert score["hits"] == ["duplicate-test-name"]


def test_score_sample_counts_duplicate_and_noise():
    score_eval = _load_score_eval()
    sample = {
        "id": "pydantic-10500",
        "expected_findings": [
            {
                "id": "duplicate-test-name",
                "file": "tests/test_types.py",
                "line_range": [7015, 7025],
                "title_keywords": ["命名冲突"],
                "evidence_keywords": ["test_base64_with_invalid_min_length"],
            }
        ],
    }
    matching_issue = {
        "file": "tests/test_types.py",
        "line": 7020,
        "title": "测试函数命名冲突",
        "evidence": ["def test_base64_with_invalid_min_length() -> None:"],
    }
    result = {
        "issues": [
            matching_issue,
            dict(matching_issue),
            {
                "file": "tests/test_types.py",
                "line": 10,
                "title": "Unrelated style issue",
                "evidence": ["x = 1"],
            },
        ]
    }

    score = score_eval.score_sample(sample, result)

    assert score["hit_count"] == 1
    assert score["noise_count"] == 1
    assert score["duplicate_count"] == 1


def test_score_sample_marks_near_miss_for_review():
    score_eval = _load_score_eval()
    sample = {
        "id": "prowler-9876",
        "expected_findings": [
            {
                "id": "empty-except",
                "file": "service.py",
                "line_range": [41, 41],
                "title_keywords": ["Empty except"],
                "evidence_keywords": ["audit_config"],
            }
        ],
    }
    result = {
        "issues": [
            {
                "file": "service.py",
                "line": 32,
                "title": "异常被静默忽略",
                "evidence": ["except Exception:", "    pass"],
            }
        ]
    }

    score = score_eval.score_sample(sample, result)

    assert score["hit_count"] == 0
    assert score["miss_count"] == 1
    assert score["review_count"] == 1
    assert score["noise_count"] == 0
    assert score["review"] == ["empty-except"]


def test_score_sample_counts_clean_pr_noise():
    score_eval = _load_score_eval()
    sample = {"id": "fastapi-14789", "expected_findings": []}
    result = {
        "issues": [
            {
                "file": "a.py",
                "line": 1,
                "title": "False positive",
                "evidence": ["x"],
            }
        ]
    }

    score = score_eval.score_sample(sample, result)

    assert score["expected_total"] == 0
    assert score["hit_count"] == 0
    assert score["noise_count"] == 1
    assert score["clean_false_positives"] == 1
