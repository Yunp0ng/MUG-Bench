# Prompt Reference

This document summarizes the prompts used in the EMUG-Bench construction and evaluation pipeline.

The executable scripts contain the original prompt text. This file provides a bilingual explanation of each prompt's role, expected input, and output behavior.

## 1. Evidence Mining

### L1 Evidence Mining

- Script: `scripts/data_construction/L1_evidence.py`
- Chinese:
  - 目标：抽取显性局部检索证据。
  - 重点：单句或连续 2-3 句内可直接回答的问题。
  - 输出：`topic`、`ids`、`reasoning`。
- English:
  - Goal: extract explicit local evidence spans for direct retrieval questions.
  - Focus: a single utterance or a short contiguous span of 2-3 utterances.
  - Output: `topic`, `ids`, and `reasoning`.

### L2 Evidence Mining

- Script: `scripts/data_construction/L2_evidence.py`
- Chinese:
  - 目标：抽取跨轮次信息聚合证据。
  - 重点：同一主题在多个位置被补充说明，而不是被反转。
  - 输出：`topic`、离散 `ids`、`reasoning`。
- English:
  - Goal: extract evidence for cross-turn information aggregation.
  - Focus: complementary information distributed across non-adjacent utterances, without decision reversal.
  - Output: `topic`, discrete `ids`, and `reasoning`.

### L3 Evidence Mining

- Script: `scripts/data_construction/L3_evidence.py`
- Chinese:
  - 目标：抽取动态追踪与语用推理证据。
  - 重点：决策反转、过程噪音过滤、隐性拒绝。
  - 输出：`pattern`、`topic`、`ids`、`reasoning`。
- English:
  - Goal: extract evidence for dynamic tracking and pragmatic reasoning.
  - Focus: decision reversal, procedural noise filtering, and implicit rejection.
  - Output: `pattern`, `topic`, `ids`, and `reasoning`.

## 2. QA Generation

### L1/L2 QA Generation

- Script: `scripts/data_construction/qa_gen.py`
- Chinese:
  - 目标：基于固定证据生成自然问题和金标答案。
  - 要求：问题像未读过会议的人提出，不泄露答案方向。
  - 输出：`question`、`answer`。
- English:
  - Goal: generate a natural question-answer pair from fixed evidence.
  - Requirement: the question should sound like it comes from a user who has not read the transcript and should not leak the answer.
  - Output: `question` and `answer`.

### L3 QA Generation

- Script: `scripts/data_construction/qa_gen.py`
- Chinese:
  - 目标：围绕最终业务结论生成问题。
  - 要求：利用推理说明理解动态性，但问题不能直接暴露“被否决/改为/最终决定”等过程。
  - 输出：`question`、`answer`。
- English:
  - Goal: generate questions around the final business conclusion.
  - Requirement: use the reasoning note to understand the dynamic logic, but do not leak the intermediate reversal or rejection pattern in the question wording.
  - Output: `question` and `answer`.

## 3. Audit

- Script: `scripts/data_construction/benchmark_audit.py`
- Chinese:
  - 目标：审核样本是否符合目标层级与证据约束。
  - 审核维度：层级匹配、问题泄露、证据充分性、难度匹配。
  - 输出动作：`keep`、`downgrade`、`upgrade`、`rewrite`、`drop`。
- English:
  - Goal: audit whether a sample fits the target benchmark level and is properly grounded.
  - Dimensions: level fit, answer leakage, evidence sufficiency, and difficulty alignment.
  - Output actions: `keep`, `downgrade`, `upgrade`, `rewrite`, or `drop`.

## 4. Cleanup

- Script: `scripts/data_construction/benchmark_cleanup.py`
- Chinese:
  - 目标：根据 audit 结果重写、重标或删除样本。
  - 重写内容：`question`、`gold_answer`、`reasoning_from_mining`。
  - 约束：证据 `evidence_ids` 保持不变，重写后需要复审。
- English:
  - Goal: apply audit decisions to rewrite, relabel, or remove samples.
  - Rewritten fields: `question`, `gold_answer`, and `reasoning_from_mining`.
  - Constraint: `evidence_ids` stay fixed, and rewritten samples are re-audited.

## 5. Evaluation

- Script: `scripts/evaluation/acmmm_eval.py`
- Chinese:
  - 目标：从答案正确性、证据支撑性、层级能力三方面对模型输出打分。
  - L1/L2/L3 使用不同细分 rubric。
  - L3 额外考虑最终态追踪、噪音过滤、隐性语义识别。
- English:
  - Goal: score model outputs from three perspectives: answer quality, evidence grounding, and level-specific skill.
  - Different rubrics are used for L1, L2, and L3.
  - L3 additionally evaluates final-state tracking, noise filtering, and implicit semantics.

## 6. Note

- The public repository provides prompt explanations, not a frozen benchmark policy document.
- If prompt wording is updated in the future, the script source should be treated as the authoritative version.
