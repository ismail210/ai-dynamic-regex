# Graph v2 Phase 5 Report

## 1. Experiment setup

Offline candidate-only Graph v2 ablation on cached `predictions_view.json`.
No production flags changed. GraphSAGE / learned fusion / ranker remain OFF.
Graph v2 is not hooked into the prediction pipeline.

## 2. Dataset used

- Documents: **8**
- Evaluated rows with candidate pools: **7314**
- Source: `backend/training/eval_cache_backups/doc_*/predictions_view.json`
- Optional join: `engineering_artifacts/*/multimodal/graph.json` when present
- Gold: printed core after shop/cut strip (`proxy_gold_section`); incomplete L → no gold / abstain

## 3. A/B/C/D methodology

- **A**: text-only (alternative confidences + live section) — ungated
- **B**: text + existing geometry similarity — ungated
- **C**: text + Graph v2 — gated pick for safety metrics; ungated recorded separately
- **D**: text + geometry + Graph v2 — gated pick; ungated recorded separately
- Gates on C/D only: explicit protect, incomplete abstain, weak-evidence keep order
- **Primary Graph signal** = ungated C vs A (gated accuracy is contaminated by explicit protection)

## 4. Overall results

| Variant | N with gold | Correct | Accuracy |
|---|---:|---:|---:|
| A | 7193 | 7038 | 0.978451 |
| B | 7193 | 7038 | 0.978451 |
| C | 7193 | 7112 | 0.988739 |
| D | 7193 | 7112 | 0.988739 |

Gated prediction changes vs A: C=171, D=171
Ungated ranking changes vs A: C=0, D=0

### Graph diagnostics (signal, not gated accuracy)

- Same-family candidate pools: **7002**
- Multi-family candidate pools: **312**
- Rows with nonzero graph score spread: **96**
- Mean graph score spread: **0.000827**
- Avg Graph v2 score: **0.190676**
- Multi-family gold rows where text family correct: **256/280**
- Multi-family gold rows where graph-argmax family correct: **216/280**
- Graph argmax prefers W on HSS gold (multi-family): **8**
- Gate reason C counts: `{"gate_explicit_protected": 7112, "gate_weak_evidence_keep_baseline_order": 84, "graph_v2_rerank": 21, "gate_explicit_missing_from_pool": 81, "gate_incomplete_abstain": 16}`

_Gated C/D accuracy includes explicit-section protection and incomplete abstain; those are safety gates, not Graph v2 ranking signal. Primary Graph v2 signal = ungated C vs A and multi-family argmax diagnostics._

## 5. L results

- **A**: acc=0.647773 (n=247), L→2L=10, thickness=60, size/leg=12, incomplete completions=16
- **B**: acc=0.647773 (n=247), L→2L=10, thickness=60, size/leg=12, incomplete completions=16
- **C**: acc=0.821862 (n=247), L→2L=0, thickness=0, size/leg=0, incomplete completions=0
- **D**: acc=0.821862 (n=247), L→2L=0, thickness=0, size/leg=0, incomplete completions=0

### L buckets (counts by variant pick class)

| Bucket | A | B | C | D |
|---|---:|---:|---:|---:|
| L_correct_explicit | 160 | 160 | 203 | 203 |
| L_wrong_thickness_or_size | 72 | 72 | 0 | 0 |
| L_to_2L | 10 | 10 | 0 | 0 |
| incomplete_L | 16 | 16 | 16 | 16 |
| L_wrong_other | 4 | 4 | 43 | 43 |

Note: gated C/D L improvements largely reflect incomplete abstain + explicit protect, not Graph-driven L candidate discrimination (ungated C==A).

## 6. HSS → W results

HSS gold rows: **864**

| Variant | HSS→W |
|---|---:|
| A | 10 |
| B | 10 |
| C (gated) | 0 |
| D (gated) | 0 |
| C ungated | 10 |
| D ungated | 10 |

Difference gated C−A: **-10**
Difference ungated C−A: **0**
Graph-argmax W preference on HSS gold (multi-family): **8**

## 7. Wrong → correct / Correct → wrong

### Ungated C vs A (true Graph ranking signal)

```json
{}
```

### Gated C vs A (includes explicit protect / abstain — not pure Graph)

```json
{
  "wrong_to_wrong": 97,
  "wrong_to_correct": 74
}
```

## 8. Unsafe cases

- Ungated C unsafe_mutation: **0**
- Ungated C explicit_label_conflict: **0**
- Gated incomplete completions: **0**
- Incomplete completions newly caused by Graph change: **0**
- Gated explicit overrides: **0**

## 9. Feature contribution analysis

Cases where ungated C differs from A: **0**

Average feature contributions on those cases:

```json
{}
```

Average feature contributions across all scored rows:

```json
{
  "spatial": 0.040174,
  "leader": 0.02579,
  "orientation": 0.0244,
  "role": 0.041815,
  "neighborhood": 0.025071,
  "family_local": 0.033427
}
```

## 10. Safety gates

```json
{
  "gate1_explicit_override_gated_C": 0,
  "gate1_explicit_override_ungated_C": 0,
  "gate2_incomplete_completed_gated_C": 0,
  "gate2_incomplete_completed_ungated_C": 16,
  "gate2_incomplete_completed_by_graph_change": 0,
  "gate3_candidates_only": true,
  "gate4_no_excel": true,
  "gate5_unsafe_size_leg_ungated_C": 0,
  "gate6_weak_evidence_forced_change": 0,
  "gate7_HSS_to_W": {
    "A": 10,
    "B": 10,
    "C": 0,
    "D": 0,
    "C_ungated": 10,
    "D_ungated": 10
  },
  "takeoff_eligible_field_unchanged": true,
  "prediction_changes_among_rows_with_takeoff_flag": 0
}
```

## 11. Recommendation

**DO NOT ENABLE**

- Text+Graph v2 ranking never differed from text baseline (same-family pools=7002)
- On multi-family pools, graph argmax family matches gold 216/280 vs text 256/280
- Graph argmax prefers W on 8 HSS-gold multi-family rows (HSS→W bias risk)
- Gated C accuracy lift is dominated by explicit-section protection, not Graph v2 candidate scoring

## 12. Exact next step

Do not add production flags. Graph v2 candidate scoring did not change text ranking and, on multi-family pools, can prefer W over HSS when role/orientation/neighbor evidence looks beam-like. Next research step (offline only): leader-target family features with anti-HSS→W constraints, or deprioritize Graph v2 versus incomplete-L abstain / explicit protect.
