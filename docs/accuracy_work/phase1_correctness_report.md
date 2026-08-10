# Accuracy Sprint — Checkpoint 1: Phases 1–4 Correctness Report

**Branch:** `accuracy-sprint/phase1-correctness` (new, based on `origin/accuracy-merge-bassam-phase-ab` @ `1c670b7`)
**Status:** Phases 1–4 complete. 6 commits, not pushed. Nothing merged into `main`/`bassam/rnd-geometry-ml-foundations`. No experimental flags enabled.

---

## 1. What Was Fixed

| # | Priority | Bug | Fix commit |
|---|---|---|---|
| 1 | P0 | Exact-section fallback accepted regex-shaped-but-non-catalog text (e.g. `W12X999`) as a final prediction | `a482e83` |
| 2 | P0 | A clean, catalog-valid exact text match could be silently overridden by weaker fusion/graph/ranker evidence (live-reproduced: `W16x26` → `W14X22`) | `a482e83` |
| 3 | P0 | Confidence/evidence/correction-reason stayed attached to the pre-swap fusion candidate after the label ranker replaced a section, misattributing the change to "geometry and structural-graph evidence" | `a482e83` |
| 4 | P0 | Holdout evaluation built a leakage-free shadow model, then discarded it before scoring — every reported accuracy number was computed against the full, leaked production model | `086e918` |
| 5 | P0 | GraphSAGE training-label generator (`neural_dataset._member_role`) fell back to a shape-family → role lookup table, contradicting its own docstring and the "family ≠ role" design | `d37dbc8` |
| 6 | P1 | `GraphFeatureProvider`/geometry page-index caches were single mutable slots on process-lifetime singletons — concurrent `/analyze` calls for different documents could interleave and cross-contaminate graph/geometry evidence | `68c0679` |
| 7 | P1 | Label-ranker `reconstruct()` call had no exception handling — any error would crash Analyze the moment either flag was enabled | `a482e83` |
| — | — | Two pre-existing test failures (stale `FakeSettings` fixture; incorrect `reasoning`-alias assertion) | `e921d18` |
| — | — | Stale `calibration.py` docstring claiming calibration never fits (it does — 92 real samples fit successfully) | `e921d18` |
| — | — | 4 new React/MUI console warnings on Drawing Review (regression vs. `ef6f71b`) | `2471683` |

Also added, per Phase 3: a standardized abstention-reason taxonomy (`LOW_CONFIDENCE` / `INSUFFICIENT_EVIDENCE` / `MODAL_DISAGREEMENT` / `OUT_OF_DISTRIBUTION` / `PIPELINE_FAILURE`) surfaced as `result["abstention_reason"]`.

**Phase 3 note on calibration labeling:** the original audit flagged the UI's "Calibrated confidence" label as potentially misleading. On direct code and live-data inspection this turned out to be **already correct** — `predictionContract.js::getDisplayConfidence` only shows "CALIBRATED CONFIDENCE" when the backend's `confidence_is_calibrated` flag is genuinely `True`, and `calibration.py::fit_calibration()` already refuses to fabricate a curve without ≥50 real samples, returning `(None, False)` otherwise. The earlier audit's claim that calibration "never fits" was itself stale — `approved_dataset.csv` already has `ranking_score`/`correct`/`eval_split` columns and a real run fit successfully from 92 samples. No behavior change was needed here beyond correcting the stale comment; this is called out explicitly so the correction is on record rather than silently dropped.

## 2. Files Changed

**Backend (production code):**
- `backend/services/exact_section_predictor.py` — shared `catalog_valid_exact_section()` check
- `backend/services/prediction/orchestrator.py` — protected exact label path, evidence recompute on ranker override, abstention-reason wiring
- `backend/services/prediction/review_policy.py` — `protected_label_conflict` param, `determine_abstention_reason()`
- `backend/services/prediction/label_ranker_hook.py` — fail-safe exception wrapping, `ranker_status`/`error_type`/`ranking_scores`
- `backend/services/prediction/contract.py` — removed incorrect `reasoning` legacy alias
- `backend/services/prediction/calibration.py` — stale docstring correction only
- `backend/services/engineering/rule_engine.py` — `_infer_role` no family fallback, canonical roles only
- `backend/services/training_pipeline/neural_dataset.py` — removed `_ROLE_FROM_FAMILY`
- `backend/services/multimodal/feature_providers.py` — `_KeyedCache`, content-fingerprinted graph/geometry caches
- `backend/scripts/evaluate_pipeline.py` — holdout scoring ordering fix, reproducibility manifest

