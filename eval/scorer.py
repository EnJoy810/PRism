"""Score PRism benchmark results against golden comments using LLM-as-judge.

Usage:
    cd /Users/zouyijie/code/PRism
    python3 eval/scorer.py --input eval/prism_benchmark_results.json
    python3 eval/scorer.py --input eval/prism_benchmark_results.json --sample 20  # spot-check N findings
"""

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

PRISM_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(PRISM_BACKEND))

from dotenv import load_dotenv
load_dotenv(PRISM_BACKEND / ".env")

from app.services.llm import LLMClient

_llm = LLMClient(budget=None)

# --------------------------------------------------------------------------- #
# Judge prompt — mirrors withmartian's methodology:
# "do these describe the same underlying issue?"
# --------------------------------------------------------------------------- #

_JUDGE_SYSTEM = """\
You are an expert code reviewer judge.
Your task: decide if a tool-generated code review comment describes the SAME UNDERLYING ISSUE as a golden reference comment.

Rules:
- Different wording is fine — only substance matters.
- Different languages are fine — if the underlying issue is the same, it is a match regardless of language.
- The tool comment can be more specific or more general, as long as the core problem is the same.
- Partial match (same file/area, similar concern) does NOT count unless the actual issue type matches.
- Output ONLY valid JSON: {"match": true/false, "confidence": "high"|"medium"|"low", "reason": "one sentence"}
"""

_JUDGE_USER_TMPL = """\
Golden comment (reference issue):
{golden}

Tool-generated comment:
{tool_comment}

Do these describe the same underlying issue? Respond with JSON only.
"""


async def judge_pair(golden: str, tool_comment: str) -> dict:
    """Ask LLM whether golden and tool_comment describe the same issue."""
    user_msg = _JUDGE_USER_TMPL.format(golden=golden, tool_comment=tool_comment)
    try:
        raw = await _llm.chat(
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=256,
        )
        text = raw.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        return {"match": False, "confidence": "low", "reason": f"judge error: {e}"}


async def score_pr(
    url: str,
    pr_data: dict,
    sem: asyncio.Semaphore,
    verbose: bool = False,
) -> dict:
    """Score a single PR: compute precision, recall for PRism vs golden."""
    goldens = [g["comment"] for g in pr_data.get("golden_comments", [])]
    findings = [c["body"] for c in pr_data.get("review_comments", [])]

    if not goldens and not findings:
        return {
            "url": url,
            "precision": None,
            "recall": None,
            "tp_precision": 0, "tp_recall": 0, "fp": 0, "fn": 0,
            "golden_count": 0,
            "finding_count": 0,
            "note": "no goldens and no findings",
        }
    if not findings:
        return {
            "url": url,
            "precision": None,
            "recall": 0.0,
            "tp_precision": 0, "tp_recall": 0, "fp": 0, "fn": len(goldens),
            "golden_count": len(goldens),
            "finding_count": 0,
            "note": "prism reported nothing",
        }
    if not goldens:
        return {
            "url": url,
            "precision": 0.0,
            "recall": None,
            "tp_precision": 0, "tp_recall": 0, "fp": len(findings), "fn": 0,
            "golden_count": 0,
            "finding_count": len(findings),
            "note": "no golden comments available",
        }

    # Build (golden_idx, finding_idx) -> judge result
    # Run all pairs concurrently within this PR, gated by global semaphore
    pairs = [(gi, fi) for gi in range(len(goldens)) for fi in range(len(findings))]

    async def _judge(gi: int, fi: int) -> tuple[int, int, dict]:
        async with sem:
            result = await judge_pair(goldens[gi], findings[fi])
        return gi, fi, result

    judgments = await asyncio.gather(*[_judge(gi, fi) for gi, fi in pairs])

    # Build match matrix
    match_matrix: dict[tuple[int, int], bool] = {}
    for gi, fi, j in judgments:
        match_matrix[(gi, fi)] = bool(j.get("match", False))

    # Recall: for each golden, was it matched by ANY finding?
    golden_matched = [
        any(match_matrix.get((gi, fi), False) for fi in range(len(findings)))
        for gi in range(len(goldens))
    ]
    # Precision: for each finding, did it match ANY golden?
    finding_matched = [
        any(match_matrix.get((gi, fi), False) for gi in range(len(goldens)))
        for fi in range(len(findings))
    ]

    tp_recall = sum(golden_matched)   # goldens that were hit
    tp_prec = sum(finding_matched)    # findings that hit something
    fn = len(goldens) - tp_recall
    fp = len(findings) - tp_prec

    precision = tp_prec / len(findings) if findings else None
    recall = tp_recall / len(goldens) if goldens else None

    if verbose:
        print(f"\n  {url}")
        for gi, g in enumerate(goldens):
            hit = "HIT" if golden_matched[gi] else "MISS"
            print(f"    [{hit}] golden: {g[:80]}")
        for fi, f in enumerate(findings):
            hit = "TP" if finding_matched[fi] else "FP"
            print(f"    [{hit}] finding: {f[:80]}")

    return {
        "url": url,
        "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "tp_recall": tp_recall,
        "tp_precision": tp_prec,
        "fp": fp,
        "fn": fn,
        "golden_count": len(goldens),
        "finding_count": len(findings),
    }


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 3)


