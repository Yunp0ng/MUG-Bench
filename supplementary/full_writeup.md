# Supplementary Material for EMUG-Bench

This document is intended to accompany the submission of **EMUG-Bench: An Evidence-aware Benchmark for Real-World Chinese Meeting Understanding**. Since the main paper has already been frozen, the goal of this supplement is to provide implementation details, release details, and additional analyses that directly address reviewer concerns.

This supplement covers the following five parts:

1. Full Prompt and Output Protocol
2. Evaluation Framework Details and Sensitivity Analysis
3. Annotation / Audit / Cleanup Protocol
4. Release / Access / Ethics Statement
5. L3 Subtype-wise Results

The companion bilingual prompt file is mirrored in:

- [Prompt_Reference_Bilingual.md](Prompt_Reference_Bilingual.md)

Supporting tables generated from the current benchmark and evaluation outputs are stored in:

- [artifacts](artifacts)

## A. Full Prompt and Output Protocol

### A.1 Prompt release policy

The public GitHub repository releases the **concrete operational prompts** used in the benchmark pipeline. These prompts are not illustrative prompt examples; they are the actual prompt templates used by the released scripts, with runtime placeholders such as `{context}`, `{question}`, and `{evidence_text}` filled programmatically.

The public repository prompt file is bilingual:

- Chinese: exact operational prompt text used by the released scripts
- English: faithful translation for supplementary-material and reproducibility use

The mirrored version used for this supplement is:

- [Prompt_Reference_Bilingual.md](Prompt_Reference_Bilingual.md)

### A.2 Prompt coverage

The released prompt file includes concrete prompt templates for:

- L1 evidence mining
- L2 evidence mining
- L3 evidence mining
- L1/L2 QA generation
- L3 QA generation
- audit
- cleanup rewrite
- evaluation judge

### A.3 Output protocol by stage

#### Evidence mining

L1/L2 return evidence groups in the following format:

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

L3 additionally returns a pattern label:

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

After post-processing, valid utterance IDs are checked against the source transcript and `original_text` is attached for manual inspection.

#### QA generation

The generator returns:

```json
{
  "question": "string",
  "answer": "string"
}
```

During benchmark packaging, `answer` is stored as `gold_answer`, and the final sample record also keeps:

- `query_id`
- `topic`
- `pattern`
- `evidence_ids`
- `reasoning_from_mining` (internal pipeline field)

#### Audit

The audit stage returns one structured decision per sample:

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

In the paper text, `upgrade` and `downgrade` are abstracted as `relabel`.

#### Cleanup / rewrite

The cleanup rewrite stage returns:

```json
{
  "question": "string",
  "gold_answer": "string",
  "reasoning_from_mining": "string"
}
```

`evidence_ids` are never rewritten during cleanup.

#### Evaluation protocol

The released evaluation script uses a level-specific judge schema. At a high level, the judge output contains:

- answer scores
- evidence scores
- level-specific reasoning scores
- penalty flags
- Chinese rationale

The per-sample exported evaluation file includes:

- `score_total`
- `score_answer`
- `score_evidence`
- `score_level_skill`
- `score_penalty`
- all 0-5 rubric sub-scores
- citation precision / recall / F1
- contradiction / hallucination / L3 error flags

The public repository currently releases the derived supplementary tables rather than the full internal per-sample evaluation export.

### A.4 Evidence citation protocol

The benchmark assumes evidence is cited at the utterance-ID level. Public evaluation therefore expects models to provide evidence IDs that can be mapped back to transcript utterances.

The released scoring pipeline follows these rules:

- gold evidence is stored as benchmark `evidence_ids`
- predicted evidence is parsed from model outputs as utterance IDs
- citation quality contributes to `citation_f1` and `citation_precision`
- if a model does not cite valid IDs, the evidence sub-score is penalized through low citation overlap and weak support sufficiency

This directly addresses the reviewer concern that citation handling should be specified explicitly.

## B. Evaluation Framework Details and Sensitivity Analysis

### B.1 Default evaluation framework

The paper uses the following top-level scoring formula:

\[
\mathrm{Score}=100\cdot(\alpha A+\beta E+\gamma L)-\mathcal{P},
\]

with the default setting:

- `alpha = 0.30`
- `beta = 0.40`
- `gamma = 0.30`

Within-dimension weights:

- `A = 0.6 * A_core + 0.4 * A_completeness`
- `E = 0.45 * E_sufficiency + 0.25 * E_specificity + 0.20 * citation_f1 + 0.10 * citation_precision`
- `L1 = 0.5 * slot_accuracy + 0.5 * localization`
- `L2 = 0.5 * multi_hop_coverage + 0.5 * synthesis_consistency`
- `L3 = 0.6 * main_subtype_skill + 0.2 * aux1 + 0.2 * aux2`

Penalty terms:

- contradiction: `10`
- hallucination: `10`
- L3 dominant error: `12`
- L3 auxiliary subtype error: `3`
- penalty cap: `30`

### B.2 Sensitivity design

