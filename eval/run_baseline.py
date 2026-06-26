"""Baseline: per-file single-prompt LLM code review, no multi-agent architecture.

For each file in the diff, sends one comprehensive prompt covering security,
quality, and performance. No judge dedup. Used to compare against PRism's
multi-agent pipeline — if baseline F1 ≈ PRism F1, the architecture adds no value.

Usage:
    cd /Users/zouyijie/code/PRism/backend
    .venv/bin/python ../eval/run_baseline.py \
        --golden-dir /tmp/code-review-benchmark/offline/golden_comments \
        --limit 10 \
        --output ../eval/baseline_results.json
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PRISM_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(PRISM_BACKEND))

from dotenv import load_dotenv
load_dotenv(PRISM_BACKEND / ".env")

from app.services.github import fetch_pr_context, parse_pr_url
from app.services.llm import LLMClient
from app.graph import split_diff_by_file, _should_skip_diff_file

_SYSTEM = """\
You are a senior software engineer reviewing a pull request.
Find real bugs and security issues introduced by this diff.
Focus only on problems that could cause incorrect behavior, data loss, security vulnerabilities, or runtime errors.
Ignore style, formatting, and minor suggestions.
"""

_USER_TMPL = """\
PR title: {title}
File: {filepath}

[DIFF]
{diff}

Review this file's diff and find real bugs, security issues, or logic errors introduced by the changes.
Check for: null/undefined access, missing error handling, race conditions, auth bypass, SQL injection,
incorrect async/await usage, off-by-one errors, data corruption, resource leaks.
Ignore style and formatting. Focus on problems that could cause incorrect behavior or failures.

Return a JSON array of findings (empty array if none):
[
  {{"line": 42, "severity": "High", "title": "short title", "description": "what the problem is and why it matters"}},
  ...
]

Return only the JSON array, nothing else.
"""

_MAX_FILE_CHARS = 12_000
_FILE_CONCURRENCY = 5


def _parse_findings(raw: str, filepath: str) -> list[dict]:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        findings = json.loads(text)
        if not isinstance(findings, list):
            return []
        result = []
        for obj in findings:
            if not isinstance(obj, dict):
                continue
            severity = obj.get("severity", "Medium")
            if isinstance(severity, str) and severity.lower() in ("high", "error"):
                severity = "High"
            elif isinstance(severity, str) and severity.lower() in ("low", "info"):
                severity = "Low"
            else:
                severity = "Medium"
            result.append({
                "path": filepath,
                "line": obj.get("line"),
                "body": f"[{severity}] {obj.get('title', '')}\n\n{obj.get('description', '')}",
                "created_at": "",
            })
        return result
    except (json.JSONDecodeError, IndexError):
        return []


async def _review_file(
    filepath: str,
    file_diff: str,
    title: str,
    llm: LLMClient,
    sem: asyncio.Semaphore,
    timeout: int,
) -> list[dict]:
    if len(file_diff) > _MAX_FILE_CHARS:
        file_diff = file_diff[:_MAX_FILE_CHARS] + "\n... [truncated]"

    user_msg = _USER_TMPL.format(title=title, filepath=filepath, diff=file_diff)

    async with sem:
        try:
            raw = await asyncio.wait_for(
                llm.chat(
                    messages=[
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.0,
                    max_tokens=1024,
                ),
                timeout=timeout,
            )
        except Exception as e:
            print(f"    LLM ERROR {filepath}: {e}", flush=True)
            return []

    return _parse_findings(raw, filepath)


async def run_baseline_single(
    url: str,
    sem: asyncio.Semaphore,
    timeout: int = 120,
) -> tuple[str, dict]:
    owner, repo, pr_number = parse_pr_url(url)
    t0 = time.monotonic()

    try:
        ctx = await asyncio.wait_for(
            fetch_pr_context(owner, repo, pr_number),
            timeout=30,
        )
    except Exception as e:
        print(f"  FETCH ERROR {url}: {e}", flush=True)
        return url, {"error": f"fetch_failed: {e}", "elapsed": 0}

    diff = ctx.get("diff", "")
    if not diff:
        return url, {"error": "empty_diff", "elapsed": 0}

    file_diffs = split_diff_by_file(diff)
    file_items = [
        (filepath, file_diff)
        for filepath, file_diff in file_diffs.items()
        if not _should_skip_diff_file(filepath)
    ]

    if not file_items:
        return url, {"error": "no_reviewable_files", "elapsed": 0}

    title = ctx.get("title", "")
    llm = LLMClient(budget=None)
    file_sem = asyncio.Semaphore(_FILE_CONCURRENCY)

    tasks = [
        _review_file(filepath, file_diff, title, llm, file_sem, timeout=timeout)
        for filepath, file_diff in file_items
    ]

    all_findings: list[dict] = []
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_findings.extend(r)

    elapsed = time.monotonic() - t0
    print(
        f"  OK {len(all_findings)} findings from {len(file_items)} files, "
        f"{elapsed:.1f}s {url}",
        flush=True,
    )
    return url, {
        "pr_title": title,
        "tool": "baseline_per_file",
        "review_comments": all_findings,
        "issue_count": len(all_findings),
        "elapsed": round(elapsed, 1),
    }


def load_golden(golden_dir: Path) -> dict[str, list]:
    golden: dict[str, list] = {}
    for json_file in sorted(golden_dir.glob("*.json")):
        with open(json_file) as f:
            entries = json.load(f)
        for entry in entries:
            url = entry["url"]
            golden[url] = entry.get("comments", [])
    return golden


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-dir", default="/tmp/code-review-benchmark/offline/golden_comments")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", default="eval/baseline_results.json")
    args = parser.parse_args()

    golden_dir = Path(args.golden_dir)
    golden_by_url = load_golden(golden_dir)

    urls = list(golden_by_url.keys())
    if args.limit:
        urls = urls[: args.limit]

    print(
        f"Baseline (per-file single-prompt) on {len(urls)} PRs "
        f"(PR concurrency={args.concurrency}, file concurrency={_FILE_CONCURRENCY})...",
        flush=True,
    )

    sem = asyncio.Semaphore(args.concurrency)
    pairs = await asyncio.gather(*[
        run_baseline_single(url, sem, timeout=args.timeout)
        for url in urls
    ])

    results = {}
    for url, data in pairs:
        if "error" not in data:
            data["golden_comments"] = golden_by_url.get(url, [])
        results[url] = data

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    total = len(results)
    errors = sum(1 for r in results.values() if "error" in r)
    total_issues = sum(r.get("issue_count", 0) for r in results.values() if "error" not in r)
    elapsed_all = sum(r.get("elapsed", 0) for r in results.values() if "error" not in r)
    print(f"\nDone: {total} PRs, {errors} errors, {total_issues} total findings")
    print(f"Avg: {elapsed_all / max(total - errors, 1):.1f}s per PR")
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
