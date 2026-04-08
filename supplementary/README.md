# Supplementary Material for EMUG-Bench

This README provides the supplementary material for **EMUG-Bench: An Evidence-aware Benchmark for Real-World Chinese Meeting Understanding**. It is written to address reproducibility and robustness questions raised during review, without requiring readers to inspect raw CSV or JSON files.

This supplement covers:

1. Full Prompt and Output Protocol
2. Evaluation Framework Details and Sensitivity Analysis
3. Annotation / Audit / Cleanup Protocol
4. Release / Access / Ethics Statement
5. L3 Subtype-wise Results
6. Cross-Judge Robustness

## 1. Full Prompt and Output Protocol

### 1.1 Prompt release policy

The public repository releases the concrete prompts used in the benchmark pipeline. These are not prompt examples; they are the operational templates used by the released scripts, with runtime placeholders filled programmatically.

The released prompt file is bilingual:

- Chinese: operational prompt text used in the scripts
- English: faithful translation for supplementary and reproducibility purposes

Full prompt templates are provided in:

- [docs/prompt_reference.md](../docs/prompt_reference.md)

### 1.2 Covered prompt stages

The released prompt document includes:

- L1 evidence mining
- L2 evidence mining
- L3 evidence mining
- L1/L2 QA generation
- L3 QA generation
- audit
- cleanup rewrite
- evaluation judge

### 1.3 Output protocol by stage

Evidence mining returns structured evidence groups. L1/L2 use:

```json
{
  "evidence_groups": [
    {
      "topic": "string",
      "ids": [1, 2, 3],
      "reasoning": "string"
    }
  ]
}
```

L3 additionally includes a pattern field:

```json
{
  "evidence_groups": [
    {
      "pattern": "A | B | C",
      "topic": "string",
      "ids": [12, 45, 63],
      "reasoning": "string"
    }
  ]
}
```

QA generation returns:

```json
{
  "question": "string",
  "answer": "string"
}
```

Audit returns one structured decision per sample:

```json
{
  "action": "keep | downgrade | upgrade | rewrite | drop",
  "recommended_level": "L1 | L2 | L3 | NA",
  "layer_fit_0_5": 0,
  "question_leakage_0_5": 0,
  "evidence_support_0_5": 0,
  "difficulty_0_5": 0,
  "primary_issue": "none | wrong_level | question_leakage | weak_evidence | too_easy | too_hard | ambiguous_gold",
  "reason": "string"
}
```

Cleanup rewrite returns:

```json
{
  "question": "string",
  "gold_answer": "string",
  "reasoning_from_mining": "string"
}
```

The evaluation pipeline exports per-sample records with:

- final score
- answer score
- evidence score
- level-skill score
- penalty score
- all rubric sub-scores
- citation precision / recall / F1
- penalty flags

### 1.4 Evidence citation protocol

The benchmark evaluates evidence grounding at the utterance-ID level.

The released scoring logic follows these rules:

- gold evidence is stored as benchmark `evidence_ids`
- predicted evidence is parsed from model outputs as utterance IDs
- citation quality contributes to citation overlap metrics
- missing or invalid citations reduce the evidence sub-score through weak citation overlap and support sufficiency

## 2. Evaluation Framework Details and Sensitivity Analysis

### 2.1 Default scoring framework

The paper uses:

\[
\mathrm{Score}=100\cdot(\alpha A+\beta E+\gamma L)-\mathcal{P},
\]

with:

- `alpha = 0.30`
- `beta = 0.40`
- `gamma = 0.30`

Sub-weights:

- `A = 0.6 * A_core + 0.4 * A_completeness`
- `E = 0.45 * E_sufficiency + 0.25 * E_specificity + 0.20 * citation_f1 + 0.10 * citation_precision`
- `L1 = 0.5 * slot_accuracy + 0.5 * localization`
- `L2 = 0.5 * multi_hop_coverage + 0.5 * synthesis_consistency`
- `L3 = 0.6 * main_subtype_skill + 0.2 * aux1 + 0.2 * aux2`

Penalty settings:

- contradiction: `10`
- hallucination: `10`
- L3 dominant error: `12`
- L3 auxiliary subtype error: `3`
- penalty cap: `30`

### 2.2 Sensitivity setup

To check whether the main conclusions depend on one narrow coefficient choice, we recomputed scores from the released per-sample judge outputs under six alternative settings:

| Setting | A | E | L | Penalty Scale |
|---|---:|---:|---:|---:|
| Default grounding-heavy | 0.30 | 0.40 | 0.30 | 1.0 |
| Balanced | 0.333 | 0.333 | 0.333 | 1.0 |
| Answer-heavy | 0.40 | 0.30 | 0.30 | 1.0 |
| Reasoning-heavy | 0.30 | 0.30 | 0.40 | 1.0 |
| Low-penalty | 0.30 | 0.40 | 0.30 | 0.5 |
| High-penalty | 0.30 | 0.40 | 0.30 | 1.5 |

### 2.3 Sensitivity results

