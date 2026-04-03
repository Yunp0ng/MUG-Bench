#!/usr/bin/env python3
"""ACMMM-style evaluation pipeline v2 for the multi-level meeting benchmark.

Implements a subtype-aware scoring framework across L1/L2/L3:
- Answer Quality (A): 0.30
- Evidence Grounding (E): 0.40
- Level Skill (L): 0.30
- Penalty: subtractive, stronger for critical failures
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import glob
import hashlib
import http.client
import itertools
import json
import math
import os
import random
import re
import statistics
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

LEVELS = ["L1", "L2", "L3"]
CITE_RE = re.compile(r"\[(\d+)\]")
RUBRIC = {
    "scale_anchor": {
        "5": "完全满足该维度要求，无关键缺陷。",
        "4": "基本满足要求，仅有轻微遗漏或不精确。",
        "3": "部分满足要求，存在明显遗漏或轻度偏差。",
        "2": "仅少量满足要求，整体明显不足。",
        "1": "几乎不满足要求，仅有碎片性正确成分。",
        "0": "完全不满足要求，或与要求明显冲突。",
    },
    "A_answer_core_correctness_0_5": {
        "definition": "是否答对了问题要求的核心业务结论/核心事实。",
        "focus": ["核心结论方向", "关键事实", "不能与 gold 冲突"],
    },
    "A_answer_completeness_0_5": {
        "definition": "答案是否覆盖关键条件、约束、组成部分和必要细节。",
        "focus": ["完整性", "约束覆盖", "关键组成部分是否遗漏"],
    },
    "E_support_sufficiency_0_5": {
        "definition": "证据文本是否足以支撑模型答案。",
        "focus": ["支撑链是否充分", "是否能推出结论", "避免无依据陈述"],
    },
    "E_support_specificity_0_5": {
        "definition": "证据是否精准命中问题所需信息，而不是泛泛相关。",
        "focus": ["证据精准性", "关键证据命中", "避免无关冗余引用"],
    },
    "L1": {
        "l1_slot_accuracy_0_5": "关键事实槽位是否正确，如人/时间/对象/数字。",
        "l1_localization_0_5": "是否定位到正确局部证据。",
    },
    "L2": {
        "l2_multi_hop_coverage_0_5": "是否覆盖跨轮次/跨段的关键证据点。",
        "l2_synthesis_consistency_0_5": "整合后的答案是否自洽，没有漏关键子结论。",
    },
    "L3": {
        "l3_final_state_tracking_0_5": "是否正确跟踪最终态，而不是停留在过程态。",
        "l3_noise_filtering_0_5": "是否成功过滤过程噪音并保留最终业务信号。",
        "l3_implicit_semantics_0_5": "是否识别隐性拒绝/延期/收缩等语义。",
        "subtype_scoring": "L3 按 pattern 做主维度 0.6 + 两个辅维度各 0.2 的加权。",
    },
    "PenaltyFlags": {
        "contradiction": "回答与 gold 最终结论冲突。",
        "hallucination": "编造了关键事实。",
        "l3_decision_flip_error": "在决策反转场景中答错最终方向。",
        "l3_noise_contamination": "把过程噪音当成最终结论。",
        "l3_implicit_rejection_miss": "漏掉隐性拒绝/延期语义。",
    },
}
JUDGE_PROMPT_VERSION = "v6_zh_schema_answer_split_subtype_aware"


def judge_schema_for_level(level: str) -> Dict[str, object]:
    common_props = {
        "answer_core_correctness_0_5": {"type": "number"},
        "answer_completeness_0_5": {"type": "number"},
        "support_sufficiency_0_5": {"type": "number"},
        "support_specificity_0_5": {"type": "number"},
        "contradiction": {"type": "boolean"},
        "hallucination": {"type": "boolean"},
        "rationale": {"type": "string"},
    }
    if level == "L1":
        props = {
            **common_props,
            "l1_slot_accuracy_0_5": {"type": "number"},
            "l1_localization_0_5": {"type": "number"},
        }
        required = [
            "answer_core_correctness_0_5",
            "answer_completeness_0_5",
            "support_sufficiency_0_5",
            "support_specificity_0_5",
            "l1_slot_accuracy_0_5",
            "l1_localization_0_5",
            "contradiction",
            "hallucination",
            "rationale",
        ]
    elif level == "L2":
        props = {
            **common_props,
            "l2_multi_hop_coverage_0_5": {"type": "number"},
            "l2_synthesis_consistency_0_5": {"type": "number"},
        }
        required = [
            "answer_core_correctness_0_5",
            "answer_completeness_0_5",
            "support_sufficiency_0_5",
            "support_specificity_0_5",
            "l2_multi_hop_coverage_0_5",
            "l2_synthesis_consistency_0_5",
            "contradiction",
            "hallucination",
            "rationale",
        ]
    else:
        props = {
            **common_props,
            "l3_final_state_tracking_0_5": {"type": "number"},
            "l3_noise_filtering_0_5": {"type": "number"},
            "l3_implicit_semantics_0_5": {"type": "number"},
            "l3_decision_flip_error": {"type": "boolean"},
            "l3_noise_contamination": {"type": "boolean"},
            "l3_implicit_rejection_miss": {"type": "boolean"},
        }
        required = [
            "answer_core_correctness_0_5",
            "answer_completeness_0_5",
            "support_sufficiency_0_5",
            "support_specificity_0_5",
            "l3_final_state_tracking_0_5",
            "l3_noise_filtering_0_5",
            "l3_implicit_semantics_0_5",
            "contradiction",
            "hallucination",
            "l3_decision_flip_error",
            "l3_noise_contamination",
            "l3_implicit_rejection_miss",
            "rationale",
        ]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"meeting_benchmark_judge_{level.lower()}",
            "schema": {
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": False,
            },
            "strict": True,
        },
    }


@dataclass
class ScoreParts:
    answer: float
    evidence: float
    level_skill: float
    penalty: float
    total: float


@dataclass
class JudgeResult:
    answer_core_correctness_0_5: float
    answer_completeness_0_5: float
    support_sufficiency_0_5: float
    support_specificity_0_5: float
    l1_slot_accuracy_0_5: float
    l1_localization_0_5: float
    l2_multi_hop_coverage_0_5: float
    l2_synthesis_consistency_0_5: float
    l3_final_state_tracking_0_5: float
    l3_noise_filtering_0_5: float
    l3_implicit_semantics_0_5: float
    contradiction: bool
    hallucination: bool
    l3_decision_flip_error: bool
    l3_noise_contamination: bool
    l3_implicit_rejection_miss: bool
    rationale: str


@dataclass
class JudgeCacheEntry:
    judge: JudgeResult
    prediction_fingerprint: str
    timestamp: Optional[dt.datetime]


@dataclass
class EvalRecord:
    model: str
    level: str
    source_file: str
    query_id: str
    question: str
    gold_answer: str
    model_answer: str
    pattern: str
    gold_evidence_ids: List[int]
    predicted_citations: List[int]
    citation_precision: float
    citation_recall: float
    citation_f1: float
    answer_lexical_f1: float
    old_score: float
    judge: JudgeResult
    score: ScoreParts


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


def judge_key(model: str, level: str, query_id: str) -> str:
    return f"{model}|{level}|{query_id}"


def parse_iso_datetime(value: object) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value))
    except Exception:
        return None


def parse_prediction_datetime(value: object) -> Optional[dt.datetime]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return dt.datetime.strptime(text, fmt)
        except Exception:
            continue
    return parse_iso_datetime(text)


def prediction_fingerprint(
    *,
    level: str,
    query_id: str,
    question: str,
    gold_answer: str,
    model_answer: str,
    predicted_citations: List[int],
) -> str:
    payload = {
        "level": level,
        "query_id": query_id,
        "question": question,
        "gold_answer": gold_answer,
        "model_answer": model_answer,
        "predicted_citations": [int(x) for x in predicted_citations],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def judge_to_dict(j: JudgeResult) -> Dict[str, object]:
    return dataclasses.asdict(j)


def judge_from_dict(d: Dict[str, object]) -> JudgeResult:
    return JudgeResult(
        answer_core_correctness_0_5=float(d.get("answer_core_correctness_0_5", 0.0)),
        answer_completeness_0_5=float(d.get("answer_completeness_0_5", 0.0)),
        support_sufficiency_0_5=float(d.get("support_sufficiency_0_5", 0.0)),
        support_specificity_0_5=float(d.get("support_specificity_0_5", 0.0)),
        l1_slot_accuracy_0_5=float(d.get("l1_slot_accuracy_0_5", 0.0)),
        l1_localization_0_5=float(d.get("l1_localization_0_5", 0.0)),
        l2_multi_hop_coverage_0_5=float(d.get("l2_multi_hop_coverage_0_5", 0.0)),
        l2_synthesis_consistency_0_5=float(d.get("l2_synthesis_consistency_0_5", 0.0)),
        l3_final_state_tracking_0_5=float(d.get("l3_final_state_tracking_0_5", 0.0)),
        l3_noise_filtering_0_5=float(d.get("l3_noise_filtering_0_5", 0.0)),
        l3_implicit_semantics_0_5=float(d.get("l3_implicit_semantics_0_5", 0.0)),
        contradiction=bool(d.get("contradiction", False)),
        hallucination=bool(d.get("hallucination", False)),
        l3_decision_flip_error=bool(d.get("l3_decision_flip_error", False)),
        l3_noise_contamination=bool(d.get("l3_noise_contamination", False)),
        l3_implicit_rejection_miss=bool(d.get("l3_implicit_rejection_miss", False)),
        rationale=str(d.get("rationale", ""))[:500],
    )


def normalize_judge_for_level(j: JudgeResult, level: str) -> JudgeResult:
    if level == "L1":
        j.l2_multi_hop_coverage_0_5 = 0.0
        j.l2_synthesis_consistency_0_5 = 0.0
        j.l3_final_state_tracking_0_5 = 0.0
        j.l3_noise_filtering_0_5 = 0.0
        j.l3_implicit_semantics_0_5 = 0.0
        j.l3_decision_flip_error = False
        j.l3_noise_contamination = False
        j.l3_implicit_rejection_miss = False
    elif level == "L2":
        j.l1_slot_accuracy_0_5 = 0.0
        j.l1_localization_0_5 = 0.0
        j.l3_final_state_tracking_0_5 = 0.0
        j.l3_noise_filtering_0_5 = 0.0
        j.l3_implicit_semantics_0_5 = 0.0
        j.l3_decision_flip_error = False
        j.l3_noise_contamination = False
        j.l3_implicit_rejection_miss = False
    elif level == "L3":
        j.l1_slot_accuracy_0_5 = 0.0
        j.l1_localization_0_5 = 0.0
        j.l2_multi_hop_coverage_0_5 = 0.0
        j.l2_synthesis_consistency_0_5 = 0.0
    else:
        j.l1_slot_accuracy_0_5 = 0.0
        j.l1_localization_0_5 = 0.0
        j.l2_multi_hop_coverage_0_5 = 0.0
        j.l2_synthesis_consistency_0_5 = 0.0
        j.l3_decision_flip_error = False
        j.l3_noise_contamination = False
        j.l3_implicit_rejection_miss = False
        j.l3_final_state_tracking_0_5 = 0.0
        j.l3_noise_filtering_0_5 = 0.0
        j.l3_implicit_semantics_0_5 = 0.0
    return j


def load_judge_cache(path: str, judge_mode: str, judge_model: str) -> Dict[str, JudgeCacheEntry]:
    out: Dict[str, JudgeCacheEntry] = {}
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
            if row.get("judge_mode") != judge_mode:
                continue
            if row.get("judge_model") != judge_model:
                continue
            if row.get("prompt_version") != JUDGE_PROMPT_VERSION:
                continue
            k = row.get("key")
            if not k:
                continue
            out[k] = JudgeCacheEntry(
                judge=judge_from_dict(row.get("judge", {})),
                prediction_fingerprint=str(row.get("prediction_fingerprint", "") or ""),
                timestamp=parse_iso_datetime(row.get("timestamp")),
            )
    return out


def append_judge_cache(
    path: str,
    key: str,
    judge_mode: str,
    judge_model: str,
    judge: JudgeResult,
    prediction_fingerprint_value: str,
) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    row = {
        "key": key,
        "judge_mode": judge_mode,
        "judge_model": judge_model,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "judge": judge_to_dict(judge),
        "prediction_fingerprint": prediction_fingerprint_value,
        "timestamp": dt.datetime.now().isoformat(),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def log_llm_error(path: str, key: str, err: str) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    row = {"timestamp": dt.datetime.now().isoformat(), "key": key, "error": err}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")




def parse_api_keys(api_keys_str: str) -> List[str]:
    return [x.strip() for x in api_keys_str.split(",") if x.strip()]

def parse_source_roots(source_roots: str) -> List[str]:
    return [x.strip() for x in source_roots.split(",") if x.strip()]


def resolve_source_path(source_root: str, source_file: str) -> Optional[str]:
    if not source_file:
        return None
    roots = parse_source_roots(source_root)
    candidates = [source_file]
    if not source_file.endswith(".json"):
        candidates.append(source_file + ".json")
    for root in roots:
        for name in candidates:
            p = os.path.join(root, name)
            if os.path.exists(p):
                return p
        for fp in glob.glob(os.path.join(root, "*.json")):
            if os.path.basename(fp) in candidates:
                return fp
    return None


def load_transcript_id_map(source_root: str, source_file: str) -> Dict[int, str]:
    path = resolve_source_path(source_root, source_file)
    if not path:
        return {}
    try:
        data = load_json(path)
    except Exception:
        return {}
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


def build_evidence_block(id_map: Dict[int, str], ids: List[int], max_items: int = 20) -> str:
    if not ids:
        return "(none)"
    unique_ids = []
    seen = set()
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        unique_ids.append(i)
    rows = []
    for i in unique_ids[:max_items]:
        rows.append(id_map.get(i, f"[{i}] <missing in source transcript>"))
    if len(unique_ids) > max_items:
        rows.append(f"... truncated {len(unique_ids) - max_items} more lines ...")
    return "\n".join(rows)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def norm_text(s: str) -> str:
    s = (s or "").lower()
    s = CITE_RE.sub(" ", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    return " ".join(s.split())


def char_f1(pred: str, gold: str) -> float:
    p = list(norm_text(pred))
    g = list(norm_text(gold))
    if not p or not g:
        return 0.0
    cp: Dict[str, int] = defaultdict(int)
    cg: Dict[str, int] = defaultdict(int)
    for ch in p:
        cp[ch] += 1
    for ch in g:
        cg[ch] += 1
    common = 0
    for k, v in cp.items():
        if k in cg:
            common += min(v, cg[k])
    if common == 0:
        return 0.0
    precision = common / len(p)
    recall = common / len(g)
    return 2 * precision * recall / (precision + recall)


def parse_citations(answer: str) -> List[int]:
    ids = [int(x) for x in CITE_RE.findall(answer or "")]
    out = []
    seen = set()
    for cid in ids:
        if cid not in seen:
            out.append(cid)
            seen.add(cid)
    return out


def is_invalid_model_answer(answer: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return True
    invalid_prefixes = [
        "ERROR:",
        "ERROR",
        "Error:",
        "Failed to get response.",
    ]
    if any(text.startswith(prefix) for prefix in invalid_prefixes):
        return True
    invalid_substrings = [
        "Failed after retries",
        "Failed to get response",
    ]
    return any(token in text for token in invalid_substrings)


def citation_metrics(predicted: List[int], gold: List[int]) -> Tuple[float, float, float]:
    if not predicted and not gold:
        return 1.0, 1.0, 1.0
    if not predicted:
        return 0.0, 0.0, 0.0
    if not gold:
        return 0.0, 0.0, 0.0
    pset = set(predicted)
    gset = set(gold)
    inter = len(pset & gset)
    precision = inter / len(pset)
    recall = inter / len(gset)
    f1 = 0.0 if precision + recall == 0 else (2 * precision * recall / (precision + recall))
    return precision, recall, f1


def citation_precision_score(p: float, citation_count: int) -> float:
    # 0~5 points: precision-dominant, with mild penalty for citation flooding.
    flooding_penalty = 0.0
    if citation_count > 12:
        flooding_penalty = min(1.0, (citation_count - 12) / 24.0)
    return max(0.0, 5.0 * p * (1.0 - 0.4 * flooding_penalty))


def simple_bool_any(text: str, kws: List[str]) -> bool:
    t = (text or "").lower()
    return any(kw in t for kw in kws)


def fallback_judge(level: str, pattern: str, question: str, gold_answer: str, model_answer: str) -> JudgeResult:
    # Deterministic fallback when no LLM judge is configured.
    f1 = char_f1(model_answer, gold_answer)
    core = min(5.0, max(0.0, 5.0 * (f1 ** 0.65)))
    comp = min(5.0, max(0.0, 5.0 * (f1 ** 0.9)))
    suff = min(5.0, max(0.0, 5.0 * (f1 ** 0.75)))
    spec = min(5.0, max(0.0, 5.0 * (f1 ** 0.85)))

    has_num_gold = bool(re.search(r"\d", gold_answer or ""))
    has_num_model = bool(re.search(r"\d", model_answer or ""))

    l1_slot = 3.0 + (1.0 if (not has_num_gold or has_num_model) else -1.0)
    l1_localize = 2.5 + 2.0 * min(1.0, f1)

    l2_cov = 2.0 + 3.0 * min(1.0, f1)
    l2_cons = 2.0 + 3.0 * min(1.0, f1)

    l3_final = 2.0 + 3.0 * min(1.0, f1)
    l3_noise = 3.5 if len(norm_text(model_answer)) <= 1.9 * max(1, len(norm_text(gold_answer))) else 2.5
    l3_impl = 2.0 + 3.0 * min(1.0, f1)

    contradiction = False
    hallucination = False
    flip_error = False
    noise_contam = False
    impl_miss = False

    # lightweight risk heuristics
    if level == "L3":
        p = (pattern or "").lower()
        if "决策反转" in p and simple_bool_any(model_answer, ["不确定", "无法判断", "没有结论"]):
            flip_error = True
        if len(norm_text(model_answer)) > 2.5 * max(1, len(norm_text(gold_answer))):
            noise_contam = True
        if "隐性拒绝" in p and simple_bool_any(model_answer, ["同意", "批准", "可以直接做"]):
            impl_miss = True

    if f1 < 0.12:
        hallucination = True
    if f1 < 0.08:
        contradiction = True

    return JudgeResult(
        answer_core_correctness_0_5=core,
        answer_completeness_0_5=comp,
        support_sufficiency_0_5=suff,
        support_specificity_0_5=spec,
        l1_slot_accuracy_0_5=max(0.0, min(5.0, l1_slot)),
        l1_localization_0_5=max(0.0, min(5.0, l1_localize)),
        l2_multi_hop_coverage_0_5=max(0.0, min(5.0, l2_cov)),
        l2_synthesis_consistency_0_5=max(0.0, min(5.0, l2_cons)),
        l3_final_state_tracking_0_5=max(0.0, min(5.0, l3_final)),
        l3_noise_filtering_0_5=max(0.0, min(5.0, l3_noise)),
        l3_implicit_semantics_0_5=max(0.0, min(5.0, l3_impl)),
        contradiction=contradiction,
        hallucination=hallucination,
        l3_decision_flip_error=flip_error,
        l3_noise_contamination=noise_contam,
        l3_implicit_rejection_miss=impl_miss,
        rationale="heuristic fallback judge",
    )


def llm_judge(
    api_host: str,
    api_path: str,
    api_key: str,
    judge_model: str,
    level: str,
    pattern: str,
    question: str,
    gold_answer: str,
    model_answer: str,
    gold_evidence_text: str,
    predicted_evidence_text: str,
    max_retries: int = 3,
    key_cycle=None,
    key_lock=None,
) -> JudgeResult:
    system_prompt = (
        "你是严格的会议问答评测裁判。"
        "请基于答案质量、证据支撑和层级特定能力进行评分，避免风格偏好，保持标尺稳定。"
    )
    if level == "L1":
        level_note = "当前是 L1，只评 L1 子项。不要返回 L2/L3 子项和 L3 错误标记。"
    elif level == "L2":
        level_note = "当前是 L2，只评 L2 子项。不要返回 L1/L3 子项和 L3 错误标记。"
    else:
        level_note = "当前是 L3，评 L3 子项，并返回 L3 错误标记。"

    user_prompt = (
        f"层级(Level): {level}\n"
        f"模式(Pattern): {pattern}\n"
        f"问题(Question): {question}\n"
        f"金标答案(Gold answer): {gold_answer}\n"
        f"模型答案(Model answer): {model_answer}\n\n"
        "金标证据原文（由 benchmark evidence IDs 映射）:\n"
        f"{gold_evidence_text}\n\n"
        "模型引用证据原文（由模型答案中的 IDs 映射）:\n"
        f"{predicted_evidence_text}\n\n"
        f"Rubric: {json.dumps(RUBRIC, ensure_ascii=False)}\n"
        "评分说明:\n"
        "- 核心结论正确性与答案完整性分别评分，不要混为一个维度。\n"
        "- 以语义正确性为主，不按字面重合打分。\n"
        "- support_sufficiency 看“证据是否足以支撑结论”，不是严格 ID 一致。\n"
        "- support_specificity 看“证据是否精准命中问题所需信息”，而不是泛泛相关。\n"
        "- 若模型没给证据或证据不相关，应降低 E_sufficiency。\n"
        "- 若模型结论正确但引用了可替代证据，允许给高分。\n"
        "- 严格使用 5/4/3/2/1/0 锚点，避免主观漂移。\n"
        "- 对 L3：三个子项都要评分，但样本通常存在主导 pattern；主导 pattern 对应能力应成为评分重点。\n"
        "- 如果最终决策方向答反，必须重罚。\n"
        f"- {level_note}\n"
        "- rationale 必须用中文，简明说明 1-2 个主要扣分点。"
    )

    payload = {
        "model": judge_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "response_format": judge_schema_for_level(level),
    }

    parsed: Optional[Dict[str, object]] = None
    last_err = ""
    for attempt in range(max_retries):
        try:
            current_api_key = api_key
            if key_cycle is not None and key_lock is not None:
                with key_lock:
                    current_api_key = next(key_cycle)
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {current_api_key}",
                "Content-Type": "application/json; charset=utf-8",
            }
            conn = http.client.HTTPSConnection(api_host, timeout=120)
            conn.request("POST", api_path, json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers)
            res = conn.getresponse()
            data = res.read().decode("utf-8")
            if res.status != 200:
                last_err = f"status={res.status} body={data[:300]}"
                continue

            cleaned = clean_json_response(data)
            top = json.loads(cleaned)
            if "choices" in top:
                content = top.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                content = clean_json_response(content)
                parsed = json.loads(content)
            else:
                parsed = top
            if isinstance(parsed, dict):
                break
        except Exception as e:
            last_err = str(e)
            continue
    if not parsed:
        raise RuntimeError(f"LLM judge parse failed after retries: {last_err}")

    def gnum(key: str) -> float:
        return float(parsed.get(key, 0.0))

    def gbool(key: str) -> bool:
        return bool(parsed.get(key, False))

    jr = JudgeResult(
        answer_core_correctness_0_5=max(0.0, min(5.0, gnum("answer_core_correctness_0_5"))),
        answer_completeness_0_5=max(0.0, min(5.0, gnum("answer_completeness_0_5"))),
        support_sufficiency_0_5=max(0.0, min(5.0, gnum("support_sufficiency_0_5"))),
        support_specificity_0_5=max(0.0, min(5.0, gnum("support_specificity_0_5"))),
        l1_slot_accuracy_0_5=max(0.0, min(5.0, gnum("l1_slot_accuracy_0_5"))),
        l1_localization_0_5=max(0.0, min(5.0, gnum("l1_localization_0_5"))),
        l2_multi_hop_coverage_0_5=max(0.0, min(5.0, gnum("l2_multi_hop_coverage_0_5"))),
        l2_synthesis_consistency_0_5=max(0.0, min(5.0, gnum("l2_synthesis_consistency_0_5"))),
        l3_final_state_tracking_0_5=max(0.0, min(5.0, gnum("l3_final_state_tracking_0_5"))),
        l3_noise_filtering_0_5=max(0.0, min(5.0, gnum("l3_noise_filtering_0_5"))),
        l3_implicit_semantics_0_5=max(0.0, min(5.0, gnum("l3_implicit_semantics_0_5"))),
        contradiction=gbool("contradiction"),
        hallucination=gbool("hallucination"),
        l3_decision_flip_error=gbool("l3_decision_flip_error"),
        l3_noise_contamination=gbool("l3_noise_contamination"),
        l3_implicit_rejection_miss=gbool("l3_implicit_rejection_miss"),
        rationale=str(parsed.get("rationale", ""))[:500],
    )
    return normalize_judge_for_level(jr, level)


def compute_score(
    level: str,
    pattern: str,
    judge: JudgeResult,
    citation_precision: float,
    citation_f1: float,
    citation_count: int,
) -> ScoreParts:
    a_core = judge.answer_core_correctness_0_5 / 5.0
    a_comp = judge.answer_completeness_0_5 / 5.0
    a_norm = 0.6 * a_core + 0.4 * a_comp
    answer = 100.0 * 0.30 * a_norm

    e_suff = judge.support_sufficiency_0_5 / 5.0
    e_spec = judge.support_specificity_0_5 / 5.0
    e_norm = 0.45 * e_suff + 0.25 * e_spec + 0.20 * citation_f1 + 0.10 * citation_precision
    evidence = 100.0 * 0.40 * e_norm

    if level == "L1":
        l_norm = 0.5 * (judge.l1_slot_accuracy_0_5 / 5.0) + 0.5 * (judge.l1_localization_0_5 / 5.0)
    elif level == "L2":
        l_norm = 0.5 * (judge.l2_multi_hop_coverage_0_5 / 5.0) + 0.5 * (judge.l2_synthesis_consistency_0_5 / 5.0)
    else:
        l_norm = l3_skill_norm(pattern, judge)
    level_skill = 100.0 * 0.30 * l_norm

    penalty = compute_penalty(level, pattern, judge)

    total = max(0.0, min(100.0, answer + evidence + level_skill - penalty))
    return ScoreParts(
        answer=answer,
        evidence=evidence,
        level_skill=level_skill,
        penalty=penalty,
        total=total,
    )


def l3_skill_norm(pattern: str, judge: JudgeResult) -> float:
    family = pattern_family(pattern)
    final_state = judge.l3_final_state_tracking_0_5 / 5.0
    noise = judge.l3_noise_filtering_0_5 / 5.0
    implicit = judge.l3_implicit_semantics_0_5 / 5.0
    if family == "A":
        main, aux1, aux2 = final_state, noise, implicit
    elif family == "B":
        main, aux1, aux2 = noise, final_state, implicit
    elif family == "C":
        main, aux1, aux2 = implicit, final_state, noise
    else:
        main, aux1, aux2 = final_state, noise, implicit
    return 0.6 * main + 0.2 * aux1 + 0.2 * aux2


def pattern_family(pattern: str) -> str:
    p = (pattern or "").strip().upper()
    if p.startswith("A") or "决策反转" in p:
        return "A"
    if p.startswith("B") or "噪音过滤" in p:
        return "B"
    if p.startswith("C") or "隐性拒绝" in p:
        return "C"
    return "N/A"


def compute_penalty(level: str, pattern: str, judge: JudgeResult) -> float:
    penalty = 0.0
    if judge.contradiction:
        penalty += 10.0
    if judge.hallucination:
        penalty += 10.0
    if level == "L3":
        family = pattern_family(pattern)
        if family == "A":
            if judge.l3_decision_flip_error:
                penalty += 12.0
            if judge.l3_noise_contamination:
                penalty += 3.0
            if judge.l3_implicit_rejection_miss:
                penalty += 3.0
        elif family == "B":
            if judge.l3_noise_contamination:
                penalty += 12.0
            if judge.l3_decision_flip_error:
                penalty += 3.0
            if judge.l3_implicit_rejection_miss:
                penalty += 3.0
        elif family == "C":
            if judge.l3_implicit_rejection_miss:
                penalty += 12.0
            if judge.l3_decision_flip_error:
                penalty += 3.0
            if judge.l3_noise_contamination:
                penalty += 3.0
        else:
            if judge.l3_decision_flip_error:
                penalty += 8.0
            if judge.l3_noise_contamination:
                penalty += 4.0
            if judge.l3_implicit_rejection_miss:
                penalty += 4.0
    return min(30.0, penalty)


def bootstrap_ci(values: List[float], iters: int = 2000, alpha: float = 0.05, seed: int = 42) -> Tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iters):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * len(means))]
    hi = means[int((1 - alpha / 2) * len(means)) - 1]
    return lo, hi


def permutation_pvalue(a: List[float], b: List[float], iters: int = 5000, seed: int = 42) -> float:
    if not a or not b:
        return 1.0
    rng = random.Random(seed)
    obs = abs((sum(a) / len(a)) - (sum(b) / len(b)))
    merged = a + b
    n_a = len(a)
    count = 0
    for _ in range(iters):
        rng.shuffle(merged)
        aa = merged[:n_a]
        bb = merged[n_a:]
        diff = abs((sum(aa) / len(aa)) - (sum(bb) / len(bb)))
        if diff >= obs:
            count += 1
    return (count + 1) / (iters + 1)


def rankdata(values: List[float]) -> List[float]:
    idx = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and values[idx[j + 1]] == values[idx[i]]:
            j += 1
        rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[idx[k]] = rank
        i = j + 1
    return ranks


def pearson_corr(x: List[float], y: List[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denx = math.sqrt(sum((a - mx) ** 2 for a in x))
    deny = math.sqrt(sum((b - my) ** 2 for b in y))
    if denx == 0 or deny == 0:
        return 0.0
    return num / (denx * deny)


def spearman_corr(x: List[float], y: List[float]) -> float:
    rx = rankdata(x)
    ry = rankdata(y)
    return pearson_corr(rx, ry)


def cohen_kappa_binary(a: List[int], b: List[int]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    n = len(a)
    agree = sum(1 for x, y in zip(a, b) if x == y) / n
    pa1 = sum(a) / n
    pb1 = sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe == 1.0:
        return 0.0
    return (agree - pe) / (1 - pe)


def krippendorff_alpha_interval(rows: List[List[float]]) -> float:
    # rows: item x raters, missing allowed as NaN
    values = []
    for row in rows:
        vals = [v for v in row if v == v]  # filter NaN
        if len(vals) >= 2:
            values.append(vals)
    if not values:
        return 0.0

    all_vals = [v for vals in values for v in vals]
    mean_all = sum(all_vals) / len(all_vals)

    do_num = 0.0
    do_den = 0
    for vals in values:
        m = len(vals)
        if m < 2:
            continue
        for i in range(m):
            for j in range(i + 1, m):
                do_num += (vals[i] - vals[j]) ** 2
                do_den += 1
    if do_den == 0:
        return 0.0
    Do = do_num / do_den

    de_num = 0.0
    de_den = 0
    n = len(all_vals)
    for i in range(n):
        for j in range(i + 1, n):
            de_num += (all_vals[i] - all_vals[j]) ** 2
            de_den += 1
    if de_den == 0:
        return 0.0
    De = de_num / de_den
    if De == 0:
        return 1.0
    return 1.0 - (Do / De)


def discover_models(pred_root: str) -> List[str]:
    models = []
    for name in os.listdir(pred_root):
        path = os.path.join(pred_root, name)
        if not os.path.isdir(path):
            continue
        if all(os.path.isdir(os.path.join(path, lv)) for lv in LEVELS):
            models.append(name)
    return sorted(models)


def load_benchmark(benchmark_root: str) -> Dict[str, Dict[str, dict]]:
    # level -> query_id -> sample
    out: Dict[str, Dict[str, dict]] = {lv: {} for lv in LEVELS}
    for lv in LEVELS:
        for fp in glob.glob(os.path.join(benchmark_root, lv, "*.json")):
            data = load_json(fp)
            for s in data.get("samples", []):
                out[lv][s["query_id"]] = {
                    "level": lv,
                    "source_file": data.get("source_file", os.path.basename(fp)),
                    "question": s.get("question", ""),
                    "gold_answer": s.get("gold_answer", ""),
                    "pattern": s.get("pattern", "N/A"),
                    "gold_evidence_ids": s.get("evidence_ids", []),
                }
    return out


def load_predictions(pred_root: str, models: List[str]) -> Dict[str, Dict[str, Dict[str, dict]]]:
    # model -> level -> query_id -> prediction row
    out: Dict[str, Dict[str, Dict[str, dict]]] = {}
    for model in models:
        out[model] = {lv: {} for lv in LEVELS}
        for lv in LEVELS:
            for fp in glob.glob(os.path.join(pred_root, model, lv, "*.json")):
                data = load_json(fp)
                for r in data.get("results", []):
                    predicted_evidence_ids = r.get("predicted_evidence_ids", [])
                    if not isinstance(predicted_evidence_ids, list):
                        predicted_evidence_ids = []
                    predicted_evidence_ids = [int(x) for x in predicted_evidence_ids if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())]
                    model_answer = r.get("model_answer", "")
                    if not model_answer:
                        final_answer = str(r.get("final_answer", "")).strip()
                        cites = "".join(f"[{i}]" for i in predicted_evidence_ids)
                        model_answer = (final_answer + (" " + cites if cites else "")).strip()
                    out[model][lv][r["query_id"]] = {
                        "source_file": data.get("meta", {}).get("source_file", os.path.basename(fp)),
                        "question": r.get("question", ""),
                        "model_answer": model_answer,
                        "final_answer": r.get("final_answer", ""),
                        "predicted_evidence_ids": predicted_evidence_ids,
                        "pattern": r.get("pattern", "N/A"),
                        "gold_evidence_ids": r.get("gold_evidence_ids", []),
                    }
    return out


def shared_query_ids(benchmark: Dict[str, Dict[str, dict]], predictions: Dict[str, Dict[str, Dict[str, dict]]], models: List[str]) -> Dict[str, List[str]]:
    shared: Dict[str, List[str]] = {}
    for lv in LEVELS:
        ids = set(benchmark[lv].keys())
        for m in models:
            ids &= set(predictions[m][lv].keys())
        shared[lv] = sorted(ids)
    return shared


def old_hard_scheme_score(answer_lexical_f1: float, citation_f1: float) -> float:
    # Baseline scheme for comparison: strict answer lexical overlap + strict citation overlap
    return 100.0 * (0.5 * answer_lexical_f1 + 0.5 * citation_f1)


def run_score(args: argparse.Namespace) -> None:
    ensure_dir(args.output_dir)
    models = discover_models(args.pred_root)
    if not models:
        raise RuntimeError(f"No model folders found under {args.pred_root}")
    if args.models:
        wanted = [x.strip() for x in args.models.split(",") if x.strip()]
        models = [m for m in models if m in wanted]
        if not models:
            raise RuntimeError(f"No requested models found under {args.pred_root}: {wanted}")

    benchmark = load_benchmark(args.benchmark_root)
    predictions = load_predictions(args.pred_root, models)
    shared_ids = shared_query_ids(benchmark, predictions, models)

    judge_mode = args.judge_mode
    api_keys_env = os.getenv("ACMMM_API_KEYS", os.getenv("ACMMM_JUDGE_API_KEY", ""))
    api_keys = parse_api_keys(api_keys_env)
    api_key = api_keys[0] if api_keys else ""
    api_host = os.getenv("ACMMM_JUDGE_API_HOST", "yunwu.ai")
    api_path = os.getenv("ACMMM_JUDGE_API_PATH", "/v1/chat/completions")
    judge_model = os.getenv("ACMMM_JUDGE_MODEL", "gpt-5")
    if judge_mode == "llm" and not api_key:
        raise RuntimeError("judge-mode=llm requires ACMMM_JUDGE_API_KEY env var")

    records: List[EvalRecord] = []
    ignored_extra: Dict[str, Dict[str, List[str]]] = {m: {lv: [] for lv in LEVELS} for m in models}
    transcript_cache: Dict[str, Dict[int, str]] = {}
    judge_cache_path = args.judge_cache_path or os.path.join(args.output_dir, "judge_cache.jsonl")
    judge_cache = load_judge_cache(judge_cache_path, judge_mode, judge_model if judge_mode == "llm" else "heuristic-fallback")
    judge_cache_lock = threading.Lock()
    transcript_lock = threading.Lock()
    llm_key_lock = threading.Lock()
    llm_key_cycle = itertools.cycle(api_keys) if api_keys else None
    excluded_invalid: Dict[str, Dict[str, int]] = {m: {lv: 0 for lv in LEVELS} for m in models}
    excluded_examples: List[Dict[str, str]] = []

    # track extras for transparency
    for m in models:
        for lv in LEVELS:
            bset = set(benchmark[lv].keys())
            pset = set(predictions[m][lv].keys())
            extras = sorted(pset - bset)
            ignored_extra[m][lv] = extras

    eval_items: List[Tuple[str, str, str]] = []
    for lv in LEVELS:
        qids = shared_ids[lv] if args.use_shared_only else sorted(benchmark[lv].keys())
        if args.preview_files_per_level > 0:
            keep_files = sorted({benchmark[lv][qid].get("source_file", "") for qid in qids})[: args.preview_files_per_level]
            qids = [qid for qid in qids if benchmark[lv][qid].get("source_file", "") in keep_files]
        for qid in qids:
            for model in models:
                eval_items.append((model, lv, qid))

    if args.max_samples > 0:
        eval_items = eval_items[: args.max_samples]

    def build_record(model: str, lv: str, qid: str) -> Optional[EvalRecord]:
        b = benchmark[lv].get(qid)
        if not b:
            return None
        pred = predictions[model][lv].get(qid)
        if not pred:
            return None

        gold_eids = [int(x) for x in b.get("gold_evidence_ids", [])]
        model_answer = pred.get("model_answer", "")
        if is_invalid_model_answer(model_answer):
            with judge_cache_lock:
                excluded_invalid[model][lv] += 1
                if len(excluded_examples) < 20:
                    excluded_examples.append(
                        {
                            "model": model,
                            "level": lv,
                            "query_id": qid,
                            "source_file": b.get("source_file", pred.get("source_file", "")),
                            "model_answer": model_answer[:200],
                        }
                    )
            return None

        pred_cites = pred.get("predicted_evidence_ids") or parse_citations(model_answer)
        pred_question = b.get("question", "")
        pred_gold_answer = b.get("gold_answer", "")
        pred_timestamp = parse_prediction_datetime(pred.get("timestamp"))
        pred_fp = prediction_fingerprint(
            level=lv,
            query_id=qid,
            question=pred_question,
            gold_answer=pred_gold_answer,
            model_answer=model_answer,
            predicted_citations=pred_cites,
        )
        c_p, c_r, c_f1 = citation_metrics(pred_cites, gold_eids)
        lex_f1 = char_f1(model_answer, pred_gold_answer)
        old_score = old_hard_scheme_score(lex_f1, c_f1)
        source_file = b.get("source_file", pred.get("source_file", ""))
        with transcript_lock:
            if source_file not in transcript_cache:
                transcript_cache[source_file] = load_transcript_id_map(args.source_meeting_root, source_file)
            id_map = transcript_cache[source_file]
        gold_evidence_text = build_evidence_block(id_map, gold_eids, max_items=args.max_evidence_lines)
        predicted_evidence_text = build_evidence_block(id_map, pred_cites, max_items=args.max_evidence_lines)

        cache_k = judge_key(model, lv, qid)
        with judge_cache_lock:
            cached_entry = judge_cache.get(cache_k)
        cache_is_valid = False
        if cached_entry is not None:
            if cached_entry.prediction_fingerprint:
                cache_is_valid = cached_entry.prediction_fingerprint == pred_fp
            elif pred_timestamp is not None and cached_entry.timestamp is not None:
                cache_is_valid = cached_entry.timestamp >= pred_timestamp
            else:
                cache_is_valid = True
        if cache_is_valid and cached_entry is not None:
            judge = cached_entry.judge
        elif judge_mode == "llm":
            try:
                judge = llm_judge(
                    api_host=api_host,
                    api_path=api_path,
                    api_key=api_key,
                    judge_model=judge_model,
                    level=lv,
                    pattern=b.get("pattern", "N/A"),
                    question=b.get("question", ""),
                    gold_answer=b.get("gold_answer", ""),
                    model_answer=model_answer,
                    gold_evidence_text=gold_evidence_text,
                    predicted_evidence_text=predicted_evidence_text,
                    max_retries=args.llm_retries,
                    key_cycle=llm_key_cycle,
                    key_lock=llm_key_lock,
                )
            except Exception as e:
                with judge_cache_lock:
                    log_llm_error(args.llm_error_log, cache_k, str(e))
                if args.llm_strict:
                    raise
                judge = fallback_judge(
                    level=lv,
                    pattern=b.get("pattern", "N/A"),
                    question=b.get("question", ""),
                    gold_answer=b.get("gold_answer", ""),
                    model_answer=model_answer,
                )
            with judge_cache_lock:
                judge_cache[cache_k] = JudgeCacheEntry(
                    judge=judge,
                    prediction_fingerprint=pred_fp,
                    timestamp=dt.datetime.now(),
                )
                append_judge_cache(
                    judge_cache_path,
                    cache_k,
                    judge_mode,
                    judge_model if judge_mode == "llm" else "heuristic-fallback",
                    judge,
                    pred_fp,
                )
        else:
            judge = fallback_judge(
                level=lv,
                pattern=b.get("pattern", "N/A"),
                question=b.get("question", ""),
                gold_answer=b.get("gold_answer", ""),
                model_answer=model_answer,
            )
            with judge_cache_lock:
                judge_cache[cache_k] = JudgeCacheEntry(
                    judge=judge,
                    prediction_fingerprint=pred_fp,
                    timestamp=dt.datetime.now(),
                )
                append_judge_cache(
                    judge_cache_path,
                    cache_k,
                    judge_mode,
                    judge_model if judge_mode == "llm" else "heuristic-fallback",
                    judge,
                    pred_fp,
                )

        judge = normalize_judge_for_level(judge, lv)
        score = compute_score(
            level=lv,
            pattern=b.get("pattern", "N/A"),
            judge=judge,
            citation_precision=c_p,
            citation_f1=c_f1,
            citation_count=len(pred_cites),
        )

        return EvalRecord(
            model=model,
            level=lv,
            source_file=source_file,
            query_id=qid,
            question=pred_question,
            gold_answer=pred_gold_answer,
            model_answer=model_answer,
            pattern=b.get("pattern", "N/A"),
            gold_evidence_ids=gold_eids,
            predicted_citations=pred_cites,
            citation_precision=c_p,
            citation_recall=c_r,
            citation_f1=c_f1,
            answer_lexical_f1=lex_f1,
            old_score=old_score,
            judge=judge,
            score=score,
        )

    if judge_mode == "llm":
        worker_count = max(1, min(args.judge_max_workers, len(eval_items), max(1, len(api_keys))))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(build_record, model, lv, qid) for model, lv, qid in eval_items]
            for fut in as_completed(futures):
                rec = fut.result()
                if rec is not None:
                    records.append(rec)
    else:
        for model, lv, qid in eval_items:
            rec = build_record(model, lv, qid)
            if rec is not None:
                records.append(rec)

    records.sort(key=lambda r: (r.model, r.level, r.source_file, r.query_id))

    # save per-sample
    per_sample_path = os.path.join(args.output_dir, "per_sample_scores.csv")
    with open(per_sample_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "model",
                "level",
                "source_file",
                "query_id",
                "pattern",
                "score_total",
                "score_answer",
                "score_evidence",
                "score_level_skill",
                "score_penalty",
                "answer_core_correctness_0_5",
                "answer_completeness_0_5",
                "support_sufficiency_0_5",
                "support_specificity_0_5",
                "l1_slot_accuracy_0_5",
                "l1_localization_0_5",
                "l2_multi_hop_coverage_0_5",
                "l2_synthesis_consistency_0_5",
                "l3_final_state_tracking_0_5",
                "l3_noise_filtering_0_5",
                "l3_implicit_semantics_0_5",
                "citation_precision",
                "citation_recall",
                "citation_f1",
                "answer_lexical_f1",
                "old_score",
                "contradiction",
                "hallucination",
                "l3_decision_flip_error",
                "l3_noise_contamination",
                "l3_implicit_rejection_miss",
                "judge_rationale",
            ]
        )
        for r in records:
            w.writerow(
                [
                    r.model,
                    r.level,
                    r.source_file,
                    r.query_id,
                    r.pattern,
                    round(r.score.total, 4),
                    round(r.score.answer, 4),
                    round(r.score.evidence, 4),
                    round(r.score.level_skill, 4),
                    round(r.score.penalty, 4),
                    round(r.judge.answer_core_correctness_0_5, 4),
                    round(r.judge.answer_completeness_0_5, 4),
                    round(r.judge.support_sufficiency_0_5, 4),
                    round(r.judge.support_specificity_0_5, 4),
                    round(r.judge.l1_slot_accuracy_0_5, 4),
                    round(r.judge.l1_localization_0_5, 4),
                    round(r.judge.l2_multi_hop_coverage_0_5, 4),
                    round(r.judge.l2_synthesis_consistency_0_5, 4),
                    round(r.judge.l3_final_state_tracking_0_5, 4),
                    round(r.judge.l3_noise_filtering_0_5, 4),
                    round(r.judge.l3_implicit_semantics_0_5, 4),
                    round(r.citation_precision, 4),
                    round(r.citation_recall, 4),
                    round(r.citation_f1, 4),
                    round(r.answer_lexical_f1, 4),
                    round(r.old_score, 4),
                    int(r.judge.contradiction),
                    int(r.judge.hallucination),
                    int(r.judge.l3_decision_flip_error),
                    int(r.judge.l3_noise_contamination),
                    int(r.judge.l3_implicit_rejection_miss),
                    r.judge.rationale,
                ]
            )

    # aggregate
    by_model_level = defaultdict(list)
    by_level = defaultdict(list)
    for r in records:
        by_model_level[(r.model, r.level)].append(r)
        by_level[r.level].append(r.score.total)

    model_summary = {}
    for m in models:
        lv_rows = [r for r in records if r.model == m]
        model_summary[m] = {
            "overall_mean": sum(r.score.total for r in lv_rows) / max(1, len(lv_rows)),
            "overall_old_mean": sum(r.old_score for r in lv_rows) / max(1, len(lv_rows)),
            "count": len(lv_rows),
            "levels": {},
            "errors": {
                "contradiction_rate": sum(int(r.judge.contradiction) for r in lv_rows) / max(1, len(lv_rows)),
                "hallucination_rate": sum(int(r.judge.hallucination) for r in lv_rows) / max(1, len(lv_rows)),
                "l3_decision_flip_error_rate": (
                    sum(int(r.judge.l3_decision_flip_error) for r in lv_rows if r.level == "L3")
                    / max(1, len([r for r in lv_rows if r.level == "L3"]))
                ),
                "l3_noise_contamination_rate": (
                    sum(int(r.judge.l3_noise_contamination) for r in lv_rows if r.level == "L3")
                    / max(1, len([r for r in lv_rows if r.level == "L3"]))
                ),
                "l3_implicit_rejection_miss_rate": (
                    sum(int(r.judge.l3_implicit_rejection_miss) for r in lv_rows if r.level == "L3")
                    / max(1, len([r for r in lv_rows if r.level == "L3"]))
                ),
            },
        }
        for lv in LEVELS:
            rows = by_model_level[(m, lv)]
            if not rows:
                continue
            vals = [r.score.total for r in rows]
            old_vals = [r.old_score for r in rows]
            lo, hi = bootstrap_ci(vals, iters=args.bootstrap_iters, seed=args.seed)
            model_summary[m]["levels"][lv] = {
                "mean": sum(vals) / len(vals),
                "ci95": [lo, hi],
                "old_mean": sum(old_vals) / len(old_vals),
                "count": len(rows),
                "answer_mean": sum(r.score.answer for r in rows) / len(rows),
                "evidence_mean": sum(r.score.evidence for r in rows) / len(rows),
                "level_skill_mean": sum(r.score.level_skill for r in rows) / len(rows),
                "penalty_mean": sum(r.score.penalty for r in rows) / len(rows),
            }

    level_summary = {}
    for lv in LEVELS:
        vals = by_level[lv]
        lo, hi = bootstrap_ci(vals, iters=args.bootstrap_iters, seed=args.seed)
        level_summary[lv] = {
            "mean": sum(vals) / max(1, len(vals)),
            "ci95": [lo, hi],
            "count": len(vals),
        }

    # significance tests for level gradient
    p_l1_l2 = permutation_pvalue(by_level["L1"], by_level["L2"], iters=args.permutation_iters, seed=args.seed)
    p_l2_l3 = permutation_pvalue(by_level["L2"], by_level["L3"], iters=args.permutation_iters, seed=args.seed)
    p_l1_l3 = permutation_pvalue(by_level["L1"], by_level["L3"], iters=args.permutation_iters, seed=args.seed)

    # ranking stability old vs new
    mnames = list(models)
    new_scores = [model_summary[m]["overall_mean"] for m in mnames]
    old_scores = [model_summary[m]["overall_old_mean"] for m in mnames]
    ranking_spearman = spearman_corr(new_scores, old_scores)

    # top failure examples per model
    top_failures = {}
    for m in models:
        rows = [r for r in records if r.model == m]
        rows = sorted(rows, key=lambda x: x.score.total)
        top_failures[m] = [
            {
                "query_id": r.query_id,
                "level": r.level,
                "score": r.score.total,
                "reason": r.judge.rationale,
            }
            for r in rows[:5]
        ]

    summary = {
        "created_at": dt.datetime.now().isoformat(),
        "config": {
            "benchmark_root": args.benchmark_root,
            "pred_root": args.pred_root,
            "source_meeting_root": args.source_meeting_root,
            "judge_mode": judge_mode,
            "judge_model": judge_model if judge_mode == "llm" else "heuristic-fallback",
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "judge_cache_path": judge_cache_path,
            "use_shared_only": args.use_shared_only,
            "rubric": RUBRIC,
            "weights": {
                "A": 0.30,
                "E": 0.40,
                "L": 0.30,
                "Penalty": "up to 30",
                "A_formula": "0.6*core + 0.4*completeness",
                "E_formula": "0.45*sufficiency + 0.25*specificity + 0.20*citation_f1 + 0.10*citation_precision",
                "L3_formula": "0.6*main_pattern_skill + 0.2*aux1 + 0.2*aux2",
            },
        },
        "coverage": {
            "models": models,
            "shared_counts": {lv: len(shared_ids[lv]) for lv in LEVELS},
            "ignored_extra_by_model": ignored_extra,
            "excluded_invalid_answers_by_model": excluded_invalid,
            "excluded_invalid_answer_examples": excluded_examples,
        },
        "level_summary": level_summary,
        "gradient_tests": {
            "pvalue_l1_vs_l2": p_l1_l2,
            "pvalue_l2_vs_l3": p_l2_l3,
            "pvalue_l1_vs_l3": p_l1_l3,
        },
        "model_summary": model_summary,
        "ranking_stability_old_vs_new_spearman": ranking_spearman,
        "top_failures": top_failures,
    }

    summary_path = os.path.join(args.output_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # case study export for paper writing
    case_study = {"created_at": dt.datetime.now().isoformat(), "cases": []}
    for lv in LEVELS:
        lv_rows = [r for r in records if r.level == lv]
        if not lv_rows:
            continue
        # hardest cases (lowest score)
        for r in sorted(lv_rows, key=lambda x: x.score.total)[: args.case_study_topk]:
            case_study["cases"].append(
                {
                    "bucket": f"{lv}_hard",
                    "model": r.model,
                    "query_id": r.query_id,
                    "score_total": round(r.score.total, 4),
                    "score_answer": round(r.score.answer, 4),
                    "score_evidence": round(r.score.evidence, 4),
                    "score_level_skill": round(r.score.level_skill, 4),
                    "penalty": round(r.score.penalty, 4),
                    "pattern": r.pattern,
                    "question": r.question,
                    "gold_answer": r.gold_answer,
                    "model_answer": r.model_answer[:1500],
                    "judge_rationale": r.judge.rationale,
                }
            )
        # strongest cases (highest score)
        for r in sorted(lv_rows, key=lambda x: x.score.total, reverse=True)[: args.case_study_topk]:
            case_study["cases"].append(
                {
                    "bucket": f"{lv}_strong",
                    "model": r.model,
                    "query_id": r.query_id,
                    "score_total": round(r.score.total, 4),
                    "score_answer": round(r.score.answer, 4),
                    "score_evidence": round(r.score.evidence, 4),
                    "score_level_skill": round(r.score.level_skill, 4),
                    "penalty": round(r.score.penalty, 4),
                    "pattern": r.pattern,
                    "question": r.question,
                    "gold_answer": r.gold_answer,
                    "model_answer": r.model_answer[:1500],
                    "judge_rationale": r.judge.rationale,
                }
            )
    case_study_json = os.path.join(args.output_dir, "case_study.json")
    with open(case_study_json, "w", encoding="utf-8") as f:
        json.dump(case_study, f, ensure_ascii=False, indent=2)

    case_study_md = os.path.join(args.output_dir, "case_study.md")
    with open(case_study_md, "w", encoding="utf-8") as f:
        f.write("# Case Study（自动导出）\n\n")
        for c in case_study["cases"]:
            f.write(f"## {c['bucket']} | {c['model']} | {c['query_id']}\n")
            f.write(f"- score_total: {c['score_total']}\n")
            f.write(f"- A/E/L/P: {c['score_answer']}/{c['score_evidence']}/{c['score_level_skill']}/{c['penalty']}\n")
            f.write(f"- pattern: {c['pattern']}\n")
            f.write(f"- question: {c['question']}\n")
            f.write(f"- gold_answer: {c['gold_answer']}\n")
            f.write(f"- judge_rationale: {c['judge_rationale']}\n")
            f.write(f"- model_answer(截断): {c['model_answer']}\n\n")

    # human template based on per-sample results, empty human columns
    human_template = os.path.join(args.output_dir, "human_review_template.csv")
    with open(human_template, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "model",
                "level",
                "query_id",
                "auto_total",
                "auto_answer",
                "auto_evidence",
                "auto_level_skill",
                "human_total_r1",
                "human_total_r2",
                "human_answer_r1",
                "human_answer_r2",
                "human_evidence_r1",
                "human_evidence_r2",
                "human_level_skill_r1",
                "human_level_skill_r2",
                "human_contradiction_r1",
                "human_contradiction_r2",
                "notes",
            ]
        )
        for r in records:
            w.writerow(
                [
                    r.model,
                    r.level,
                    r.query_id,
                    round(r.score.total, 4),
                    round(r.score.answer, 4),
                    round(r.score.evidence, 4),
                    round(r.score.level_skill, 4),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )

    # consistency check by repeated judging on subset
    if args.consistency_runs > 1:
        subset = [r for i, r in enumerate(records) if i % max(1, args.consistency_stride) == 0]
        var_rows = []
        for r in subset:
            totals = [r.score.total]
            for _ in range(args.consistency_runs - 1):
                if judge_mode == "llm":
                    try:
                        if r.source_file not in transcript_cache:
                            transcript_cache[r.source_file] = load_transcript_id_map(args.source_meeting_root, r.source_file)
                        id_map = transcript_cache[r.source_file]
                        jx = llm_judge(
                            api_host=api_host,
                            api_path=api_path,
                            api_key=api_key,
                            judge_model=judge_model,
                            level=r.level,
                            pattern=r.pattern,
                            question=r.question,
                            gold_answer=r.gold_answer,
                            model_answer=r.model_answer,
                            gold_evidence_text=build_evidence_block(id_map, r.gold_evidence_ids, max_items=args.max_evidence_lines),
                            predicted_evidence_text=build_evidence_block(id_map, r.predicted_citations, max_items=args.max_evidence_lines),
                            max_retries=args.llm_retries,
                        )
                    except Exception:
                        jx = fallback_judge(r.level, r.pattern, r.question, r.gold_answer, r.model_answer)
                else:
                    jx = fallback_judge(r.level, r.pattern, r.question, r.gold_answer, r.model_answer)
                sx = compute_score(r.level, r.pattern, jx, r.citation_precision, r.citation_f1, len(r.predicted_citations))
                totals.append(sx.total)
            var_rows.append({
                "model": r.model,
                "level": r.level,
                "query_id": r.query_id,
                "mean": sum(totals) / len(totals),
                "std": statistics.pstdev(totals) if len(totals) > 1 else 0.0,
                "runs": totals,
            })
        with open(os.path.join(args.output_dir, "consistency_check.json"), "w", encoding="utf-8") as f:
            json.dump(var_rows, f, ensure_ascii=False, indent=2)

    # error injection test (L3)
    if args.run_error_injection:
        l3 = [r for r in records if r.level == "L3"]
        sample = l3[: min(len(l3), args.error_injection_limit)]
        drops = []
        for r in sample:
            injected = [
                ("decision_flip", "最终结论与金标准相反。" + r.model_answer),
                ("noise_contamination", r.model_answer + " 另外会议里改PPT字体是最关键结论。"),
                ("implicit_rejection_miss", "会议没有否决任何提议，最终都同意推进。" + r.model_answer),
            ]
            base = r.score.total
            for etype, ans in injected:
                jx = (
                    fallback_judge(r.level, r.pattern, r.question, r.gold_answer, ans)
                    if judge_mode != "llm"
                    else fallback_judge(r.level, r.pattern, r.question, r.gold_answer, ans)
                )
                sx = compute_score(r.level, r.pattern, jx, r.citation_precision, r.citation_f1, len(r.predicted_citations))
                drops.append(
                    {
                        "model": r.model,
                        "query_id": r.query_id,
                        "error_type": etype,
                        "base_score": base,
                        "injected_score": sx.total,
                        "drop": base - sx.total,
                    }
                )
        with open(os.path.join(args.output_dir, "error_injection.json"), "w", encoding="utf-8") as f:
            json.dump(drops, f, ensure_ascii=False, indent=2)

    print(f"Saved: {summary_path}")
    print(f"Saved: {per_sample_path}")
    print(f"Saved: {human_template}")
    print(f"Saved: {case_study_json}")
    print(f"Saved: {case_study_md}")


def run_sample_human(args: argparse.Namespace) -> None:
    src = args.per_sample_csv
    if not os.path.exists(src):
        raise RuntimeError(f"Missing per-sample csv: {src}")

    rows = []
    with open(src, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)

    rng = random.Random(args.seed)
    n = len(rows)
    k = max(1, int(n * args.ratio))
    sampled = rows[:]
    rng.shuffle(sampled)
    sampled = sampled[:k]

    out = os.path.join(args.output_dir, f"human_review_sample_{k}.csv")
    ensure_dir(args.output_dir)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "model",
                "level",
                "query_id",
                "auto_total",
                "auto_answer",
                "auto_evidence",
                "auto_level_skill",
                "human_total_r1",
                "human_total_r2",
                "human_answer_r1",
                "human_answer_r2",
                "human_evidence_r1",
                "human_evidence_r2",
                "human_level_skill_r1",
                "human_level_skill_r2",
                "human_contradiction_r1",
                "human_contradiction_r2",
                "notes",
            ]
        )
        for x in sampled:
            w.writerow(
                [
                    x.get("model", ""),
                    x.get("level", ""),
                    x.get("query_id", ""),
                    x.get("score_total", ""),
                    x.get("score_answer", ""),
                    x.get("score_evidence", ""),
                    x.get("score_level_skill", ""),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    print(f"Saved: {out}")


def _to_float_or_nan(x: str) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def _to_int_or_zero(x: str) -> int:
    try:
        return int(float(x))
    except Exception:
        return 0


def run_analyze_human(args: argparse.Namespace) -> None:
    if not os.path.exists(args.human_file):
        raise RuntimeError(f"Missing human file: {args.human_file}")

    rows = []
    with open(args.human_file, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    auto = []
    human_mean = []
    total_pairs = []
    contradiction_r1 = []
    contradiction_r2 = []

    alpha_rows = []
    for row in rows:
        a = _to_float_or_nan(row.get("auto_total", ""))
        h1 = _to_float_or_nan(row.get("human_total_r1", ""))
        h2 = _to_float_or_nan(row.get("human_total_r2", ""))
        if a == a and (h1 == h1 or h2 == h2):
            hm = statistics.mean([v for v in [h1, h2] if v == v])
            auto.append(a)
            human_mean.append(hm)
        if h1 == h1 and h2 == h2:
            total_pairs.append((h1, h2))
        alpha_rows.append([h1, h2])

        c1 = row.get("human_contradiction_r1", "")
        c2 = row.get("human_contradiction_r2", "")
        if c1 != "" and c2 != "":
            contradiction_r1.append(_to_int_or_zero(c1))
            contradiction_r2.append(_to_int_or_zero(c2))

    out = {
        "count_rows": len(rows),
        "count_scored": len(auto),
        "auto_human_pearson": pearson_corr(auto, human_mean) if len(auto) >= 2 else 0.0,
        "auto_human_spearman": spearman_corr(auto, human_mean) if len(auto) >= 2 else 0.0,
        "human_total_krippendorff_alpha": krippendorff_alpha_interval(alpha_rows),
        "human_total_pairwise_pearson": (
            pearson_corr([a for a, _ in total_pairs], [b for _, b in total_pairs]) if len(total_pairs) >= 2 else 0.0
        ),
        "human_contradiction_cohen_kappa": (
            cohen_kappa_binary(contradiction_r1, contradiction_r2)
            if len(contradiction_r1) >= 2 and len(contradiction_r1) == len(contradiction_r2)
            else 0.0
        ),
    }

    ensure_dir(args.output_dir)
    path = os.path.join(args.output_dir, "human_analysis.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Saved: {path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ACMMM benchmark evaluator")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("score", help="run automatic scoring")
    ps.add_argument("--benchmark-root", default="out/Benchmark_QA")
    ps.add_argument("--pred-root", default="real_meeting")
    ps.add_argument("--models", default="", help="comma-separated model folder names to evaluate")
    ps.add_argument("--output-dir", default="out/eval_acmmm")
    ps.add_argument("--judge-mode", choices=["heuristic", "llm"], default="heuristic")
    ps.add_argument("--source-meeting-root", default="data/Real_meeting,data/VCSum_prepared/meetings")
    ps.add_argument("--max-evidence-lines", type=int, default=20)
    ps.add_argument("--use-shared-only", action="store_true", default=True)
    ps.add_argument("--judge-cache-path", default="")
    ps.add_argument("--llm-retries", type=int, default=3)
    ps.add_argument("--llm-strict", action="store_true")
    ps.add_argument("--llm-error-log", default="out/eval_acmmm/llm_errors.log")
    ps.add_argument("--judge-max-workers", type=int, default=4)
    ps.add_argument("--preview-files-per-level", type=int, default=0)
    ps.add_argument("--max-samples", type=int, default=0)
    ps.add_argument("--bootstrap-iters", type=int, default=1500)
    ps.add_argument("--permutation-iters", type=int, default=3000)
    ps.add_argument("--consistency-runs", type=int, default=1)
    ps.add_argument("--consistency-stride", type=int, default=25)
    ps.add_argument("--run-error-injection", action="store_true")
    ps.add_argument("--error-injection-limit", type=int, default=120)
    ps.add_argument("--case-study-topk", type=int, default=5)
    ps.add_argument("--seed", type=int, default=42)

    ph = sub.add_parser("sample-human", help="sample human review subset")
    ph.add_argument("--per-sample-csv", default="out/eval_acmmm/per_sample_scores.csv")
    ph.add_argument("--output-dir", default="out/eval_acmmm")
    ph.add_argument("--ratio", type=float, default=0.12)
    ph.add_argument("--seed", type=int, default=42)

    pa = sub.add_parser("analyze-human", help="analyze human annotation agreement/correlation")
    pa.add_argument("--human-file", required=True)
    pa.add_argument("--output-dir", default="out/eval_acmmm")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "score":
        run_score(args)
    elif args.cmd == "sample-human":
        run_sample_human(args)
    elif args.cmd == "analyze-human":
        run_analyze_human(args)


if __name__ == "__main__":
    main()
