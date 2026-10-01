# POST-A8 Accuracy Validation / Release Gate

**Date:** 2026-09-13  
**Mode:** Investigation + validation only  
**Production code modified:** NONE  
**Experimental flags enabled:** NONE  

Supporting rerun artifacts (this audit only):  
`backend/validation_reports/post_a8/`

---

## 1. Executive verdict

**READY FOR NEXT BUILD** *(amended 2026-09-13 after A1 E2E)*

A1–A8 deliverables exist, safety for incomplete **L/2L** still holds, focused tests pass, and `drawing_semantics.json` schema-validates.  

**Amendment:** Fresh production Analyze on the River Road Phase 3 extract (`validation_reports/post_a8/A1_E2E_RERUN_REPORT.md`, run `posta8_a1_e2e_20260913T113422Z`) **verified** that incomplete `L4X4`/`L5X3` now land on the `predictions` compiler surface with `missing_thickness` / `takeoff_eligible=false` and no invented thickness. The prior blocking item is **closed**. Frozen Phase 3 artifacts remain historical/stale by design.

---

## 2. A1–A8 verification table

| ID | Claimed deliverable | Verified in code/artifacts? | Residual / limitation |
|---|---|---|---|
| **A1** | Incomplete L on compiler surface; abstention kept | **Partial.** Legend gate (`legend_extractor_v5b`) + pipeline restore of `missing_thickness` after `partition_takeoff` exist and are unit-tested. On River Road extract PDF text, pages with incomplete L now get `strong=True` and are **not** demoted. | Frozen Phase 3 raw preds + sidecars still have RR `L4X4`/`L5X3` in `context_definitions` / `object_scope=context_definition`. No fresh Analyze artifact proves predictions-surface placement. |
| **A2** | 87-row extract/group gold | **Yes.** `june_16page_extract_group_gold.json`: 87 rows; ops `{abstain_incomplete:17, normalization:15, none:55}`; `human_verified=17` (abstains only). Under `eval_cache_backups/` — **not training**. | 70/87 rows are Phase-3 seeded (`human_verified=false`). Not full human extract/group gold. |
| **A3** | Rotation/bracket grouping; F1=1.0 | **Yes on synthetic multi-fragment seeds.** `fragment_grouper.py` + `measure_grouping_f1.py` → F1 **1.0** (12/12). | F1 measures **synthetic** splits of complete `W` strings in gold, not OCR/PDF multi-span recovery on real pages. |
| **A4** | Deterministic canonicalize; no false corrections | **Yes on A2 gold.** `section_canonicalize.py`; audit `false_correction_count=0`, `incomplete_preserved=17`. | Helper is additive; production path still primarily uses existing normalize/`catalog_form`. Not a full-corpus accuracy %. |
| **A5** | Repair shadow metrics; flags off | **Yes.** Shadow script coverage **1.0** on 5 cases; `ML_LABEL_RANKER_*=false` in settings and Phase 3 flags. | Coverage ≠ repair accuracy. No production remap. |
| **A6** | SOURCE_VERIFIED design + fixtures | **Yes.** Design doc + 5 fixtures; policy `incomplete_l_auto_complete_enabled=false`; fixture tests pass. | Design only — **not** production-enabled. |
| **A7** | 100 association links; measure precision | **Partial.** Exactly **100** links; methods present (`leader_tip_to_stroke` 25, `proximity_stroke` 37, `ambiguous_members` 38). | **0/100** `human_verified`; all `human_label=UNREVIEWED`. Precision = **null** (not estimated). |
| **A8** | Emit `drawing_semantics.json` | **Yes.** Writer + schema validate on RR/Burrville/SOME (401 / 562 / 148 anns). Policy: excel not used; no auto L complete; GH not required. | Projection is read-model; `operations` arrays are empty (by design — projection does not invent ops). Sidecars replay Phase 3 buckets (stale A1 scope). |

---

## 3. Test / measurement results

