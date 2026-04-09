# Supplementary Material for EMUG-Bench

This document provides supplementary material for the EMUG-Bench submission. It complements the main paper by clarifying the public release format, prompt and output protocol, annotation and cleanup procedure, evaluation sensitivity, cross-judge robustness, and the implementation details of the lightweight RAG baseline.

## 1. Public Release and Access

To make the benchmark inspectable while respecting the release constraints of the full dataset, the public repository exposes a sampled subset with `50` instances for each of `L1`, `L2`, and `L3`, together with the aligned VCSum transcripts, the released construction and evaluation scripts, and bilingual prompt documentation. The full EMUG-Bench release is not hosted on GitHub; access is available upon request for academic or research use via `Yunpeng.Li21@student.xjtlu.edu.cn`.

## 2. Repository Contents

```text
EMUG-Bench/
├── data/
│   ├── benchmark/
│   │   ├── L1.json
│   │   ├── L2.json
│   │   └── L3.json
│   ├── transcripts/
│   │   └── vcsum/
│   └── selection_summary.json
├── scripts/
│   ├── data_construction/
│   └── evaluation/
├── docs/
│   └── prompt_reference.md
└── requirements.txt
```

The released benchmark files are [data/benchmark/L1.json](data/benchmark/L1.json), [data/benchmark/L2.json](data/benchmark/L2.json), and [data/benchmark/L3.json](data/benchmark/L3.json). The aligned transcripts for the public subset are stored under [data/transcripts/vcsum](data/transcripts/vcsum).

## 3. Data Schema

### 3.1 Benchmark JSON

Each released level file follows the schema below:

```json
{
  "dataset": "EMUG-Bench",
  "subset": "vcsum_sampled_release",
  "level": "L1",
  "sample_count": 50,
  "samples": [
    {
      "sample_id": "emug_l1_001",
      "level": "L1",
      "source_file": "mug_vcsum_249011272.json",
      "query_id": "mug_vcsum_249011272.json_L1_1",
      "topic": "共享服务中心建设问题",
      "pattern": "N/A",
      "question": "会议中提到企业在共享服务中心建设中面临的主要问题是什么？",
      "gold_answer": "......",
      "evidence_ids": [12, 13],
      "transcript_path": "../transcripts/vcsum/mug_vcsum_249011272.json"
    }
  ]
}
```

The fields have the following meanings:

- `dataset`: dataset name
- `subset`: release type
- `level`: benchmark level (`L1`, `L2`, `L3`)
- `sample_count`: number of released instances in the file
- `sample_id`: public sample identifier
- `source_file`: aligned transcript filename
- `query_id`: original cleaned-benchmark query identifier
- `topic`: topic tag inherited from evidence mining / QA construction
- `pattern`: reasoning pattern label
  - `L1` and `L2`: always `N/A`
  - `L3`: `A`, `B`, or `C`
- `question`: benchmark question
- `gold_answer`: manually cleaned reference answer
- `evidence_ids`: supporting utterance IDs
- `transcript_path`: relative path to the aligned transcript file

### 3.2 Transcript JSON

Each transcript file is stored in a unified JSON format:

```json
{
  "dataset": "VCSum",
  "source_dataset": "VCSum",
  "vcsum_id": "231",
  "av_num": 80645348,
  "split": "train",
  "speakers": [
    {"speaker_id": 1, "name": "Speaker 1"}
  ],
  "utterances": [
    {"id": 1, "speaker_id": 1, "text": "..."}
  ]
}
```

The transcript fields have the following meanings:

- `dataset`: dataset family name
- `source_dataset`: original source dataset
- `vcsum_id`: original VCSum instance identifier
- `av_num`: VCSum meeting identifier
- `split`: original split
- `speakers`: speaker list
- `utterances`: ordered utterance list
- `utterances[].id`: utterance ID used by `evidence_ids`
- `utterances[].speaker_id`: speaker index
- `utterances[].text`: utterance content

