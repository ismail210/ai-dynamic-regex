# 05 — Testing & Metrics Audit

## Headline finding

**No test in `backend/tests/*.py` calls `services.engineering.structural_graph.build_structural_graph` — the actual graph-builder used in production.** The only test touching graph logic (`test_engineering_pipeline.py`) exercises the lower-level `graph_builder.build_graph`, and only asserts `node_count > 0` and key presence — never edge content, edge types, or thresholds. `structural_graph.py`'s semantic enrichment layer (`_semantic_kind`, the pairwise beam/column/bolt inference, `graph_features_for_source`) has **zero direct test coverage**, confirmed by grepping every test file for `structural_graph` (zero hits).

Also confirmed: `geometry_extractor.py`, `geometry_adapters.py`, and `matching_engine.py` are exercised only by shallow smoke assertions (object counts ≥1, key presence) against a single synthetic PDF containing one rectangle, one line, and one circle — never a curve, leader, dimension, overlapping label, malformed/degenerate geometry, multi-page drawing, or a page dense enough to trigger the 250/60/350 caps documented in `03_geometry_audit.md` and `04_graph_audit.md`.

## Test coverage table

| Test file | Module(s) under test | Type | Notably missing |
|---|---|---|---|
| `test_engineering_pipeline.py` | `geometry_extractor`, `graph_builder.build_graph`, `matching_engine`, `object_confidence`, `suggestion_engine`, `takeoff_interface`, `validation_engine` (engineering/), `excel_loader`, `correction_dataset` | Integration, shallow-assertion | No edge-type/edge-count assertions; no curved/arc geometry; no overlapping labels; no malformed geometry; no multi-page; no dense-page (>250/>60/>350) behavior; no test of `_classify_path`, `_looks_like_leader`, `_looks_like_dimension`, `_attach_nearest_objects` |
| `test_multimodal_pipeline.py` | `document_intelligence`, `extraction_engine`, `pdf_parser`, `token_extractor`, `geometry_adapters` (capability contract only), `correction_engine`, `pipeline`, `fusion_engine` | Integration, smoke | Pipeline test never asserts geometry object count/kind, graph node/edge content, or prediction correctness beyond key presence; no DWG/3DM adapter behavior; `FUSION_WEIGHTS["text"]==0.48` assertion appears stale against `ATTENTION_PRIORS["text"]=0.32` in `modular_fusion.py` — see `06_research_findings.md` |
| `test_ranking.py` | `prediction/ranking.py`, `wildcard_matcher.py` | Unit | Ranking with >2 near-tied candidates; catalog lookup failure mid-ranking |
| `test_wildcard_matcher.py` | `wildcard_matcher.py` | Unit (real catalog) | Multiple ambiguous wildcard positions; malformed mask syntax |
| `test_normalization.py` | `normalization.py` | Unit | Mixed-case+unicode combinations; multi-line/multi-token edge cases |
| `test_exact_section_predictor.py` | `exact_section_predictor.py` | Unit (mocked) | Zero-approved-row training; retrain regression vs. prior version |
| `test_multimodal_correction_engine.py` | `correction_engine.py` | Unit (mocked) | Cross-family corrections (W→HSS misread); conflicting reviewed examples |
| `test_multimodal_validation_engine.py` | `multimodal/validation_engine.py` (the live one) | Unit (synthetic fixtures, no real geometry/graph ever built) | Multiple simultaneous issue types on one token; batch-scale behavior |
| `test_modular_multimodal_fusion.py` | `encoder_contracts`, `encoder_registry`, `modular_fusion` | Unit | Partial-modality fusion; encoder exceptions; >2 near-identical candidates |
| `test_prediction_orchestrator.py` | `contract.py`, `orchestrator.py`, `suggestion_engine.py` | Unit (geometry/graph/rules all mocked out) | Orchestrator behavior on AI-prediction failure; multi-candidate wildcard orchestration |
| `test_calibration.py` | `calibration.py` | Unit | Non-monotonic distributions; all-one-class labels; re-fit after new approvals |
| `test_canonical_contract.py` | `canonical_contract.py` | Unit | >2-candidate near-ties; malformed bbox inputs |
| `test_documents_api.py` | FastAPI routes end-to-end | Integration (real TestClient + real PDF) | Concurrent uploads; corrupt/oversized PDFs; multi-page documents; auth (none exists) |
| `test_takeoff_platform.py` | `takeoff/*`, `entity_taxonomy` | Mixed (parsing real, AI pipeline mocked) | Length/weight-accuracy formula never independently stress-tested; graph-derived matching untested since `run_multimodal_pipeline` is mocked in the end-to-end test |
| `test_continuous_learning_pipeline.py` | `training_pipeline/*` | Unit (heavy mocking) | Partial-metric-regression promotion gate; concurrent dataset-registry writes |
| `test_entity_diagnostics.py`, `test_feature_pipeline.py` | `entity_diagnostics`, `feature_extractor`, `preprocessing_pipeline`, `training_service` | Unit | Non-square confusion matrices; class imbalance |

