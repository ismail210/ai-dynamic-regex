# A1 — Context-scope / extraction-surface audit

**Date:** 2026-09-13  
**Track:** Extraction & Compilation Accuracy  
**Status:** FIXED (legend gate + compilation-surface partition)

---

## Root cause

Phase 3 River Road extract pages 4–7 (source 33 / 34 / 38 / 41) were classified as `GENERAL_NOTES` by `legend_profile.detect_context_pages` because:

1. Title-block text contains repeated “SEE GENERAL NOTES…” cross-references.
2. Catalog-valid section density was **moderate** (≈5–12) — below the hard guard of 25 and without a `FRAMING PLAN` / schedule title match.
3. Structural **DETAIL** sheets were not treated as drawing evidence.

`annotate_takeoff_scope` then demoted **every** token on those pages to `object_scope=context_definition` / `takeoff_eligible=False`.

Separately, `partition_takeoff` in `multimodal/pipeline.py` moved **all** `takeoff_eligible=False` predictions into the `context_definitions` artifact bucket — including incomplete-L **abstentions** (`completion_status=missing_thickness`). That removed them from the served `predictions` list used as the compiler input surface.

Safety was still correct: thickness was not invented. The bug was **visibility / scoping**, not unsafe completion.

---

## Fixtures (Phase 3 evidence)

| Source page | Extract page | Incomplete printed | Pre-fix bucket |
|---:|---:|---|---|
| 34 | 5 | `L4X4` | context_definitions |
| 38 | 6 | `L5X3` | context_definitions |
| 41 | 7 | `L4X4` (×2) | context_definitions |
| SOME 65 | — | `L5X3`, `L4X3` | context_definitions |

Preserved artifacts: `training/eval_cache_backups/june_phase3/raw_predictions/doc_juneph3riverroad_predictions.json`.

---

## Fix (minimal)

1. **`legend_profile._has_strong_structural_drawing_evidence`** (`legend_extractor_v5b`):
   - Incomplete-L callouts **required** for DETAIL-title promotion (complete-only typical-details / GENERAL NOTES stay demoted).
   - DETAIL title **or** moderate catalog density, plus ≥1 incomplete-L callout → drawing evidence.

2. **`multimodal/pipeline.py`**:
   - After `partition_takeoff`, restore `missing_thickness` rows onto `predictions` for compilation/review (still `takeoff_eligible=False`).
   - Allow review-queue enqueue for `missing_thickness` even when takeoff-ineligible; still skip true `context_definition` definitions.

---

## Gates

- Incomplete L remains `completion_status=missing_thickness`, `takeoff_eligible=false`.
- Incomplete L appears on the **compilation prediction surface** after re-run.
- True GENERAL NOTES / legend definition tables still demote.
- No ML flags enabled; no auto-completion.
