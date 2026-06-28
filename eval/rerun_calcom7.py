"""Re-run PRism on the 7 cal.com PRs and build a benchmark results JSON.

Golden comments are copied from prism_benchmark_results_v3_7pr.json so the
same scorer.py pipeline can be used for A/B comparison.

Usage:
    cd /Users/zouyijie/code/PRism
    # baseline (diff-only):
    python eval/rerun_calcom7.py --output eval/prism_benchmark_results_v9_baseline.json
    # with callgraph:
    python eval/rerun_calcom7.py --output eval/prism_benchmark_results_v9_callgraph.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv
load_dotenv(BACKEND / ".env")

from app.graph import ReviewGraph  # noqa: E402

PR_URLS = [
    "https://github.com/calcom/cal.com/pull/8087",
    "https://github.com/calcom/cal.com/pull/10600",
    "https://github.com/calcom/cal.com/pull/10967",
    "https://github.com/calcom/cal.com/pull/22345",
    "https://github.com/calcom/cal.com/pull/7232",
    "https://github.com/calcom/cal.com/pull/8330",
    "https://github.com/calcom/cal.com/pull/14943",
]

GOLDEN_SOURCE = ROOT / "eval" / "prism_benchmark_results_v3_7pr.json"


def _load_goldens() -> dict[str, list[dict]]:
    """Load golden_comments from the reference file keyed by PR URL."""
    with open(GOLDEN_SOURCE) as f:
        d = json.load(f)
    return {url: pr["golden_comments"] for url, pr in d.items()}


def _to_review_comments(result: dict) -> list[dict]:
    """Convert graph.run() result to flat list of review_comments."""
    comments = []
    for issue in result.get("issues", []):
        comments.append({
            "path": issue.get("file", ""),
            "line": issue.get("line", 0),
            "body": (
                f"[{issue.get('severity', '?')}] {issue.get('title', '')}\n\n"
                f"{issue.get('description', '')}"
            ),
            "created_at": "",
        })
    return comments


async def run_all(output_path: Path) -> None:
    goldens = _load_goldens()
    graph = ReviewGraph()
    results: dict[str, dict] = {}

    for url in PR_URLS:
        print(f"  running {url.split('/')[-1]}...", flush=True)
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(graph.run(pr_url=url), timeout=300)
            elapsed = time.monotonic() - t0
            review_comments = _to_review_comments(result)
            results[url] = {
                "pr_title": result.get("summary", "")[:80],
                "golden_comments": goldens.get(url, []),
                "source_file": "",
                "tool": "prism",
                "review_comments": review_comments,
                "issue_count": len(review_comments),
                "risk_level": result.get("risk_level", ""),
                "evidence_gate_stats": result.get("evidence_gate_stats", {}),
                "elapsed": elapsed,
            }
            print(f"    done: {len(review_comments)} issues, {elapsed:.1f}s", flush=True)
        except Exception as exc:
            elapsed = time.monotonic() - t0
            print(f"    ERROR: {exc}", flush=True)
            results[url] = {
                "pr_title": "",
                "golden_comments": goldens.get(url, []),
                "source_file": "",
                "tool": "prism",
                "review_comments": [],
                "issue_count": 0,
                "risk_level": "",
                "evidence_gate_stats": {},
                "elapsed": elapsed,
                "error": str(exc),
            }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    total = sum(r["issue_count"] for r in results.values())
    print(f"\nWrote {output_path}  ({total} total findings across {len(results)} PRs)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(f"Starting eval → {args.output}")
    print(f"Ran at: {datetime.now(UTC).isoformat()}")
    asyncio.run(run_all(Path(args.output)))


if __name__ == "__main__":
    main()