**Frontend** (`predictionContract.test.js`, `ResultsPage.test.jsx`, `AnalysisContext.test.jsx`, `AppLayout.test.jsx`, `PredictionExplainability.test.jsx`): all unit/component-level with fully mocked data; none exercise a real backend call or a real geometry/graph payload.

## Geometry/graph logic with zero test coverage

- `structural_graph.py` — **entire file**: `_semantic_kind`, `_edge`, `build_structural_graph`'s pairwise inference (near/above/below/supports/connected_to/inside with their distance thresholds), `source_features` computation (the `graph_consistency` formula that actually reaches prediction), `graph_features_for_source`.
- `geometry_extractor.py` — `_attach_nearest_objects`, `_classify_path` (never exercised with a curve or ambiguous shape), `_is_closed`, `_looks_like_leader`, `_looks_like_dimension`, `_nearby_text`.
- `graph_builder.py` — `_intersects`/`_contains`/`_touches` predicates and their hardcoded tolerances; `_classify_text_node`; no test asserts a specific edge was or wasn't created, or checks a `relationship` value.
- `matching_engine.py` — `_geometry_linked_labels`, `_check_size_mismatches`, `_closest_shape` — untested (module is also dead in production, see `04_graph_audit.md §9`).
- `geometry_adapters.py` — `extract_geometry_document()` itself (the wrapper actually called in production) is never directly unit tested; only its capability-metadata siblings are.

None of these are exercised with: curved/arc members, overlapping/stacked labels, degenerate geometry (zero-length segments, self-intersecting polygons), multi-page cross-references, or drawings large enough to hit the 250/60/350-node caps.

## What the evaluation scripts actually measure

### `backend/scripts/evaluate_pipeline.py` (4 sections)

- **Section A — extraction fidelity**: `raw_text_exact_match_rate`, `normalized_match_rate`, `source_text_coverage`, `page_number_coverage`, `bounding_box_coverage` — measures whether *provenance* was captured, not whether geometry/entities were correctly extracted.
- **Section B — prediction performance**: genuine `top_1_accuracy`, `top_3_accuracy`, `top_5_accuracy`, `candidate_generation_recall`, broken out `accuracy_by_family`/`accuracy_by_corruption_type`, `wildcard_resolution_accuracy` — but computed over `approved_dataset.csv`, the **same dataset also used for calibration fitting and continuous-learning training splits** (per `test_calibration.py`/`test_continuous_learning_pipeline.py`), so there is no confirmed train/eval separation — reported accuracy may be optimistic relative to true generalization.
- **Section C — review behavior**: `correction_acceptance_rate`, `manual_review_rate_on_holdout`, `unresolved_rate_on_holdout` — the only manual-review-rate metric in the codebase.
- **Section D — confidence**: calibration fit status + a crude 3-band (`high/medium/low`) empirical-accuracy reliability check — not a formal ECE or Brier score.

### `backend/services/takeoff/ground_truth_evaluation.py`

