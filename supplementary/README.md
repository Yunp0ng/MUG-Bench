# Supplementary Material for EMUG-Bench

This folder contains supplementary materials for the paper submission of **EMUG-Bench: An Evidence-aware Benchmark for Real-World Chinese Meeting Understanding**.

The current supplement focuses on five parts:

1. Full Prompt and Output Protocol
2. Evaluation Framework Details and Sensitivity Analysis
3. Annotation / Audit / Cleanup Protocol
4. Release / Access / Ethics Statement
5. L3 Subtype-wise Results

## Files

### Main Supplement

- [full_writeup.md](full_writeup.md)
- [Prompt_Reference_Bilingual.md](Prompt_Reference_Bilingual.md)

These files provide:

- a structured supplementary write-up
- a bilingual prompt reference mirror

The prompt reference covers:

- evidence mining prompts
- QA generation prompts
- audit prompts
- cleanup prompts
- evaluation prompts

### Evaluation Sensitivity

- [eval_sensitivity_overall.csv](artifacts/eval_sensitivity_overall.csv)
- [eval_sensitivity_levelwise.csv](artifacts/eval_sensitivity_levelwise.csv)
- [eval_sensitivity_rankings.csv](artifacts/eval_sensitivity_rankings.csv)

These files report recomputed model scores under multiple coefficient and penalty settings. The main takeaway is that the frontier-model ranking is unchanged across the tested settings.

### Audit / Cleanup Statistics

- [audit_cleanup_summary.json](artifacts/audit_cleanup_summary.json)

This file summarizes the final audit and cleanup outcomes:

- `1729` candidate instances
- `1042` keep
- `511` relabel (`506` downgrade + `5` upgrade)
- `175` rewrite
- `1` drop
- `1708` retained after cleanup
- `21` removed

### L3 Subtype Analysis

- [l3_subtype_distribution.json](artifacts/l3_subtype_distribution.json)
- [l3_subtype_results.csv](artifacts/l3_subtype_results.csv)

These files provide:

- subtype distribution for L3 (`A/B/C`)
- subtype-wise model performance

## Notes

- The public repository releases a sampled benchmark subset, scripts, prompt documentation, and supplementary analysis artifacts.
- The full dataset is not hosted in this repository.
- For full benchmark access, please contact `Yunpeng.Li21@student.xjtlu.edu.cn`.