## 4. Prompt and Output Protocol

This section supplements the methodology description in the main paper by specifying the released prompt and output protocol. The public repository exposes the concrete prompt templates actually used in the released pipeline rather than illustrative prompt examples; these prompts are documented in bilingual form in [docs/prompt_reference.md](docs/prompt_reference.md). The released prompt stages cover L1/L2/L3 evidence mining, QA generation, audit, cleanup rewrite, and evaluation.

### 4.1 Evidence Mining Output

L1/L2 evidence mining returns:

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

L3 evidence mining additionally includes a pattern field:

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

### 4.2 QA Generation Output

```json
{
  "question": "string",
  "answer": "string"
}
```

### 4.3 Audit Output

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

### 4.4 Cleanup Rewrite Output

```json
{
  "question": "string",
  "gold_answer": "string",
  "reasoning_from_mining": "string"
}
```

The evaluation pipeline then scores answer quality, evidence grounding, level-specific skill, penalties, and citation overlap from utterance-ID evidence references.

## 5. Annotation, Audit, and Cleanup

The benchmark construction pipeline has four stages:

1. multi-level evidence mining
2. QA generation
3. audit
4. cleanup and post-audit

All model-assisted stages use GPT-5, while all final retained QA instances and evidence annotations are manually checked before inclusion in the released benchmark.

The audit stage jointly evaluates level fit, question leakage, evidence sufficiency, and difficulty alignment. It assigns one of five implementation-level actions: `keep`, `downgrade`, `upgrade`, `rewrite`, or `drop`. In the paper text, `upgrade` and `downgrade` are abstracted as `relabel`.

### 5.1 Cleanup Statistics

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

These statistics clarify an implementation detail that is only summarized briefly in the main paper: the cleanup stage is conservative, and most imperfect instances are repaired through relabeling or QA rewrite rather than being removed from the final benchmark.

## 6. Evaluation Framework and Sensitivity Analysis

The main paper uses:

`Score = 100 * (alpha * A + beta * E + gamma * L) - P`

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

To supplement the evaluation framework in the main paper, we tested whether the main conclusions depend strongly on one narrow coefficient choice. We therefore recomputed the frontier-model scores under six alternative settings.

| Setting | A | E | L | Penalty Scale |
|---|---:|---:|---:|---:|
| Default grounding-heavy | 0.30 | 0.40 | 0.30 | 1.0 |
| Balanced | 0.333 | 0.333 | 0.333 | 1.0 |
| Answer-heavy | 0.40 | 0.30 | 0.30 | 1.0 |
| Reasoning-heavy | 0.30 | 0.30 | 0.40 | 1.0 |
| Low-penalty | 0.30 | 0.40 | 0.30 | 0.5 |
| High-penalty | 0.30 | 0.40 | 0.30 | 1.5 |

### 6.1 Recomputed Overall Scores

The scores in Table A1 are overall benchmark scores, i.e., means aggregated over the full benchmark rather than level-specific averages.

| Model | Default | Balanced | Answer-heavy | Reasoning-heavy | Low-penalty | High-penalty |
|---|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 82.64 | 83.05 | 83.21 | 83.30 | 83.44 | 82.04 |
| GLM-5 | 78.94 | 79.58 | 79.90 | 79.91 | 80.09 | 77.99 |
| Qwen3.5-397B | 78.68 | 79.29 | 79.58 | 79.62 | 79.86 | 77.68 |
| GPT-5 | 74.62 | 75.20 | 75.52 | 75.47 | 75.87 | 73.57 |
| Qwen-Plus | 74.05 | 74.67 | 75.00 | 74.97 | 75.54 | 72.86 |
| Claude-Opus-4.6 | 73.78 | 74.52 | 74.91 | 74.88 | 75.44 | 72.37 |
| DeepSeek-V3.2 | 72.27 | 72.85 | 73.14 | 73.16 | 73.73 | 71.10 |

### 6.2 Level-wise Scores Under Alternative Settings

