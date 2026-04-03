#!/usr/bin/env python3
"""Apply benchmark audit decisions and build a cleaned benchmark dataset."""

from __future__ import annotations

import argparse
import collections
import copy
import csv
import datetime as dt
import glob
import http.client
import itertools
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from benchmark_audit import (
    LEVELS,
    build_evidence_block,
    call_audit_llm,
    clean_json_response,
    ensure_dir,
    load_json,
    load_transcript_id_map,
    parse_api_keys,
)


PROMPT_VERSION = "cleanup_v3_zh_rewrite_plus_reaudit_level_specific"

REWRITE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "benchmark_sample_rewrite",
        "schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "gold_answer": {"type": "string"},
                "reasoning_from_mining": {"type": "string"},
            },
            "required": ["question", "gold_answer", "reasoning_from_mining"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


def load_audit_rows(path: str) -> Dict[Tuple[str, str, str], dict]:
    rows: Dict[Tuple[str, str, str], dict] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows[(row["level"], row["source_file"], row["query_id"])] = row
    return rows


def load_benchmark_samples(benchmark_root: str) -> List[dict]:
    rows: List[dict] = []
    for level in LEVELS:
        for fp in sorted(glob.glob(os.path.join(benchmark_root, level, "*.json"))):
            payload = load_json(fp)
            source_file = payload.get("source_file", os.path.basename(fp))
            for sample in payload.get("samples", []):
                rows.append(
                    {
                        "source_file": source_file,
                        "file_path": fp,
                        "level": level,
                        "sample": sample,
                    }
                )
    return rows


def append_cache(path: str, key: str, rewrite: dict) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    row = {
        "key": key,
        "prompt_version": PROMPT_VERSION,
        "timestamp": dt.datetime.now().isoformat(),
        "rewrite": rewrite,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_rewrite_cache(path: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("prompt_version") != PROMPT_VERSION:
                continue
            out[row["key"]] = row["rewrite"]
    return out


def rewrite_key(level: str, source_file: str, query_id: str) -> str:
    return f"{level}|{source_file}|{query_id}"


def rewrite_prompt_for_level(level: str) -> str:
    if level == "L1":
        return (
            "L1 重写要求:\n"
            "1. 问题必须是显性局部检索题，答案应由 1-2 句证据直接决定。\n"
            "2. 不允许依赖前后文补全、跨段聚合、隐含决策态或冲突消解。\n"
            "3. 金标答案应简洁直接，只保留证据明确表达的事实槽位，如人名、时间、数值、对象、结论。\n"
            "4. 若当前证据不足以支持一个合格的 L1 问题，就应尽量收缩问题范围，而不是脑补。"
        )
    if level == "L2":
        return (
            "L2 重写要求:\n"
            "1. 问题必须要求跨段聚合，答案信息至少分布在多个位置。\n"
            "2. 但不能依赖前后反转、最终态变化、隐性拒绝或强噪音过滤；若依赖这些机制就不是 L2。\n"
            "3. 金标答案应体现聚合结果，但只能保留证据中稳定出现的信息，不能扩写额外细节。\n"
            "4. reasoning_from_mining 要点明这是跨段整合，而非动态推理。"
        )
    return (
        "L3 重写要求:\n"
        "1. 问题必须保留动态性，只有跟踪最终态、过滤噪音或识别隐性拒绝，才能稳定答对。\n"
        "2. 若最后一句直接明牌且前文不存在会误导模型的变化、噪音或拒绝语义，就不应写成 L3。\n"
        "3. 金标答案必须明确给出最终业务结论，而不是过程性讨论。\n"
        "4. reasoning_from_mining 要写清楚这条样本的 L3 机制是什么，例如反转、噪音干扰、隐性拒绝。"
    )


def call_rewrite_llm(
    api_keys: List[str],
    api_host: str,
    api_path: str,
    model: str,
    target_level: str,
    source_file: str,
    sample: dict,
    audit: dict,
    evidence_text: str,
    max_retries: int,
    key_cycle,
    key_lock: threading.Lock,
) -> dict:
    system_prompt = (
        "你是中文会议 benchmark 数据清洗助手。"
        "你的任务是根据审核意见，重写 benchmark 样本中的问题、金标答案和简短推理说明。"
        "你必须严格受限于给定证据，不得引入证据中不存在的事实。"
    )
    user_prompt = (
        f"目标层级: {target_level}\n"
        f"source_file: {source_file}\n"
        f"原 query_id: {sample.get('query_id', '')}\n"
        f"原问题: {sample.get('question', '')}\n"
        f"原金标答案: {sample.get('gold_answer', '')}\n"
        f"原 reasoning_from_mining: {sample.get('reasoning_from_mining', '')}\n"
        f"原 pattern: {sample.get('pattern', 'N/A')}\n\n"
        f"审核动作: {audit['action']}\n"
        f"审核主问题: {audit['primary_issue']}\n"
        f"审核理由: {audit['reason']}\n\n"
        f"证据原文:\n{evidence_text}\n\n"
        "重写要求:\n"
        "1. 只输出由证据直接或稳健支持的问题与答案，不能脑补。\n"
        "2. 问题应自然，不泄露答案方向。\n"
        "3. 金标答案应只回答问题本身，不附加问题未问到的细节。\n"
        "4. reasoning_from_mining 用1-2句中文说明为什么这条样本符合目标层级。\n"
        "5. 不要改动 evidence_ids，这些由程序保留。\n\n"
        f"{rewrite_prompt_for_level(target_level)}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "response_format": REWRITE_SCHEMA,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
    }
    last_err = ""
    for _ in range(max_retries):
        try:
            with key_lock:
                api_key = next(key_cycle)
            headers["Authorization"] = f"Bearer {api_key}"
            conn = http.client.HTTPSConnection(api_host, timeout=120)
            conn.request("POST", api_path, json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers)
            res = conn.getresponse()
            data = res.read().decode("utf-8")
            if res.status != 200:
                last_err = f"status={res.status} body={data[:300]}"
                if res.status == 429:
                    time.sleep(5)
                continue
            top = json.loads(clean_json_response(data))
            if "choices" in top:
                content = top.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                return json.loads(clean_json_response(content))
            return top
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"rewrite failed: {last_err}")


def rewrite_sample(
    sample_row: dict,
    audit: dict,
    target_level: str,
    id_map: Dict[int, str],
    api_keys: List[str],
    api_host: str,
    api_path: str,
    model: str,
    max_retries: int,
    key_cycle,
    key_lock: threading.Lock,
    cache: Dict[str, dict],
    cache_path: str,
    cache_lock: threading.Lock,
) -> dict:
    sample = sample_row["sample"]
    key = rewrite_key(sample_row["level"], sample_row["source_file"], sample["query_id"])
    with cache_lock:
        cached = cache.get(key)
    if cached is not None:
        return cached
    evidence_text = build_evidence_block(id_map, sample.get("evidence_ids", []))
    rewrite = call_rewrite_llm(
        api_keys=api_keys,
        api_host=api_host,
        api_path=api_path,
        model=model,
        target_level=target_level,
        source_file=sample_row["source_file"],
        sample=sample,
        audit=audit,
        evidence_text=evidence_text,
        max_retries=max_retries,
        key_cycle=key_cycle,
        key_lock=key_lock,
    )
    with cache_lock:
        cache[key] = rewrite
        append_cache(cache_path, key, rewrite)
    return rewrite


def post_audit_cache_key(level: str, source_file: str, query_id: str) -> str:
    return f"{level}|{source_file}|{query_id}"


def append_post_audit_cache(path: str, key: str, audit: dict) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    row = {
        "key": key,
        "prompt_version": PROMPT_VERSION,
        "timestamp": dt.datetime.now().isoformat(),
        "post_audit": audit,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_post_audit_cache(path: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("prompt_version") != PROMPT_VERSION:
                continue
            if "post_audit" in row:
                out[row["key"]] = row["post_audit"]
    return out


def post_audit_rewritten_sample(
    sample_row: dict,
    rewritten_sample: dict,
    target_level: str,
    id_map: Dict[int, str],
    api_keys: List[str],
    api_host: str,
    api_path: str,
    model: str,
    max_retries: int,
    key_cycle,
    key_lock: threading.Lock,
    cache: Dict[str, dict],
    cache_path: str,
    cache_lock: threading.Lock,
) -> dict:
    key = post_audit_cache_key(target_level, sample_row["source_file"], sample_row["sample"]["query_id"])
    with cache_lock:
        cached = cache.get(key)
    if cached is not None:
        return cached
    audit = call_audit_llm(
        api_keys=api_keys,
        api_host=api_host,
        api_path=api_path,
        model=model,
        level=target_level,
        query_id=rewritten_sample.get("query_id", sample_row["sample"]["query_id"]),
        source_file=sample_row["source_file"],
        question=rewritten_sample.get("question", ""),
        gold_answer=rewritten_sample.get("gold_answer", ""),
        pattern=rewritten_sample.get("pattern", "N/A"),
        evidence_text=build_evidence_block(id_map, rewritten_sample.get("evidence_ids", [])),
        max_retries=max_retries,
        key_cycle=key_cycle,
        key_lock=key_lock,
    )
    with cache_lock:
        cache[key] = audit
        append_post_audit_cache(cache_path, key, audit)
    return audit


def finalize_groups(groups: Dict[Tuple[str, str], List[dict]]) -> Dict[Tuple[str, str], dict]:
    output: Dict[Tuple[str, str], dict] = {}
    for (level, source_file), samples in groups.items():
        finalized = []
        for idx, sample in enumerate(samples):
            item = copy.deepcopy(sample)
            item["level"] = level
            item["query_id"] = f"{source_file}_{level}_{idx}"
            finalized.append(item)
        output[(level, source_file)] = {
            "source_file": source_file,
            "level": level,
            "sample_count": len(finalized),
            "samples": finalized,
        }
    return output


def write_outputs(
    output_root: str,
    grouped_payloads: Dict[Tuple[str, str], dict],
    manifest_rows: List[dict],
    summary: dict,
) -> None:
    for level in LEVELS:
        ensure_dir(os.path.join(output_root, level))
    for (level, source_file), payload in grouped_payloads.items():
        out_path = os.path.join(output_root, level, source_file)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    manifest_json = os.path.join(output_root, "cleanup_manifest.json")
    manifest_csv = os.path.join(output_root, "cleanup_manifest.csv")
    summary_json = os.path.join(output_root, "cleanup_summary.json")

    with open(manifest_json, "w", encoding="utf-8") as f:
        json.dump(manifest_rows, f, ensure_ascii=False, indent=2)
    with open(manifest_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "source_file",
            "original_level",
            "original_query_id",
            "audit_action",
            "recommended_level",
            "final_status",
            "final_level",
            "new_query_id",
            "rewrite_applied",
            "post_audit_action",
            "post_audit_recommended_level",
            "post_audit_primary_issue",
            "primary_issue",
            "reason",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply audit results and build cleaned benchmark dataset")
    parser.add_argument("--benchmark-root", default="out/Benchmark_QA")
    parser.add_argument("--audit-results", default="out/benchmark_audit_v2/audit_results.csv")
    parser.add_argument("--source-root", default="data/Real_meeting")
    parser.add_argument("--output-root", default="out/Benchmark_QA_cleaned")
    parser.add_argument("--rewrite-mode", choices=["llm", "keep", "drop"], default="llm")
    parser.add_argument("--rewrite-cache-path", default="out/benchmark_cleanup/rewrite_cache.jsonl")
    parser.add_argument("--post-audit-cache-path", default="out/benchmark_cleanup/post_audit_cache.jsonl")
    parser.add_argument("--post-audit-model", default="")
    parser.add_argument("--include-post-audit-failed", action="store_true")
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--api-keys", default="")
    parser.add_argument("--api-keys-env", default="ACMMM_AUDIT_API_KEYS")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args()

    audit_rows = load_audit_rows(args.audit_results)
    benchmark_rows = load_benchmark_samples(args.benchmark_root)
    transcript_cache: Dict[str, Dict[int, str]] = {}
    rewrite_cache = load_rewrite_cache(args.rewrite_cache_path)
    post_audit_cache = load_post_audit_cache(args.post_audit_cache_path)
    grouped: Dict[Tuple[str, str], List[dict]] = collections.defaultdict(list)
    manifest_rows: List[dict] = []

    needs_llm = args.rewrite_mode == "llm"
    api_keys = parse_api_keys(args)
    api_host = os.getenv("ACMMM_JUDGE_API_HOST", "yunwu.ai")
    api_path = os.getenv("ACMMM_JUDGE_API_PATH", "/v1/chat/completions")
    if needs_llm and not api_keys:
        raise RuntimeError("rewrite_mode=llm requires API keys via --api-keys, ACMMM_AUDIT_API_KEYS, or ACMMM_JUDGE_API_KEY")

    rewrite_tasks = []
    for row in benchmark_rows:
        sample = row["sample"]
        key = (row["level"], row["source_file"], sample["query_id"])
        audit = audit_rows.get(key)
        if audit is None:
            raise KeyError(f"missing audit result for {key}")
        row["audit"] = audit
        if row["source_file"] not in transcript_cache:
            transcript_cache[row["source_file"]] = load_transcript_id_map(args.source_root, row["source_file"])
        row["id_map"] = transcript_cache[row["source_file"]]
        if audit["action"] == "rewrite" and args.rewrite_mode == "llm":
            rewrite_tasks.append(row)

    if rewrite_tasks:
        key_cycle = itertools.cycle(api_keys)
        key_lock = threading.Lock()
        cache_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
            future_map = {
                executor.submit(
                    rewrite_sample,
                    row,
                    row["audit"],
                    row["audit"]["recommended_level"] if row["audit"]["recommended_level"] in LEVELS else row["level"],
                    row["id_map"],
                    api_keys,
                    api_host,
                    api_path,
                    args.model,
                    args.max_retries,
                    key_cycle,
                    key_lock,
                    rewrite_cache,
                    args.rewrite_cache_path,
                    cache_lock,
                ): row
                for row in rewrite_tasks
            }
            for future in as_completed(future_map):
                row = future_map[future]
                row["rewrite"] = future.result()

            post_audit_model = args.post_audit_model or args.model
            post_future_map = {
                executor.submit(
                    post_audit_rewritten_sample,
                    row,
                    {
                        **copy.deepcopy(row["sample"]),
                        "question": row["rewrite"]["question"].strip(),
                        "gold_answer": row["rewrite"]["gold_answer"].strip(),
                        "reasoning_from_mining": row["rewrite"]["reasoning_from_mining"].strip(),
                    },
                    row["audit"]["recommended_level"] if row["audit"]["recommended_level"] in LEVELS else row["level"],
                    row["id_map"],
                    api_keys,
                    api_host,
                    api_path,
                    post_audit_model,
                    args.max_retries,
                    key_cycle,
                    key_lock,
                    post_audit_cache,
                    args.post_audit_cache_path,
                    cache_lock,
                ): row
                for row in rewrite_tasks
            }
            for future in as_completed(post_future_map):
                row = post_future_map[future]
                row["post_audit"] = future.result()

    action_counts = collections.Counter()
    final_level_counts = collections.Counter()
    final_status_counts = collections.Counter()
    rewrite_applied = 0
    post_audit_pass_count = 0
    post_audit_fail_count = 0

    for row in benchmark_rows:
        sample = copy.deepcopy(row["sample"])
        audit = row["audit"]
        action = audit["action"]
        target_level = audit["recommended_level"] if audit["recommended_level"] in LEVELS else row["level"]
        final_status = "kept"
        rewrite_used = False
        post_audit = None

        if action == "drop":
            final_status = "dropped"
        elif action in {"downgrade", "upgrade"}:
            sample["audit_original_level"] = row["level"]
            target_level = audit["recommended_level"]
            final_status = "moved"
        elif action == "rewrite":
            if args.rewrite_mode == "drop":
                final_status = "dropped_rewrite"
            elif args.rewrite_mode == "keep":
                sample["needs_rewrite"] = True
                sample["audit_reason"] = audit["reason"]
                final_status = "kept_unrewritten"
            else:
                rewrite = row.get("rewrite")
                if rewrite is None:
                    raise RuntimeError(f"missing rewrite result for {sample['query_id']}")
                sample["question"] = rewrite["question"].strip()
                sample["gold_answer"] = rewrite["gold_answer"].strip()
                sample["reasoning_from_mining"] = rewrite["reasoning_from_mining"].strip()
                sample["rewritten_by_cleanup"] = True
                sample["audit_reason"] = audit["reason"]
                rewrite_used = True
                rewrite_applied += 1
                post_audit = row.get("post_audit")
                if post_audit is None:
                    raise RuntimeError(f"missing post-audit result for {sample['query_id']}")
                sample["post_audit"] = post_audit
                post_ok = (
                    post_audit["action"] == "keep"
                    and post_audit["recommended_level"] == target_level
                )
                if post_ok:
                    final_status = "rewritten"
                    post_audit_pass_count += 1
                else:
                    final_status = "post_audit_failed"
                    post_audit_fail_count += 1

        sample["original_query_id"] = row["sample"]["query_id"]
        sample["audit_action"] = action
        sample["audit_primary_issue"] = audit["primary_issue"]

        manifest = {
            "source_file": row["source_file"],
            "original_level": row["level"],
            "original_query_id": row["sample"]["query_id"],
            "audit_action": action,
            "recommended_level": audit["recommended_level"],
            "final_status": final_status,
            "final_level": "" if final_status.startswith("dropped") else target_level,
            "new_query_id": "",
            "rewrite_applied": "yes" if rewrite_used else "no",
            "post_audit_action": post_audit["action"] if post_audit else "",
            "post_audit_recommended_level": post_audit["recommended_level"] if post_audit else "",
            "post_audit_primary_issue": post_audit["primary_issue"] if post_audit else "",
            "primary_issue": audit["primary_issue"],
            "reason": audit["reason"],
        }

        action_counts[action] += 1
        final_status_counts[final_status] += 1

        should_include = (
            not final_status.startswith("dropped")
            and (final_status != "post_audit_failed" or args.include_post_audit_failed)
        )
        if should_include:
            grouped[(target_level, row["source_file"])].append(sample)
            final_level_counts[target_level] += 1
            manifest_rows.append(manifest)
        else:
            manifest_rows.append(manifest)

    grouped_payloads = finalize_groups(grouped)

    new_id_map = {}
    for payload in grouped_payloads.values():
        for sample in payload["samples"]:
            new_id_map[(payload["level"], payload["source_file"], sample["original_query_id"])] = sample["query_id"]
    for row in manifest_rows:
        if row["final_level"]:
            row["new_query_id"] = new_id_map.get((row["final_level"], row["source_file"], row["original_query_id"]), "")

    summary = {
        "created_at": dt.datetime.now().isoformat(),
        "prompt_version": PROMPT_VERSION,
        "benchmark_root": args.benchmark_root,
        "audit_results": args.audit_results,
        "rewrite_mode": args.rewrite_mode,
        "rewrite_model": args.model if args.rewrite_mode == "llm" else "N/A",
        "post_audit_model": (args.post_audit_model or args.model) if args.rewrite_mode == "llm" else "N/A",
        "input_sample_count": len(benchmark_rows),
        "output_sample_count": sum(len(payload["samples"]) for payload in grouped_payloads.values()),
        "rewrite_applied_count": rewrite_applied,
        "post_audit_pass_count": post_audit_pass_count,
        "post_audit_fail_count": post_audit_fail_count,
        "action_counts": action_counts,
        "final_status_counts": final_status_counts,
        "final_level_counts": final_level_counts,
    }

    write_outputs(args.output_root, grouped_payloads, manifest_rows, summary)
    print(f"Saved cleaned benchmark to: {args.output_root}")
    print(f"Saved manifest to: {os.path.join(args.output_root, 'cleanup_manifest.csv')}")
    print(f"Saved summary to: {os.path.join(args.output_root, 'cleanup_summary.json')}")


if __name__ == "__main__":
    main()
