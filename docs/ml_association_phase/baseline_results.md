# Phase 1 — Deterministic Correctness & Observability: Results

Scope: `docs/geometry_graph_audit/08_prioritized_roadmap.md` P0.1–P0.3, P0.6 (partial), P1.2, and the corresponding items from the ChatGPT deep-research report's implementation prompt (rotation tests, dense-page fixture, STRtree comparator). This is a data/observability phase — **no production prediction behavior changed**. See `docs/ml_association_phase/repository_evidence.md` for Phase 0.

## What changed

| Area | File(s) | Change | Production behavior change? |
|---|---|---|---|
| Deterministic geometry IDs | `services/engineering/geometry_extractor.py` | `_gid()` now derives IDs from `(page_number, ordinal, bbox, kind)` via SHA-1 instead of `uuid.uuid4()` | **No** — IDs are still unique strings with the same `geom_` prefix and length; nothing compares old vs. new ID values |
| Deterministic graph IDs | `services/engineering/graph_builder.py` | `_nid()` now derives node/edge IDs from stable source facts (`token_id`, `geometry_id`, edge `(source,target,relation,occurrence)`) instead of `uuid.uuid4()` | **No** — same reasoning; `txt_`/`geo_` prefix convention preserved (verified by test) |
| Node-construction refactor | `services/engineering/graph_builder.py` | Extracted inline node-building into `build_text_nodes()`/`build_geometry_nodes()`, called by both `build_graph()` and the new experimental `spatial_index.py` | **No** — pure extraction, behavior-preserving (verified by full regression run) |
| Dense-page cap diagnostics | `services/engineering/geometry_extractor.py` | Added `raw_drawing_count`, `retained_drawing_count`, `drawings_dropped_by_cap`, `zero_area_path_count`, `dropped_degenerate_count`, `dense_page_cap_strategy`, `cap_strategy_agreement`, `page_rotation`, `scale_value`/`scale_source`/`scale_confidence` (reserved) fields to `geometry.json`'s `page_summaries` | **No** — additive fields only |
| Dense-page cap A/B fix (opt-in) | `services/engineering/geometry_extractor.py` | New `dense_page_cap_strategy` parameter on `extract_geometry()`, default `"legacy_area"` (unchanged), opt-in `"length_aware"` fixes the zero-area sort bug | **No by default** — the corrected strategy is not the default; a caller must explicitly opt in |
| Graph/semantic window diagnostics | `services/engineering/graph_builder.py`, `structural_graph.py` | Added `graph["diagnostics"]` (per-page node/edge counts, window-trigger flags, candidate pairs considered/possible/pruned) merging both the 60/12 and 350/44 window regimes | **No** — additive field only |
| Experimental STRtree candidate generator | new `services/engineering/spatial_index.py` | Spatially-complete, extraction-order-independent label→geometry candidate generation + leader-endpoint resolution + coverage-recall measurement vs. the production windowed loop | **No** — not imported by any router or the live pipeline (enforced by a dedicated test) |
| New dependency | `backend/requirements.txt` | Added `shapely==2.1.2` | Adds a dependency; does not change any existing behavior |

## Test results

**New tests added** (5 files, 26 test cases, all passing):

| File | Tests | What it verifies |
|---|---|---|
| `tests/test_deterministic_ids.py` | 5 | Geometry/graph/edge IDs and the full `graph.json` artifact are byte-identical across two independent extraction runs of the same document; `txt_`/`geo_` prefix convention preserved; edge IDs never collide |
| `tests/test_dense_page_geometry_cap.py` | 6 | Reproduces the exact defect (300 long lines + 20 tiny specks → cap keeps all specks, drops 70 of the significant lines) under the default `legacy_area` strategy; confirms the opt-in `length_aware` strategy measurably reduces that loss; confirms the default strategy is unchanged; confirms invalid strategy names are rejected; confirms diagnostics degrade gracefully below the cap threshold |
| `tests/test_pdf_rotation_coordinates.py` | 4 (12 subtests) | Confirms PyMuPDF `1.28.0` (the version actually pinned in this repo) matches the deep-research report's documented rotation contract at 0°/90°/180°/270°: `get_drawings()` returns unrotated coordinates; `rotation_matrix`/`derotation_matrix` round-trip correctly; documents (does not yet change) that `extract_geometry` currently reports unrotated coordinates verbatim |
| `tests/test_spatial_index.py` | 11 | STRtree finds spatially-close pairs the production windowed loop misses; extraction-order invariance (spatially-complete result unaffected by shuffling, windowed result IS affected — demonstrating the defect); measurable recall gap on a dense shuffled synthetic page; ranked multi-candidate output (not just single greedy pick); leader-endpoint resolution finds the real target member beyond the leader's own position; no-valid-target returns empty; end-to-end smoke + reproducibility on a real extracted PDF; **explicit guard that this module is not imported by the production pipeline or orchestrator** |