| Command | Result | Pass/fail | Artifact | What it actually proves |
|---|---|---|---|---|
| `pytest` StrongDrawingEvidence + incomplete abstention + fragment_grouper + section_canonicalize + drawing_semantics + compilation_surface_partition + a6 fixtures + semantic_contract | `66 passed, 27 subtests` | **PASS** | `validation_reports/post_a8/focused_pytest.txt` | Unit/contract behavior for A1–A4/A6/A8 pieces — **not** full-doc Analyze accuracy |
| `scripts/measure_grouping_f1.py` | F1=1.0, P=1.0, R=1.0, n=12 | **PASS** | `validation_reports/post_a8/a3_grouping_f1.json` | Grouper joins synthetic multi-fragment W seeds |
| `scripts/audit_normalize_false_corrections.py` | false_corrections=0; 17 incompletes preserved | **PASS** | `validation_reports/post_a8/a4_normalize_audit.json` | Canonicalize does not invent thickness on A2 gold |
| `scripts/measure_repair_shadow.py` | coverage=1.0; flags false | **PASS** | `validation_reports/post_a8/a5_repair_shadow.json` | Candidate gen returns ≥1 catalog candidate on 5 shadow cases; **no enable** |
| `scripts/measure_association_precision.py` | rate=1.0 system assoc; precision=null | **PASS (measurement)** / precision **N/A** | `validation_reports/post_a8/a7_association_precision.json` | System produced a geometry method for 100/100 links; **no human correctness** |
| `scripts/emit_drawing_semantics.py` | 3 docs; validation_errors=[] | **PASS** | `validation_reports/post_a8/drawing_semantics/` | Schema-valid sidecar emit from Phase 3 records |
| Legend gate on `river_road_phase3_extract.pdf` pages 4–7 | `strong=True`, not demoted; incomplete hits ≥1 | **PASS (simulation)** | (stdout in audit session) | Current legend code would not whole-page demote those sheets |
| Fresh Analyze re-run post-A1 | 4/4 incomplete L on `predictions`; abstention intact | **PASS** | `validation_reports/post_a8/A1_E2E_RERUN_REPORT.md` | Closes A1 compiler-surface blocker |

**Failure taxonomy:** no product test failures in the focused suite; no environment failures observed with `./venv/bin/python`. Missing human labels are **measurement gaps**, not test failures.

---

## 4. Real accuracy metrics (evidence-backed only)

| Operation | Evidence available | Metric available | Result | Confidence / limitation |
|---|---|---|---|---|
| Extraction | Phase 3 row counts; A2 gold presence | Count / coverage only | 1111 rows all buckets; 609 takeoff predictions (Phase 3); A2 has 87 labeled rows | **Not accuracy.** No extract recall/precision vs full human page gold |
| Grouping | 12 multi-fragment A2 seeds | Grouping F1 | **1.0** | High on synthetic seeds only; low external validity |
| Normalization | A2 gold + A4 audit; Phase 3 format tags | False-correction count; format_correction_ok=30 (Phase 3 tag) | **0** false corrections on A2 incomplete/format audit | Format-only; not semantic correctness % |
| Repair | A5 shadow cases (5) | Candidate coverage | **1.0** coverage | **Not accuracy.** Shadow only; flags off |
| Completion | Phase 3 safety; A6 fixtures; incomplete L samples | Abstention / unsafe completion | Incomplete L/2L: **6 abstained, 0 unsafe** (Phase 3 safety PASS). A6: catalog/conflict → abstain | Policy/safety measured; SOURCE_VERIFIED auto-complete **disabled** |
| Association | 100 A7 links | Precision on reviewed | **null** (0 reviewed). System association rate 100% | Rate ≠ precision. Do not treat coverage as accuracy |
| Semantic compilation | A8 sidecars | Schema validation | **0** schema errors; raw preserved | Schema validity ≠ semantic correctness |

---

