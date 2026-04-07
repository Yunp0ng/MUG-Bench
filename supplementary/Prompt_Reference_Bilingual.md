# Prompt Reference

This document provides the concrete prompt templates used in the public EMUG-Bench pipeline.

- The operational prompts in the released scripts are written in Chinese.
- The English blocks below are faithful translations for supplementary-material use.
- Placeholder variables such as `{context}` and `{question}` are filled at runtime.

## 1. Evidence Mining

### L1 Evidence Mining

- Script: `scripts/data_construction/L1_evidence.py`

#### Chinese System Prompt

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

#### English Translation

```text
You are a strict meeting-data quality inspector.
Your task is to extract evidence spans for [Level 1: explicit local retrieval] from meeting transcripts.

### Level 1 Definition
- What you see is what you get: the answer is fully contained in one local span and is stated explicitly.
- Fact-oriented information: focus on concrete time, place, numbers (budget/headcount), person names, definitions, or enumerated lists.
- Structural constraint: each evidence span must be either a single utterance or 2-3 consecutive utterances. The utterance IDs must therefore be consecutive.

### Task Requirements
1. Scan the full transcript and find dense factual spans.
2. Extract the corresponding utterance IDs.
3. Ensure that the extracted information is not revised or overturned later in the meeting.
4. Extract as many valid evidence groups as possible, with at least 8-10 groups when feasible.
```

#### User Prompt Template

```text
会议记录原文：
{context}
```

#### English Translation

```text
Meeting transcript:
{context}
```

### L2 Evidence Mining

- Script: `scripts/data_construction/L2_evidence.py`

#### Chinese System Prompt

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

#### English Translation

```text
You are an expert in information aggregation.
Your task is to extract evidence spans for [Level 2: cross-turn information aggregation] from meeting transcripts.

### Level 2 Definition
- Puzzle-like aggregation: information about the same concrete topic is distributed across different points in the meeting.
- Complementary relation: later evidence supplements earlier evidence (for example, the first span gives the time and the later span gives the owner), rather than contradicting it.
- Structural constraint: the evidence IDs must be discrete. The gap between the first and the last evidence utterance is preferably greater than 20 turns.

### Task Requirements
1. Find topics that are revisited multiple times in the meeting.
2. Extract all relevant utterance IDs so that the selected evidence can jointly form a complete answer.
3. Do not extract evidence with logical conflict or decision reversal.
```

#### User Prompt Template

```text
会议记录原文：
{context}
```

#### English Translation

```text
Meeting transcript:
{context}
```

### L3 Evidence Mining

- Script: `scripts/data_construction/L3_evidence.py`

#### Chinese System Prompt

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

#### English Translation

```text
You are a senior business decision analyst.
Your task is to extract evidence spans for [Level 3: dynamic state tracking and pragmatic reasoning] from meeting transcripts.

### Level 3 Definition
- Non-monotonic reasoning: the true conclusion changes over time, or is buried inside a large amount of procedural noise.
- Structural constraint: the evidence IDs are usually non-consecutive and carry internal tension.

### Task Requirements (find one of the following patterns)

Pattern A: Decision Flip
- Logic: propose X -> discussion/dispute -> final decision Y.
- Requirement: the evidence must include both the early proposal and the final decision.

Pattern B: Signal in Noise
- Logic: a long noisy discussion focuses on procedural details such as slide formatting or microphone settings, while one sentence contains the real business decision.
- Requirement: extract the core decision and ensure that the evidence chain crosses the noisy region.

Pattern C: Implicit Rejection
- Logic: the meeting never states “no” directly; instead, the proposal is stalled through excuses such as “let’s revisit later” or “the budget is insufficient.”
- Requirement: extract the proposal utterance and the hedged rejection utterances.
```

#### User Prompt Template

```text
会议记录原文：
{context}
```

#### English Translation

```text
Meeting transcript:
{context}
```

## 2. QA Generation

### L1/L2 QA Generation

- Script: `scripts/data_construction/qa_gen.py`

#### Chinese System Prompt

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

#### English Translation

