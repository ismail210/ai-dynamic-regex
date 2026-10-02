# June Phase 3 First-Run Validation

**Generated:** 2026-09-13T10:06:04.103680+00:00
**Experiment:** `june_phase3_first_run_2026-09-13`

## 1. Executive Verdict

**PASS WITH LIMITATIONS**

Limitations:
- Repair not independently measurable from production payloads
- No human gold — metrics are coverage/counts, not accuracy %
- Page extracts are extract-local for document-prior/legend scope (not full-PDF Analyze context)
- Incomplete printed 2L not observed in River Road + Burrville corpus scan / this subset
- Incomplete L rows observed primarily as context_definition (excluded from takeoff predictions) — residual scope finding

## 2. Corpus

- Root: `Testing Projects`
- PDFs available: **19** across **13** folders
- Evaluated: **16 pages** in 18 - River Road, 51 - Burrvile ES, 41 - SOME
- Selection: Phase 0C representative steel subset (verified locally)
- Incomplete printed `2L` **not present** in this subset (corpus scan: 0 hits on River Road + Burrville)

### Selected pages

| Project | Pages |
|---|---|
| 18 - River Road | 25, 28, 30, 33, 34, 38, 41 |
| 51 - Burrvile ES | 54, 59, 63, 65, 72, 75, 78 |
| 41 - SOME | 58, 65 |

## 3. Pipeline Path Used

- **entry:** `services.multimodal.pipeline.run_multimodal_pipeline`
- **prediction_owner:** `services.prediction.orchestrator via fusion_engine.predict`
- **eval_classifier:** `scripts.evaluate_first_run._classify_row`
- **semantic_projection:** `services.prediction.semantic_contract.project_semantic_annotation`
- **buckets_evaluated:** `['predictions', 'context_definitions', 'non_member_annotations', 'repeated_detail_members']`
- **excel:** `None`
- **persist:** `True`
- **metrics_pass:** `recompute_from_preserved_artifacts`

Feature flags (must remain false):

```
{
  "learned_fusion_enabled": false,
  "graphsage_section_scoring_enabled": false,
  "geometry_missing_label_inference_enabled": false,
  "ml_label_ranker_enabled": false,
  "ml_label_ranker_shadow": false,
  "legend_profile_llm_enabled": false,
  "ml_association_dataset_enabled": false
}
```

## 4. Extraction

- Total evaluated rows (all buckets): **1111**
- Takeoff predictions only: **609**
- Bucket counts: `{'predictions': 609, 'context_definitions': 353, 'non_member_annotations': 149}`
- By project (takeoff): `{'river_road': 135, 'burrville': 358, 'some': 116}`
- Pages with zero takeoff predictions: **7**
  - 18 - River Road p33: Incomplete L4X4 + complete L angles (abstention)
  - 18 - River Road p34: Incomplete L4X4 near completes — must not auto-complete
  - 18 - River Road p38: Incomplete L5X3 + completes
  - 18 - River Road p41: Incomplete L4X4 on opening detail
  - 51 - Burrvile ES p54: Half-leg L5X3-1/2X5/16 must stay complete
  - 51 - Burrvile ES p72: 2L + complete L details
  - 41 - SOME p65: Half-leg completes / detector false-positive guard
- Note: Takeoff predictions vs context_definitions/non_member retained separately; no extraction gold accuracy

## 5. Normalization

- Observed normalization ops (heuristic from raw≠normalized / format tags): **59**
- format_correction_ok tags: **30**
- catalog_equivalent_ok tags: **0**
- Note: Format/catalog-form only; not semantic inference

## 6. Repair

**not_independently_measurable** — Production payloads do not label REPAIR distinctly

## 7. Completion / Abstention

- Incomplete printed (detector): **6**
- Incomplete in context_definitions: **6**
- Incomplete in takeoff predictions: **0**
- Incomplete abstained (`missing_thickness` + not takeoff-eligible): **6**
- Unsafe completions: **0**
- incomplete_abstention_ok tags: **6**

Sample incomplete rows:

| Project | Page | Bucket | Raw | Section | Status | Takeoff |
|---|---:|---|---|---|---|---|
| 18 - River Road | 34 | context_definitions | `L4X4` | `L4X4` | missing_thickness | False |
| 18 - River Road | 38 | context_definitions | `L5X3` | `L5X3` | missing_thickness | False |
| 18 - River Road | 41 | context_definitions | `L4X4` | `L4X4` | missing_thickness | False |
| 18 - River Road | 41 | context_definitions | `L4X4` | `L4X4` | missing_thickness | False |
| 41 - SOME | 65 | context_definitions | `L5X3` | `L5X3` | missing_thickness | False |
| 41 - SOME | 65 | context_definitions | `L4X3` | `L4X3` | missing_thickness | False |

