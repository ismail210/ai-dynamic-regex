# Phase 0 — Repository Audit (G8-era review → production gate)

**Date:** 2026-09-21  
**Purpose:** Locate entry points before executing the G8-era human review sequence.  
**No artifacts modified in this phase beyond this report.**

---

## Current pipeline entry points

| Stage | Script | Artifacts |
|---|---|---|
| G7 | `backend/scripts/rd_geometry_integration/geometry_bbox_audit_g7.py` | `docs/validation/rd_geometry_integration/geometry_bbox_audit_g7_*` |
| G8 | `backend/scripts/rd_geometry_integration/representation_repair_g8.py` | `representation_repair_g8_results.jsonl` (+ renders/review/report) |
| G9 | `backend/scripts/rd_geometry_integration/association_shadow_g9.py` | `association_shadow_g9_results.jsonl` (+ renders/review/report) |
| False-assoc audit | `backend/scripts/rd_geometry_integration/g9_false_association_audit.py` | `g9_false_association_audit/` |
| D-case forensics | (emit under audit) | `g9_false_association_audit/d_case_forensics/` |
| G8-era prep | `backend/scripts/rd_geometry_integration/g8_era_human_validation_prep.py` | `g8_era_human_validation/` |

## Current review entry point

- **UI:** `docs/validation/rd_geometry_integration/g8_era_human_validation/review.html`
- **Manifest:** `g8_era_human_validation_manifest.jsonl` (27 PENDING cases)
- **Schema:** `g8_era_human_validation_schema.json`
- **Decision sink:** `g8_era_human_validation/decisions_pending/` (currently empty except README)

Open review UI:
```bash
open docs/validation/rd_geometry_integration/g8_era_human_validation/review.html
```

## Current output directories

`docs/validation/rd_geometry_integration/` — G7/G8/G9/audit/prep artifacts  
`docs/validation/rd_geometry_integration/g8_era_human_validation/decisions_pending/` — **new review layer only**

## Frozen historical gold

- Path: `docs/validation/rd_geometry_integration/review_kit/gold_outcomes.jsonl`
- SHA: `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`
- Metrics: `review_kit/gold_metrics.json` — **do not modify**

## G8/G9 evaluation commands (from `backend/`)

```bash
# Do NOT regenerate unless explicitly requested — freeze is intentional
# python scripts/rd_geometry_integration/representation_repair_g8.py
# python scripts/rd_geometry_integration/association_shadow_g9.py
python -m pytest tests/test_rd_geometry_representation_g8.py tests/test_rd_geometry_association_g9.py \
  tests/test_rd_geometry_g9_false_association_audit.py tests/test_rd_geometry_g8_era_human_validation_prep.py -q
```

Frozen SHAs verified at Phase 0 start:
- G8 results: `1931707165664d9e8e6ea198171624b9f9d8bb25dda2edd40d86619126ed3c44`
- G9 results: `b459522eb097c285a359bd01a2be61c389daeded6415f236b6a0c47323cb4814`

G9 baselines already in results rows:
- `baseline_a_production_geometry_id` (production nearest)
- `baseline_b_nearest_candidate_id` (nearest eligible G8)

## Production association entry point

- Spatial nearest: `backend/services/engineering/spatial_index.py` → `nearest_geometry_candidates`
- Graph edges: `backend/services/engineering/graph_builder.py` (`nearest_geometry`)
- Member association helper: `backend/services/engineering/member_geometry.py` → `associate_text_to_member_candidate`
- **Not wired** to G8 R&D candidates / G9 scorer (shadow only)

## Files that must NOT be modified

- `review_kit/gold_outcomes.jsonl` / `gold_metrics.json` / historical `decisions/`
- `representation_repair_g8_results.jsonl` / G8 script (unless separate approved change)
- `association_shadow_g9_results.jsonl` / G9 script weights/thresholds
- `backend/services/engineering/geometry_extractor.py` (production extraction)
- Production association path above
- Prior G7/G8/G9/audit reports (append-only new downstream artifacts OK)

## Verified state entering Phase 1

- Manifest: 27 rows, all `PENDING` (B=21, C=5, D=1)
- `decisions_pending/`: no decision JSON yet
- Historical gold SHA intact
- G10 not started
