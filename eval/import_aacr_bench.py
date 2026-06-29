"""Import Alibaba AACR-Bench into PRism eval format.

Dataset: https://huggingface.co/datasets/Alibaba-Aone/aacr-bench
Paper:   https://arxiv.org/abs/2601.19494

200 real PRs, 10 languages, 1505 expert-verified review comments with line numbers.
Only label=1 rows are ground truth (positive findings).

Usage:
    cd backend && .venv/bin/python ../eval/import_aacr_bench.py
    cd backend && .venv/bin/python ../eval/import_aacr_bench.py --limit 50 --lang Python
    cd backend && .venv/bin/python ../eval/import_aacr_bench.py --context diff
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

SEVERITY_MAP = {
    "Code Defect": "ERROR",
    "Security Vulnerability": "ERROR",
    "Performance": "WARNING",
    "Maintainability and Readability": "INFO",
}

CONTEXT_FILTER_MAP = {
    "diff": "Diff Level",
    "file": "File Level",
    "repo": "Repo Level",
}


def _slug(pr_url: str) -> str:
    # https://github.com/owner/repo/pull/123 → owner_repo_123
    parts = pr_url.rstrip("/").split("/")
    return f"{parts[-4]}_{parts[-3]}_{parts[-1]}"


def build_samples(rows: list[dict], limit: int | None) -> list[dict[str, Any]]:
    by_pr: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_pr[row["pr_url"]].append(row)

    samples: list[dict[str, Any]] = []
    for pr_url, findings in sorted(by_pr.items()):
        sample_id = f"aacr_{_slug(pr_url)}"
        expected: list[dict[str, Any]] = []
        for i, f in enumerate(findings, 1):
            from_line = f.get("from_line")
            to_line = f.get("to_line")
            line_range = [from_line, to_line] if from_line and to_line else None
            expected.append({
                "id": f"{sample_id}-g{i}",
                "file": f.get("path", ""),
                "line_range": line_range,
                "description": (f.get("note") or "").strip(),
                "severity": SEVERITY_MAP.get(f.get("category", ""), "WARNING"),
                "category": f.get("category", ""),
                "context_level": f.get("context", ""),
                "is_ai_comment": f.get("is_ai_comment", True),
            })

        samples.append({
            "id": sample_id,
            "url": pr_url,
            "kind": "aacr-bench",
            "language": findings[0].get("project_main_language", ""),
            "pr_category": findings[0].get("pr_category", ""),
            "expected_findings": expected,
        })

        if limit and len(samples) >= limit:
            break

    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Alibaba AACR-Bench")
    parser.add_argument("--out", default="eval/prs_aacr_bench.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Max PRs to import")
    parser.add_argument("--lang", default=None, help="Filter by language (e.g. Python, Java, TypeScript)")
    parser.add_argument("--context", default=None, choices=["diff", "file", "repo"],
                        help="Filter by context level required")
    args = parser.parse_args()

    print("Loading Alibaba-Aone/aacr-bench from HuggingFace...", flush=True)
    from datasets import load_dataset  # noqa: PLC0415
    ds = load_dataset("Alibaba-Aone/aacr-bench", split="train", trust_remote_code=True)

    rows = [r for r in ds if r["label"] == 1]
    print(f"  {len(rows)} positive findings across {len(set(r['pr_url'] for r in rows))} PRs")

    if args.lang:
        rows = [r for r in rows if r.get("project_main_language", "").lower() == args.lang.lower()]
        print(f"  After lang={args.lang}: {len(rows)} findings")

    if args.context:
        ctx_val = CONTEXT_FILTER_MAP[args.context]
        rows = [r for r in rows if r.get("context") == ctx_val]
        print(f"  After context={args.context}: {len(rows)} findings")

    samples = build_samples(rows, args.limit)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        yaml.dump(samples, f, allow_unicode=True, sort_keys=False, width=120)

    total_findings = sum(len(s["expected_findings"]) for s in samples)
    print(f"\nWrote {len(samples)} samples ({total_findings} findings) → {out}")

    # Language breakdown
    from collections import Counter  # noqa: PLC0415
    langs = Counter(s["language"] for s in samples)
    print("Language breakdown:")
    for lang, cnt in langs.most_common():
        print(f"  {lang}: {cnt} PRs")


if __name__ == "__main__":
    main()
