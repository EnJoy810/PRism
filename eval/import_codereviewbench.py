"""Import CodeReviewBench test cases into PRism's eval sample format.

Usage:
    python eval/import_codereviewbench.py --out eval/prs_codereviewbench.yaml
    python eval/import_codereviewbench.py --lang python --out eval/prs_codereviewbench_py.yaml

The CodeReviewBench dataset (https://github.com/kodustech/codereviewbench) contains
75 synthetic test cases across 5 languages with precise bug locations as ground truth.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

SAMPLES_URL = (
    "https://raw.githubusercontent.com/kodustech/codereviewbench/main"
    "/src/lib/data/samples.json"
)
SAMPLES_LOCAL = Path("/tmp/codereviewbench/src/lib/data/samples.json")


# ---------------------------------------------------------------------------
# Patch format conversion
# ---------------------------------------------------------------------------

def _convert_patch(patch: str) -> str:
    """Convert CodeReviewBench patch format to standard unified diff.

    CodeReviewBench uses:
        ## file: 'path'
        @@ -N,M +N,M @@
        __new hunk__
        10  context line
        11 +added line

    Standard unified diff uses:
        --- a/path
        +++ b/path
        @@ -N,M +N,M @@
         context line
        +added line
    """
    out: list[str] = []
    for line in patch.splitlines():
        # File header
        if line.startswith("## file: '"):
            path = line[10:].rstrip("'")
            out.append(f"--- a/{path}")
            out.append(f"+++ b/{path}")
            continue
        # Separator
        if line.strip() == "__new hunk__":
            continue
        # Hunk header (keep as-is)
        if line.startswith("@@"):
            out.append(line)
            continue
        # Code line: "{linenum} {marker}{content}"
        m = re.match(r"^\d+ (.*)$", line)
        if m:
            out.append(m.group(1))
            continue
        # Fallback
        out.append(line)
    return "\n".join(out) + "\n"


def _extract_files(patch: str) -> list[str]:
    """Extract file paths from CodeReviewBench patch."""
    return re.findall(r"^## file: '([^']+)'", patch, re.MULTILINE)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

def _load_samples() -> list[dict[str, Any]]:
    if SAMPLES_LOCAL.exists():
        with SAMPLES_LOCAL.open() as f:
            return json.load(f)
    print("Downloading samples.json from GitHub...", file=sys.stderr)
    with urllib.request.urlopen(SAMPLES_URL, timeout=60) as resp:
        return json.load(resp)


def _deduplicate(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one entry per test case (dataset has one row per model per test)."""
    seen: dict[str, dict[str, Any]] = {}
    for s in samples:
        key = s["testDescription"]
        if key not in seen:
            seen[key] = s
    return list(seen.values())


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def _make_sample_id(test_description: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", test_description.casefold()).strip("_")
    return f"codereviewbench__{slug}"


def convert_sample(raw: dict[str, Any]) -> dict[str, Any]:
    sample_id = _make_sample_id(raw["testDescription"])
    diff = _convert_patch(raw["patch"])
    files = _extract_files(raw["patch"])

    expected_findings = []
    for i, bug in enumerate(raw.get("referenceBugs") or [], 1):
        start = bug["relevantLinesStart"]
        end = bug["relevantLinesEnd"]
        expected_findings.append(
            {
                "id": f"{sample_id}-b{i}",
                "file": bug["relevantFile"],
                "line_range": [start, end],
                "title_keywords": [],
                "evidence_keywords": [],
                "severity": "ERROR",
                "source": "codereviewbench",
                "reason": f"Bug at lines {start}-{end} per CodeReviewBench ground truth",
            }
        )

    return {
        "id": sample_id,
        "url": f"synthetic://codereviewbench/{sample_id}",
        "kind": f"codereviewbench-{raw['category']}",
        "lang": raw["lang"],
        "synthetic_diff": diff,
        "synthetic_files": files,
        "synthetic_pr_title": raw.get("prSummary", raw["testDescription"])[:120],
        "synthetic_pr_description": raw.get("prSummary", ""),
        "expected_findings": expected_findings,
        "notes": (
            "Synthetic test case from CodeReviewBench. "
            "Ground truth is exact bug line ranges, not human review comments."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Import CodeReviewBench into PRism eval YAML")
    parser.add_argument("--lang", default=None, help="Filter by language (e.g. python, java)")
    parser.add_argument("--category", default=None, help="Filter by category: local or cross-file")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    raw_samples = _load_samples()
    samples = _deduplicate(raw_samples)

    if args.lang:
        samples = [s for s in samples if s["lang"] == args.lang]
    if args.category:
        samples = [s for s in samples if s["category"] == args.category]
    if args.limit:
        samples = samples[: args.limit]

    converted = [convert_sample(s) for s in samples]
    Path(args.out).write_text(yaml.safe_dump(converted, sort_keys=False, allow_unicode=True))
    print(f"wrote {len(converted)} samples to {args.out}")


if __name__ == "__main__":
    main()