**Full existing suite**: `134 passed, 5 failed` (up from `108 passed, 5 failed` on the unmodified baseline — the 26-test difference is exactly the new Phase 1 tests above; the 108 baseline-passing tests still pass unchanged).

**The 5 failures are confirmed pre-existing** — verified by running the identical suite against the unmodified baseline (via `git stash -u`) before any Phase 1 changes: the same 5 tests fail with the same errors on both. None are caused by this phase's work.

| Failing test | Cause (from inspection) |
|---|---|
| `test_modular_multimodal_fusion.py::AttentionFusionTests::test_contributions_sum_to_one_and_database_is_zero` | Unrelated to geometry/graph; not investigated further in this phase (out of scope) |
| `test_modular_multimodal_fusion.py::AttentionFusionTests::test_database_cannot_be_supplied_as_candidate_modality` | Unrelated to geometry/graph; not investigated further |
| `test_multimodal_pipeline.py::RichExtractionTests::test_extraction_preflight_does_not_start_prediction` | Stage-name mismatch (`'extracted' != 'extraction_complete'`), unrelated to geometry/graph |
| `test_multimodal_pipeline.py::AdapterAndCorrectionTests::test_ai_first_fusion_does_not_require_database_to_decide` | **Confirmed in Phase 0**: `FUSION_WEIGHTS["text"] == 0.48` assertion is stale — `ATTENTION_PRIORS["text"]` is `0.32` today (see `repository_evidence.md`, resolves the deep-research report's open question #13) |
| `test_takeoff_platform.py::GroundTruthExcelTests::test_parse_real_estimate_if_present` | Environmental: pandas cannot determine the Excel engine for a real `.xlsm` fixture file on this machine; unrelated to any code change |

None of these five block Phase 1's exit criteria (repeated runs deterministic; candidate pruning observable; candidate-generation metrics runnable on real projects) — all of Phase 1's own tests pass cleanly.

## Candidate-generation coverage (measured, not estimated)

Running `spatial_index.coverage_report()` against a synthetic 150-node dense/shuffled page (`test_coverage_report_recall_is_measurably_below_one_on_a_dense_shuffled_page`) reproduces the deep-research report's core finding **against this repository's actual node-construction and windowing code**, not a standalone script: the production 60/12 windowed loop's `window_recall` is measurably below 1.0 on a shuffled dense page. Exact percentages depend on the random seed and node layout (the test asserts `< 1.0`, not a specific figure, since the report itself notes its own 10.8%–19% figures are "not estimates of production performance"). The mechanism is now directly testable against real code, which is the actionable outcome of this phase — a future step can run `coverage_report()` against real project PDFs once they're available (see `repository_evidence.md`'s "still unanswered" items).

## What Phase 1 deliberately did NOT do

- Did not change the default dense-page cap strategy (`legacy_area` remains production default).
- Did not wire `spatial_index.py` into `multimodal/pipeline.py` or `prediction/orchestrator.py` (enforced by a test that will fail loudly if this changes accidentally).
- Did not delete the four dead engineering modules.
- Did not touch any prediction-selection, ranking, fusion, or calibration code.
- Did not add scale/unit detection (only reserved schema placeholder fields — `scale_value`/`scale_source`/`scale_confidence`, all `None` today).

## Recommendation

Phase 1's own exit criteria (`docs/ml_association_phase` plan: "repeated runs are deterministic; all candidate pruning is observable; candidate-generation metrics run on real projects") are met for the *synthetic-fixture* case. The **real-project** case is still open — this environment has no real project PDFs to run `coverage_report()`/the dense-page diagnostics against (see `repository_evidence.md`). Recommend proceeding to **Phase 2 (annotation foundation)** in parallel with sourcing real project PDFs to validate Phase 1's diagnostics against production-scale documents before Phase 3's frozen baselines are cut.
