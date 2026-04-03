#!/usr/bin/env python3
"""Merge multiple cleaned benchmark roots into a single benchmark root."""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
from pathlib import Path


LEVELS = ["L1", "L2", "L3"]


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_samples(root: str) -> list[dict]:
    rows: list[dict] = []
    for level in LEVELS:
        for fp in sorted(glob.glob(os.path.join(root, level, "*.json"))):
            payload = load_json(fp)
            source_file = payload.get("source_file", os.path.basename(fp))
            for sample in payload.get("samples", []):
                rows.append(
                    {
                        "root": root,
                        "level": level,
                        "source_file": source_file,
                        "sample": sample,
                    }
                )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge cleaned benchmark roots")
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=["out/Benchmark_QA_cleaned_v1", "out_vcsum_batch1/Benchmark_QA_cleaned"],
        help="input benchmark roots to merge",
    )
    parser.add_argument("--output-root", default="out/Benchmark_QA_merged_v2")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    for level in LEVELS:
        ensure_dir(str(output_root / level))

    all_rows: list[dict] = []
    input_counts: dict[str, dict[str, int]] = {}
    for root in args.inputs:
        rows = collect_samples(root)
        all_rows.extend(rows)
        counter = collections.Counter(r["level"] for r in rows)
        input_counts[root] = {
            "total_samples": len(rows),
            "L1": counter.get("L1", 0),
            "L2": counter.get("L2", 0),
            "L3": counter.get("L3", 0),
        }

    grouped: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for row in all_rows:
        grouped[(row["level"], row["source_file"])].append(row["sample"])

    merged_counts = collections.Counter()
    source_file_counts = collections.Counter()
    merged_files = 0
    for (level, source_file), samples in sorted(grouped.items(), key=lambda x: (LEVELS.index(x[0][0]), x[0][1])):
        merged_files += 1
        finalized = []
        for idx, sample in enumerate(samples):
            item = dict(sample)
            item["level"] = level
            item["query_id"] = f"{source_file}_{level}_{idx}"
            finalized.append(item)
        payload = {
            "source_file": source_file,
            "level": level,
            "sample_count": len(finalized),
            "samples": finalized,
        }
        with open(output_root / level / source_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        merged_counts[level] += len(finalized)
        source_file_counts[source_file] += len(finalized)

    summary = {
        "inputs": args.inputs,
        "input_counts": input_counts,
        "merged_total_samples": sum(merged_counts.values()),
        "merged_level_counts": dict(merged_counts),
        "merged_file_count": merged_files,
        "distinct_source_files": len(source_file_counts),
        "output_root": str(output_root),
    }

    with open(output_root / "merge_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