## 5. `drawing_semantics.json` end-to-end validation

| Check | River Road | Burrville | SOME |
|---|---|---|---|
| Sidecar exists | Yes | Yes | Yes |
| Schema-valid (`drawing_semantics_v1`) | Yes (0 errors) | Yes | Yes |
| Annotation count | 401 | 562 | 148 |
| Stable `annotation_id` (non-null, unique) | 401/401 | 562/562 | 148/148 |
| Raw text present / `original_text_preserved` | Yes / no False | Yes | Yes |
| Normalized separate from raw | Yes (`normalized_text`) | Yes | Yes |
| Operation classification explicit | **Weak** — `operations=[]` on all rows (projection does not invent ops) | Same | Same |
| Completion status explicit | Yes | Yes | Yes |
| Evidence / confidence / review fields | Present; review_required counts 234 / 199 / 28 | Yes | Yes |
| Geometry evidence optional | Present as optional structure; not treated as text truth | Yes | Yes |
| Incomplete L core preserved / missing_thickness / not completed / takeoff_eligible=false | **4** RR cores (`L4X4`×3, `L5X3`×1): all preserved, missing_thickness, eligible false | None in this extract set | **2** (`L5X3`,`L4X3`): same |
| Excel-derived prediction in semantics | Policy `excel_role=not_used`; Phase 3 raw `excel=null`, `role=first_run_raw_model_output` | Same emit path | Same |
| Unlabeled geometry as semantic truth | 0 cases of empty raw + geometry-invented text | 0 | 0 |
| ML/VLM/GraphSAGE promoted | No graphsage/vlm markers; flags false in Phase 3 + live settings | Same | Same |
| Takeoff formulas in sidecar | No quantity/cost formula fields observed | Same | Same |

**Violations / caveats**

1. **Stale A1 scope in sidecars:** RR incomplete L still `source_bucket=context_definitions`, `object_scope=context_definition` because emit replays Phase 3, not a post-A1 Analyze.  
2. **Empty `operations`:** contract allows projection without inventing ops; four-op classification is therefore **not** populated in these sidecars.  
3. **HSS note (out of L policy, still observed):** some `missing_thickness` HSS rows in Phase 3 have `section` like `HSS6X3X1/2` while `normalized_text` stays `HSS6X3` and `takeoff_eligible=false` (review prompt). Sidecar keeps raw/normalized incomplete. This is **not** an incomplete-L auto-complete failure; do not confuse with L4X4→thickness.

---

## 6. River Road A1 regression verification

### Lifecycle (frozen Phase 3 → sidecar) — still shows OLD scoping

| Stage | `L4X4` p34 | `L5X3` p38 | `L4X4` p41 (×2) |
|---|---|---|---|
| Raw text | `L4X4` | `L5X3` | `L4X4` |
| Normalized | `L4X4` | `L5X3` | `L4X4` |
| Completion | `missing_thickness` | same | same |
| Takeoff eligible | **false** | **false** | **false** |
| Phase 3 bucket | `context_definitions` | same | same |
| `object_scope` | `context_definition` | same | same |
| Sidecar `source_bucket` | `context_definitions` | same | same |
| Thickness invented? | **No** | **No** | **No** |

Abstention safety: **PASS**. Compiler-surface placement on frozen artifacts: **FAIL (still demoted).**

### Current-code evidence (not a full Analyze)

1. **Legend gate on extract PDF** (pages with incomplete L): `strong=True`, page **not** in `detect_context_pages` demotion set.  
2. **Partition restore simulation** on frozen preds: `missing_thickness` rows are restored onto the predictions list, but **`object_scope` remains `context_definition`** until a re-run reclassifies scope.  
3. **Unit tests:** DETAIL+incomplete L not demoted; complete-only typical details still demoted; compilation-surface restore tested.

**Conclusion:** Thickness abstention never broke. Visibility/scoping fix is implemented and locally evidenced, but **E2E compiler-surface correction on River Road is unverified** until Analyze is re-run and new predictions are preserved.

