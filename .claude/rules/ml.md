---
paths:
  - "backend/services/training_pipeline/**/*.py"
  - "backend/services/ml_association/**/*.py"
  - "backend/services/label_reconstruction/**/*.py"
  - "backend/services/multimodal/**/*.py"
  - "backend/services/prediction/ranking.py"
  - "backend/services/prediction/calibration.py"
  - "backend/services/feature_extractor.py"
  - "backend/services/retrain_service.py"
  - "backend/services/self_learning_engine.py"
  - "backend/services/model_versioning.py"
  - "backend/training/**/*.py"
  - "backend/scripts/**/*.py"
---

# ML / training / evaluation rules

See `docs/TRAINING.md` first.

- Never edit datasets, model binaries, registries, or frozen reports to move a metric:
  `backend/training/models/**`, `backend/training/experiments/**`, `backend/database/**`,
  `*.pkl/*.joblib/*.pt`, and the gitignored bulk dirs. Regenerate only via the documented
  scripts, when the task asks. A `PreToolUse` hook blocks these paths.
- Preprocessing and feature extraction are **shared** between training lanes and serving — the
  same function must feed training and `prediction/orchestrator.py`. Check train/serve feature
  parity whenever `training_pipeline/feature_engineering.py`, `preprocessing.py`, or
  `feature_extractor.py` changes (`test_ranker_feature_consistency`, `test_feature_schema_order`,
  `test_feature_pipeline`).
- Augmentation (`training_pipeline/augmentation.py`) runs **only after** the leakage-safe split.
- Splits must be group-aware to avoid cross-entity/label leakage
  (`test_groupcv_and_candidate_gen`, `phase2_build_group_folds.py`,
  `test_evaluate_pipeline_holdout`). Check the candidate-recall ceiling before blaming the
  ranker (`audit_candidate_recall_v16.py`, `test_*candidate*`).
- The evaluation holdout is frozen — never let the reported test set influence model or
  hyperparameter selection (`analyze_frozen_test_rows.py`, `diagnose_val_test_gap.py`).
- Promotion is gated by configured accuracy/F1 tolerances and minimum sample counts, not by
  "training finished". Dataset/model versions are immutable and carry schema versions.
- Self-learning / continuous-learning changes must stay auditable and provenance-tagged
  (`self_learning_engine.py`, `training_pipeline/continuous_learning.py`,
  `test_continuous_learning_pipeline`).
- `label_reconstruction` and `ml_association` stay shadow-only — not wired into production.
- Compare a claimed improvement against the correct existing baseline with the same holdout and
  metric definitions; run `ml-audit` before declaring it real.
