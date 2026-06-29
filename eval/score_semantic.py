"""Semantic (LLM-judge) scorer for withmartian-style eval sets.

Unlike score_eval.py which uses line-range matching, this scorer uses an LLM
to semantically match PRism findings against golden comments — the same approach
used by withmartian's benchmark pipeline.

Usage:
    python eval/score_semantic.py \\
        --golden eval/prs_withmartian.yaml \\
        --run eval/runs/<timestamp> \\
        [--model gpt-4o-mini]  # model for judge calls

Outputs a markdown table + aggregate P/R/F1, same format as score_eval.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Minimal async LLM client (uses same env vars as PRism)
# ---------------------------------------------------------------------------

try:
    from openai import AsyncOpenAI
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

JUDGE_SYSTEM = """You are a code review evaluation judge. Determine whether a tool's finding
describes the same underlying issue as a golden comment from a human reviewer.

Accept semantic matches — different wording is fine if both describe the same problem.
Respond ONLY with valid JSON: {"match": true/false, "confidence": 0.0-1.0, "reasoning": "brief"}"""

JUDGE_USER = """Golden comment (human reviewer):
{golden}

Tool finding (to evaluate):
{finding}

Do these describe the same underlying code issue?"""


async def judge_match(client, model: str, golden: str, finding: str) -> dict:
    """Ask LLM judge if finding matches golden. Returns {match, confidence, reasoning}."""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": JUDGE_USER.format(golden=golden, finding=finding)},
            ],
            temperature=0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"match": False, "confidence": 0.0, "reasoning": f"error: {e}"}


async def evaluate_sample(
    client,
    model: str,
    golden_findings: list[dict],
    tool_findings: list[dict],
    concurrency: int = 8,
) -> dict:
    """
    For each golden finding, find the best-matching tool finding.
    Returns {tp, fp, fn, matched_pairs}.
    """
    if not tool_findings:
        return {
            "tp": 0, "fp": 0, "fn": len(golden_findings),
            "matched_pairs": [],
        }
    if not golden_findings:
        return {
            "tp": 0, "fp": len(tool_findings), "fn": 0,
            "matched_pairs": [],
        }

    # Build all (golden_idx, tool_idx) pairs to judge
    sem = asyncio.Semaphore(concurrency)

    async def _judge(gi: int, ti: int) -> tuple[int, int, dict]:
        async with sem:
            g_text = golden_findings[gi]["description"]
            t_text = _finding_text(tool_findings[ti])
            result = await judge_match(client, model, g_text, t_text)
            return gi, ti, result

    tasks = [
        _judge(gi, ti)
        for gi in range(len(golden_findings))
        for ti in range(len(tool_findings))
    ]
    results = await asyncio.gather(*tasks)

    # Build match matrix: best confidence per (golden, tool) pair
    matrix: dict[tuple[int, int], dict] = {}
    for gi, ti, r in results:
        matrix[(gi, ti)] = r

    # Greedy matching: for each golden, find best-matching unmatched tool finding
    used_tool = set()
    matched_pairs = []
    tp = 0

    for gi in range(len(golden_findings)):
        best_conf = 0.5  # threshold
        best_ti = -1
        for ti in range(len(tool_findings)):
            if ti in used_tool:
                continue
            r = matrix.get((gi, ti), {})
            if r.get("match") and r.get("confidence", 0) > best_conf:
                best_conf = r["confidence"]
                best_ti = ti
        if best_ti >= 0:
            used_tool.add(best_ti)
            tp += 1
            matched_pairs.append({
                "golden": golden_findings[gi]["description"],
                "finding": _finding_text(tool_findings[best_ti]),
                "confidence": best_conf,
            })

    fp = len(tool_findings) - len(used_tool)
    fn = len(golden_findings) - tp

    return {"tp": tp, "fp": fp, "fn": fn, "matched_pairs": matched_pairs}


def _finding_text(finding: dict) -> str:
    parts = []
    if finding.get("title"):
        parts.append(finding["title"])
    if finding.get("description"):
        parts.append(finding["description"])
    return " — ".join(parts) if parts else str(finding)


def load_run(run_dir: Path, sample_id: str) -> list[dict]:
    """Load PRism findings for a sample from the run directory."""
    result_path = run_dir / f"{sample_id}.json"
    if not result_path.exists():
        return []
    with open(result_path) as f:
        data = json.load(f)
    result = data.get("result", data)
    return result.get("issues", result.get("findings", []))


async def main_async(args: argparse.Namespace) -> None:
    if not _HAS_OPENAI:
        print("ERROR: openai package not installed. Run: pip install openai", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL")
    model = args.model or os.environ.get("LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        print("ERROR: set LLM_API_KEY or OPENAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    client_kwargs: dict = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = AsyncOpenAI(**client_kwargs)

    with open(args.golden) as f:
        samples = yaml.safe_load(f)

    run_dir = Path(args.run)

    total_tp = total_fp = total_fn = 0
    rows = []

    print(f"Scoring {len(samples)} samples with LLM judge ({model})...")
    print()

    for sample in samples:
        sid = sample["id"]
        golden_findings = sample.get("expected_findings", [])
        tool_findings = load_run(run_dir, sid)

        if not golden_findings:
            continue

        result = await evaluate_sample(client, model, golden_findings, tool_findings)
        tp, fp, fn = result["tp"], result["fp"], result["fn"]
        total_tp += tp
        total_fp += fp
        total_fn += fn

        p = tp / (tp + fp) if tp + fp else 0
        r = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * p * r / (p + r) if p + r else 0

        repo = sample.get("repo_group", "?")
        status = "✓" if tool_findings else "✗ (no run)"
        rows.append((sid, repo, len(golden_findings), tp, fp, fn, f1, status))
        print(f"  {sid:<45} tp={tp} fp={fp} fn={fn}  F1={f1:.2f}  {status}")

    print()
    print("=" * 70)
    precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0
    recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    print(f"Overall  TP={total_tp}  FP={total_fp}  FN={total_fn}")
    print(f"Precision={precision:.3f}  Recall={recall:.3f}  F1={f1:.3f}")
    print()

    # Per-repo breakdown
    from collections import defaultdict
    repo_stats: dict[str, dict] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    for sid, repo, ng, tp, fp, fn, f1_, status in rows:
        repo_stats[repo]["tp"] += tp
        repo_stats[repo]["fp"] += fp
        repo_stats[repo]["fn"] += fn

    print("Per-repo breakdown:")
    for repo, s in sorted(repo_stats.items()):
        p = s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else 0
        r = s["tp"] / (s["tp"] + s["fn"]) if s["tp"] + s["fn"] else 0
        f = 2 * p * r / (p + r) if p + r else 0
        print(f"  {repo:<20}  P={p:.3f}  R={r:.3f}  F1={f:.3f}  "
              f"(tp={s['tp']} fp={s['fp']} fn={s['fn']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic LLM-judge scorer for withmartian eval")
    parser.add_argument("--golden", required=True, help="YAML file with expected_findings")
    parser.add_argument("--run", required=True, help="Run directory with per-sample JSON files")
    parser.add_argument("--model", default=None, help="LLM judge model (default: LLM_MODEL env or gpt-4o-mini)")
    parser.add_argument("--concurrency", type=int, default=8, help="Max concurrent judge calls per sample")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
