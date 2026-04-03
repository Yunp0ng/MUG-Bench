#!/usr/bin/env python3
"""Audit existing benchmark samples and recommend keep/rewrite/relabel/drop."""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import glob
import http.client
import itertools
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple


LEVELS = ["L1", "L2", "L3"]
CITE_RE = re.compile(r"\[(\d+)\]")
PROMPT_VERSION = "audit_v2_zh_level_specific"

AUDIT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "benchmark_sample_audit",
        "schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["keep", "downgrade", "upgrade", "rewrite", "drop"],
                },
                "recommended_level": {
                    "type": "string",
                    "enum": ["L1", "L2", "L3", "NA"],
                },
                "layer_fit_0_5": {"type": "number"},
                "question_leakage_0_5": {"type": "number"},
                "evidence_support_0_5": {"type": "number"},
                "difficulty_0_5": {"type": "number"},
                "primary_issue": {
                    "type": "string",
                    "enum": [
                        "none",
                        "wrong_level",
                        "question_leakage",
                        "weak_evidence",
                        "too_easy",
                        "too_hard",
                        "ambiguous_gold",
                    ],
                },
                "reason": {"type": "string"},
            },
            "required": [
                "action",
                "recommended_level",
                "layer_fit_0_5",
                "question_leakage_0_5",
                "evidence_support_0_5",
                "difficulty_0_5",
                "primary_issue",
                "reason",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

AUDIT_FIELD_GUIDE = """
返回字段说明：

1. action
- keep: 当前样本质量合格，保留在当前层级
- downgrade: 当前样本过难，应该降到更低层级
- upgrade: 当前样本过难或存在动态性，应该升到更高层级
- rewrite: 样本核心信息可用，但问题或答案表述需要重写
- drop: 样本不适合进入benchmark，应删除

2. recommended_level
- 若 action 是 keep，则填当前层级
- 若 action 是 downgrade / upgrade，则填建议的新层级
- 若 action 是 rewrite，可填当前更合适的层级
- 若 action 是 drop，则填 NA

3. layer_fit_0_5
- 评估样本是否符合当前层级定义
- 5: 完全符合当前层级
- 4: 基本符合，只有轻微边界问题
- 3: 有明显边界问题，但还能勉强归入当前层级
- 2: 更像别的层级
- 1: 几乎不符合当前层级
- 0: 完全分错层级

4. question_leakage_0_5
- 评估问题是否泄露答案方向、最终态或关键推理路径
- 5: 完全不泄露，问题自然
- 4: 轻微提示，但不影响判断
- 3: 有一定提示性
- 2: 明显泄露答案方向
- 1: 几乎直接提示答案
- 0: 基本等于把答案问出来

5. evidence_support_0_5
- 评估给定证据是否足以支撑金标答案
- 5: 证据充分且直接支撑答案
- 4: 基本充分，有少量隐含推断
- 3: 证据只能部分支撑
- 2: 证据较弱，答案依赖额外推断
- 1: 证据几乎不支撑答案
- 0: 证据与答案不匹配

6. difficulty_0_5
- 评估样本本身难度是否与该层级预期一致
- 5: 难度与该层级非常匹配
- 4: 基本匹配
- 3: 难度偏高或偏低
- 2: 明显不匹配
- 1: 严重不匹配
- 0: 完全不应放在该层级

7. primary_issue
- none: 无明显问题
- wrong_level: 层级不对
- question_leakage: 问题泄露太强
- weak_evidence: 证据不足
- too_easy: 太简单
- too_hard: 太难或依赖额外推理
- ambiguous_gold: 金标答案本身含混或不够稳定

8. reason
- 用中文简洁解释最主要的判断依据
- 1到3句话，指出为什么保留、重写、升降级或删除
"""

LEVEL_AUDIT_GUIDE = {
    "L1": (
        "当前只审核 L1 样本。\n"
        "L1 定义：答案应由 1-2 句显性证据直接决定，重点考察局部事实定位。\n"
        "判定要点：\n"
        "1. 若需要跨段聚合、背景补全或前后冲突消解，这条样本就不应算 L1。\n"
        "2. 问题应聚焦单个明确事实槽位或同一局部片段中的直接事实。\n"
        "3. 若证据存在指代不清、ASR 误写、答案超出证据边界，优先考虑 rewrite。\n"
        "4. 不要按 L2/L3 的标准额外加分或扣分。"
    ),
    "L2": (
        "当前只审核 L2 样本。\n"
        "L2 定义：答案需要跨段聚合，信息分布在会议多个位置，但不应依赖反转或最终态变化。\n"
        "判定要点：\n"
        "1. 若单段就能直接答出，不应算 L2。\n"
        "2. 若必须跟踪前后反转、噪音过滤或隐性拒绝，应该升到 L3。\n"
        "3. 问题应要求对多个片段做互补整合，而不是只复述某一段。\n"
        "4. 若 gold_answer 超出多个证据共同支持的范围，优先考虑 rewrite。"
    ),
    "L3": (
        "当前只审核 L3 样本。\n"
        "L3 定义：只有跟踪最终态、过滤噪音或识别隐性拒绝，才能稳定答对。\n"
        "判定要点：\n"
        "1. 若最终结论在单句中直接明牌，且不需要动态追踪，则不应算 L3。\n"
        "2. 若只是跨段聚合、没有动态变化，应该降到 L2。\n"
        "3. 问题不应泄露“被否决/改为/最终决定”等答案方向。\n"
        "4. gold_answer 必须回答最终业务结论，而不是过程性讨论。"
    ),
}


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_json_response(content: str) -> str:
    if not content:
        return content
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(json)?", "", content, flags=re.IGNORECASE).strip()
        content = re.sub(r"```$", "", content).strip()
    return content


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def resolve_source_path(source_root: str, source_file: str) -> Optional[str]:
    if not source_file:
        return None
    names = [source_file]
    if not source_file.endswith(".json"):
        names.append(source_file + ".json")
    for name in names:
        p = os.path.join(source_root, name)
        if os.path.exists(p):
            return p
    for fp in glob.glob(os.path.join(source_root, "*.json")):
        if os.path.basename(fp) in names:
            return fp
    return None


def load_transcript_id_map(source_root: str, source_file: str) -> Dict[int, str]:
    path = resolve_source_path(source_root, source_file)
    if not path:
        return {}
    data = load_json(path)
    speaker_map = {str(s.get("speaker_id")): s.get("name", "Unknown") for s in data.get("speakers", [])}
    out: Dict[int, str] = {}
    for utt in data.get("utterances", []):
        try:
            uid = int(utt.get("id"))
        except Exception:
            continue
        spk = speaker_map.get(str(utt.get("speaker_id")), "Unknown")
        txt = str(utt.get("text", "")).strip()
        out[uid] = f"[{uid}] {spk}: {txt}"
    return out


def build_evidence_block(id_map: Dict[int, str], ids: List[int], max_items: int = 16) -> str:
    if not ids:
        return "(none)"
    rows = []
    seen = set()
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        rows.append(id_map.get(i, f"[{i}] <missing>"))
        if len(rows) >= max_items:
            break
    return "\n".join(rows)


def audit_key(level: str, query_id: str) -> str:
    return f"{level}|{query_id}"


def load_cache(path: str) -> Dict[str, dict]:
    out = {}
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
            out[row["key"]] = row["audit"]
    return out


def append_cache(path: str, key: str, audit: dict) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    row = {
        "key": key,
        "prompt_version": PROMPT_VERSION,
        "timestamp": dt.datetime.now().isoformat(),
        "audit": audit,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_api_keys(args: argparse.Namespace) -> List[str]:
    keys: List[str] = []
    if args.api_keys:
        keys.extend([x.strip() for x in args.api_keys.split(",") if x.strip()])
    env_keys = os.getenv(args.api_keys_env, "")
    if env_keys:
        keys.extend([x.strip() for x in env_keys.split(",") if x.strip()])
    single = os.getenv("ACMMM_JUDGE_API_KEY", "")
    if single:
        keys.append(single.strip())
    uniq = []
    seen = set()
    for k in keys:
        if not k or k in seen:
            continue
        uniq.append(k)
        seen.add(k)
    return uniq


def call_audit_llm(
    api_keys: List[str],
    api_host: str,
    api_path: str,
    model: str,
    level: str,
    query_id: str,
    source_file: str,
    question: str,
    gold_answer: str,
    pattern: str,
    evidence_text: str,
    max_retries: int,
    key_cycle,
    key_lock: threading.Lock,
) -> dict:
    system_prompt = (
        "你是中文会议 benchmark 审核员。"
        "你的任务不是回答问题，而是只根据当前层级定义审核这条样本，并给出清洗建议。"
    )
    user_prompt = (
        f"当前层级: {level}\n"
        f"query_id: {query_id}\n"
        f"source_file: {source_file}\n"
        f"pattern: {pattern}\n\n"
        f"问题: {question}\n\n"
        f"金标答案: {gold_answer}\n\n"
        f"证据原文:\n{evidence_text}\n\n"
        "审核目标:\n"
        "1. 判断该样本是否真的符合当前层级定义。\n"
        "2. 判断问题是否泄露答案方向或最终态。\n"
        "3. 判断证据是否足以支撑金标答案。\n"
        "4. 判断样本是否过于简单、过于含混，或者更适合别的层级。\n"
        "5. 给出动作建议：keep / downgrade / upgrade / rewrite / drop。\n"
        "要求:\n"
        "- 只按当前层级标准判断，不要把其他层级的理想特征混进当前评分。\n"
        "- reason 用中文，简洁说清主要问题。\n\n"
        f"{LEVEL_AUDIT_GUIDE[level]}\n\n"
        f"{AUDIT_FIELD_GUIDE}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "response_format": AUDIT_SCHEMA,
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
    raise RuntimeError(f"audit failed: {last_err}")


def audit_single_sample(
    level: str,
    source_file: str,
    sample: dict,
    id_map: Dict[int, str],
    cache: Dict[str, dict],
    cache_path: str,
    api_keys: List[str],
    api_host: str,
    api_path: str,
    model: str,
    max_retries: int,
    key_cycle,
    key_lock: threading.Lock,
    cache_lock: threading.Lock,
) -> dict:
    key = audit_key(level, sample["query_id"])
    with cache_lock:
        cached = cache.get(key)
    if cached is not None:
        audit = cached
    else:
        audit = call_audit_llm(
            api_keys=api_keys,
            api_host=api_host,
            api_path=api_path,
            model=model,
            level=level,
            query_id=sample["query_id"],
            source_file=source_file,
            question=sample.get("question", ""),
            gold_answer=sample.get("gold_answer", ""),
            pattern=sample.get("pattern", "N/A"),
            evidence_text=build_evidence_block(id_map, sample.get("evidence_ids", [])),
            max_retries=max_retries,
            key_cycle=key_cycle,
            key_lock=key_lock,
        )
        with cache_lock:
            cache[key] = audit
            append_cache(cache_path, key, audit)
    return {
        "level": level,
        "source_file": source_file,
        "query_id": sample["query_id"],
        "pattern": sample.get("pattern", "N/A"),
        "question": sample.get("question", ""),
        "gold_answer": sample.get("gold_answer", ""),
        **audit,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit benchmark samples")
    parser.add_argument("--benchmark-root", default="out/Benchmark_QA")
    parser.add_argument("--source-root", default="data/Real_meeting")
    parser.add_argument("--output-dir", default="out/benchmark_audit")
    parser.add_argument("--cache-path", default="out/benchmark_audit/audit_cache.jsonl")
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--api-keys", default="")
    parser.add_argument("--api-keys-env", default="ACMMM_AUDIT_API_KEYS")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args()

    api_keys = parse_api_keys(args)
    api_host = os.getenv("ACMMM_JUDGE_API_HOST", "yunwu.ai")
    api_path = os.getenv("ACMMM_JUDGE_API_PATH", "/v1/chat/completions")
    if not api_keys:
        raise RuntimeError("At least one API key is required via --api-keys, ACMMM_AUDIT_API_KEYS, or ACMMM_JUDGE_API_KEY")

    ensure_dir(args.output_dir)
    cache = load_cache(args.cache_path)
    transcript_cache: Dict[str, Dict[int, str]] = {}
    rows = []
    tasks: List[Tuple[str, str, dict, Dict[int, str]]] = []
    key_cycle = itertools.cycle(api_keys)
    key_lock = threading.Lock()
    cache_lock = threading.Lock()

    for level in LEVELS:
        for fp in sorted(glob.glob(os.path.join(args.benchmark_root, level, "*.json"))):
            data = load_json(fp)
            source_file = data.get("source_file", os.path.basename(fp))
            if source_file not in transcript_cache:
                transcript_cache[source_file] = load_transcript_id_map(args.source_root, source_file)
            id_map = transcript_cache[source_file]
            for sample in data.get("samples", []):
                tasks.append((level, source_file, sample, id_map))
                if args.max_samples > 0 and len(tasks) >= args.max_samples:
                    break
            if args.max_samples > 0 and len(tasks) >= args.max_samples:
                break
        if args.max_samples > 0 and len(tasks) >= args.max_samples:
            break

    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
        future_map = {
            executor.submit(
                audit_single_sample,
                level,
                source_file,
                sample,
                id_map,
                cache,
                args.cache_path,
                api_keys,
                api_host,
                api_path,
                args.model,
                args.max_retries,
                key_cycle,
                key_lock,
                cache_lock,
            ): (level, sample["query_id"])
            for level, source_file, sample, id_map in tasks
        }
        for future in as_completed(future_map):
            rows.append(future.result())

    rows.sort(key=lambda r: (LEVELS.index(r["level"]), r["source_file"], r["query_id"]))

    json_path = os.path.join(args.output_dir, "audit_results.json")
    csv_path = os.path.join(args.output_dir, "audit_results.csv")
    summary_path = os.path.join(args.output_dir, "audit_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "level",
            "source_file",
            "query_id",
            "pattern",
            "question",
            "gold_answer",
            "action",
            "recommended_level",
            "layer_fit_0_5",
            "question_leakage_0_5",
            "evidence_support_0_5",
            "difficulty_0_5",
            "primary_issue",
            "reason",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "created_at": dt.datetime.now().isoformat(),
        "prompt_version": PROMPT_VERSION,
        "model": args.model,
        "num_api_keys": len(api_keys),
        "max_workers": args.max_workers,
        "sample_count": len(rows),
        "action_counts": collections.Counter(r["action"] for r in rows),
        "issue_counts": collections.Counter(r["primary_issue"] for r in rows),
        "level_action_counts": {
            level: collections.Counter(r["action"] for r in rows if r["level"] == level)
            for level in LEVELS
        },
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Saved: {json_path}")
    print(f"Saved: {csv_path}")
    print(f"Saved: {summary_path}")


if __name__ == "__main__":
    main()
