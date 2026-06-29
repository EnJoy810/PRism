"""Run PRism reviews for a small PR evaluation set.

Usage:
    cd backend && .venv/bin/python ../eval/run_eval.py --samples ../eval/prs_golden.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env", override=True)

from app.graph import ReviewGraph  # noqa: E402
from app.models.review import ReviewStats  # noqa: E402
from app.services.github import fetch_pr_context, parse_pr_url  # noqa: E402


def _load_samples(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of PR samples in {path}")
    return data


def _render_markdown(sample: dict[str, Any], result: dict[str, Any]) -> str:
    issues = result.get("issues", [])
    lines = [
        f"# {sample['id']}",
        "",
        f"PR: {sample['url']}",
        f"Summary: {result.get('summary', '')}",
        f"Risk: {result.get('risk_level', '')}",
        f"Recommendation: {result.get('merge_recommendation', '')}",
        f"Issues: {len(issues)}",
        "",
        "## Findings",
        "",
    ]
    for index, issue in enumerate(issues, 1):
        lines.extend(
            [
                f"### {index}. {issue.get('title', '')}",
                f"- severity: {issue.get('severity', '')}",
                f"- file: {issue.get('file', '')}:{issue.get('line', '')}",
                f"- confidence: {issue.get('confidence', '')}",
                f"- description: {issue.get('description', '')}",
                f"- evidence: {', '.join(issue.get('evidence') or [])}",
                "- human_label: TODO",
                "- label_reason: TODO",
                "",
            ]
        )
    if not issues:
        lines.append("No findings.")
    return "\n".join(lines).rstrip() + "\n"


def _build_synthetic_context(sample: dict[str, Any]) -> dict[str, Any]:
    """Build a ReviewGraph context dict from a synthetic CodeReviewBench sample."""
    diff = sample["synthetic_diff"]
    files = sample.get("synthetic_files") or []
    return {
        "title": sample.get("synthetic_pr_title", sample["id"]),
        "description": sample.get("synthetic_pr_description", ""),
        "diff": diff,
        "diff_truncated": False,
        "files": files,
        "stats": ReviewStats(
            files_changed=len(files),
            additions=diff.count("\n+"),
            deletions=diff.count("\n-"),
            issues_by_severity={"ERROR": 0, "WARNING": 0, "INFO": 0},
        ),
        "head_sha": "",
        "base_branch": "main",
        "head_branch": "feature",
        "author_name": "synthetic",
        "author_avatar": "",
        "updated_at": "",
        "created_at": "",
        "pr_url": sample["url"],
        "pr_title": sample.get("synthetic_pr_title", sample["id"]),
        "pr_description": sample.get("synthetic_pr_description", ""),
    }


async def _run_sample(
    graph: ReviewGraph,
    sample: dict[str, Any],
    out_dir: Path,
    timeout_seconds: int,
) -> None:
    if "synthetic_diff" in sample:
        context = _build_synthetic_context(sample)
        result = await asyncio.wait_for(
            graph.run(pr_url=sample["url"], context=context),
            timeout=timeout_seconds,
        )
    else:
        result = await asyncio.wait_for(
            graph.run(pr_url=sample["url"]),
            timeout=timeout_seconds,
        )
    payload = {
        "sample": sample,
        "ran_at": datetime.now(UTC).isoformat(),
        "result": result,
    }
    (out_dir / f"{sample['id']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )
    (out_dir / f"{sample['id']}.md").write_text(_render_markdown(sample, result))


async def _fetch_context_only(sample: dict[str, Any], out_dir: Path) -> None:
    owner, repo, number = parse_pr_url(sample["url"])
    context = await fetch_pr_context(owner, repo, number)
    payload = {
        "sample": sample,
        "fetched_at": datetime.now(UTC).isoformat(),
        "title": context.get("title", ""),
        "description": context.get("description", ""),
        "head_sha": context.get("head_sha", ""),
        "base_sha": context.get("base_sha", ""),
        "files": context.get("files", []),
        "diff_len": len(context.get("diff", "")),
        "diff_truncated": context.get("diff_truncated", False),
    }
    (out_dir / f"{sample['id']}.context.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run PRism eval samples")
    parser.add_argument("--samples", default=str(ROOT / "eval" / "prs_golden.yaml"))
    parser.add_argument("--out", default=str(ROOT / "eval" / "runs"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--context-only", action="store_true")
    args = parser.parse_args()

    samples = _load_samples(Path(args.samples))
    if args.limit is not None:
        samples = samples[: args.limit]

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = None if args.context_only else ReviewGraph()
    for sample in samples:
        print(f"running {sample['id']} {sample['url']}", flush=True)
        try:
            if args.context_only:
                await _fetch_context_only(sample, out_dir)
            else:
                assert graph is not None
                await _run_sample(graph, sample, out_dir, args.timeout)
        except Exception as exc:  # noqa: BLE001
            error_payload = {"sample": sample, "error": str(exc)}
            (out_dir / f"{sample['id']}.error.json").write_text(
                json.dumps(error_payload, ensure_ascii=False, indent=2)
            )
            print(f"failed {sample['id']}: {exc}", flush=True)

    print(f"wrote {out_dir}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
