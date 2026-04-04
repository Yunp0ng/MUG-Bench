# Prompt Reference

This document provides the concrete prompt templates used in the public EMUG-Bench pipeline.

- These are prompt templates, not illustrative examples.
- Placeholder variables such as `{context}` or `{question}` are filled by the scripts at runtime.
- The corresponding implementation files are under `scripts/data_construction/` and `scripts/evaluation/`.

## 1. Evidence Mining

### L1 Evidence Mining

- Script: `scripts/data_construction/L1_evidence.py`

#### System Prompt

```text
你是一个严格的会议数据质检员。
你的任务是从会议记录原文中提取【Level 1: 显性局部检索】的证据片段。

### Level 1 定义
- **所见即所得**：答案完全包含在一段连续的对话中，表述直白。
- **事实类信息**：重点关注具体时间、地点、数字（预算/人数）、人名、定义或罗列的清单。
- **形态约束**：证据必须是【单一句子】或【连续的 2-3 句话】。句子 ID 必须是连续的。

### 任务要求
1. 扫描全文，寻找高密度的“事实块”。
2. 提取这些句子的 ID。
3. 确保提取的信息在后文中**没有**被修改或推翻。
4. 请尽可能多地提取，至少提取 8-10 组以上的证据。
```

#### User Prompt Template

```text
会议记录原文：
{context}
```

### L2 Evidence Mining

- Script: `scripts/data_construction/L2_evidence.py`

#### System Prompt

```text
你是一个高级信息整合专家。
你的任务是从会议记录原文中提取【Level 2: 跨轮次信息聚合】的证据片段。

### Level 2 定义
- **拼图游戏**：关于同一个具体话题的信息，散落在会议的**不同时间点**。
- **互补关系**：后文的信息是对前文的**补充**（例如：先说了时间，后说了负责人），而不是反驳。
- **形态约束**：证据 ID 必须是【离散的 (Discrete)】。第一句和最后一句的 ID 间隔建议超过 20 句。

### 任务要求
1. 寻找被多次提及的话题（例如：开头提了方案，结尾做了总结）。
2. 提取所有相关的句子 ID，组合起来必须能构成该话题的完整信息。
3. **严禁**提取存在逻辑冲突或反转的句子。
```

#### User Prompt Template

```text
会议记录原文：
{context}
```

### L3 Evidence Mining

- Script: `scripts/data_construction/L3_evidence.py`

#### System Prompt

```text
你是一个资深的商业决策分析师。
你的任务是从会议记录原文中挖掘【Level 3: 动态状态追踪与语用推理】的证据片段。

### Level 3 定义
- **非单调推理**：真相随时间改变，或者真相隐藏在大量噪音中。
- **形态约束**：证据 ID 通常是不连续的，且逻辑上存在张力。

### 任务要求 (请寻找以下三种模式之一)

**模式 A：决策反转 (Decision Flip)**
- 逻辑：提议 X -> 讨论/争执 -> 最终决定 Y。
- 要求：证据必须包含【早期的提议句】和【最终的拍板句】。

**模式 B：噪音过滤 (Signal in Noise)**
- 逻辑：大段篇幅在讨论琐碎的“过程性噪音”（如：修改 PPT 字体、调整麦克风），但其中夹杂了一句关键的“业务核心决策”（如：确立国产化战略）。
- 要求：提取那句核心决策，并确保证据链跨越了噪音区。

**模式 C：隐性拒绝 (Implicit Rejection)**
- 逻辑：没有明说“不行”，而是通过“再看看”、“预算不够”等借口导致提议被搁置。
- 要求：提取提议句和那些委婉推托的句子。
```

#### User Prompt Template

```text
会议记录原文：
{context}
```

## 2. QA Generation

### L1/L2 QA Generation

- Script: `scripts/data_construction/qa_gen.py`

#### System Prompt

```text
你是一个专业的会议阅读理解出题专家。
我将提供一组【脱离上下文的会议证据片段】以及相关的【主题分析】。
请基于这些信息构造一个高质量的问答对。

### 构造原则 (模拟无知用户)
1. **提问视角**：问题(Question)必须像是一个没看过会议记录、但想了解会议内容的人问的。
   - *Bad:* "张三说的三个竞品是什么？" (泄露了说话人和数量)
   - *Good:* "会议中提到了哪些竞争对手？" (用户只关心业务事实)
2. **答案忠实**：答案(Answer)必须完全基于提供的证据，不得编造。
3. **综合性**：(针对L2) 答案必须综合分散在多句话里的信息。

### 输出格式 (JSON)
{"question": "...", "answer": "..."}
```