To test whether conclusions depend heavily on one specific parameter choice, we recomputed overall scores from the released per-sample judge outputs under six alternative settings while keeping the per-dimension sub-score definitions unchanged.

Tested settings:

- `default_grounding_heavy`: `A/E/L = 0.30 / 0.40 / 0.30`, penalty scale `1.0`
- `balanced`: `0.333 / 0.333 / 0.333`, penalty scale `1.0`
- `answer_heavy`: `0.40 / 0.30 / 0.30`, penalty scale `1.0`
- `reasoning_heavy`: `0.30 / 0.30 / 0.40`, penalty scale `1.0`
- `low_penalty`: default weights, penalty scale `0.5`
- `high_penalty`: default weights, penalty scale `1.5`

The generated ranking summary is stored in:

- [eval_sensitivity_rankings.csv](artifacts/eval_sensitivity_rankings.csv)

Full score tables are stored in:

- [eval_sensitivity_overall.csv](artifacts/eval_sensitivity_overall.csv)
- [eval_sensitivity_levelwise.csv](artifacts/eval_sensitivity_levelwise.csv)

### B.3 Sensitivity results

The model ranking over the seven frontier models remains unchanged under all six settings:

| Configuration | Ranking | Spearman vs. Default |
|---|---|---:|
| default_grounding_heavy | gemini-3-pro-preview > glm-5 > qwen3.5-397b-a17b > gpt-5 > qwen-plus > claude-opus-4-6 > deepseek-v3.2 | 1.0 |
| balanced | gemini-3-pro-preview > glm-5 > qwen3.5-397b-a17b > gpt-5 > qwen-plus > claude-opus-4-6 > deepseek-v3.2 | 1.0 |
| answer_heavy | gemini-3-pro-preview > glm-5 > qwen3.5-397b-a17b > gpt-5 > qwen-plus > claude-opus-4-6 > deepseek-v3.2 | 1.0 |
| reasoning_heavy | gemini-3-pro-preview > glm-5 > qwen3.5-397b-a17b > gpt-5 > qwen-plus > claude-opus-4-6 > deepseek-v3.2 | 1.0 |
| low_penalty | gemini-3-pro-preview > glm-5 > qwen3.5-397b-a17b > gpt-5 > qwen-plus > claude-opus-4-6 > deepseek-v3.2 | 1.0 |
| high_penalty | gemini-3-pro-preview > glm-5 > qwen3.5-397b-a17b > gpt-5 > qwen-plus > claude-opus-4-6 > deepseek-v3.2 | 1.0 |

This analysis supports the claim that the headline model ranking in the main paper is not an artifact of one narrow coefficient choice.

### B.4 Stability of qualitative conclusions

We additionally checked whether the main qualitative findings remain stable under the same six settings.

Observed stability:

- `L3` remains the lowest-scoring level for every frontier model under all six settings.
- the top group remains stable (`Gemini-3-Pro`, `GLM-5`, `Qwen3.5-397B-A17B`)
- higher penalty strength lowers absolute scores, but does not change the ranking or the conclusion that L3 is the most challenging level

Interpretation:

- the current weighting scheme is not uniquely responsible for the paper’s main conclusions
- the claims “grounding matters,” “L3 is hardest,” and “strong models remain separated mainly at L3” are stable under reasonable perturbations

## C. Annotation / Audit / Cleanup Protocol

### C.1 End-to-end construction protocol

The benchmark construction pipeline consists of four stages:

1. multi-level evidence mining
2. QA generation
3. audit
4. cleanup and post-audit

All model-assisted stages are implemented with GPT-5, but all final QA instances and evidence annotations are manually checked before inclusion in the release benchmark.

### C.2 Level-specific annotation principles

#### L1

- answer should be directly recoverable from one utterance or a short contiguous span
- no cross-turn aggregation
- no dynamic decision-state reasoning

#### L2

- answer requires cross-turn aggregation
- supporting evidence is distributed across non-adjacent utterances
- later evidence complements earlier evidence rather than reversing it

#### L3

- answering requires dynamic state tracking or pragmatic reasoning
- includes:
  - decision reversal
  - procedural noise filtering
  - implicit rejection

### C.3 Audit protocol

The audit stage evaluates:

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

For paper presentation, `upgrade` and `downgrade` are merged into `relabel`.

### C.4 Cleanup protocol

Cleanup applies audit decisions as follows:

- `keep`: keep the sample unchanged
- `relabel`: move the sample to a more appropriate level
- `rewrite`: rewrite `question`, `gold_answer`, and `reasoning_from_mining`
- `drop`: remove the sample

For rewritten cases:

- `evidence_ids` stay fixed
- the rewritten sample is post-audited before final retention

### C.5 Audit and cleanup statistics

The aggregated cleanup summary used in this supplement is stored in:

- [audit_cleanup_summary.json](artifacts/audit_cleanup_summary.json)

Across all four cleaned benchmark partitions:

- candidate instances: `1729`
- `keep`: `1042` (`60.27%`)
- `relabel`: `511` (`29.55%`)
  - `downgrade`: `506`
  - `upgrade`: `5`
