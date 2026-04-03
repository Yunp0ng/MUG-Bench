#!/usr/bin/env python3
"""Build the lightweight EMUG-Bench release subset from cleaned benchmark inputs."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path


TARGET_PER_LEVEL = 50
LEVELS = ["L1", "L2", "L3"]
BAD_L1_TERMS = ("最终", "为什么", "如何", "怎么看", "意味着", "讨论中", "围绕")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalize_pattern(level: str, pattern: object) -> str:
    if level in {"L1", "L2"}:
        return "N/A"
    text = str(pattern or "N/A").strip()
    if ("A" in text and "决策反转" in text) or text in {"A", "A:", "A："}:
        return "A"
    if ("B" in text and "噪音" in text) or text in {"B", "B:", "B："}:
        return "B"
    if ("C" in text and "隐性拒绝" in text) or text in {"C", "C:", "C："}:
        return "C"
    if text.startswith("A"):
        return "A"
    if text.startswith("B"):
        return "B"
    if text.startswith("C"):
        return "C"
    return "N/A"


def quality_score(level: str, sample: dict) -> int:
    question = sample["question"]
    answer = sample["gold_answer"]
    score = 0
    score -= len(sample.get("evidence_ids", []))
    score -= max(0, len(question) - 32) // 8
    score -= max(0, len(answer) - 120) // 20
    if level == "L1":
        if len(sample.get("evidence_ids", [])) <= 2:
            score += 3
        if not any(term in question for term in BAD_L1_TERMS):
            score += 2
        if "会议中提到" in question:
            score += 1
    elif level == "L2":
        if sample.get("audit_action") == "keep":
            score += 2
        if sample.get("audit_primary_issue") == "none":
            score += 2
    else:
        if sample.get("audit_action") == "keep":
            score += 2
        if sample.get("audit_primary_issue") == "none":
            score += 2
        if normalize_pattern(level, sample.get("pattern")) in {"A", "B", "C"}:
            score += 1
    return score


def is_candidate(level: str, sample: dict) -> bool:
    question = sample.get("question", "").strip()
    answer = sample.get("gold_answer", "").strip()
    evidence_ids = sample.get("evidence_ids", [])
    if not question or not answer or not evidence_ids:
        return False
    if len(answer) > 260 or len(question) > 80:
        return False
    if level == "L1":
        if len(evidence_ids) > 3:
            return False
        if any(term in question for term in BAD_L1_TERMS):
            return False
        if sample.get("audit_primary_issue") not in {"wrong_level", "too_easy"}:
            return False
        return True
    if level == "L2":
        return sample.get("audit_action") == "keep" and sample.get("audit_primary_issue") == "none"
    return sample.get("audit_action") == "keep" and sample.get("audit_primary_issue") == "none"


def collect_candidates(benchmark_root: Path, transcript_root: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {level: [] for level in LEVELS}

    for level in LEVELS:
        for bench_path in sorted((benchmark_root / level).glob("mug_vcsum_*.json")):
            benchmark = load_json(bench_path)
            transcript = load_json(transcript_root / bench_path.name)
            split = transcript.get("split", "unknown")
            for sample in benchmark.get("samples", []):
                if not is_candidate(level, sample):
                    continue
                row = dict(sample)
                row["_level"] = level
                row["_source_file"] = benchmark["source_file"]
                row["_transcript_split"] = split
                row["_pattern_norm"] = normalize_pattern(level, sample.get("pattern"))
                row["_quality"] = quality_score(level, row)
                out[level].append(row)

    for level in LEVELS:
        out[level].sort(
            key=lambda row: (
                -row["_quality"],
                row["_source_file"],
                row["query_id"],
            )
        )
    return out


def take_diverse(candidates: list[dict], target: int, group_order: list[str]) -> list[dict]:
    grouped = defaultdict(list)
    for row in candidates:
        grouped[row["_group"]].append(row)

    selected: list[dict] = []
    used_query_ids: set[str] = set()
    used_files: set[str] = set()

    # First pass: maximize source-file coverage.
    while len(selected) < target:
        progress = False
        for group in group_order:
            bucket = grouped[group]
            while bucket and bucket[0]["query_id"] in used_query_ids:
                bucket.pop(0)
            if not bucket:
                continue
            idx = 0
            while idx < len(bucket) and bucket[idx]["_source_file"] in used_files:
                idx += 1
            if idx >= len(bucket):
                continue
            row = bucket.pop(idx)
            selected.append(row)
            used_query_ids.add(row["query_id"])
            used_files.add(row["_source_file"])
            progress = True
            if len(selected) >= target:
                break
        if not progress:
            break

    # Second pass: fill the rest by score.
    if len(selected) < target:
        remaining = []
        for group in group_order:
            remaining.extend(grouped[group])
        remaining.sort(key=lambda row: (-row["_quality"], row["_source_file"], row["query_id"]))
        for row in remaining:
            if row["query_id"] in used_query_ids:
                continue
            selected.append(row)
            used_query_ids.add(row["query_id"])
            if len(selected) >= target:
                break

    if len(selected) != target:
        raise RuntimeError(f"expected {target} samples, got {len(selected)}")
    return selected


def select_samples(candidates: dict[str, list[dict]]) -> dict[str, list[dict]]:
    selected = {}

    l1 = []
    for row in candidates["L1"]:
        row = dict(row)
        row["_group"] = "all"
        l1.append(row)
    selected["L1"] = take_diverse(l1, TARGET_PER_LEVEL, ["all"])

    l2 = []
    for row in candidates["L2"]:
        row = dict(row)
        row["_group"] = row["_transcript_split"]
        l2.append(row)
    selected["L2"] = take_diverse(l2, TARGET_PER_LEVEL, ["train", "dev", "test", "unknown"])

    l3 = []
    for row in candidates["L3"]:
        row = dict(row)
        row["_group"] = row["_pattern_norm"]
        l3.append(row)
    selected["L3"] = take_diverse(l3, TARGET_PER_LEVEL, ["A", "B", "C", "N/A"])

    return selected


def build_release(benchmark_root: Path, transcript_root_in: Path, data_root: Path) -> None:
    selected = select_samples(collect_candidates(benchmark_root, transcript_root_in))

    benchmark_root = data_root / "benchmark"
    transcript_root = data_root / "transcripts" / "vcsum"
    if data_root.exists():
        shutil.rmtree(data_root)
    transcript_root.mkdir(parents=True, exist_ok=True)

    all_files = set()
    summary = {"levels": {}, "unique_transcript_count": 0}

    for level in LEVELS:
        rows = []
        for idx, row in enumerate(selected[level], start=1):
            all_files.add(row["_source_file"])
            rows.append(
                {
                    "sample_id": f"emug_{level.lower()}_{idx:03d}",
                    "level": level,
                    "source_file": row["_source_file"],
                    "query_id": row["query_id"],
                    "topic": row.get("topic", ""),
                    "pattern": row["_pattern_norm"],
                    "question": row["question"],
                    "gold_answer": row["gold_answer"],
                    "evidence_ids": row["evidence_ids"],
                    "transcript_path": f"../transcripts/vcsum/{row['_source_file']}",
                }
            )
        dump_json(
            benchmark_root / f"{level}.json",
            {
                "dataset": "EMUG-Bench",
                "subset": "vcsum_sampled_release",
                "level": level,
                "sample_count": len(rows),
                "samples": rows,
            },
        )
        summary["levels"][level] = {
            "sample_count": len(rows),
            "source_files": len({row["source_file"] for row in rows}),
            "pattern_distribution": count_values(rows, "pattern"),
        }

    for source_file in sorted(all_files):
        shutil.copy2(transcript_root_in / source_file, transcript_root / source_file)

    summary["unique_transcript_count"] = len(all_files)
    dump_json(data_root / "selection_summary.json", summary)


def count_values(rows: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field, "N/A"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the public EMUG-Bench sampled release.")
    parser.add_argument("--benchmark-root", required=True, help="cleaned benchmark root with L1/L2/L3 folders")
    parser.add_argument("--transcript-root", required=True, help="VCSum transcript root")
    parser.add_argument("--output-root", required=True, help="output data root")
    args = parser.parse_args()
    build_release(
        benchmark_root=Path(args.benchmark_root),
        transcript_root_in=Path(args.transcript_root),
        data_root=Path(args.output_root),
    )


if __name__ == "__main__":
    main()