To make the coefficient sensitivity more interpretable, Tables A2-A4 report the recomputed scores separately for `L1`, `L2`, and `L3`.

#### L1

| Model | Default | Balanced | Answer-heavy | Reasoning-heavy | Low-penalty | High-penalty |
|---|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 85.88 | 86.58 | 86.89 | 86.99 | 86.49 | 85.28 |
| GLM-5 | 80.60 | 81.49 | 81.94 | 81.94 | 81.60 | 79.61 |
| Qwen3.5-397B | 80.64 | 81.46 | 81.86 | 81.88 | 81.62 | 79.67 |
| GPT-5 | 76.85 | 77.66 | 78.10 | 78.03 | 77.98 | 75.80 |
| Qwen-Plus | 76.80 | 77.63 | 78.08 | 77.99 | 78.09 | 75.60 |
| Claude-Opus-4.6 | 75.78 | 76.78 | 77.37 | 77.20 | 77.27 | 74.35 |
| DeepSeek-V3.2 | 74.75 | 75.55 | 75.94 | 75.98 | 76.06 | 73.56 |

#### L2

| Model | Default | Balanced | Answer-heavy | Reasoning-heavy | Low-penalty | High-penalty |
|---|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 84.72 | 85.02 | 85.10 | 85.24 | 85.08 | 84.38 |
| GLM-5 | 82.02 | 82.60 | 82.85 | 82.94 | 82.75 | 81.30 |
| Qwen3.5-397B | 81.23 | 81.87 | 82.14 | 82.24 | 82.03 | 80.44 |
| Qwen-Plus | 76.45 | 77.01 | 77.25 | 77.33 | 77.51 | 75.45 |
| Claude-Opus-4.6 | 75.83 | 76.54 | 76.80 | 77.00 | 77.11 | 74.59 |
| DeepSeek-V3.2 | 75.07 | 75.63 | 75.88 | 75.95 | 76.09 | 74.07 |
| GPT-5 | 74.08 | 74.59 | 74.85 | 74.84 | 75.07 | 73.13 |

#### L3

| Model | Default | Balanced | Answer-heavy | Reasoning-heavy | Low-penalty | High-penalty |
|---|---:|---:|---:|---:|---:|---:|
| GPT-5 | 68.08 | 68.04 | 68.11 | 67.96 | 70.80 | 66.64 |
| Gemini-3-Pro | 62.56 | 62.29 | 62.26 | 62.07 | 65.73 | 61.05 |
| Qwen3.5-397B | 61.85 | 61.55 | 61.46 | 61.35 | 65.15 | 59.91 |
| GLM-5 | 61.41 | 61.26 | 61.30 | 61.10 | 64.59 | 59.69 |
| Claude-Opus-4.6 | 58.62 | 58.48 | 58.59 | 58.26 | 62.33 | 56.69 |
| Qwen-Plus | 54.71 | 54.77 | 54.93 | 54.75 | 58.50 | 52.91 |
| DeepSeek-V3.2 | 52.51 | 52.34 | 52.39 | 52.16 | 56.14 | 50.75 |

### 6.3 Ranking Stability

| Setting | Ranking | Spearman vs. Default |
|---|---|---:|
| Default grounding-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Balanced | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Answer-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Reasoning-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Low-penalty | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| High-penalty | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |

Across all six settings, `L3` remains the hardest level for every frontier model and the model ordering is unchanged. This supports the interpretation that the headline conclusions reported in the main paper are not artifacts of one specific coefficient choice.

## 7. Cross-Judge Robustness

To evaluate judge robustness, we constructed a stratified subset of `90` benchmark instances:

- `30` from `L1`
- `30` from `L2`
- `30` from `L3`

Within `L3`, the subset preserves subtype coverage with:

- `A = 9`
- `B = 6`
- `C = 15`

All cross-judge statistics reported below are computed on this same subset. Therefore, the `L1`, `L2`, and `L3` score tables are directly comparable across the two judges because they are based on the same `30/30/30` level split.