**Backend (tests, 6 new files + 3 modified):**
- New: `test_protected_exact_label.py`, `test_evaluate_pipeline_holdout.py`, `test_role_family_independence.py`, `test_graph_feature_provider_concurrency.py`, `test_label_ranker_evidence_recompute.py`, `test_abstention_reason.py`
- Modified: `test_exact_section_predictor.py`, `test_label_ranker_hook.py`, `test_multimodal_pipeline.py`

**Frontend:**
- `frontend/src/components/pdf/PdfDocumentViewer.jsx` — `Stack`→`Box`+`sx` (react-pdf prop-forwarding fix)
- `frontend/src/components/pdf/SectionResultsList.jsx` — `InputProps`/`secondaryTypographyProps` → `slotProps`

## 3. Regression Tests Added

| File | Tests | What it proves |
|---|---|---|
| `test_protected_exact_label.py` | 12 (incl. 32 subtests) | Direct reproduction of `W16x26`→`W14X22`; catalog-bypass rejection; family coverage (W/HSS/C/L/WT) survives conflicting fusion |
| `test_evaluate_pipeline_holdout.py` | 2 | Shadow model built+used for every prediction BEFORE production artifact is restored; reproducibility manifest present |
| `test_role_family_independence.py` | 11 (32 subtests) | Same role for all families under identical orientation/connectivity; missing signal → `other` not `beam`; no family fallback anywhere |
| `test_graph_feature_provider_concurrency.py` | 1 | 50 interleaved concurrent calls across 2 documents, forced race window, zero cross-contamination |
| `test_label_ranker_evidence_recompute.py` | 4 | Confidence/evidence/reason reflect the ranker's own signal, not the stale fusion candidate's |
| `test_abstention_reason.py` | 7 | Priority ordering across all 5 reason codes |

**Total new/changed test assertions:** 37 new test functions across 6 new files, plus 3 existing files repaired.

## 4. Before / After Behavior

### Live application (real 23-page structural drawing, `ST_sample.pdf`)

| | Before | After |
|---|---|---|
| `W16x26` (100% text match) final section | `W14X22` (64% text evidence, **20% confidence**, shown as "Corrected Prediction") | **`W16X26`, High confidence, "Formatting-Normalized Match"** |
| Review routing on this token | Not forced to review despite the gate having failed | (Now a non-issue — label is correct; protected-label-conflict routing verified separately in unit tests) |
| Drawing Review console | — | 0 errors/warnings (previously 4, confirmed live before and after) |

Screenshotted and verified directly in a running instance of this branch (backend + Vite dev server), not inferred from code reading alone.

### Holdout evaluation (`scripts/evaluate_pipeline.py`, real `approved_dataset.csv`, 1045 rows)

Ran for real, unmocked, against the fixed code:

```
top_1_accuracy: 0.2588   (85 holdout rows, 960 train rows)
top_3_accuracy: 0.3176
top_5_accuracy: 0.3529
candidate_generation_recall: 0.3529
abstention_rate: 0.1647
auto_accepted_rate: 0.2, auto_accepted_accuracy: 0.4706
```

These numbers are **not directly comparable to any pre-fix run** — the pre-fix code was scoring against the leaked production model, which this repo has no saved report of running standalone (the bug was only caught by code inspection during the audit, not by a captured before-metric). What matters here: this is now the **first honest number this pipeline has ever produced** for exact-section holdout accuracy. It is low. That is itself the finding — accuracy work in later phases has a real, unflattering baseline to improve against instead of an inflated one. The full reproducibility manifest (dataset version hash, split composition, model artifact provenance, code commit) is attached to every run going forward.

### Role-label training truth

