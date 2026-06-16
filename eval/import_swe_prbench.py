"""Import a small SWE-PRBench slice into PRism's golden sample format.

Usage:
    python eval/import_swe_prbench.py --limit 10 --out eval/prs_swe_prbench_seed.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

DATASET = "foundry-ai/swe-prbench"
CONFIG = "prs"
SPLIT = "train"
BOT_MARKERS = ("bot", "gemini", "code-assist", "copilot", "coderabbit")
RISK_MARKERS = (
    "break",
    "bug",
    "crash",
    "error",
    "fail",
    "incorrect",
    "invalid",
    "leak",
    "null",
    "performance",
    "regression",
    "runtime",
    "security",
    "timeout",
    "wrong",
)
LOW_SIGNAL_MARKERS = (
    "add some docs",
    "could you add docs",
    "correct me if i'm wrong",
    "irrelevant for this pr",
    "let's wait for the ci",
    "nit",
    "out of scope",
    "seems harmless",
    "why would",
    "what is the rule",
)


def _is_human_line_comment(comment: dict[str, Any]) -> bool:
    author = str(comment.get("author") or "").casefold()
    if any(marker in author for marker in BOT_MARKERS):
        return False
    body = str(comment.get("body") or "").casefold()
    if len(body) < 30 or any(marker in body for marker in LOW_SIGNAL_MARKERS):
        return False
    if not any(marker in body for marker in RISK_MARKERS):
        return False
    return bool(comment.get("path")) and isinstance(comment.get("line"), int)


def _keywords_from_comment(comment: dict[str, Any]) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", str(comment.get("body") or ""))
    keywords: list[str] = []
    for word in words:
        lowered = word.casefold()
        if lowered in {"this", "that", "with", "from", "should", "would", "could", "when", "have", "been"}:
            continue
        if word not in keywords:
            keywords.append(word)
        if len(keywords) >= 3:
            break
    path = str(comment.get("path") or "")
    stem = Path(path).stem
    if stem and stem not in keywords:
        keywords.append(stem)
    return keywords[:4]


def _keywords_from_hunk(comment: dict[str, Any]) -> list[str]:
    hunk = str(comment.get("diffHunk") or "")
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", hunk)
    keywords: list[str] = []
    for word in words:
        if word in keywords:
            continue
        keywords.append(word)
        if len(keywords) >= 3:
            break
    path = str(comment.get("path") or "")
    stem = Path(path).stem
    if stem and stem not in keywords:
        keywords.append(stem)
    return keywords[:4]


def convert_row(row: dict[str, Any], max_findings: int) -> dict[str, Any] | None:
    if row.get("language") != "Python":
        return None

    comments = [comment for comment in row.get("human_review_comments") or [] if _is_human_line_comment(comment)]
    if not comments:
        return None

    task_id = str(row["task_id"])
    expected_findings = []
    for index, comment in enumerate(comments[:max_findings], 1):
        line = int(comment["line"])
        body = str(comment.get("body") or "").strip()
        expected_findings.append(
            {
                "id": f"{task_id}-c{index}",
                "file": comment["path"],
                "line_range": [line, line],
                "title_keywords": _keywords_from_comment(comment),
                "evidence_keywords": _keywords_from_hunk(comment),
                "severity": "WARNING",
                "source": "swe-prbench-human-review",
                "reason": body,
            }
        )

    return {
        "id": task_id,
        "repo": row["repo"],
        "url": row["pr_url"],
        "kind": f"swe-prbench-{row.get('difficulty', 'unknown')}",
        "expected_findings": expected_findings,
        "notes": (
            "Imported from SWE-PRBench human review comments; "
            "use as external eval signal, not absolute bug truth."
        ),
    }


def fetch_rows(offset: int, length: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"dataset": DATASET, "config": CONFIG, "split": SPLIT, "offset": offset, "length": length}
    )
    url = f"https://datasets-server.huggingface.co/rows?{params}"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.load(response)
    return [item["row"] for item in payload.get("rows", [])]


def import_samples(limit: int, page_size: int, max_findings: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    offset = 0
    while len(samples) < limit:
        rows = fetch_rows(offset, page_size)
        if not rows:
            break
        for row in rows:
            sample = convert_row(row, max_findings=max_findings)
            if sample is not None:
                samples.append(sample)
            if len(samples) >= limit:
                break
        offset += len(rows)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Import SWE-PRBench samples into PRism eval YAML")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-findings", type=int, default=3)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    samples = import_samples(limit=args.limit, page_size=args.page_size, max_findings=args.max_findings)
    Path(args.out).write_text(yaml.safe_dump(samples, sort_keys=False, allow_unicode=True))
    print(f"wrote {len(samples)} samples to {args.out}")


if __name__ == "__main__":
    main()