- `rewrite`: `175` (`10.12%`)
- `drop`: `1` (`0.06%`)

Final cleanup outcomes:

- retained: `1708` (`98.79%`)
- removed: `21` (`1.21%`)

Retained samples consist of:

- `kept`: `1042`
- `moved`: `511`
- `rewritten and passed post-audit`: `155`

Removed samples consist of:

- direct `drop`: `1`
- `post_audit_failed`: `20`

These statistics show that the cleanup pipeline is conservative: most imperfect samples are repaired through relabeling or rewrite rather than being removed outright.

## D. Release / Access / Ethics Statement

### D.1 Public release

The public GitHub repository provides a controlled public release designed for inspection, reproducibility, and lightweight benchmarking:

- sample benchmark data
- aligned transcript subset
- data construction scripts
- evaluation scripts
- bilingual prompt documentation

Public repository:

- [EMUG-Bench GitHub](https://github.com/Yunp0ng/EMUG-Bench.git)

### D.2 Full release

The full benchmark release has been normalized into the same schema as the public sample subset and packaged as a controlled full-release package for off-platform distribution.

This package contains:

- full `L1/L2/L3` benchmark files in the public sample format
- aligned `real_meeting` transcripts
- aligned `vcsum` transcripts
- release statistics in `release_summary.json`

The intended distribution path for the full release is controlled sharing via Google Drive rather than unrestricted GitHub hosting.

### D.3 Access policy

The current release policy is:

- GitHub: public sample release, scripts, prompt documentation, scoring code
- Full dataset: available upon request for academic/research use
- Contact email: `Yunpeng.Li21@student.xjtlu.edu.cn`

The public README and repository state this explicitly.

### D.4 Privacy and ethics

The real-meeting portion is privacy-sensitive. For that reason:

- all real meeting transcripts are de-identified before release
- personal names and organization identifiers are replaced or removed
- public GitHub hosting is restricted to the sample release only
- full-access release is controlled rather than fully open

The public release intentionally omits internal metadata that is not necessary for benchmark use.

## E. L3 Subtype-wise Results

### E.1 Dataset distribution

The full L3 benchmark contains the following subtype distribution:

- decision reversal (`A`): `52`
- procedural noise (`B`): `15`
- implicit rejection (`C`): `133`
- uncategorized / legacy pattern field (`N/A`): `1`

Distribution file:

- [l3_subtype_distribution.json](artifacts/l3_subtype_distribution.json)

Because subtype `B` is relatively small, subtype-wise conclusions should be interpreted with that sample imbalance in mind.

### E.2 Model-wise subtype performance

Full model-wise subtype results are stored in:

- [l3_subtype_results.csv](artifacts/l3_subtype_results.csv)

Mean L3 total scores by subtype:

| Model | A | B | C |
|---|---:|---:|---:|
| claude-opus-4-6 | 59.7332 | 60.2328 | 58.4537 |
| deepseek-v3.2 | 53.5304 | 69.4295 | 50.3658 |
| gemini-3-pro-preview | 57.9046 | 82.3018 | 61.8938 |
| glm-5 | 57.6238 | 71.4122 | 61.8941 |
| gpt-5 | 62.5118 | 82.3722 | 68.8856 |
| qwen-plus | 51.6777 | 68.6753 | 54.4155 |
| qwen3.5-397b-a17b | 54.2976 | 83.8189 | 62.3952 |
| qwen3.5-27b | 56.3839 | 70.9210 | 55.9727 |
| qwen3.5-9b | 53.3929 | 71.3656 | 55.1060 |
| qwen3.5-4b | 41.5613 | 64.8217 | 49.8070 |

### E.3 Interpretation

Three patterns are worth noting:

- subtype `C` (implicit rejection) is the largest and also consistently challenging across models
- subtype `A` (decision reversal) remains difficult, especially for smaller models
- subtype `B` (procedural noise) appears easier for stronger models, but this result should be interpreted cautiously because the subtype contains only `15` samples

For example:

- `GPT-5` achieves the strongest score on subtype `C` (`68.8856`)
- `Qwen3.5-397B-A17B` is strongest on subtype `B` (`83.8189`)
- `Qwen3.5-4B` shows the largest weakness on subtype `A` (`41.5613`)

These subtype-wise results support the reviewer suggestion that L3 should be decomposed further rather than treated as a single undifferentiated level.

## F. Files added for this supplement

This supplement is supported by the following repository files:

- [README.md](README.md)
- [Prompt_Reference_Bilingual.md](Prompt_Reference_Bilingual.md)
- [eval_sensitivity_overall.csv](artifacts/eval_sensitivity_overall.csv)
- [eval_sensitivity_levelwise.csv](artifacts/eval_sensitivity_levelwise.csv)
- [eval_sensitivity_rankings.csv](artifacts/eval_sensitivity_rankings.csv)
- [l3_subtype_results.csv](artifacts/l3_subtype_results.csv)
- [l3_subtype_distribution.json](artifacts/l3_subtype_distribution.json)
- [audit_cleanup_summary.json](artifacts/audit_cleanup_summary.json)
