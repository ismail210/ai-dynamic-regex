# Phase 1: feature-set freeze decision (validation only)
Train groups: 16781, validation groups: 3547. Metric: group top-1 accuracy. Test split not used.

| Config | Val Top-1 | Delta vs A | Modern Top-1 | Historical Top-1 |
|---|---|---|---|---|
| A_all_features | 0.9278 | +0.0000 | 0.9272 | 0.9328 |
| B_without_generation_provenance | 0.9636 | +0.0358 | 0.9622 | 0.9758 |
| C1_without_provenance_ranks_only | 0.9639 | +0.0361 | 0.9628 | 0.9731 |
| C2_without_provenance_reasons_only | 0.9273 | -0.0006 | 0.9272 | 0.9274 |