Not independently re-verified live (this fix affects `neural_dataset.py`'s dataset-*building* path, which only runs via an offline script, not the live Analyze pipeline) — verified via the 32-subtest `test_role_family_independence.py` suite instead, which is the correct verification surface for this specific fix.

## 5. Test Results

**Backend (pytest, full suite, real venv, no mocking of the test runner):**
```
345 passed, 1 skipped, 1 warning, 64 subtests passed
```
Zero failures (was 303 passed / 2 failed / 1 skipped at original-audit time; +42 net new tests from this sprint, both original failures fixed).

**Frontend (vitest, full suite):**
```
Test Files  7 passed (7)
Tests       32 passed (32)
```

**Live browser verification (Drawing Review, real analyzed document):**
- Page load: 0 console errors/warnings (was 4)
- Section-select/highlight interaction (exercises the Chip/ListItemText path specifically): 0 console errors/warnings
- PDF renders correctly, section list renders correctly, `W16X26` clean-label fix confirmed visually

## 6. Remaining Known Risks (not fixed in this checkpoint, in scope for later phases or explicitly out of scope)

- **`graph_builder.py::_FAMILY_NODE_KIND` still hard-codes W/S/M→beam, HP→column** for the *live graph-evidence* path (distinct from the training-label path fixed here). This sprint's Phase 1C instructions named only `rule_engine.py` and `neural_dataset.py`; `graph_builder.py` was flagged P1 in the original audit and is not addressed yet. A bare `W14X90` with no context on a real drawing will still be graphed as "beam."
- **No project-level split is possible today** — `approved_dataset.csv` has no project/document identifier column. The evaluation manifest now says this honestly (`project_level_split: false`) instead of silently assuming it. This is a real limitation for Phase 5+ (honest baseline scorecard) to plan around, not something fixable by this checkpoint alone.
- **GraphSAGE has no certified checkpoint anywhere in this repo** — Phase 10 (clean retrain) cannot start until candidate recall/association work (Phases 6–7) produces something to train on, per the sprint's own required ordering.
- **Label ranker remains fully unpromoted** (`ML_LABEL_RANKER_ENABLED`/`SHADOW` both still default off, untouched by this checkpoint) — the fail-safe wrapping (Phase 2B) makes it *safe* to shadow-test, not *tested*.
- **`dense-page geometry cap` ceiling is still a flat count** (250) — only the ranking strategy under that cap was previously fixed (pre-sprint); not addressed here (Phase 9 territory).
- **Frontend has no dedicated unit tests for `PdfDocumentViewer.jsx`/`SectionResultsList.jsx`** — the MUI-warning fix was verified live in-browser rather than via a new component test; a `SectionResultsList.test.jsx` would be a reasonable low-cost addition later.
- **honest top-1 accuracy (25.88%) is now visible and low.** This is expected and correct given Phases 5+ (candidate recall, association, calibration) haven't started — flagging so it isn't mistaken for a regression when Phase 5's baseline scorecard reports the same number.

## 7. Safety Confirmation

- No experimental flag was enabled at any point (`ML_LABEL_RANKER_SHADOW`/`ENABLED`, `ML_ASSOCIATION_DATASET_ENABLED`, `LEARNED_FUSION_ENABLED` all untouched, still default).
- No branch merges performed; `bassam/rnd-geometry-ml-foundations` and `origin/main`/`origin/accuracy-merge-bassam-phase-ab` untouched.
- 6 commits made locally on `accuracy-sprint/phase1-correctness`; **nothing pushed**.
- Local training-data files that changed as a side effect of running the app during browser verification (`backend/training/documents/doc_0bfc2d61245dbce2.json`, `engineering_corrections.jsonl`, `history.csv`, `multimodal_review_index.json`, `unknown_tokens.csv`, `upload_log.csv`) were deliberately **left uncommitted** — they are local run artifacts, not code changes, and committing them would mix test-run noise into the commit history.

---

**Recommendation:** tests are green enough to trust evaluation. Ready to proceed to Phase 5 (trustworthy baseline scorecard) on request — holding here per the sprint's explicit checkpoint instruction.
