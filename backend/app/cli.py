"""CLI entry point for local PR review testing.

Usage:
    python -m app.cli review https://github.com/owner/repo/pull/42
    python -m app.cli review https://github.com/owner/repo/pull/42 --token ghp_xxx
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from app.graph import ReviewGraph  # noqa: E402

DEFAULT_REVIEW_TIMEOUT_SECONDS = 300


async def review(
    pr_url: str,
    token: str | None = None,
    timeout_seconds: int = DEFAULT_REVIEW_TIMEOUT_SECONDS,
):
    print(f"Reviewing {pr_url}...\n")

    graph = ReviewGraph()
    try:
        result = await asyncio.wait_for(
            graph.run(pr_url=pr_url, github_token=token),
            timeout=timeout_seconds,
        )
    except TimeoutError as e:
        raise RuntimeError(
            f"Review timed out after {timeout_seconds}s. "
            "Check stage logs above for the last completed step."
        ) from e

    issues = result.get("issues", [])
    stats = result.get("stats", {})
    risk = result.get("risk_level", "LOW")
    decision = result.get("merge_recommendation", "N/A")

    print(f"## PRism Review: {result.get('summary', '')}")
    print(f"\n**风险等级**: {risk}")
    print(f"**推荐**: {decision}")
    print(f"**文件变更**: {stats.get('files_changed', 0)} | "
          f"+{stats.get('additions', 0)} -{stats.get('deletions', 0)}")
    print(f"**问题数**: {len(issues)}")

    if issues:
        print("\n---\n## 发现的问题\n")
        for i, issue in enumerate(issues, 1):
            sev = issue.get("severity", "INFO")
            label = {"ERROR": "🔴 ERROR", "WARNING": "🟡 WARNING", "INFO": "🔵 INFO"}.get(sev, sev)
            print(f"### {i}. [{label}] {issue.get('title', '')}")
            line_str = f":{issue.get('line', '')}" if issue.get('line') else ""
            print(f"- **文件**: `{issue.get('file', '')}`{line_str}")
            print(f"- **描述**: {issue.get('description', '')}")
            print(f"- **置信度**: {issue.get('confidence', 0):.2f}")
            evidence = issue.get("evidence")
            if evidence:
                print(f"- **证据**: {', '.join(evidence)}")
            print()

    skipped = result.get("skipped_agents", [])
    if skipped:
        print(f"\n⚠️  **部分 Agent 失败，结果可能不完整**: {', '.join(skipped)}")

    print("\n---")
    print("Review complete.")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="PRism CLI — local PR review")
    subparsers = parser.add_subparsers(dest="command", required=True)

    review_parser = subparsers.add_parser("review", help="Review a PR")
    review_parser.add_argument("pr_url", help="GitHub PR URL")
    review_parser.add_argument("--token", help="GitHub token (optional, falls back to env)")
    review_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_REVIEW_TIMEOUT_SECONDS,
        help="Review timeout in seconds",
    )

    args = parser.parse_args()

    if args.command == "review":
        try:
            asyncio.run(review(args.pr_url, args.token, args.timeout))
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(1) from e


if __name__ == "__main__":
    main()
