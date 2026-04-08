# EMUG-Bench

EMUG-Bench is an evidence-aware benchmark for Chinese meeting understanding.

This public repository is a lightweight release for external users. It does **not** contain the full benchmark. The public version only includes a curated VCSum-based subset with:

- `50` samples for `L1`
- `50` samples for `L2`
- `50` samples for `L3`
- corresponding VCSum transcripts for the selected samples
- data construction scripts
- evaluation scripts
- prompt documentation

The project name used in this repository is **EMUG-Bench**.

## Overview

EMUG-Bench evaluates whether a model can:

- answer questions over meeting transcripts,
- ground its answer in supporting evidence,
- handle progressively harder meeting-understanding skills.

The benchmark is organized into three levels:

- `L1`: explicit local retrieval
- `L2`: cross-turn information aggregation
- `L3`: higher-level meeting understanding with decision reversal, procedural noise, and implicit rejection

## Public Release Scope

This GitHub repository only provides a **sampled release subset** for public inspection and lightweight experimentation.

- All released QA samples in this repository are from **VCSum**.
- Each level contains **50 manually selected samples**.
- The selection prioritizes coverage across meetings and removes samples with obviously vague or visibly problematic question wording.
- The corresponding transcripts are included under `data/transcripts/vcsum/`.
- The previously uploaded full benchmark folders are not part of the public release anymore.

## Full Access

The full benchmark is **not** publicly distributed in this repository.

If you need full access, please email:

`Yunpeng.Li21@student.xjtlu.edu.cn`

and request permission for the full EMUG-Bench release.

## Repository Structure

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

## Data Files

### Benchmark Files

The public QA subset is stored in:

- [L1.json](data/benchmark/L1.json)
- [L2.json](data/benchmark/L2.json)
- [L3.json](data/benchmark/L3.json)

Each file contains a flat sample list for one benchmark level.

### Transcript Files

The transcript files used by the public subset are stored in:

- [data/transcripts/vcsum](data/transcripts/vcsum)

Each sample in the benchmark points to a transcript through `source_file` and `transcript_path`.

## JSON Format

### Benchmark JSON

Each level file follows this structure:

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

### Benchmark Field Description

- `dataset`: dataset name
- `subset`: release type of the current file
- `level`: benchmark level (`L1`, `L2`, `L3`)
- `sample_count`: number of samples in the file
- `sample_id`: public sample identifier in this release
- `source_file`: transcript filename aligned to the sample
- `query_id`: original query identifier from the cleaned benchmark pipeline
- `topic`: topic tag carried from evidence mining / QA construction
- `pattern`: normalized reasoning pattern
  - `L1` / `L2`: always `N/A`
  - `L3`: `A`, `B`, or `C`
- `question`: benchmark question
- `gold_answer`: manually cleaned reference answer
- `evidence_ids`: transcript utterance IDs supporting the answer
- `transcript_path`: relative path to the aligned transcript file

### Transcript JSON

Each transcript file is stored in a unified VCSum-style JSON format:

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

### Transcript Field Description

- `dataset`: dataset family name
- `source_dataset`: original source dataset name
- `vcsum_id`: original VCSum instance identifier
- `av_num`: VCSum meeting ID
- `split`: original split (`train`, `dev`, `test`)
- `speakers`: speaker list
- `utterances`: ordered meeting utterances
- `utterances[].id`: utterance ID used by `evidence_ids`
- `utterances[].speaker_id`: speaker index
- `utterances[].text`: utterance content

## Scripts

### Data Construction Scripts

The main construction scripts are under [scripts/data_construction](scripts/data_construction):

- `L1_evidence.py`
- `L2_evidence.py`
- `L3_evidence.py`
- `qa_gen.py`
- `benchmark_audit.py`
- `benchmark_cleanup.py`
- `merge_benchmarks.py`
- `run_benchmark_pipeline.sh`

These public copies are cleaned for release:

- hard-coded API keys have been removed
- API access is controlled through environment variables
- paths are adjusted for repository-local execution

### Evaluation Script

The evaluation script is under [scripts/evaluation/acmmm_eval.py](scripts/evaluation/acmmm_eval.py).

It implements an ACMMM-style rubric with separate scoring logic for `L1`, `L2`, and `L3`.

## Prompt Documentation

Prompt documentation is provided in:

- [prompt_reference.md](docs/prompt_reference.md)

This file contains **concrete Chinese prompts and English translations** for:

- concrete evidence mining prompt templates
- concrete QA generation prompt templates
- concrete audit prompts
- concrete cleanup prompts
- concrete evaluation prompts

## Supplementary Materials

This section provides the supplementary material for the EMUG-Bench paper, including prompt/output protocol, evaluation sensitivity, annotation and cleanup statistics, release/access policy, L3 subtype analysis, and cross-judge robustness.

### 1. Full Prompt and Output Protocol

The public repository releases the concrete prompt templates used in the benchmark pipeline. These are operational prompts rather than illustrative examples, and they are documented in bilingual form in [docs/prompt_reference.md](docs/prompt_reference.md).

Released prompt stages:

- L1 evidence mining
- L2 evidence mining
- L3 evidence mining
- L1/L2 QA generation
- L3 QA generation
- audit
- cleanup rewrite
- evaluation judge

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

The evaluation pipeline scores answer quality, evidence grounding, level-specific skill, penalties, and citation overlap from utterance-ID evidence references.

### 2. Evaluation Framework Details and Sensitivity Analysis

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

To test whether the main conclusions depend on a narrow coefficient choice, we recomputed the overall scores of the seven frontier models under six alternative settings.

| Setting | A | E | L | Penalty Scale |
|---|---:|---:|---:|---:|
| Default grounding-heavy | 0.30 | 0.40 | 0.30 | 1.0 |
| Balanced | 0.333 | 0.333 | 0.333 | 1.0 |
| Answer-heavy | 0.40 | 0.30 | 0.30 | 1.0 |
| Reasoning-heavy | 0.30 | 0.30 | 0.40 | 1.0 |
| Low-penalty | 0.30 | 0.40 | 0.30 | 0.5 |
| High-penalty | 0.30 | 0.40 | 0.30 | 1.5 |

| Model | Default | Balanced | Answer-heavy | Reasoning-heavy | Low-penalty | High-penalty |
|---|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 82.64 | 83.05 | 83.21 | 83.30 | 83.44 | 82.04 |
| GLM-5 | 78.94 | 79.58 | 79.90 | 79.91 | 80.09 | 77.99 |
| Qwen3.5-397B | 78.68 | 79.29 | 79.58 | 79.62 | 79.86 | 77.68 |
| GPT-5 | 74.62 | 75.20 | 75.52 | 75.47 | 75.87 | 73.57 |
| Qwen-Plus | 74.05 | 74.67 | 75.00 | 74.97 | 75.54 | 72.86 |
| Claude-Opus-4.6 | 73.78 | 74.52 | 74.91 | 74.88 | 75.44 | 72.37 |
| DeepSeek-V3.2 | 72.27 | 72.85 | 73.14 | 73.16 | 73.73 | 71.10 |

| Setting | Ranking | Spearman vs. Default |
|---|---|---:|
| Default grounding-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Balanced | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Answer-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Reasoning-heavy | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| Low-penalty | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |
| High-penalty | Gemini-3-Pro > GLM-5 > Qwen3.5-397B > GPT-5 > Qwen-Plus > Claude-Opus-4.6 > DeepSeek-V3.2 | 1.0 |

Across all six settings, `L3` remains the hardest level for every frontier model and the frontier-model ordering remains unchanged.

### 3. Annotation / Audit / Cleanup Protocol

The construction pipeline has four stages:

1. multi-level evidence mining
2. QA generation
3. audit
4. cleanup and post-audit

