"""Run PRism on withmartian benchmark PRs and save results for pipeline injection.

Usage:
    cd /Users/zouyijie/code/PRism
    python3 eval/run_withmartian.py --limit 3 --golden-dir /tmp/code-review-benchmark/offline/golden_comments
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add PRism backend to path
PRISM_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(PRISM_BACKEND))

from dotenv import load_dotenv
load_dotenv(PRISM_BACKEND / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)

from app.services.github import parse_pr_url
from app.graph import ReviewGraph


def load_all_pr_urls(golden_dir: Path) -> list[dict]:
    """Load all PR URLs from golden comment files."""
    prs = []
    for json_file in sorted(golden_dir.glob("*.json")):
        with open(json_file) as f:
            entries = json.load(f)
        for entry in entries:
            url = entry["url"]
            # Some entries use 'original_url', some use 'url'
            original = entry.get("original_url") or url
            prs.append({
                "url": url,
                "original_url": original,
                "pr_title": entry.get("pr_title", ""),
                "golden_comments": entry.get("comments", []),
                "source_file": json_file.name,
            })
    return prs


def convert_prism_to_review_comments(result: dict) -> list[dict]:
    """Convert PRism review result to benchmark review_comments format."""
    comments = []
    for issue in result.get("issues", []):
        file = issue.get("file", "")
        line = issue.get("line")
        severities = {"ERROR": "High", "WARNING": "Medium", "INFO": "Low"}
        severity_label = severities.get(issue.get("severity", ""), "Medium")
        body = f"[{severity_label}] {issue.get('title', '')}\n\n{issue.get('description', '')}"
        if body not in {c["body"] for c in comments}:
            comments.append({
                "path": file or None,
                "line": line,
                "body": body,
                "created_at": "",
            })

    return comments


async def run_prism_full(pr_url: str, timeout: int = 300) -> dict | None:
    """Run PRism review on a single PR with full investigate (blast radius, symbol, sast).
    Blast radius requires repo clone; if clone fails, graph auto-degrades to diff-only.
    """
    graph = ReviewGraph()
    try:
        result = await asyncio.wait_for(
            graph.run(pr_url),
            timeout=timeout,
        )
        return result
    except asyncio.TimeoutError:
        print(f"  TIMEOUT after {timeout}s", flush=True)
        return None
    except Exception as e:
        print(f"  ERROR: {e}", flush=True)
        return None


async def _run_one(
    sem: asyncio.Semaphore,
    i: int,
    total: int,
    pr_info: dict,
    timeout: int,
) -> tuple[str, dict]:
    url = pr_info["url"]
    async with sem:
        print(f"[{i}/{total}] START {url}", flush=True)
        t0 = time.monotonic()
        result = await run_prism_full(url, timeout=timeout)
        elapsed = time.monotonic() - t0

    if result is None:
        print(f"[{i}/{total}] FAILED ({elapsed:.1f}s) {url}", flush=True)
        return url, {"error": "review_failed", "elapsed": round(elapsed, 1)}

    review_comments = convert_prism_to_review_comments(result)
    gate = result.get("evidence_gate_stats", {})
    print(
        f"[{i}/{total}] OK {len(result.get('issues', []))} issues "
        f"(gate {gate.get('before_gate', '?')}->{gate.get('after_gate', '?')}) "
        f"{elapsed:.1f}s {url}",
        flush=True,
    )
    return url, {
        "pr_title": pr_info["pr_title"],
        "golden_comments": pr_info["golden_comments"],
        "source_file": pr_info["source_file"],
        "tool": "prism",
        "review_comments": review_comments,
        "issue_count": len(result.get("issues", [])),
        "risk_level": result.get("risk_level", ""),
        "evidence_gate_stats": gate,
        "elapsed": round(elapsed, 1),
    }


async def main():
    parser = argparse.ArgumentParser(description="Run PRism on withmartian benchmark PRs")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of PRs to process")
    parser.add_argument("--timeout", type=int, default=300, help="Per-PR timeout in seconds (clone + review)")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent PR reviews")
    parser.add_argument("--golden-dir", default="", help="Golden comments directory")
    parser.add_argument("--output", default="eval/prism_benchmark_results.json", help="Output file")
    parser.add_argument("--urls", default="", help="Comma-separated PR URLs to run (subset mode)")
    args = parser.parse_args()

    if args.golden_dir:
        golden_dir = Path(args.golden_dir)
    else:
        golden_dir = Path("/tmp/code-review-benchmark/offline/golden_comments")

    all_prs = load_all_pr_urls(golden_dir)
    if args.urls:
        url_filter = {u.strip() for u in args.urls.split(",") if u.strip()}
        all_prs = [p for p in all_prs if p["url"] in url_filter]
    elif args.limit:
        all_prs = all_prs[:args.limit]

    print(f"Running PRism (full mode, with blast radius) on {len(all_prs)} PRs (concurrency={args.concurrency})...", flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    tasks = [
        _run_one(sem, i, len(all_prs), pr_info, args.timeout)
        for i, pr_info in enumerate(all_prs, 1)
    ]
    pairs = await asyncio.gather(*tasks)
    results = dict(pairs)

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Summary
    total = len(results)
    errors = sum(1 for r in results.values() if "error" in r)
    total_issues = sum(r.get("issue_count", 0) for r in results.values() if "error" not in r)
    total_elapsed = sum(r.get("elapsed", 0) for r in results.values() if "error" not in r)

    # Evidence gate summary
    gate_stats = [r["evidence_gate_stats"] for r in results.values() if "evidence_gate_stats" in r]
    if gate_stats:
        total_before = sum(g["before_gate"] for g in gate_stats)
        total_after = sum(g["after_gate"] for g in gate_stats)
        filter_pct = (total_before - total_after) / max(total_before, 1) * 100
        print(f"\nEvidence Gate: {total_before} raw -> {total_after} final ({filter_pct:.1f}% filtered)")

    print(f"Done: {total} PRs, {errors} errors, {total_issues} total issues")
    print(f"Avg time: {total_elapsed / max(total - errors, 1):.1f}s per PR")
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
