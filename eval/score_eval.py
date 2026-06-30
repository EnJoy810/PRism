"""Score PRism eval runs against a small golden set.

Usage:
    python eval/score_eval.py --golden eval/prs_golden.yaml --run eval/runs/<run_id>
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "ERROR": 2}


def _load_yaml_list(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}")
    return data


def _load_result(run_dir: Path, sample_id: str) -> dict[str, Any]:
    result_path = run_dir / f"{sample_id}.json"
    error_path = run_dir / f"{sample_id}.error.json"
    if error_path.exists():
        return {"issues": [], "_eval_error": json.loads(error_path.read_text()).get("error", "unknown error")}
    if not result_path.exists():
        return {"issues": [], "_eval_error": "no result"}
    payload = json.loads(result_path.read_text())
    result = payload.get("result", {})
    if not isinstance(result, dict):
        raise ValueError(f"Expected result object in {result_path}")
    return result


def _text_contains_any(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    normalized = text.casefold()
    return any(keyword.casefold() in normalized for keyword in keywords)


def _issue_text(issue: dict[str, Any]) -> str:
    evidence = issue.get("evidence") or []
    if isinstance(evidence, list):
        evidence_text = "\n".join(str(item) for item in evidence)
    else:
        evidence_text = str(evidence)
    return "\n".join(
        str(issue.get(field, ""))
        for field in ("title", "description", "impact_statement")
    ) + f"\n{evidence_text}"


def _severity_matches(issue: dict[str, Any], expected: dict[str, Any]) -> bool:
    expected_severity = expected.get("severity")
    if not expected_severity:
        return True
    issue_rank = SEVERITY_RANK.get(str(issue.get("severity", "INFO")).upper(), 0)
    expected_rank = SEVERITY_RANK.get(str(expected_severity).upper(), 0)
    return issue_rank >= expected_rank - 1


# ---------------------------------------------------------------------------
# Hunk-aware diff parsing
# ---------------------------------------------------------------------------

HunkList = list[tuple[int, int]]  # (new_start, new_end) inclusive


def _parse_hunks_by_file(diff: str) -> dict[str, HunkList]:
    """Parse a unified diff and return hunk ranges keyed by file path.

    Each hunk is represented as (new_start, new_end) — the inclusive range of
    new-file line numbers covered by that hunk header.  We use the +start,count
    fields from the @@ header directly; we do NOT walk individual diff lines,
    so this is O(hunk-headers) rather than O(diff-lines).
    """
    hunks_by_file: dict[str, HunkList] = {}
    current_file: str | None = None

    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            # Strip leading "b/" that git adds
            if path.startswith("b/"):
                path = path[2:]
            current_file = path
            hunks_by_file.setdefault(current_file, [])
        elif line.startswith("@@ ") and current_file is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                new_start = int(m.group(1))
                new_count = int(m.group(2)) if m.group(2) is not None else 1
                new_end = new_start + max(new_count - 1, 0)
                hunks_by_file[current_file].append((new_start, new_end))

    return hunks_by_file


def _hunk_index(line: int, hunks: HunkList) -> int | None:
    """Return the index of the hunk that contains *line*, or None."""
    for i, (start, end) in enumerate(hunks):
        # Small slack (1 line) to handle off-by-one at hunk boundaries
        if start - 1 <= line <= end + 1:
            return i
    return None


def _line_in_same_hunk(pred_line: int, golden_start: int, golden_end: int, hunks: HunkList) -> bool:
    """True if pred_line and the golden range share a hunk."""
    pred_hunk = _hunk_index(pred_line, hunks)
    if pred_hunk is None:
        return False
    golden_hunk = _hunk_index(golden_start, hunks) or _hunk_index(golden_end, hunks)
    return pred_hunk == golden_hunk


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _matches_expected(
    issue: dict[str, Any],
    expected: dict[str, Any],
    hunks_by_file: dict[str, HunkList] | None = None,
) -> bool:
    if issue.get("file") != expected.get("file"):
        return False

    line = issue.get("line")
    line_range = expected.get("line_range") or []
    if isinstance(line, int) and len(line_range) == 2:
        start, end = int(line_range[0]), int(line_range[1])
        file_hunks = (hunks_by_file or {}).get(issue.get("file", ""), [])
        if file_hunks:
            # Hunk-aware: predicted line must be in the same hunk as the golden range
            if not _line_in_same_hunk(line, start, end, file_hunks):
                return False
        else:
            # Fallback: ±5 absolute tolerance
            if not start - 5 <= line <= end + 5:
                return False

    text = _issue_text(issue)
    title_ok = _text_contains_any(text, list(expected.get("title_keywords") or []))
    evidence_ok = _text_contains_any(text, list(expected.get("evidence_keywords") or []))
    # title OR evidence 匹配即可——LLM 用中文描述时 title keywords 可能不匹配但 evidence
    # （代码变量名）通常保留英文原文；两者满足其一已足够证明找到了同一个 bug
    if not (title_ok or evidence_ok):
        return False

    return _severity_matches(issue, expected)


def _needs_review(
    issue: dict[str, Any],
    expected: dict[str, Any],
    hunks_by_file: dict[str, HunkList] | None = None,
) -> bool:
    if issue.get("file") != expected.get("file"):
        return False

    line = issue.get("line")
    line_range = expected.get("line_range") or []
    near_line = False
    if isinstance(line, int) and len(line_range) == 2:
        start, end = int(line_range[0]), int(line_range[1])
        file_hunks = (hunks_by_file or {}).get(issue.get("file", ""), [])
        if file_hunks:
            # Within 2 hunks counts as "near"
            pred_hunk = _hunk_index(line, file_hunks)
            golden_hunk = _hunk_index(start, file_hunks) or _hunk_index(end, file_hunks)
            if pred_hunk is not None and golden_hunk is not None:
                near_line = abs(pred_hunk - golden_hunk) <= 1
        else:
            near_line = start - 20 <= line <= end + 20

    text = _issue_text(issue)
    shares_expected_text = _text_contains_any(text, list(expected.get("title_keywords") or [])) or _text_contains_any(
        text, list(expected.get("evidence_keywords") or [])
    )
    return near_line or shares_expected_text


# ---------------------------------------------------------------------------
# Miss reason classification
# ---------------------------------------------------------------------------

MissReason = str  # "not_detected" | "line_offset" | "wrong_file" | "severity_miss"


def _classify_miss(
    golden: dict[str, Any],
    issues: list[dict[str, Any]],
    hunks_by_file: dict[str, HunkList] | None = None,
) -> MissReason:
    """Classify why a golden finding was not matched.

    Checked in order (first match wins):
    - not_detected  : no issue reports the same file at all
    - severity_miss : same file + nearby line, but severity too low
    - line_offset   : same file + matching text/hunk, but line outside match window
    """
    golden_file = golden.get("file", "")
    line_range = golden.get("line_range") or []
    golden_start = int(line_range[0]) if len(line_range) == 2 else None
    golden_end = int(line_range[1]) if len(line_range) == 2 else None

    same_file_issues = [iss for iss in issues if iss.get("file") == golden_file]
    if not same_file_issues:
        return "not_detected"

    file_hunks = (hunks_by_file or {}).get(golden_file, [])

    for iss in same_file_issues:
        pred_line = iss.get("line")

        # Check if text/keyword would match
        text = _issue_text(iss)
        title_ok = _text_contains_any(text, list(golden.get("title_keywords") or []))
        evidence_ok = _text_contains_any(text, list(golden.get("evidence_keywords") or []))
        text_ok = title_ok or evidence_ok

        # Check if line is in a broad proximity (±50 or same/adjacent hunk)
        if isinstance(pred_line, int) and golden_start is not None and golden_end is not None:
            if file_hunks:
                pred_hunk = _hunk_index(pred_line, file_hunks)
                golden_hunk = _hunk_index(golden_start, file_hunks) or _hunk_index(golden_end, file_hunks)
                broadly_near = (
                    pred_hunk is not None
                    and golden_hunk is not None
                    and abs(pred_hunk - golden_hunk) <= 2
                )
            else:
                broadly_near = golden_start - 50 <= pred_line <= golden_end + 50
        else:
            broadly_near = False

        if broadly_near and text_ok and not _severity_matches(iss, golden):
            return "severity_miss"

        if (broadly_near or text_ok) and not _matches_expected(iss, golden, hunks_by_file):
            return "line_offset"

    return "not_detected"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_sample(
    sample: dict[str, Any],
    result: dict[str, Any],
    hunks_by_file: dict[str, HunkList] | None = None,
) -> dict[str, Any]:
    issues = result.get("issues") or []
    expected_findings = sample.get("expected_findings") or []
    noise_count = 0

    # Build match matrix: issue_idx -> list of matching expected_ids
    match_matrix: list[list[str]] = []
    review_matrix: list[list[str]] = []
    for issue in issues:
        matches = [str(e["id"]) for e in expected_findings if _matches_expected(issue, e, hunks_by_file)]
        reviews = [str(e["id"]) for e in expected_findings if _needs_review(issue, e, hunks_by_file)]
        match_matrix.append(matches)
        review_matrix.append(reviews)

    # Optimal bipartite matching (greedy by most-constrained first)
    # Sort issues by number of candidates ascending so tight ones get first pick
    order = sorted(range(len(issues)), key=lambda i: len(match_matrix[i]) if match_matrix[i] else 999)
    matched_expected: set[str] = set()
    unmatched_issues: list[int] = []
    duplicate_count = 0

    for i in order:
        candidates = match_matrix[i]
        if not candidates:
            unmatched_issues.append(i)
            continue
        # Pick first unoccupied candidate
        assigned = next((c for c in candidates if c not in matched_expected), None)
        if assigned:
            matched_expected.add(assigned)
        else:
            duplicate_count += 1

    # Review / noise for unmatched issues
    review_expected: set[str] = set()
    for i in unmatched_issues:
        reviews = [r for r in review_matrix[i] if r not in matched_expected]
        if reviews:
            review_expected.add(reviews[0])
        else:
            noise_count += 1

    expected_ids = {str(expected["id"]) for expected in expected_findings}
    misses = sorted(expected_ids - matched_expected)
    review_ids = sorted(review_expected - matched_expected)

    # Classify each miss
    miss_reasons: dict[str, MissReason] = {}
    golden_by_id = {str(e["id"]): e for e in expected_findings}
    for miss_id in misses:
        golden = golden_by_id.get(miss_id, {})
        miss_reasons[miss_id] = _classify_miss(golden, issues, hunks_by_file)

    # Aggregate miss reason counts
    reason_counts: dict[str, int] = {}
    for reason in miss_reasons.values():
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "sample_id": sample["id"],
        "expected_total": len(expected_findings),
        "issue_total": len(issues),
        "hit_count": len(matched_expected),
        "miss_count": len(misses),
        "review_count": len(review_ids),
        "noise_count": noise_count,
        "duplicate_count": duplicate_count,
        "clean_false_positives": noise_count if not expected_findings else 0,
        "hits": sorted(matched_expected),
        "misses": misses,
        "miss_reasons": miss_reasons,
        "miss_reason_counts": reason_counts,
        "review": review_ids,
        "error": result.get("_eval_error", ""),
    }


def _load_diff_for_sample(run_dir: Path, sample: dict[str, Any]) -> str | None:
    """Try to recover the diff used for this sample.

    For synthetic samples the diff is stored in the run JSON under
    payload["sample"]["synthetic_diff"].  For real PR samples the diff is not
    persisted — return None in that case.
    """
    if "synthetic_diff" in sample:
        return sample["synthetic_diff"]
    result_path = run_dir / f"{sample['id']}.json"
    if result_path.exists():
        payload = json.loads(result_path.read_text())
        inner_sample = payload.get("sample", {})
        if "synthetic_diff" in inner_sample:
            return inner_sample["synthetic_diff"]
    return None


def score_run(samples: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    sample_scores = []
    for sample in samples:
        diff = _load_diff_for_sample(run_dir, sample)
        hunks_by_file = _parse_hunks_by_file(diff) if diff else None
        result = _load_result(run_dir, sample["id"])
        sample_scores.append(score_sample(sample, result, hunks_by_file))

    # Aggregate miss reason counts across all samples
    total_miss_reasons: dict[str, int] = {}
    for score in sample_scores:
        for reason, count in score.get("miss_reason_counts", {}).items():
            total_miss_reasons[reason] = total_miss_reasons.get(reason, 0) + count

    return {
        "samples": sample_scores,
        "totals": {
            "samples": len(sample_scores),
            "expected_total": sum(score["expected_total"] for score in sample_scores),
            "hit_count": sum(score["hit_count"] for score in sample_scores),
            "miss_count": sum(score["miss_count"] for score in sample_scores),
            "review_count": sum(score["review_count"] for score in sample_scores),
            "noise_count": sum(score["noise_count"] for score in sample_scores),
            "duplicate_count": sum(score["duplicate_count"] for score in sample_scores),
            "clean_false_positives": sum(score["clean_false_positives"] for score in sample_scores),
            "error_count": sum(1 for score in sample_scores if score["error"]),
            "miss_reasons": total_miss_reasons,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    totals = report["totals"]
    miss_reasons = totals.get("miss_reasons", {})
    lines = [
        "# PRism Eval Score",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| samples | {totals['samples']} |",
        f"| expected_total | {totals['expected_total']} |",
        f"| hit_count | {totals['hit_count']} |",
        f"| miss_count | {totals['miss_count']} |",
        f"| review_count | {totals['review_count']} |",
        f"| noise_count | {totals['noise_count']} |",
        f"| duplicate_count | {totals['duplicate_count']} |",
        f"| clean_false_positives | {totals['clean_false_positives']} |",
        f"| error_count | {totals['error_count']} |",
    ]
    if miss_reasons:
        lines += [
            "",
            "## Miss Reason Breakdown",
            "",
            "| reason | count | meaning |",
            "|---|---:|---|",
            f"| not_detected | {miss_reasons.get('not_detected', 0)} | LLM did not report any issue in this file |",
            f"| line_offset | {miss_reasons.get('line_offset', 0)} | LLM found the bug but reported wrong line / different hunk |",
            f"| severity_miss | {miss_reasons.get('severity_miss', 0)} | Found near the right line but severity too low |",
        ]
    lines += [
        "",
        "## Samples",
        "",
        "| sample | expected | hits | misses | review | noise | dup | not_det | line_off | sev_miss | error |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for score in report["samples"]:
        rc = score.get("miss_reason_counts", {})
        lines.append(
            f"| {score['sample_id']} | {score['expected_total']} | {score['hit_count']} | "
            f"{score['miss_count']} | {score['review_count']} | {score['noise_count']} | "
            f"{score['duplicate_count']} | {rc.get('not_detected', 0)} | "
            f"{rc.get('line_offset', 0)} | {rc.get('severity_miss', 0)} | {score['error']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a PRism eval run against a golden set")
    parser.add_argument("--golden", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()

    report = score_run(_load_yaml_list(Path(args.golden)), Path(args.run))
    print(render_markdown(report), end="")


if __name__ == "__main__":
    main()