## 8. Catalog Matching

- match_ok: **915**
- catalog_equivalent_ok: **0**
- catalog_matching_error: **0**
- non_catalog_designation: **2**
- Note: Catalog verification only; Excel not used

## 9. BBox Coverage

- Rows with bbox: **1111**
- Bbox coverage: **1.0**
- Note: Coverage only — no bbox gold accuracy

## 10. Geometry Association

- Rows with spatial/preview association: **1111**
- Spatial coverage: **1.0**
- Rows with member_geometry: **1111**
- Association text rewrites detected: **0**
- Note: Coverage only; geometry evidence != semantic truth

## 11. Duplicate Analysis

Per-document merge audit from existing pipeline:

```
[
  {
    "doc_key": "river_road",
    "duplicates": {
      "merged": 0,
      "merges": []
    }
  },
  {
    "doc_key": "burrville",
    "duplicates": {
      "merged": 2,
      "merges": [
        {
          "kept": "geom_assoc_a07df1f30169",
          "dropped": "geom_assoc_a07df1f30169",
          "label": "W16X26"
        },
        {
          "kept": "geom_assoc_fff7a17d3beb",
          "dropped": "geom_assoc_82b8477fe806",
          "label": "HSS6X6X3/8"
        }
      ]
    }
  },
  {
    "doc_key": "some",
    "duplicates": {
      "merged": 0,
      "merges": []
    }
  }
]
```

## 12. Missing Analysis

- missing_extraction tags: **177**
- Note: No Excel-as-GT; includes pages where steel text exists only as context_definition
- Excel was **not** used (no GT / no predictor).

## 13. Semantic Operations

| operation | count |
|---|---:|
| normalization | 59 |
| repair | 0 |
| completion (unsafe tag only) | 0 |
| association | 1111 |

Note: Heuristic from existing fields; COMPLETION = unsafe_completion tags only

Phase 2 `project_semantic_annotation` applied additively to every row.

## 14. Confidence / Review

Existing fields only (`confidence`, `confidence_basis`, `needs_review`, `review_status`, `review_reason`) are preserved on each record in `june_phase3_results.json`. No new scorer.

## 15. Safety Audit

**Safety verdict: PASS**

| Invariant | OK |
|---|---|
| incomplete_l_no_auto_thickness | PASS |
| incomplete_2l_no_auto_thickness | PASS |
| complete_l_remain_complete | PASS |
| catalog_not_used_as_missing_thickness_evidence | PASS |
| excel_not_used_as_predictor | PASS |
| unlabeled_geometry_not_takeoff_truth | PASS |
| raw_text_preserved | PASS |
| non_catalog_not_silently_replaced | PASS |
| high_confidence_incomplete_still_ineligible | PASS |

No safety failures observed on this subset.

## 16. Residual Error Taxonomy

Observed tag counts (not accuracy):

```
{
  "match_ok": 915,
  "format_correction_ok": 30,
  "missing_extraction": 177,
  "punctuation_trailing_noise_error": 168,
  "incomplete_abstention_ok": 6,
  "untagged": 11,
  "non_catalog_designation": 2
}
```

## 17. What Phase 3 Proves

- The existing production multimodal path can be run on page extracts of June steel pages.
- First-run predictions can be preserved and classified without Excel-as-GT.
- Phase 2 semantic projection is additive and does not require builder changes.
- Incomplete L abstention behavior is measurable on River Road incomplete pages in this subset (see metrics).
- Experimental flags remained off for this run.

## 18. What Phase 3 Does NOT Prove

- Overall corpus accuracy (no gold).
- Bbox or geometry association precision/recall.
- Repair quality (not labeled).
- Incomplete `2L` live behavior on June pages (none in subset / none found in River+Burrville scan).
- GH / Rhino coordinate or BeamTxt↔BeamCrv contracts.
- That page extracts are identical to full-document Analyze context (document-prior/legend scope is extract-local).

## 19. Phase 4 Recommendation

**ONE next task:** Investigate why incomplete printed `L4X4`/`L5X3` on River Road detail pages are scoped as `context_definition` (excluded from takeoff `predictions`) despite correct `missing_thickness` / `takeoff_eligible=false` abstention — determine whether `annotate_takeoff_scope` / legend-region heuristics are over-scoping real member callouts; evidence-only, no inference change yet.

---

Artifacts: `JUNE_PHASE3_VALIDATION_MANIFEST.json`, `june_phase3_results.json`, `training/eval_cache_backups/june_phase3/`.