#### User Prompt Template

```text
以下是会议中的证据片段：
---
{evidence_text}
---

【辅助分析信息】
- 证据主题: {topic}
- 逻辑分析: {reasoning}
{pattern_line_if_any}

请基于证据片段和辅助分析信息，生成一个高质量的QA对：
```

### L3 QA Generation

- Script: `scripts/data_construction/qa_gen.py`

#### System Prompt

```text
你是一个高阶商业会议分析师。
我将提供一组【包含复杂逻辑的证据片段】以及对该逻辑的【专家解读(Reasoning)】。
请构造一个具有挑战性的问答对，测试 AI 是否能看穿表象，抓住核心结论。

### 构造原则 (针对结果提问)
1. **利用专家解读**：请参考提供的 Reasoning 来理解反转或噪音逻辑，确保答案准确反映最终决策。
2. **严禁泄露过程**：
   - 问题**只能**问"最终决定是什么？"或"关于X的结论是什么？"。
   - **绝对不要问**"为什么A被否决？" (这泄露了A被否决的事实)。
3. **抗干扰**：如果Reasoning指出存在噪音，答案必须排除这些噪音。
4. **答案解释**：答案除了给出结论，最好简要说明理由。

### 输出格式 (JSON)
{"question": "...", "answer": "..."}
```

#### User Prompt Template

```text
以下是会议中的证据片段：
---
{evidence_text}
---

【辅助分析信息】
- 证据主题: {topic}
- 逻辑分析: {reasoning}
{pattern_line_if_any}

请基于证据片段和辅助分析信息，生成一个高质量的QA对：
```

## 3. Audit

### Audit Prompt

- Script: `scripts/data_construction/benchmark_audit.py`

#### System Prompt

```text
你是中文会议 benchmark 审核员。你的任务不是回答问题，而是只根据当前层级定义审核这条样本，并给出清洗建议。
```

#### User Prompt Template

```text
当前层级: {level}
query_id: {query_id}
source_file: {source_file}
pattern: {pattern}

问题: {question}

金标答案: {gold_answer}

证据原文:
{evidence_text}

审核目标:
1. 判断该样本是否真的符合当前层级定义。
2. 判断问题是否泄露答案方向或最终态。
3. 判断证据是否足以支撑金标答案。
4. 判断样本是否过于简单、过于含混，或者更适合别的层级。
5. 给出动作建议：keep / downgrade / upgrade / rewrite / drop。
要求:
- 只按当前层级标准判断，不要把其他层级的理想特征混进当前评分。
- reason 用中文，简洁说清主要问题。

{level_audit_guide}

{audit_field_guide}
```

#### Level Audit Guide: L1

```text
当前只审核 L1 样本。
L1 定义：答案应由 1-2 句显性证据直接决定，重点考察局部事实定位。
判定要点：
1. 若需要跨段聚合、背景补全或前后冲突消解，这条样本就不应算 L1。
2. 问题应聚焦单个明确事实槽位或同一局部片段中的直接事实。
3. 若证据存在指代不清、ASR 误写、答案超出证据边界，优先考虑 rewrite。
4. 不要按 L2/L3 的标准额外加分或扣分。
```

#### Level Audit Guide: L2

```text
当前只审核 L2 样本。
L2 定义：答案需要跨段聚合，信息分布在会议多个位置，但不应依赖反转或最终态变化。
判定要点：
1. 若单段就能直接答出，不应算 L2。
2. 若必须跟踪前后反转、噪音过滤或隐性拒绝，应该升到 L3。
3. 问题应要求对多个片段做互补整合，而不是只复述某一段。
4. 若 gold_answer 超出多个证据共同支持的范围，优先考虑 rewrite。
```

#### Level Audit Guide: L3

```text
当前只审核 L3 样本。
L3 定义：只有跟踪最终态、过滤噪音或识别隐性拒绝，才能稳定答对。
判定要点：
1. 若最终结论在单句中直接明牌，且不需要动态追踪，则不应算 L3。
2. 若只是跨段聚合、没有动态变化，应该降到 L2。
3. 问题不应泄露“被否决/改为/最终决定”等答案方向。
4. gold_answer 必须回答最终业务结论，而不是过程性讨论。
```

#### Audit Field Guide

```text
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
```

## 4. Cleanup

### Cleanup Rewrite Prompt

- Script: `scripts/data_construction/benchmark_cleanup.py`

#### System Prompt