```text
You are an expert question writer for meeting reading comprehension.
I will provide a set of out-of-context meeting evidence spans together with topic analysis.
Please construct a high-quality QA pair based only on this information.

### Construction Principles (simulate a user who has not read the meeting)
1. Question perspective: the question must sound like it comes from someone who has not read the transcript but wants to know the meeting content.
   - Bad: "What are the three competitors mentioned by Zhang San?" (leaks the speaker and the count)
   - Good: "Which competitors were mentioned in the meeting?" (asks only for the business fact)
2. Faithful answer: the answer must be fully grounded in the provided evidence and must not invent facts.
3. Aggregation: for L2, the answer must integrate information distributed across multiple utterances.

### Output Format (JSON)
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

#### English Translation

```text
Below are evidence spans from a meeting:
---
{evidence_text}
---

[Auxiliary Analysis]
- Evidence topic: {topic}
- Reasoning: {reasoning}
{pattern_line_if_any}

Please generate a high-quality QA pair based on the evidence spans and the auxiliary analysis:
```

### L3 QA Generation

- Script: `scripts/data_construction/qa_gen.py`

#### Chinese System Prompt

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

#### English Translation

```text
You are an advanced business-meeting analyst.
I will provide a set of evidence spans with complex logic, together with expert reasoning about that logic.
Please construct a challenging QA pair that tests whether an AI model can see through surface form and capture the true conclusion.

### Construction Principles (ask about the final outcome)
1. Use the expert reasoning to understand reversal or noise patterns and ensure that the answer reflects the final decision correctly.
2. Do not leak the process:
   - The question should only ask for the final decision or the conclusion about topic X.
   - Do not ask "Why was A rejected?" because that leaks the hidden outcome.
3. Resist noise: if the reasoning says there is procedural noise, the answer must exclude it.
4. Explain the answer briefly when helpful.

### Output Format (JSON)
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

#### English Translation

```text
Below are evidence spans from a meeting:
---
{evidence_text}
---

[Auxiliary Analysis]
- Evidence topic: {topic}
- Reasoning: {reasoning}
{pattern_line_if_any}

Please generate a high-quality QA pair based on the evidence spans and the auxiliary analysis:
```

## 3. Audit

### Audit Prompt

- Script: `scripts/data_construction/benchmark_audit.py`

#### Chinese System Prompt

```text
你是中文会议 benchmark 审核员。你的任务不是回答问题，而是只根据当前层级定义审核这条样本，并给出清洗建议。
```

#### English Translation

```text
You are an auditor for a Chinese meeting benchmark. Your task is not to answer the question, but to judge whether the sample fits the current benchmark level and to provide a cleanup action.
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

#### English Translation

```text
Current level: {level}
query_id: {query_id}
source_file: {source_file}
pattern: {pattern}

Question: {question}

Gold answer: {gold_answer}

Evidence text:
{evidence_text}

Audit goals:
1. Decide whether the sample truly fits the current level definition.
2. Decide whether the question leaks the answer direction or final state.
3. Decide whether the evidence is sufficient to support the gold answer.
4. Decide whether the sample is too easy, too vague, or better suited to another level.
5. Return one action: keep / downgrade / upgrade / rewrite / drop.
Requirements:
- Judge strictly under the current level definition; do not mix in ideal properties of other levels.
- The `reason` field must be in Chinese and must state the main problem concisely.

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

#### English Translation

```text
Audit only L1 samples.
L1 definition: the answer should be directly determined by 1-2 explicit evidence utterances, focusing on local fact retrieval.
Decision criteria:
1. If the sample requires cross-segment aggregation, background completion, or conflict resolution, it should not be L1.
2. The question should focus on one clear factual slot or one local factual span.
3. If the evidence has unclear references, ASR errors, or the answer goes beyond the evidence boundary, prefer rewrite.
4. Do not score the sample using L2/L3 expectations.
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

#### English Translation

```text
Audit only L2 samples.
L2 definition: the answer must require cross-segment aggregation, with information distributed across multiple meeting positions, but it should not rely on reversal or final-state change.
Decision criteria:
1. If one local span is sufficient to answer the question, the sample should not be L2.
2. If the sample requires tracking reversal, filtering noise, or recognizing implicit rejection, it should be upgraded to L3.
3. The question should require complementary integration across multiple spans rather than simple restatement.
4. If the gold answer goes beyond what the evidence jointly supports, prefer rewrite.
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

