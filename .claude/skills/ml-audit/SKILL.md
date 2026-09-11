---
name: ml-audit
description: >-
  Audit a training / ranking / multimodal / continuous-learning experiment in this repo for
  leakage, split correctness, candidate-recall ceiling, train/serve parity, evaluation
  methodology, baseline comparability, artifact provenance, and whether a claimed improvement
  is genuinely supported. Use before trusting an experiment or metric.
---

# ML Audit

Work read-only. Use existing scripts/tests; do not modify datasets, models, or reports.

Check, in order:

1. **Data leakage** — target-derived or future-information features in
   `training_pipeline/feature_engineering.py`, `feature_extractor.py`, `multimodal/*`.
2. **Split / group correctness** — are splits group-aware so the same drawing / component /
   label family cannot span train and eval? (`phase2_build_group_folds.py`,
   `test_groupcv_and_candidate_gen`, `test_evaluate_pipeline_holdout`.)
3. **Candidate-recall ceiling** — can the candidate generator even contain the right answer?
   Audit before blaming the ranker (`scripts/audit_candidate_recall_v16.py`).
4. **Train/serve feature parity** — the function computing each feature for training must be the
   one `prediction/orchestrator.py` uses at serve time (`test_ranker_feature_consistency`,
   `test_feature_schema_order`).
5. **Feature skew** — distribution differences between training rows and live extraction rows.
6. **Corruption / evaluation methodology** — is the synthetic corruption
   (`generate_label_corruption_dataset*.py`) representative; are metrics computed the same way
   as the baseline (`scripts/evaluate_*`, `docs/TRAINING.md`).
7. **Frozen evaluation** — did the reported holdout influence model or hyperparameter
   selection? (`analyze_frozen_test_rows.py`, `diagnose_val_test_gap.py`,
   `phase1_feature_freeze.py`.)
8. **Baseline comparability** — same holdout, same metric definitions, same candidate set as
   the baseline being beaten.
9. **Model artifact provenance** — which dataset version / config / commit produced the
   artifact in `backend/training/models/**`; is it recorded in the registry
   (`training_pipeline/model_registry.py`, `dataset_registry.py`).
10. **Promotion gate** — was promotion gated by configured tolerances and minimum sample
    counts, not "training completed"?
11. **Self-learning safety** — continuous-learning changes stay auditable, provenance-tagged,
    and cannot silently overwrite approved corrections (`self_learning_engine.py`,
    `training_pipeline/continuous_learning.py`).
12. **Reproducibility** — fixed seeds, recorded config, deterministic preprocessing.
13. **Is the gain real** — effect size vs. noise / run-to-run variance
    (`scripts/paired_compare_rankers.py`, `phase14_final_consolidated_eval.py`); is it within
    the confidence interval of the baseline?

Output — table only:
`Finding | Severity | Evidence (file:line / script / experiment dir) | Consequence | Minimum corrective action`

Audit, do not redesign. Do not rewrite the pipeline because a cleaner architecture is imaginable.
