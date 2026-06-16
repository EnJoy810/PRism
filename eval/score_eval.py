"""Score PRism eval runs against a small golden set.

Usage:
    python eval/score_eval.py --golden eval/prs_golden.yaml --run eval/runs/<run_id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "ERROR": 2}


def _load_yaml_list(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}")
    return data


def _load_result(run_dir: Path, sample_id: str) -> dict[str, Any]:
    result_path = run_dir / f"{sample_id}.json"
    error_path = run_dir / f"{sample_id}.error.json"
    if error_path.exists():
        return {"issues": [], "_eval_error": json.loads(error_path.read_text()).get("error", "unknown error")}
    payload = json.loads(result_path.read_text())
    result = payload.get("result", {})
    if not isinstance(result, dict):
        raise ValueError(f"Expected result object in {result_path}")
    return result


def _text_contains_any(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    normalized = text.casefold()
    return any(keyword.casefold() in normalized for keyword in keywords)


def _issue_text(issue: dict[str, Any]) -> str:
    evidence = issue.get("evidence") or []
    if isinstance(evidence, list):
        evidence_text = "\n".join(str(item) for item in evidence)
    else:
        evidence_text = str(evidence)
    return "\n".join(
        str(issue.get(field, ""))
        for field in ("title", "description", "impact_statement")
    ) + f"\n{evidence_text}"


def _severity_matches(issue: dict[str, Any], expected: dict[str, Any]) -> bool:
    expected_severity = expected.get("severity")
    if not expected_severity:
        return True
    issue_rank = SEVERITY_RANK.get(str(issue.get("severity", "INFO")).upper(), 0)
    expected_rank = SEVERITY_RANK.get(str(expected_severity).upper(), 0)
    return issue_rank >= expected_rank - 1


def _matches_expected(issue: dict[str, Any], expected: dict[str, Any]) -> bool:
    if issue.get("file") != expected.get("file"):
        return False

    line = issue.get("line")
    line_range = expected.get("line_range") or []
    if isinstance(line, int) and len(line_range) == 2:
        start, end = int(line_range[0]), int(line_range[1])
        if not start - 5 <= line <= end + 5:
            return False

    text = _issue_text(issue)
    title_ok = _text_contains_any(text, list(expected.get("title_keywords") or []))
    evidence_ok = _text_contains_any(text, list(expected.get("evidence_keywords") or []))
    # title OR evidence 匹配即可——LLM 用中文描述时 title keywords 可能不匹配但 evidence
    # （代码变量名）通常保留英文原文；两者满足其一已足够证明找到了同一个 bug
    if not (title_ok or evidence_ok):
        return False

    return _severity_matches(issue, expected)


def _needs_review(issue: dict[str, Any], expected: dict[str, Any]) -> bool:
    if issue.get("file") != expected.get("file"):
        return False

    line = issue.get("line")
    line_range = expected.get("line_range") or []
    near_line = False
    if isinstance(line, int) and len(line_range) == 2:
        start, end = int(line_range[0]), int(line_range[1])
        near_line = start - 20 <= line <= end + 20

    text = _issue_text(issue)
    shares_expected_text = _text_contains_any(text, list(expected.get("title_keywords") or [])) or _text_contains_any(
        text, list(expected.get("evidence_keywords") or [])
    )
    return near_line or shares_expected_text


def score_sample(sample: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    issues = result.get("issues") or []
    expected_findings = sample.get("expected_findings") or []
    matched_expected: set[str] = set()
    review_expected: set[str] = set()
    duplicate_count = 0
    noise_count = 0

    for issue in issues:
        expected_id = None
        review_id = None
        for expected in expected_findings:
            if _matches_expected(issue, expected):
                expected_id = str(expected["id"])
                break
            if review_id is None and _needs_review(issue, expected):
                review_id = str(expected["id"])

        if expected_id is None:
            if review_id is None:
                noise_count += 1
            else:
                review_expected.add(review_id)
        elif expected_id in matched_expected:
            duplicate_count += 1
        else:
            matched_expected.add(expected_id)

    expected_ids = {str(expected["id"]) for expected in expected_findings}
    misses = sorted(expected_ids - matched_expected)
    review_ids = sorted(review_expected - matched_expected)
    return {
        "sample_id": sample["id"],
        "expected_total": len(expected_findings),
        "issue_total": len(issues),
        "hit_count": len(matched_expected),
        "miss_count": len(misses),
        "review_count": len(review_ids),
        "noise_count": noise_count,
        "duplicate_count": duplicate_count,
        "clean_false_positives": noise_count if not expected_findings else 0,
        "hits": sorted(matched_expected),
        "misses": misses,
        "review": review_ids,
        "error": result.get("_eval_error", ""),
    }


def score_run(samples: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    sample_scores = [score_sample(sample, _load_result(run_dir, sample["id"])) for sample in samples]
    return {
        "samples": sample_scores,
        "totals": {
            "samples": len(sample_scores),
            "expected_total": sum(score["expected_total"] for score in sample_scores),
            "hit_count": sum(score["hit_count"] for score in sample_scores),
            "miss_count": sum(score["miss_count"] for score in sample_scores),
            "review_count": sum(score["review_count"] for score in sample_scores),
            "noise_count": sum(score["noise_count"] for score in sample_scores),
            "duplicate_count": sum(score["duplicate_count"] for score in sample_scores),
            "clean_false_positives": sum(score["clean_false_positives"] for score in sample_scores),
            "error_count": sum(1 for score in sample_scores if score["error"]),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    totals = report["totals"]
    lines = [
        "# PRism Eval Score",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| samples | {totals['samples']} |",
        f"| expected_total | {totals['expected_total']} |",
        f"| hit_count | {totals['hit_count']} |",
        f"| miss_count | {totals['miss_count']} |",
        f"| review_count | {totals['review_count']} |",
        f"| noise_count | {totals['noise_count']} |",
        f"| duplicate_count | {totals['duplicate_count']} |",
        f"| clean_false_positives | {totals['clean_false_positives']} |",
        f"| error_count | {totals['error_count']} |",
        "",
        "## Samples",
        "",
        "| sample | expected | hits | misses | review | noise | duplicate | error |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for score in report["samples"]:
        lines.append(
            f"| {score['sample_id']} | {score['expected_total']} | {score['hit_count']} | "
            f"{score['miss_count']} | {score['review_count']} | {score['noise_count']} | "
            f"{score['duplicate_count']} | {score['error']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a PRism eval run against a golden set")
    parser.add_argument("--golden", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()

    report = score_run(_load_yaml_list(Path(args.golden)), Path(args.run))
    print(render_markdown(report), end="")


if __name__ == "__main__":
    main()