All model-assisted stages use GPT-5, while all final retained QA instances and evidence annotations are manually checked before inclusion in the released benchmark.

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

### 4. Release / Access / Ethics Statement

The public GitHub repository provides:

- a sampled public benchmark subset
- aligned transcript subset
- data construction scripts
- evaluation scripts
- bilingual prompt documentation

The full benchmark is packaged in the same normalized schema as the public release, but is not hosted on GitHub. Full access is controlled and intended for academic or research use.

Contact:

- `Yunpeng.Li21@student.xjtlu.edu.cn`

Privacy safeguards:

- all real-meeting transcripts are de-identified before release
- personal and organization identifiers are replaced or removed
- public GitHub hosting is restricted to the sample release
- full release is distributed under controlled access rather than unrestricted hosting

### 5. L3 Subtype-wise Results

The full L3 benchmark contains:

| Subtype | Meaning | Count |
|---|---|---:|
| A | Decision reversal | 52 |
| B | Procedural noise | 15 |
| C | Implicit rejection | 133 |
| N/A | Legacy uncategorized pattern | 1 |

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

Subtype `C` is the largest and remains challenging across models. Subtype `B` is smaller and should be interpreted more cautiously.

### 6. Cross-Judge Robustness

We constructed a stratified robustness subset of `90` benchmark questions:

- `30` from `L1`
- `30` from `L2`
- `30` from `L3`

For `L3`, the subset covers subtype `A = 9`, `B = 6`, and `C = 15`.

This subset was re-scored with `gemini-3-pro-preview` as an alternative judge, while the main paper results use `GPT-5` as the judge. This is a cross-judge robustness analysis rather than a human-correlation analysis.

The theoretical maximum size is `630` scored items (`90` samples × `7` frontier models). The matched comparison size is `629`, because one `Claude-Opus-4.6` response on an `L3` sample was invalid and excluded by the evaluation pipeline.

| Metric | Value |
|---|---:|
| Pearson correlation on total score | 0.8588 |
| Spearman correlation on total score | 0.8460 |

| Level | Count | GPT-5 Mean | Gemini Mean | Pearson | Spearman |
|---|---:|---:|---:|---:|---:|
| L1 | 210 | 68.97 | 79.50 | 0.8248 | 0.8814 |
| L2 | 210 | 63.56 | 70.30 | 0.8626 | 0.7927 |
| L3 | 209 | 48.38 | 58.63 | 0.8609 | 0.8591 |

#### L1 Mean Scores by Judge

| Model | GPT-5 A | GPT-5 E | GPT-5 L | GPT-5 Overall | Gemini A | Gemini E | Gemini L | Gemini Overall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 24.48 | 31.06 | 25.30 | 79.17 | 26.96 | 32.21 | 26.90 | 85.73 |
| GLM-5 | 22.84 | 26.49 | 23.50 | 69.16 | 26.68 | 30.58 | 27.00 | 83.26 |
| Qwen3.5-397B | 23.84 | 27.53 | 23.60 | 71.64 | 26.68 | 30.51 | 26.20 | 83.05 |
| GPT-5 | 19.76 | 22.05 | 19.30 | 57.63 | 20.60 | 24.35 | 21.00 | 64.31 |
| Qwen-Plus | 22.08 | 26.34 | 22.70 | 67.13 | 24.16 | 29.04 | 24.20 | 75.40 |
| Claude-Opus-4.6 | 23.52 | 27.16 | 23.30 | 71.01 | 27.12 | 30.35 | 27.30 | 83.53 |
| DeepSeek-V3.2 | 21.04 | 26.18 | 22.50 | 67.05 | 25.48 | 30.07 | 26.00 | 81.22 |

#### L2 Mean Scores by Judge

