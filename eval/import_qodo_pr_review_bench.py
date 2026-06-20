"""Import a small Qodo PR-Review-Bench slice into PRism's eval format.

Usage:
    python eval/import_qodo_pr_review_bench.py --limit 3 --out eval/prs_qodo_sample.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

import yaml

DATASET_URL = "https://huggingface.co/datasets/Qodo/PR-Review-Bench/raw/main/git_code_review_bench_100_w_open_prs.jsonl"

STYLE_MARKERS = (
    "class order",
    "double quotes",
    "indentation",
    "license header",
    "line exceeds",
    "missing semicolon",
    "naming",
    "single quotes",
    "tailwind",
    "var keyword",
)
RISK_MARKERS = (
    "broken",
    "crash",
    "error",
    "exception",
    "fail",
    "incorrect",
    "leak",
    "missing required",
    "non-functional",
    "race condition",
    "runtime",
    "security",
    "stale",
    "undefined",
    "wrong",
)


def _keywords(text: str, path: str | None = None) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text)
    keywords: list[str] = []
    for word in words:
        lowered = word.casefold()
        if lowered in {"this", "that", "with", "from", "will", "when", "should", "would", "could", "cause"}:
            continue
        if word not in keywords:
            keywords.append(word)
        if len(keywords) >= 3:
            break
    if path:
        stem = Path(path).stem
        if stem and stem not in keywords:
            keywords.append(stem)
    return keywords[:4]


def _is_functional_issue(issue: dict[str, Any]) -> bool:
    text = " ".join(str(issue.get(field) or "") for field in ("title", "description", "rule_name")).casefold()
    if any(marker in text for marker in STYLE_MARKERS):
        return False
    return any(marker in text for marker in RISK_MARKERS)


def convert_row(row: dict[str, Any], max_findings: int) -> dict[str, Any] | None:
    issues = [issue for issue in row.get("issues") or [] if _is_functional_issue(issue) and issue.get("file_path")]
    if not issues:
        return None

    repo = str(row["repo"])
    pr_url = str(row["pr_url_to_review"])
    sample_id = f"qodo-{repo.casefold().replace('.', '-').replace('/', '-')}-{pr_url.rstrip('/').rsplit('/', 1)[-1]}"
    expected_findings = []
    for index, issue in enumerate(issues[:max_findings], 1):
        path = str(issue["file_path"])
        start = int(issue.get("start_line") or issue.get("end_line") or 1)
        end = int(issue.get("end_line") or start)
        expected_findings.append(
            {
                "id": f"{sample_id}-i{index}",
                "file": path,
                "line_range": [start, end],
                "title_keywords": _keywords(str(issue.get("title") or ""), path),
                "evidence_keywords": _keywords(str(issue.get("problematic_code_snippet") or ""), path),
                "severity": "WARNING",
                "source": "qodo-pr-review-bench-injected-issue",
                "reason": str(issue.get("description") or issue.get("title") or "").strip(),
            }
        )

    return {
        "id": sample_id,
        "repo": f"agentic-review-benchmarks/{repo}",
        "url": pr_url,
        "kind": "qodo-pr-review-bench",
        "expected_findings": expected_findings,
        "notes": "Imported from Qodo PR-Review-Bench; functional-looking injected issues only.",
    }


def import_samples(limit: int, max_findings: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with urllib.request.urlopen(DATASET_URL, timeout=120) as response:
        for raw_line in response:
            sample = convert_row(json.loads(raw_line), max_findings=max_findings)
            if sample is None:
                continue
            samples.append(sample)
            if len(samples) >= limit:
                break
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Qodo PR-Review-Bench samples into PRism eval YAML")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-findings", type=int, default=2)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    samples = import_samples(limit=args.limit, max_findings=args.max_findings)
    Path(args.out).write_text(yaml.safe_dump(samples, sort_keys=False, allow_unicode=True))
    print(f"wrote {len(samples)} samples to {args.out}")


if __name__ == "__main__":
    main()
