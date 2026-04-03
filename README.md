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
│   ├── evaluation/
│   └── release/
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
  - `L1` / `L2`: usually `N/A`
  - `L3`: commonly `A`, `B`, or `C`
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

### Release Script

The public subset in this repository is generated by:

- [build_release_subset.py](scripts/release/build_release_subset.py)

This script creates the 50-per-level public release from a cleaned benchmark root and a VCSum transcript root provided by the user.

## Prompt Documentation

Prompt documentation is provided in:

- [prompt_reference.md](docs/prompt_reference.md)

This file contains **Chinese and English descriptions** for:

- evidence mining prompts
- QA generation prompts
- audit prompts
- cleanup prompts
- evaluation prompt/rubric roles

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