The main paper uses `GPT-5` as the judge. For the robustness check, we re-scored the same subset with `gemini-3-pro-preview` as an alternative judge. This is a cross-judge robustness analysis rather than a human-correlation analysis.

The cross-judge comparison covers `630` judged model-instance pairs (`90` samples × `7` models).

### 7.1 Sample-level and Level-wise Agreement

| Metric | Value |
|---|---:|
| Pearson correlation on total score | 0.8588 |
| Spearman correlation on total score | 0.8460 |

| Level | Count | GPT-5 Mean | Gemini Mean | Pearson | Spearman |
|---|---:|---:|---:|---:|---:|
| L1 | 210 | 68.97 | 79.50 | 0.8248 | 0.8814 |
| L2 | 210 | 63.56 | 70.30 | 0.8626 | 0.7927 |
| L3 | 209 | 48.38 | 58.63 | 0.8609 | 0.8591 |

The alternative judge is systematically more lenient in absolute score, but the relative ordering of samples remains highly correlated across all three levels.

### 7.2 Per-level Mean Scores by Judge

The following tables report the mean `A`, `E`, `L`, and overall scores for the seven frontier models. All values are computed from the same `30`-instance subset for each level.

#### L1

| Model | Count | GPT-5 A | GPT-5 E | GPT-5 L | GPT-5 Overall | Gemini A | Gemini E | Gemini L | Gemini Overall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 30 | 24.48 | 31.06 | 25.30 | 79.17 | 26.96 | 32.21 | 26.90 | 85.73 |
| GLM-5 | 30 | 22.84 | 26.49 | 23.50 | 69.16 | 26.68 | 30.58 | 27.00 | 83.26 |
| Qwen3.5-397B | 30 | 23.84 | 27.53 | 23.60 | 71.64 | 26.68 | 30.51 | 26.20 | 83.05 |
| GPT-5 | 30 | 19.76 | 22.05 | 19.30 | 57.63 | 20.60 | 24.35 | 21.00 | 64.31 |
| Qwen-Plus | 30 | 22.08 | 26.34 | 22.70 | 67.13 | 24.16 | 29.04 | 24.20 | 75.40 |
| Claude-Opus-4.6 | 30 | 23.52 | 27.16 | 23.30 | 71.01 | 27.12 | 30.35 | 27.30 | 83.53 |
| DeepSeek-V3.2 | 30 | 21.04 | 26.18 | 22.50 | 67.05 | 25.48 | 30.07 | 26.00 | 81.22 |

#### L2

| Model | Count | GPT-5 A | GPT-5 E | GPT-5 L | GPT-5 Overall | Gemini A | Gemini E | Gemini L | Gemini Overall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 30 | 22.68 | 29.85 | 22.90 | 73.80 | 23.96 | 31.02 | 23.30 | 77.71 |
| GLM-5 | 30 | 22.60 | 28.29 | 23.00 | 70.89 | 24.08 | 29.61 | 24.00 | 76.78 |
| Qwen3.5-397B | 30 | 21.88 | 27.69 | 22.30 | 69.20 | 23.32 | 29.19 | 23.40 | 74.96 |
| GPT-5 | 30 | 17.52 | 23.48 | 17.60 | 54.47 | 17.88 | 23.64 | 17.90 | 57.09 |
| Qwen-Plus | 30 | 18.32 | 23.31 | 18.70 | 55.70 | 19.52 | 26.07 | 19.70 | 62.19 |
| Claude-Opus-4.6 | 30 | 19.96 | 23.98 | 21.40 | 59.97 | 23.12 | 28.18 | 23.80 | 73.59 |
| DeepSeek-V3.2 | 30 | 19.32 | 24.89 | 19.70 | 60.88 | 21.64 | 27.20 | 21.90 | 69.74 |

#### L3

