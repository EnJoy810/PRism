"""Upload PRism eval golden set to Langfuse Datasets.

Usage:
    cd backend && .venv/bin/python ../eval/upload_dataset_to_langfuse.py
    cd backend && .venv/bin/python ../eval/upload_dataset_to_langfuse.py --golden ../eval/prs_codereviewbench_supported.yaml --name prism-codereviewbench

Each YAML sample becomes one DatasetItem:
  input:  {id, url, kind, lang, synthetic_diff (if present)}
  output: {expected_findings: [...]}
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")


def upload(golden_path: Path, dataset_name: str) -> None:
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        print("ERROR: LANGFUSE_PUBLIC_KEY not set in .env")
        sys.exit(1)

    from langfuse import Langfuse
    lf = Langfuse()

    samples = yaml.safe_load(golden_path.read_text())
    if not isinstance(samples, list):
        raise ValueError(f"Expected a list in {golden_path}")

    print(f"Creating / refreshing dataset '{dataset_name}' ({len(samples)} items)...")
    lf.create_dataset(name=dataset_name, description="PRism CodeReviewBench golden set")

    ok = 0
    for s in samples:
        item_input = {
            "id": s["id"],
            "url": s.get("url", ""),
            "kind": s.get("kind", ""),
            "lang": s.get("lang", ""),
        }
        if s.get("synthetic_diff"):
            item_input["synthetic_diff"] = s["synthetic_diff"]

        item_output = {"expected_findings": s.get("expected_findings", [])}

        lf.create_dataset_item(
            dataset_name=dataset_name,
            input=item_input,
            expected_output=item_output,
            id=s["id"],
        )
        ok += 1

    lf.flush()
    print(f"Done — {ok} items uploaded to '{dataset_name}'.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default="eval/prs_codereviewbench_supported.yaml")
    parser.add_argument("--name", default="prism-codereviewbench")
    args = parser.parse_args()
    upload(Path(args.golden), args.name)


if __name__ == "__main__":
    main()
