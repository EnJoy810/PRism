"""Import withmartian/code-review-benchmark offline golden comments into PRism eval format.

Usage:
    python eval/import_withmartian.py --out eval/prs_withmartian.yaml
    python eval/import_withmartian.py --out eval/prs_withmartian.yaml --skip-mirrors

Golden comments source:
    https://github.com/withmartian/code-review-benchmark/tree/main/offline/golden_comments

Each entry in the YAML uses kind=withmartian. Because withmartian golden comments
have no line numbers (only text descriptions), scoring must use semantic/LLM matching
(see score_semantic.py) rather than the line-range scorer used for CodeReviewBench.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

import yaml

GOLDEN_BASE = (
    "https://raw.githubusercontent.com/withmartian/code-review-benchmark"
    "/main/offline/golden_comments/{repo}.json"
)

REPOS = ["sentry", "grafana", "discourse", "keycloak", "cal_dot_com"]

SEVERITY_MAP = {
    "Critical": "ERROR",
    "High": "ERROR",
    "Medium": "WARNING",
    "Low": "INFO",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def _best_url(item: dict) -> tuple[str, bool]:
    """Return (pr_url, is_mirror)."""
    raw_url = item.get("url", "")
    orig_url = item.get("original_url") or ""
    is_mirror = "ai-code-review-evaluation" in raw_url
    is_commit = "/commit/" in orig_url

    if not is_mirror:
        return raw_url, False
    if orig_url and not is_commit:
        return orig_url, False
    # mirror PR with commit-only original — use the mirror (it has the PR diff)
    return raw_url, True


def fetch_golden(repo: str) -> list[dict]:
    url = GOLDEN_BASE.format(repo=repo)
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


def build_sample(repo: str, idx: int, item: dict) -> dict | None:
    pr_url, is_mirror = _best_url(item)
    if not pr_url:
        return None

    comments = item.get("comments", [])
    if not comments:
        return None

    title = item.get("pr_title", "")
    sample_id = f"withmartian_{repo}_{idx + 1}"

    expected_findings = []
    for j, c in enumerate(comments):
        desc = c.get("comment", "").strip()
        sev_raw = c.get("severity", "Medium")
        severity = SEVERITY_MAP.get(sev_raw, "WARNING")
        if not desc:
            continue
        expected_findings.append({
            "id": f"{sample_id}-g{j + 1}",
            "description": desc,
            "severity": severity,
            "severity_original": sev_raw,
            # No line_range — semantic matching only
        })

    if not expected_findings:
        return None

    sample: dict = {
        "id": sample_id,
        "url": pr_url,
        "kind": "withmartian",
        "repo_group": repo,
        "is_mirror": is_mirror,
    }
    if title:
        sample["pr_title"] = title
    if item.get("az_comment"):
        sample["note"] = item["az_comment"]
    sample["expected_findings"] = expected_findings
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(description="Import withmartian benchmark")
    parser.add_argument("--out", default="eval/prs_withmartian.yaml")
    parser.add_argument(
        "--skip-mirrors",
        action="store_true",
        help="Skip PRs whose URL is a mirrored repo (ai-code-review-evaluation)",
    )
    args = parser.parse_args()

    samples: list[dict] = []
    total_golden = 0

    for repo in REPOS:
        print(f"Fetching {repo}...", end=" ", flush=True)
        items = fetch_golden(repo)
        print(f"{len(items)} PRs")
        for idx, item in enumerate(items):
            sample = build_sample(repo, idx, item)
            if sample is None:
                continue
            if args.skip_mirrors and sample["is_mirror"]:
                print(f"  skip mirror: {sample['url']}")
                continue
            n = len(sample["expected_findings"])
            total_golden += n
            print(f"  [{sample['id']}] {n} golden  {sample['url'][:70]}")
            samples.append(sample)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        yaml.dump(samples, f, allow_unicode=True, sort_keys=False, width=120)

    print(f"\nWrote {len(samples)} samples ({total_golden} golden findings) → {out}")
    print("Note: use score_semantic.py for LLM-judge scoring (no line numbers in this dataset)")


if __name__ == "__main__":
    main()