| Model | Count | GPT-5 A | GPT-5 E | GPT-5 L | GPT-5 Overall | Gemini A | Gemini E | Gemini L | Gemini Overall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 30 | 16.56 | 24.03 | 14.56 | 46.37 | 18.64 | 26.15 | 17.96 | 56.88 |
| GLM-5 | 30 | 19.04 | 25.07 | 16.64 | 50.16 | 20.60 | 24.66 | 18.64 | 58.23 |
| Qwen3.5-397B | 30 | 18.48 | 25.65 | 17.04 | 53.62 | 20.80 | 26.89 | 20.76 | 63.96 |
| GPT-5 | 30 | 19.56 | 26.82 | 18.36 | 56.84 | 22.08 | 27.30 | 21.84 | 67.58 |
| Qwen-Plus | 30 | 15.64 | 22.21 | 13.96 | 40.39 | 17.72 | 24.02 | 17.52 | 54.07 |
| Claude-Opus-4.6 | 30 | 18.70 | 24.39 | 16.76 | 49.32 | 20.81 | 25.55 | 19.20 | 59.40 |
| DeepSeek-V3.2 | 30 | 16.24 | 21.04 | 14.24 | 42.00 | 17.52 | 22.42 | 16.92 | 50.33 |

The `L3` table addresses a key concern raised by the review process about possible judge bias. Under both judges, `GPT-5` remains the strongest `L3` model on this robustness subset:

- `56.84` under the GPT-5 judge
- `67.58` under the Gemini judge

This indicates that the relatively strong `L3` performance of `GPT-5` is not created by using GPT-5 as the judge. At the same time, `GPT-5` does not lead on `L1` or `L2` under either judge, which explains why its overall ranking on the robustness subset is not the highest even though it remains strongest on `L3`.

### 7.3 Model Ranking Under the Two Judges

| Judge | Ranking |
|---|---|
| GPT-5 judge | Gemini-3-Pro > Qwen3.5-397B > GLM-5 > Claude-Opus-4.6 > DeepSeek-V3.2 > GPT-5 > Qwen-Plus |
| Gemini judge | Qwen3.5-397B > Gemini-3-Pro > GLM-5 > Claude-Opus-4.6 > DeepSeek-V3.2 > Qwen-Plus > GPT-5 |

| Metric | Value |
|---|---:|
| Spearman rank correlation | 0.9286 |

The top two models swap positions under the alternative judge, while the remaining ranking is largely preserved.

### 7.4 Penalty-flag Agreement

Table A5 compares whether the two judges assign the same binary penalty flags to the same samples. `Agreement` is the raw proportion of samples on which the two judges make the same yes/no decision for a given flag. `Cohen's Kappa` reports a stricter agreement measure that discounts agreement expected by chance. `GPT-5 Positive` and `Gemini Positive` denote the numbers of samples for which each judge activates the corresponding penalty flag.

| Flag | Agreement | Cohen’s Kappa | GPT-5 Positive | Gemini Positive |
|---|---:|---:|---:|---:|
| contradiction | 0.9221 | 0.7283 | 124 | 93 |
| hallucination | 0.8633 | 0.3846 | 115 | 39 |
| l3_decision_flip_error | 0.9555 | 0.6973 | 62 | 38 |
| l3_noise_contamination | 0.9491 | 0.7909 | 98 | 80 |
| l3_implicit_rejection_miss | 0.9507 | 0.7752 | 91 | 66 |

Agreement is high for contradiction and the L3-specific penalty flags, while hallucination is visibly less stable than the other binary penalties under judge substitution.

## 8. RAG Baseline Details and Failure Analysis

This section supplements the brief RAG description in the main paper. The reported RAG results come from a lightweight adaptive Meeting-RAG baseline rather than a heavily tuned retrieval system.

### 8.1 Implementation Details