def _aggregate(pr_scores: list[dict]) -> dict:
    """Micro-average across all PRs (sum TP/FP/FN then compute)."""
    valid = [s for s in pr_scores if s.get("golden_count", 0) > 0]
    if not valid:
        return {}

    total_tp_prec = sum(s["tp_precision"] for s in valid)
    total_tp_recall = sum(s["tp_recall"] for s in valid)
    total_findings = sum(s["finding_count"] for s in valid)
    total_goldens = sum(s["golden_count"] for s in valid)
    total_fp = sum(s["fp"] for s in valid)
    total_fn = sum(s["fn"] for s in valid)

    precision = total_tp_prec / total_findings if total_findings else None
    recall = total_tp_recall / total_goldens if total_goldens else None

    return {
        "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "f1": _f1(precision, recall),
        "total_prs": len(valid),
        "total_findings": total_findings,
        "total_goldens": total_goldens,
        "total_tp_precision": total_tp_prec,
        "total_tp_recall": total_tp_recall,
        "total_fp": total_fp,
        "total_fn": total_fn,
    }


def _gate_summary(results: dict) -> dict | None:
    stats = [r["evidence_gate_stats"] for r in results.values() if "evidence_gate_stats" in r]
    if not stats:
        return None
    total_before = sum(g["before_gate"] for g in stats)
    total_after = sum(g["after_gate"] for g in stats)
    filter_pct = (total_before - total_after) / max(total_before, 1) * 100
    return {
        "total_before_gate": total_before,
        "total_after_gate": total_after,
        "filter_rate": round(filter_pct / 100, 3),
        "filter_pct": round(filter_pct, 1),
    }


async def main():
    parser = argparse.ArgumentParser(description="Score PRism benchmark results with LLM judge")
    parser.add_argument("--input", default="eval/prism_benchmark_results.json")
    parser.add_argument("--output", default="eval/prism_scores.json")
    parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent LLM judge calls")
    parser.add_argument("--limit", type=int, default=None, help="Score only first N PRs")
    parser.add_argument("--verbose", action="store_true", help="Print per-PR match details")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Spot-check mode: randomly sample N findings and print judge verdicts",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        results: dict = json.load(f)

    # Filter out errored PRs
    valid = {url: r for url, r in results.items() if "error" not in r}
    if args.limit:
        valid = dict(list(valid.items())[: args.limit])

    # ------------------------------------------------------------------ #
    # Spot-check mode: sample N (golden, finding) pairs and show verdicts  #
    # ------------------------------------------------------------------ #
    if args.sample:
        pairs = []
        for url, pr in valid.items():
            for g in pr.get("golden_comments", []):
                for f in pr.get("review_comments", []):
                    pairs.append((url, g["comment"], f["body"]))
        sample = random.sample(pairs, min(args.sample, len(pairs)))
        print(f"Spot-checking {len(sample)} (golden, finding) pairs...\n")
        sem = asyncio.Semaphore(args.concurrency)
        for url, golden, finding in sample:
            async with sem:
                j = await judge_pair(golden, finding)
            match_str = "MATCH" if j.get("match") else "NO MATCH"
            print(f"[{match_str}] conf={j.get('confidence', '?')}")
            print(f"  golden:  {golden[:100]}")
            print(f"  finding: {finding[:100]}")
            print(f"  reason:  {j.get('reason', '')}\n")
        return

    # ------------------------------------------------------------------ #
    # Full scoring                                                          #
    # ------------------------------------------------------------------ #
    print(f"Scoring {len(valid)} PRs with LLM judge (concurrency={args.concurrency})...", flush=True)
    t0 = time.monotonic()

    sem = asyncio.Semaphore(args.concurrency)
    pr_scores = await asyncio.gather(*[
        score_pr(url, pr, sem, verbose=args.verbose)
        for url, pr in valid.items()
    ])

    elapsed = time.monotonic() - t0
    agg = _aggregate(list(pr_scores))
    gate = _gate_summary(results)

    output = {
        "aggregate": agg,
        "evidence_gate": gate,
        "elapsed_seconds": round(elapsed, 1),
        "per_pr": pr_scores,
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'='*50}")
    print(f"RESULTS (micro-average, {agg.get('total_prs', 0)} PRs)")
    print(f"  Precision : {agg.get('precision', 'N/A')}")
    print(f"  Recall    : {agg.get('recall', 'N/A')}")
    print(f"  F1        : {agg.get('f1', 'N/A')}")
    print(f"  Findings  : {agg.get('total_findings', 0)} total, "
          f"{agg.get('total_tp_precision', 0)} TP, {agg.get('total_fp', 0)} FP")
    print(f"  Goldens   : {agg.get('total_goldens', 0)} total, "
          f"{agg.get('total_tp_recall', 0)} hit, {agg.get('total_fn', 0)} missed")
    if gate:
        print(f"\nEvidence Gate:")
        print(f"  {gate['total_before_gate']} raw -> {gate['total_after_gate']} final "
              f"({gate['filter_pct']}% filtered)")
    print(f"\nDone in {elapsed:.1f}s. Full results: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