| Model | GPT-5 A | GPT-5 E | GPT-5 L | GPT-5 Overall | Gemini A | Gemini E | Gemini L | Gemini Overall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 22.68 | 29.85 | 22.90 | 73.80 | 23.96 | 31.02 | 23.30 | 77.71 |
| GLM-5 | 22.60 | 28.29 | 23.00 | 70.89 | 24.08 | 29.61 | 24.00 | 76.78 |
| Qwen3.5-397B | 21.88 | 27.69 | 22.30 | 69.20 | 23.32 | 29.19 | 23.40 | 74.96 |
| GPT-5 | 17.52 | 23.48 | 17.60 | 54.47 | 17.88 | 23.64 | 17.90 | 57.09 |
| Qwen-Plus | 18.32 | 23.31 | 18.70 | 55.70 | 19.52 | 26.07 | 19.70 | 62.19 |
| Claude-Opus-4.6 | 19.96 | 23.98 | 21.40 | 59.97 | 23.12 | 28.18 | 23.80 | 73.59 |
| DeepSeek-V3.2 | 19.32 | 24.89 | 19.70 | 60.88 | 21.64 | 27.20 | 21.90 | 69.74 |

#### L3 Mean Scores by Judge

| Model | GPT-5 A | GPT-5 E | GPT-5 L | GPT-5 Overall | Gemini A | Gemini E | Gemini L | Gemini Overall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemini-3-Pro | 16.56 | 24.03 | 14.56 | 46.37 | 18.64 | 26.15 | 17.96 | 56.88 |
| GLM-5 | 19.04 | 25.07 | 16.64 | 50.16 | 20.60 | 24.66 | 18.64 | 58.23 |
| Qwen3.5-397B | 18.48 | 25.65 | 17.04 | 53.62 | 20.80 | 26.89 | 20.76 | 63.96 |
| GPT-5 | 19.56 | 26.82 | 18.36 | 56.84 | 22.08 | 27.30 | 21.84 | 67.58 |
| Qwen-Plus | 15.64 | 22.21 | 13.96 | 40.39 | 17.72 | 24.02 | 17.52 | 54.07 |
| Claude-Opus-4.6 | 18.70 | 24.39 | 16.76 | 49.32 | 20.81 | 25.55 | 19.20 | 59.40 |
| DeepSeek-V3.2 | 16.24 | 21.04 | 14.24 | 42.00 | 17.52 | 22.42 | 16.92 | 50.33 |

| Judge | Ranking |
|---|---|
| GPT-5 judge | Gemini-3-Pro > Qwen3.5-397B > GLM-5 > Claude-Opus-4.6 > DeepSeek-V3.2 > GPT-5 > Qwen-Plus |
| Gemini judge | Qwen3.5-397B > Gemini-3-Pro > GLM-5 > Claude-Opus-4.6 > DeepSeek-V3.2 > Qwen-Plus > GPT-5 |

| Metric | Value |
|---|---:|
| Spearman rank correlation | 0.9286 |

Under both judges, `GPT-5` remains the strongest `L3` model on this robustness subset (`56.84` under GPT-5 judge and `67.58` under Gemini judge). This indicates that the relatively strong `L3` performance of `GPT-5` is not an artifact of using GPT-5 as the judge.

## Installation

```bash
pip install -r requirements.txt
```

## Example Usage

### Read the Public Benchmark

```python
import json

with open("data/benchmark/L3.json", "r", encoding="utf-8") as f:
    benchmark = json.load(f)

sample = benchmark["samples"][0]
print(sample["question"])
print(sample["evidence_ids"])
```

### Run a Data Construction Script

```bash
export ACMMM_JUDGE_API_KEY=your_api_key
python scripts/data_construction/L1_evidence.py
```

### Run the Evaluation Script

```bash
python scripts/evaluation/acmmm_eval.py --help
```

## Notes

- This repository is designed to be readable and usable by external researchers.
- The public release is intentionally smaller than the full internal benchmark.
- The sampled public subset is meant for demonstration, lightweight evaluation, and repository transparency.
- Full benchmark access requires explicit permission by email.