The baseline uses overlapping utterance-window chunks rather than semantic segments or oracle evidence spans. Each chunk contains 10 utterances with a stride of 5, and retrieval is based on lexical overlap between the question and chunk text, with `top_k = 6` in the first round. Under the adaptive routing policy, `L2` and `L3` default to multi-round retrieval, while `L1` switches to multi-round only for questions with markers such as “最终”, “决定”, or “结论”. In the second round, the model first generates a follow-up query from the initial answer hypothesis and then retrieves additional chunks with `top_k = 3`. The generation side uses a constrained JSON output containing `final_answer`, `predicted_evidence_ids`, and `used_chunk_ids`, with `temperature = 0.1`, `max_retries = 3`, and `request_timeout = 180`.

This implementation is intentionally lightweight. It does not include dense retrieval, BM25-hybrid retrieval, reranking, speaker-aware retrieval scoring, event-boundary segmentation, or oracle-evidence retrieval. Accordingly, the negative RAG result in the main paper should be interpreted as a result about this specific lightweight baseline rather than as a general claim about all retrieval-augmented approaches.

### 8.2 Main Quantitative Result

Table A6 compares the three Qwen small models with and without the lightweight RAG pipeline. Scores are level-wise total scores under the same evaluation framework as the main paper.

| Model | L1 w/o RAG | L1 +RAG | Delta | L2 w/o RAG | L2 +RAG | Delta | L3 w/o RAG | L3 +RAG | Delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5-4B | 72.65 | 30.91 | -41.74 | 71.00 | 56.80 | -14.20 | 48.68 | 24.13 | -24.55 |
| Qwen3.5-9B | 74.23 | 31.46 | -42.77 | 73.21 | 55.97 | -17.24 | 55.76 | 25.19 | -30.57 |
| Qwen3.5-27B | 79.59 | 33.17 | -46.42 | 80.63 | 62.01 | -18.62 | 57.04 | 35.37 | -21.67 |

The degradation is consistent across all three models and all three levels, with the largest drops on `L1` and `L3`. This pattern aligns with the main paper’s qualitative claim that naive retrieval is particularly mismatched to local precision and final-state reasoning in meetings.

### 8.3 Error Profile Under RAG

The RAG runs also increase failure rates on contradiction and L3-specific penalties. Table A7 reports the main error statistics for the three RAG models.

| Model | Contradiction Rate | Hallucination Rate | L3 Decision Flip | L3 Noise Contamination | L3 Implicit Rejection Miss |
|---|---:|---:|---:|---:|---:|
| Qwen3.5-4B +RAG | 0.348 | 0.217 | 0.468 | 0.711 | 0.682 |
| Qwen3.5-9B +RAG | 0.382 | 0.204 | 0.433 | 0.657 | 0.677 |
| Qwen3.5-27B +RAG | 0.385 | 0.166 | 0.353 | 0.552 | 0.572 |

For comparison, the non-RAG versions are substantially lower on the same error families:

- Qwen3.5-4B:
  contradiction `0.104`, decision-flip `0.313`, noise contamination `0.488`, implicit-rejection miss `0.463`
- Qwen3.5-9B:
  contradiction `0.095`, decision-flip `0.224`, noise contamination `0.408`, implicit-rejection miss `0.383`
- Qwen3.5-27B:
  contradiction `0.082`, decision-flip `0.239`, noise contamination `0.393`, implicit-rejection miss `0.398`

### 8.4 Failure Analysis

The observed failure pattern is consistent with the discussion in the main paper and mainly reflects a mismatch between this lightweight retrieval design and the structure of meeting transcripts: a fixed sliding-window retriever is often too coarse for `L1`, does not reliably recover missing cross-turn evidence for `L2`, and is especially vulnerable on `L3`, where correct answering depends on tracking final decisions across long discussion trajectories rather than retrieving locally similar process fragments. Correspondingly, the RAG runs show higher contradiction, decision-flip, noise-contamination, and implicit-rejection-miss rates, reinforcing the paper’s conclusion that meeting understanding requires more carefully designed retrieval strategies for turn structure, evidence chaining, and decision dynamics.