Table A1 reports the recomputed overall scores of the seven frontier models under all six coefficient settings.

| Model | Default | Balanced | Answer-heavy | Reasoning-heavy | Low-penalty | High-penalty |
|---|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 82.64 | 83.05 | 83.21 | 83.30 | 83.44 | 82.04 |
| GLM-5 | 78.94 | 79.58 | 79.90 | 79.91 | 80.09 | 77.99 |
| Qwen3.5-397B | 78.68 | 79.29 | 79.58 | 79.62 | 79.86 | 77.68 |
| GPT-5 | 74.62 | 75.20 | 75.52 | 75.47 | 75.87 | 73.57 |
| Qwen-Plus | 74.05 | 74.67 | 75.00 | 74.97 | 75.54 | 72.86 |
| Claude-Opus-4.6 | 73.78 | 74.52 | 74.91 | 74.88 | 75.44 | 72.37 |
| DeepSeek-V3.2 | 72.27 | 72.85 | 73.14 | 73.16 | 73.73 | 71.10 |

Table A2 reports the corresponding ranking stability.

| Setting | Ranking | Spearman vs. Default |
|---|---|---:|
| Default grounding-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Balanced | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Answer-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Reasoning-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Low-penalty | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| High-penalty | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |

These results show that the reported frontier-model ordering is stable under reasonable perturbations of the coefficient and penalty settings.

### 2.4 Stability of qualitative conclusions

Across all six settings, `L3` remains the hardest level for every frontier model, the top model group remains unchanged, and varying the penalty strength changes absolute scores without changing the main qualitative conclusions of the paper.

## 3. Annotation / Audit / Cleanup Protocol

### 3.1 Pipeline

The construction pipeline has four stages:

1. multi-level evidence mining
2. QA generation
3. audit
4. cleanup and post-audit

All model-assisted stages use GPT-5, but all final retained QA instances and evidence annotations are manually checked before inclusion in the released benchmark.

### 3.2 Level-specific principles

`L1`

- answer should be directly recoverable from one utterance or a short contiguous span
- no cross-turn aggregation
- no dynamic state tracking

`L2`

- answer requires cross-turn aggregation
- evidence is distributed across non-adjacent utterances
- later evidence complements earlier evidence rather than reversing it

`L3`

- answering requires dynamic state tracking or pragmatic reasoning
- includes decision reversal, procedural noise, and implicit rejection

### 3.3 Audit actions

Audit evaluates:

- level fit
- question leakage
- evidence sufficiency
- difficulty alignment

Audit actions are:

- `keep`
- `downgrade`
- `upgrade`
- `rewrite`
- `drop`

In the paper text, `upgrade` and `downgrade` are abstracted as `relabel`.

### 3.4 Cleanup statistics

| Quantity | Count | Ratio |
|---|---:|---:|
| Candidate instances | 1729 | 100.00% |
| Keep | 1042 | 60.27% |
| Relabel | 511 | 29.55% |
| Rewrite | 175 | 10.12% |
| Drop | 1 | 0.06% |
| Final retained | 1708 | 98.79% |
| Final removed | 21 | 1.21% |

Final retained instances consist of:

- kept unchanged: `1042`
- moved after relabel: `511`
- rewritten and passed post-audit: `155`

Final removed instances consist of:

- direct drop: `1`
- post-audit failure after rewrite: `20`

This shows that the cleanup pipeline is conservative: most imperfect samples are repaired through relabeling or rewrite rather than being deleted.

## 4. Release / Access / Ethics Statement

### 4.1 Public release

The public GitHub repository provides:

- a sampled public benchmark subset
- aligned transcript subset
- data construction scripts
- evaluation scripts
- bilingual prompt documentation
- this supplementary document

Repository:

- [EMUG-Bench GitHub](https://github.com/Yunp0ng/EMUG-Bench.git)

### 4.2 Full release

The full benchmark is packaged in the same normalized schema as the public release, but is not hosted on GitHub.

Full access is controlled and intended for academic / research use.

Contact:

- `Yunpeng.Li21@student.xjtlu.edu.cn`

### 4.3 Privacy safeguards

The real-meeting portion is privacy-sensitive. Therefore:

- all real meeting transcripts are de-identified before release
- personal and organization identifiers are replaced or removed
- public GitHub hosting is restricted to the sample release
- full release is distributed under controlled access rather than unrestricted hosting

## 5. L3 Subtype-wise Results

### 5.1 Subtype distribution

The full L3 benchmark contains:

| Subtype | Meaning | Count |
|---|---|---:|
| A | Decision reversal | 52 |
| B | Procedural noise | 15 |
| C | Implicit rejection | 133 |
| N/A | Legacy uncategorized pattern | 1 |

Subtype `B` is much smaller than `A` and `C`, so subtype-wise conclusions for `B` should be interpreted cautiously.

### 5.2 Model-wise subtype performance

Mean L3 total scores by subtype:

| Model | A | B | C |
|---|---:|---:|---:|
| Claude-Opus-4.6 | 59.73 | 60.23 | 58.45 |
| DeepSeek-V3.2 | 53.53 | 69.43 | 50.37 |
| Gemini-3-Pro | 57.90 | 82.30 | 61.89 |
| GLM-5 | 57.62 | 71.41 | 61.89 |
| GPT-5 | 62.51 | 82.37 | 68.89 |
| Qwen-Plus | 51.68 | 68.68 | 54.42 |
| Qwen3.5-397B | 54.30 | 83.82 | 62.40 |
| Qwen3.5-27B | 56.38 | 70.92 | 55.97 |
| Qwen3.5-9B | 53.39 | 71.37 | 55.11 |
| Qwen3.5-4B | 41.56 | 64.82 | 49.81 |

Interpretation:

- subtype `C` is the largest and remains challenging across models
- subtype `A` is also difficult, especially for smaller models
- subtype `B` appears easier for stronger models, but this is partly influenced by its small sample count

## 6. Cross-Judge Robustness

### 6.1 Setup

To test judge robustness, we constructed a stratified subset of `90` benchmark questions:

- `30` from `L1`
- `30` from `L2`
- `30` from `L3`

For `L3`, the subset was balanced by subtype:

- `A = 9`
- `B = 6`
- `C = 15`

This subset was re-scored with `gemini-3-pro-preview` as an alternative judge, while the main paper results used `GPT-5` as the judge.

This is a **cross-judge robustness analysis**, not a human-correlation analysis.

### 6.2 Coverage note

The theoretical maximum for this setup is:

- `90` samples
- `7` frontier models
- total possible scored items: `630`

The final matched comparison size is `629`, because one Claude-Opus-4.6 prediction on an `L3` sample was an invalid response (`ERROR: Failed after retries.`) and was excluded by the evaluation pipeline.

### 6.3 Cross-judge score agreement

Across the matched `629` judge records, the two judges show strong sample-level agreement on total score.

| Metric | Value |
|---|---:|
| Pearson correlation on total score | 0.8588 |
| Spearman correlation on total score | 0.8460 |

Table A3 reports level-wise agreement.

| Level | Count | GPT-5 Mean | Gemini Mean | Pearson | Spearman |
|---|---:|---:|---:|---:|---:|
| L1 | 210 | 68.97 | 79.50 | 0.8248 | 0.8814 |
| L2 | 210 | 63.56 | 70.30 | 0.8626 | 0.7927 |
| L3 | 209 | 48.38 | 58.63 | 0.8609 | 0.8591 |

The alternative judge is more lenient in absolute score, but the relative ordering of samples remains highly correlated across levels.

### 6.4 Cross-judge model scores and ranking

Table A4 reports the per-model mean scores under the two judges on the same robustness subset.

| Model | Count | GPT-5 Judge Mean | Gemini Judge Mean |
|---|---:|---:|---:|
| Qwen3.5-397B | 90 | 64.82 | 73.99 |
| Gemini-3-Pro | 90 | 66.45 | 73.44 |
| GLM-5 | 90 | 63.40 | 72.76 |
| Claude-Opus-4.6 | 89 | 60.22 | 72.32 |
| DeepSeek-V3.2 | 90 | 56.64 | 67.10 |
| Qwen-Plus | 90 | 54.40 | 63.89 |
| GPT-5 | 90 | 56.31 | 62.99 |

Table A5 reports the resulting model ordering.

| Judge | Ranking |
|---|---|
| GPT-5 judge | Gemini-3-Pro > Qwen3.5-397B > GLM-5 > Claude-Opus-4.6 > DeepSeek-V3.2 > GPT-5 > Qwen-Plus |
| Gemini judge | Qwen3.5-397B > Gemini-3-Pro > GLM-5 > Claude-Opus-4.6 > DeepSeek-V3.2 > Qwen-Plus > GPT-5 |

| Metric | Value |
|---|---:|
| Spearman rank correlation | 0.9286 |

The top two models swap positions under the alternative judge, while the remaining ordering is largely preserved.

### 6.6 Penalty-flag agreement

| Flag | Agreement | Cohen’s Kappa | GPT-5 Positive | Gemini Positive |
|---|---:|---:|---:|---:|
| contradiction | 0.9221 | 0.7283 | 124 | 93 |
| hallucination | 0.8633 | 0.3846 | 115 | 39 |
| l3_decision_flip_error | 0.9555 | 0.6973 | 62 | 38 |
| l3_noise_contamination | 0.9491 | 0.7909 | 98 | 80 |
| l3_implicit_rejection_miss | 0.9507 | 0.7752 | 91 | 66 |

Agreement is high for contradiction and L3-specific penalty flags, while hallucination is less stable than the other flags under judge substitution.

## 7. Release Notes

- The public repository intentionally presents the supplementary material as a readable document rather than a collection of raw analysis files.
- The benchmark sample release, scripts, prompt reference, and supplementary material are public.
- The full dataset is not publicly hosted and requires controlled access.