Treats each canonical section label (quantity-summed across the whole document) as the unit of comparison: `precision = TP/(TP+FP)`, `recall = TP/(TP+FN)`, `f1`. This is **label-set precision/recall**, not per-instance or per-geometry-object association accuracy. Also computes `quantity_accuracy`, `quantity_coverage` (normalized absolute error), `length_accuracy` (±8%/±0.5 tolerance), `weight_accuracy` (±10%/±1.0 tolerance), `member_accuracy`.

## Gap list vs. a full geometry/graph metric suite

| Target metric | Currently measured? | Notes |
|---|---|---|
| Geometry extraction accuracy | **No** | No geometry ground truth exists anywhere in the repo |
| Entity detection recall | **No** | Closest proxy (`candidate_generation_recall`) measures label-candidate generation, not "was a real member found" |
| Label extraction accuracy | Partial | Conflated with comparison-status logic in Section A, not isolated |
| Candidate-generation recall | **Yes** | `evaluate_pipeline.py` Section B |
| Label-to-geometry association accuracy | **No** | `_attach_nearest_objects` / graph `nearest_geometry` untested and unmeasured |
| Graph edge precision/recall | **No** | No ground-truth edge set exists |
| Graph connectivity correctness | **No** | `structural_graph.py` stats are descriptive counts, not correctness checks |
| Top-1 / top-k accuracy | **Yes** | Section B |
| Calibration | **Partial** | Fit-status + 3-band accuracy, not ECE/Brier; and calibration is structurally never fit today — see `06_research_findings.md`/`04_graph_audit.md` cross-reference |
| Manual-review rate | **Yes** | Section C |
| Escaped-error rate | **No** | No mechanism tracks auto-accepted predictions later proven wrong |
| Quantity error | **Yes** | `ground_truth_evaluation.py` |
| Project-level (multi-document) performance | **No** | Everything is per-document/per-row; no cross-document rollup |
| Runtime / memory | **No** | `inference_time_ms` exists in pipeline summaries but is never aggregated or reported |

## Recommended metric suite for geometry and graph quality specifically

To be added (see `08_prioritized_roadmap.md` for sequencing) — definitions, not yet implemented:

- **Node precision/recall**: of geometry objects a human would call "a real structural line," what fraction did extraction produce (recall), and of what extraction produced, what fraction are real (precision)? Requires a small hand-annotated set of pages.
- **Edge precision/recall**: of the `nearest_label`/`nearest_geometry`/`connected_to`/`supports` edges the graph emits, what fraction match a human-annotated "this label really refers to this member" ground truth?
- **Relation-type F1**: per relation type (parallel, perpendicular, contains, connected), precision/recall against hand-labeled pairs on a held-out set of drawings.
- **Association top-k recall**: for each label, is the *correct* geometry object within the top-k nearest candidates the system considered (not just the single greedy pick)?
- **Connected-component accuracy**: does the graph's connected-component structure match the human notion of "these nodes belong to the same assembly/detail"?
- **Graph edit distance** (where practical, likely only for small hand-labeled fixtures): edits needed to transform the produced graph into the ground-truth graph.
- **Member-axis endpoint error / orientation error / length error**: for member-shaped geometry, distance between extracted and true endpoints/orientation/length, in real-world units once scale-awareness exists (`03_geometry_audit.md`).
- **Spatial-link false-positive rate**: fraction of emitted edges (any relation type) that a human would reject as spurious.
- **Cross-detail contamination rate**: fraction of edges/associations that incorrectly link entities from two different details/regions on the same sheet — currently unmeasurable because no detail-region concept exists (`04_graph_audit.md §13`).
- **Candidate-generation recall**: already implemented (Section B) — keep, but confirm/fix train/eval separation.
- **Project-level exact-match rate**: fraction of whole documents where every predicted section label + quantity exactly matches ground truth — currently no project-level rollup exists.

## Open questions

See `09_open_questions.md`. Key ones: whether `evaluate_pipeline.py` Section B is ever run against genuinely held-out data; whether `structural_graph.py`'s complete absence from the test suite is a known/tracked gap; and whether any hand-annotated geometry/graph ground truth exists outside the paths reviewed (the untracked `ai-dynamic-regex/` nested directory and the `.gitignore`'d artifact directories were not inspected for content).