#### English Translation

```text
Audit only L3 samples.
L3 definition: the sample should require final-state tracking, noise filtering, or implicit-rejection recognition to answer reliably.
Decision criteria:
1. If the final conclusion is explicitly stated in one utterance and no dynamic tracking is needed, it should not be L3.
2. If the sample only needs cross-segment aggregation without dynamic change, it should be downgraded to L2.
3. The question should not leak the answer direction through phrases such as “rejected,” “changed to,” or “final decision.”
4. The gold answer must state the final business conclusion rather than procedural discussion.
```

## 4. Cleanup

### Cleanup Rewrite Prompt

- Script: `scripts/data_construction/benchmark_cleanup.py`

#### Chinese System Prompt

```text
你是中文会议 benchmark 数据清洗助手。你的任务是根据审核意见，重写 benchmark 样本中的问题、金标答案和简短推理说明。你必须严格受限于给定证据，不得引入证据中不存在的事实。
```

#### English Translation

```text
You are a data-cleaning assistant for a Chinese meeting benchmark. Your task is to rewrite the benchmark question, gold answer, and short reasoning note according to the audit result. You must stay strictly within the provided evidence and may not introduce unsupported facts.
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

#### English Translation

```text
Target level: {target_level}
source_file: {source_file}
Original query_id: {query_id}
Original question: {original_question}
Original gold answer: {original_gold_answer}
Original reasoning_from_mining: {original_reasoning}
Original pattern: {pattern}

Audit action: {audit_action}
Audit primary issue: {audit_primary_issue}
Audit reason: {audit_reason}

Evidence text:
{evidence_text}

Rewrite requirements:
1. Output only a question and answer that are directly or robustly supported by the evidence.
2. The question should sound natural and should not leak the answer direction.
3. The gold answer should answer only the question itself, without adding extra details not asked for.
4. `reasoning_from_mining` should use 1-2 Chinese sentences to explain why the sample fits the target level.
5. Do not modify `evidence_ids`; they are preserved by the program.

{rewrite_prompt_for_level}
```

## 5. Evaluation

### LLM Judge Prompt

- Script: `scripts/evaluation/acmmm_eval.py`

#### Chinese System Prompt

```text
你是严格的会议问答评测裁判。请基于答案质量、证据支撑和层级特定能力进行评分，避免风格偏好，保持标尺稳定。
```

#### English Translation

```text
You are a strict judge for meeting QA evaluation. Score the model output based on answer quality, evidence grounding, and level-specific ability. Avoid stylistic preference and keep the scoring standard stable.
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

#### English Translation

```text
Level: {level}
Pattern: {pattern}
Question: {question}
Gold answer: {gold_answer}
Model answer: {model_answer}

Gold evidence text (mapped from benchmark evidence IDs):
{gold_evidence_text}

Model-cited evidence text (mapped from IDs cited in the model answer):
{predicted_evidence_text}

Rubric: {rubric_json}
Scoring instructions:
- Score core conclusion correctness and answer completeness separately.
- Use semantic correctness rather than surface lexical overlap.
- `support_sufficiency` evaluates whether the cited evidence is sufficient to support the conclusion, not whether the IDs match exactly.
- `support_specificity` evaluates whether the cited evidence precisely targets the information required by the question rather than being only broadly relevant.
- If the model provides no evidence or irrelevant evidence, reduce evidence sufficiency.
- If the model gives the correct conclusion with alternative but still valid evidence, high scores are allowed.
- Use the 5/4/3/2/1/0 anchors strictly and avoid rubric drift.
- For L3, score all three subskills, but emphasize the subskill associated with the dominant pattern.
- If the model gets the final decision direction wrong, penalize heavily.
- {level_note}
- The `rationale` field must be in Chinese and should briefly explain the one or two main deductions.
```
