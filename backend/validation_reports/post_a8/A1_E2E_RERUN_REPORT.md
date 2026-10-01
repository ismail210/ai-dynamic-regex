# A1 E2E Production Analyze Verification

**Run ID:** `posta8_a1_e2e_20260913T113422Z`  
**Finished:** 2026-09-13T11:35:11Z  
**Mode:** Validation only — production code not modified  

## Final A1 verdict

**A1 E2E VERIFIED**

The Post-A8 release-gate blocker (compiler-surface visibility of River Road incomplete L) is **closed**.

---

## 1. Input artifact

| Field | Value |
|---|---|
| PDF | `training/eval_cache_backups/june_phase3/page_extracts/river_road_phase3_extract.pdf` |
| Pages (extract → source) | 1→25, 2→28, 3→30, 4→33, 5→34, 6→38, 7→41 |
| Excel | **None** (`expected_excel_path=None`) |
| Document ID | `doc_posta8a1riverroad` (distinct from Phase 3 `doc_juneph3riverroad`) |

## 2. Production Analyze path

```text
services.multimodal.pipeline.run_multimodal_pipeline(
    river_road_phase3_extract.pdf,
    expected_excel_path=None,
    persist=True,
    document_id="doc_posta8a1riverroad",
)
```

| Field | Value |
|---|---|
| Pipeline version | `4.19-member-resolution-and-repeated-detail` |
| Elapsed | 47265.63 ms |
| Feature flags | all false (fusion / GraphSAGE / geom-missing-label / ML ranker / ML shadow / legend LLM) |

## 3. Fresh artifact paths

| Artifact | Path |
|---|---|
| Run meta | `validation_reports/post_a8/a1_e2e_rerun/run_meta.json` |
| Raw first-run predictions | `validation_reports/post_a8/a1_e2e_rerun/doc_posta8a1riverroad_predictions.json` |
| Fresh sidecar | `validation_reports/post_a8/a1_e2e_rerun/doc_posta8a1riverroad_drawing_semantics.json` |
| Sidecar validation | `validation_reports/post_a8/a1_e2e_rerun/drawing_semantics_validation.json` |

Counts (fresh): predictions **174**, context_definitions **145**, non_member **82**  
(Phase 3 stale: predictions 135, context_definitions 184)

---

## 4. Before / after River Road table

| Case | Old Phase 3 bucket/scope | Fresh A1 bucket/scope | Completion | Eligible | Thickness invented |
|---|---|---|---|---|---|
| L4X4 source p34 (extract p5) | `context_definitions` / `context_definition` | `predictions` / `takeoff` | `missing_thickness` | false | **No** |
| L5X3 source p38 (extract p6) | `context_definitions` / `context_definition` | `predictions` / `detail_reference` | `missing_thickness` | false | **No** |
| L4X4 source p41 #1 (extract p7) | `context_definitions` / `context_definition` | `predictions` / `takeoff` | `missing_thickness` | false | **No** |
| L4X4 source p41 #2 (extract p7) | `context_definitions` / `context_definition` | `predictions` / `takeoff` | `missing_thickness` | false | **No** |

Old Phase 3 artifact left unchanged.

**Observation (non-blocking):** p38 `L5X3` has `object_scope=detail_reference` but is on the **predictions** compiler surface (not only `context_definitions`). A1 visibility criteria still pass.

---

## 5. Per-case lifecycle (fresh run)

### L4X4 — source page 34 (`token_p5_317`)

| Stage | Value |
|---|---|
| raw_text | `L4X4` |
| normalized_text | `L4X4` |
| section | `L4X4` |
| source_bucket | `predictions` |
| object_scope | `takeoff` |
| completion_status | `missing_thickness` |
| takeoff_eligible | false |
| on predictions surface | **yes** |
| on context_definitions only | **no** |
| needs_review | true |

### L5X3 — source page 38 (`token_p6_464`)

| Stage | Value |
|---|---|
| raw_text | `L5X3` |
| normalized_text | `L5X3` |
| section | `L5X3` |
| source_bucket | `predictions` |
| object_scope | `detail_reference` |
| completion_status | `missing_thickness` |
| takeoff_eligible | false |
| on predictions surface | **yes** |
| on context_definitions only | **no** |

### L4X4 — source page 41 (`token_p7_508`, `token_p7_510`)

| Stage | Value |
|---|---|
| raw_text | `L4X4` (both) |
| normalized_text | `L4X4` |
| section | `L4X4` |
| source_bucket | `predictions` |
| object_scope | `takeoff` |
| completion_status | `missing_thickness` |
| takeoff_eligible | false |
| on predictions surface | **yes** |

---

## 6. Safety checks (A1 acceptance)

| # | Criterion | Result |
|---|---|---|
| 1 | Visible on compiler/semantic input surface | **PASS** (all 4 in `predictions`) |
| 2 | Not only in `context_definitions` | **PASS** |
| 3 | `completion_status=missing_thickness` | **PASS** |
| 4 | `takeoff_eligible=false` | **PASS** |
| 5 | No thickness invented | **PASS** |
| 6 | `L4X4` ≠ `L4X4X1/4` | **PASS** |
| 7 | `L5X3` has no thickness | **PASS** |
| 8 | No `L4X4` → `2L4X4` | **PASS** |
| 9 | Catalog not used as thickness evidence | **PASS** (core preserved; no auto-complete) |
| 10 | No Excel involved | **PASS** (`excel=null`, `excel_is_prediction=false`) |
| 11 | No ML/VLM/GraphSAGE/fusion promotion | **PASS** (flags false) |

---

## 7. Fresh `drawing_semantics.json` validation

| Check | Result |
|---|---|
| Schema `drawing_semantics_v1` | **PASS** (0 validation errors) |
| Annotation count | 319 |
| Incomplete L `source_bucket` | all **`predictions`** |
| Raw / normalized core | preserved (`L4X4` / `L5X3`) |
| `missing_thickness` | yes |
| `takeoff_eligible` | false |
| `original_text_preserved` | true |
| Policy | excel not used; incomplete_l_auto_complete false |

Emitted from **fresh** raw output only (not Phase 3).

---

## 8. Final A1 verdict

**A1 E2E VERIFIED**

Post-A8 release-gate blocker closed: incomplete River Road L callouts appear on the production Analyze `predictions` surface with abstention intact.

---

Production code modified: NONE  
Experimental flags enabled: NONE  
Completion policy changed: NO  
Takeoff logic changed: NO  
Excel used as predictor: NO  
ML/VLM/GraphSAGE enabled: NO  