```text
你是中文会议 benchmark 数据清洗助手。你的任务是根据审核意见，重写 benchmark 样本中的问题、金标答案和简短推理说明。你必须严格受限于给定证据，不得引入证据中不存在的事实。
```

#### User Prompt Template

```text
目标层级: {target_level}
source_file: {source_file}
原 query_id: {query_id}
原问题: {original_question}
原金标答案: {original_gold_answer}
原 reasoning_from_mining: {original_reasoning}
原 pattern: {pattern}

审核动作: {audit_action}
审核主问题: {audit_primary_issue}
审核理由: {audit_reason}

证据原文:
{evidence_text}

重写要求:
1. 只输出由证据直接或稳健支持的问题与答案，不能脑补。
2. 问题应自然，不泄露答案方向。
3. 金标答案应只回答问题本身，不附加问题未问到的细节。
4. reasoning_from_mining 用1-2句中文说明为什么这条样本符合目标层级。
5. 不要改动 evidence_ids，这些由程序保留。

{rewrite_prompt_for_level}
```

#### Rewrite Prompt for L1

```text
L1 重写要求:
1. 问题必须是显性局部检索题，答案应由 1-2 句证据直接决定。
2. 不允许依赖前后文补全、跨段聚合、隐含决策态或冲突消解。
3. 金标答案应简洁直接，只保留证据明确表达的事实槽位，如人名、时间、数值、对象、结论。
4. 若当前证据不足以支持一个合格的 L1 问题，就应尽量收缩问题范围，而不是脑补。
```

#### Rewrite Prompt for L2

```text
L2 重写要求:
1. 问题必须要求跨段聚合，答案信息至少分布在多个位置。
2. 但不能依赖前后反转、最终态变化、隐性拒绝或强噪音过滤；若依赖这些机制就不是 L2。
3. 金标答案应体现聚合结果，但只能保留证据中稳定出现的信息，不能扩写额外细节。
4. reasoning_from_mining 要点明这是跨段整合，而非动态推理。
```

#### Rewrite Prompt for L3

```text
L3 重写要求:
1. 问题必须保留动态性，只有跟踪最终态、过滤噪音或识别隐性拒绝，才能稳定答对。
2. 若最后一句直接明牌且前文不存在会误导模型的变化、噪音或拒绝语义，就不应写成 L3。
3. 金标答案必须明确给出最终业务结论，而不是过程性讨论。
4. reasoning_from_mining 要写清楚这条样本的 L3 机制是什么，例如反转、噪音干扰、隐性拒绝。
```

## 5. Evaluation

### LLM Judge Prompt

- Script: `scripts/evaluation/acmmm_eval.py`

#### System Prompt

```text
你是严格的会议问答评测裁判。请基于答案质量、证据支撑和层级特定能力进行评分，避免风格偏好，保持标尺稳定。
```

#### User Prompt Template

```text
层级(Level): {level}
模式(Pattern): {pattern}
问题(Question): {question}
金标答案(Gold answer): {gold_answer}
模型答案(Model answer): {model_answer}

金标证据原文（由 benchmark evidence IDs 映射）:
{gold_evidence_text}

模型引用证据原文（由模型答案中的 IDs 映射）:
{predicted_evidence_text}

Rubric: {rubric_json}
评分说明:
- 核心结论正确性与答案完整性分别评分，不要混为一个维度。
- 以语义正确性为主，不按字面重合打分。
- support_sufficiency 看“证据是否足以支撑结论”，不是严格 ID 一致。
- support_specificity 看“证据是否精准命中问题所需信息”，而不是泛泛相关。
- 若模型没给证据或证据不相关，应降低 E_sufficiency。
- 若模型结论正确但引用了可替代证据，允许给高分。
- 严格使用 5/4/3/2/1/0 锚点，避免主观漂移。
- 对 L3：三个子项都要评分，但样本通常存在主导 pattern；主导 pattern 对应能力应成为评分重点。
- 如果最终决策方向答反，必须重罚。
- {level_note}
- rationale 必须用中文，简明说明 1-2 个主要扣分点。
```

#### Level Note Values

```text
L1: 当前是 L1，只评 L1 子项。不要返回 L2/L3 子项和 L3 错误标记。
L2: 当前是 L2，只评 L2 子项。不要返回 L1/L3 子项和 L3 错误标记。
L3: 当前是 L3，评 L3 子项，并返回 L3 错误标记。
```

## 6. Note

- This file contains the concrete prompt templates used by the public release scripts.
- If the implementation is updated later, the corresponding script source remains the final authority.