---

## 7. Safety invariant table

| # | Invariant | Result | Evidence |
|---|---|---|---|
| 1 | `L4X4` does not become `L4X4X1/4` without verified drawing evidence | **PASS** | Phase 3 incomplete L samples; canonicalize; sidecar normalized=`L4X4` |
| 2 | `L5X3` does not receive invented thickness | **PASS** | Same |
| 3 | `2L4X4` not invented from `L4X4` | **PASS** | Incomplete detector / canonicalize keep family; no 2L promotion observed on these rows |
| 4 | Catalog alone does not complete missing thickness | **PASS** (L/2L policy) | Phase 3 safety `catalog_not_used_as_missing_thickness_evidence`; A6 fixtures |
| 5 | Excel is not a predictor | **PASS** | Phase 3 flags/safety; raw `excel=null`; sidecar policy |
| 6 | Unlabeled geometry is not truth | **PASS** | Phase 3 safety; sidecar check (0 invents) |
| 7 | ML label ranker disabled | **PASS** | `settings.ml_label_ranker_enabled=False`, shadow False; Phase 3 flags |
| 8 | GraphSAGE disabled | **PASS** | `graphsage_section_scoring_enabled=False` |
| 9 | Learned fusion disabled | **PASS** | `learned_fusion_enabled=False` |
| 10 | VLM disabled | **PASS** | No VLM enablement in Phase 3 flags / sidecar |
| 11 | SOURCE_VERIFIED completion disabled | **PASS** | A6 `auto_apply=false`; sidecar `incomplete_l_auto_complete=false` |
| 12 | Semantic compilation does not own takeoff quantities | **PASS** | Sidecar has no quantity formulas; read-model only |

---

## 8. Remaining gaps

### A. Blocking accuracy gaps
1. *(None after A1 E2E.)* Prior blocker closed — see `validation_reports/post_a8/A1_E2E_RERUN_REPORT.md`.

### B. Non-blocking measurement gaps
1. A3 F1 is synthetic-seed only.  
2. A4/A5 metrics are audits/coverage, not production accuracy %.  
3. Sidecar `operations` empty (projection policy).  
4. HSS `section` review-suggestion vs preserved `normalized_text` should be documented in semantic export clarity later (not an L auto-complete fail).
5. p38 `L5X3` is on predictions with `object_scope=detail_reference` (visible; scope nuance only).

### C. Human-review gaps
1. A2: 70/87 rows unverified.  
2. A7: **0/100** CORRECT/WRONG labels → association precision unknown.

### D. Product/design gaps
1. SOURCE_VERIFIED completion designed but intentionally off.  
2. Four-op provenance not fully populated on emit path.  
3. Takeoff eligibility remains a recorded field; quantity engine is out of scope.

### E. Deferred integrations
1. Live GHX / Rhino.Compute (still blocked / late).  
2. PDF rewrite, VLM, OCR, GraphSAGE, learned fusion, XGB enable — **not** indicated as the measured bottleneck by this gate.

**Do not recommend** VLM / GraphSAGE / XGB enable / OCR / dense-page cap / GHX / PDF rewrite as the next step based on current evidence.

---

## 9. Release-gate decision

**READY FOR NEXT BUILD** *(amended after A1 E2E VERIFIED)*

See `validation_reports/post_a8/A1_E2E_RERUN_REPORT.md`.

---

## 10. ONE recommended next action

**Human-label A7 association gold (CORRECT/WRONG) on the existing 100 links** so association precision is measurable before any association-model or dense-geometry work.

---

## Production Changes Made
NONE

## Experimental Flags Enabled
NONE

## Completion Policy Changed
NO

## Takeoff Logic Changed
NO

## Excel Used As Predictor
NO

## ML/VLM/GraphSAGE Enabled
NO

## Final Verdict
READY FOR NEXT BUILD
