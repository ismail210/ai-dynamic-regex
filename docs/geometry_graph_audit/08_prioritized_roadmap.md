# 08 — Prioritized Improvement Roadmap

## P0 — Correctness and observability

### P0.1 — Fix the 250-drawing-cap sort bug
- **Problem**: `geometry_extractor.py:292-305` sorts by raw bbox area to decide which drawings survive on dense pages; axis-aligned lines have area=0 and are dropped first, the opposite of the stated intent.
- **Change**: sort by a metric that doesn't penalize zero-area axis-aligned lines (e.g. `max(length, area)`, or exclude the area=0 special case explicitly).
- **Files**: `backend/services/engineering/geometry_extractor.py`
- **Dependencies**: none
- **Tests required**: new fixture PDF with >250 drawings including axis-aligned lines; assert lines survive
- **Metrics affected**: geometry extraction completeness on dense pages
- **Migration risk**: low — isolated function, single sort key change
- **Effort**: 0.5–1 day
- **Acceptance criteria**: a synthetic dense-page fixture with 300 orthogonal lines + 50 hatch fills retains the lines over the hatches when capped to 250

### P0.2 — Make graph node/edge IDs deterministic
- **Problem**: `_nid()` uses unseeded `uuid.uuid4()`; identical documents produce different `graph.json` byte-for-byte, breaking diffing/caching and undermining any future ground-truth comparison.
- **Change**: derive `node_id`/`edge_id` from `source_id` (+ relation, for edges) via a stable hash, not a random UUID.
- **Files**: `backend/services/engineering/graph_builder.py`
- **Dependencies**: none
- **Tests required**: run the same document twice, assert identical `graph.json`
- **Metrics affected**: enables all future graph-diffing/regression tooling
- **Migration risk**: low — any consumer keying off `source_id` already (most do) is unaffected
- **Effort**: 0.5 day
- **Acceptance criteria**: two runs of the same document produce byte-identical `graph.json`

### P0.3 — Add graph/geometry diagnostics to pipeline output
- **Problem**: no visibility today into how many drawings were dropped by the 250-cap, how many pairs were skipped by the 60/350-item windowing, how many geometry objects got no `nearest_label` edge, etc.
- **Change**: add a `diagnostics` block to `geometry.json`/`graph.json` recording: `drawings_dropped_by_cap`, `pairs_skipped_by_window`, `isolated_geometry_nodes`, `isolated_text_nodes`.
- **Files**: `geometry_extractor.py`, `graph_builder.py`, `structural_graph.py`
- **Dependencies**: none
- **Tests required**: assert diagnostics populate correctly on a known-dense fixture
- **Metrics affected**: makes silent coverage loss visible for the first time
- **Migration risk**: low, additive fields only
- **Effort**: 1–2 days
- **Acceptance criteria**: a dense fixture shows non-zero `pairs_skipped_by_window`; a normal fixture shows zero

### P0.4 — Centralize the "how far is nearby" constant
- **Problem**: three independently-tuned distance constants for the same concept: `graph_builder.max_edge_distance=160.0`, `structural_graph.max_near_distance=180.0`, `validation_engine.far_label_distance=140.0` (dead code).
- **Change**: one shared constant/config value, with the option to override per relation type explicitly (not accidentally, via copy-paste drift).
- **Files**: `graph_builder.py`, `structural_graph.py`, `config.py`
- **Dependencies**: none
- **Tests required**: regression test confirming edge counts don't silently change when the constant is centralized
- **Metrics affected**: graph edge consistency
- **Migration risk**: medium — changing an effective threshold changes edge counts; needs a before/after regression comparison on real fixtures
- **Effort**: 1 day

### P0.5 — Remove or wire in the four dead graph/matching modules
- **Problem**: `matching_engine.py`, `suggestion_engine.py`, `validation_engine.py` (`engineering/`), `object_confidence.py` are fully built but unreachable from any router or live pipeline — confirmed by import grep.
- **Change**: a product decision, not just engineering — either delete (if genuinely obsolete) or wire into `multimodal/pipeline.py` (if intended functionality). Either way, resolve the ambiguity; do not leave feature-complete code silently dead.
- **Files**: the four modules + `multimodal/pipeline.py` if wiring in
- **Dependencies**: requires a decision from whoever owns the roadmap — see `09_open_questions.md`
- **Tests required**: if wired in, full test coverage per `05_testing_metrics_audit.md`'s gap list; if removed, confirm no hidden callers first
- **Metrics affected**: n/a directly, but resolves a major "is this actually running" ambiguity for every future contributor
- **Migration risk**: low if removing (confirmed no live callers); medium if wiring in (changes live prediction behavior)
- **Effort**: 0.5 day to decide + delete, OR 1–2 weeks to properly wire in with tests

### P0.6 — Fix the `intersection`/`intersects`, `containment`/`inside`, `connected`/`connected_to` duplicate-relation-name pattern
- **Problem**: each pair name encodes one geometric fact but is emitted as two different relation strings; consumers checking only one name get a partial picture (`04_graph_audit.md §2`, §12).
- **Change**: emit one canonical relation name per fact, with a `direction` field for the reverse sense where needed, instead of two separate dict entries.
- **Files**: `graph_builder.py`
- **Dependencies**: any consumer currently checking specific relation-name sets (`validation_engine.py`, dead) needs updating
- **Tests required**: assert exactly one edge per geometric fact
- **Metrics affected**: graph edge count (roughly halves for these three relation families), connectivity metrics become accurate
- **Migration risk**: medium — any downstream code checking relation-name sets must be re-audited (this audit found `validation_engine.py` already under-counts because of this; fixing it changes that count)
- **Effort**: 1–2 days

## P1 — Strong deterministic improvements

### P1.1 — Scale-aware tolerances
- **Problem**: every geometric threshold in the codebase is a raw-PDF-point magic number; behavior silently drifts across drawings plotted at different scales.
- **Change**: detect drawing scale (title-block text pattern matching, e.g. `1/4"=1'-0"`, or a known reference dimension), carry a `scale_factor` alongside `GeometryDocument`, convert key thresholds (leader length, dimension length, nearby-text radius, grid cell sizes) to real-world-unit-derived values.
- **Files**: `geometry_extractor.py`, `geometry_adapters.py`, `document_intelligence.py` (title-block detection already partially exists there — reuse it), `models.py`
- **Dependencies**: P0.3 diagnostics helps validate this incrementally
- **Tests required**: fixtures at two different plotted scales with equivalent real-world content, assert equivalent classification results
- **Metrics affected**: geometry extraction accuracy, cross-detail contamination rate (new metric from `05_testing_metrics_audit.md`)
- **Migration risk**: medium-high — touches most geometry thresholds; needs careful staged rollout with the diagnostics from P0.3 as a safety net
- **Effort**: 1–2 weeks
- **Acceptance criteria**: two fixtures depicting the same real-world beam at different plot scales classify identically

### P1.2 — Replace uniform grids + windowed loops with a real spatial index
- **Problem**: four independently-tuned uniform grids plus two list-order-windowed pairwise loops (`page_geom[:60]` window-12, `page_nodes[:350]` window-44) silently miss spatially-proximate pairs on dense pages.
- **Change**: adopt `shapely.strtree.STRtree` (or an equivalent R-tree) for all "find nearby entities" queries, replacing both the ad hoc grids and the windowed loops.
- **Files**: `geometry_extractor.py`, `pdf_parser.py`, `graph_builder.py`, `structural_graph.py`
- **Dependencies**: P0.3 diagnostics (to measure the before/after coverage improvement directly)
- **Tests required**: dense-page fixture (>350 objects) with known spatially-proximate-but-list-distant pairs; assert relations are now found
- **Metrics affected**: spatial-link false-positive rate, association top-k recall (new metrics)
- **Migration risk**: medium — changes which edges get created on dense pages (a correctness improvement, but a behavior change requiring regression review)
- **Effort**: 3–5 days

### P1.3 — Line-segment consolidation (collinear/fragmented merging)
- **Problem**: no merging exists; CAD-exported fragmented members become multiple unrelated geometry objects.
- **Change**: post-extraction pass clustering near-collinear, endpoint-proximate segments into one merged member candidate, with `merged_from` provenance retained.
- **Files**: new module, e.g. `geometry_normalizer.py`, invoked after `geometry_extractor.extract_geometry`
- **Dependencies**: P1.1 (merge tolerance should be scale-aware, not another raw-point magic number)
- **Tests required**: fixture with a deliberately-fragmented member (2-3 collinear segments), assert one merged candidate results
- **Metrics affected**: member-axis endpoint error, geometry extraction accuracy
- **Migration risk**: medium — changes geometry object counts and IDs downstream; needs the `normalized_geometry.json` artifact split proposed in `07_target_architecture.md` to avoid breaking existing consumers of raw `geometry.json`
- **Effort**: 3–5 days

### P1.4 — Detail-region segmentation
- **Problem**: no concept of "these entities belong to the same detail view"; multi-detail pages are one flat pool.
- **Change**: cluster geometry/text by large-rectangle containment + whitespace-gap heuristics into `DrawingRegion` records (`07_target_architecture.md` schema); use region membership as a required-match filter before generating association candidates (prevents cross-detail contamination).
- **Files**: new module + `graph_builder.py` (filter candidates by region before nearest-neighbor search)
- **Dependencies**: P1.1, P1.2
- **Tests required**: fixture with 2 side-by-side details containing similarly-named members; assert no cross-detail association
- **Metrics affected**: cross-detail contamination rate (new metric)
- **Migration risk**: medium
- **Effort**: 1–2 weeks

### P1.5 — Typed evidence-graph relations, remove duplicate meanings
- **Problem**: `connected_to`/`above`/`below`/`inside` mean different things depending on which of the two passes (`graph_builder.py` vs `structural_graph.py`) emitted them, with different thresholds and no reconciliation.
- **Change**: adopt the `EvidenceRelation` typed-enum + always-populated `confidence`/`provenance` schema from `07_target_architecture.md`; stop `structural_graph.py` from overwriting `node["kind"]` in place — write hypotheses as separate linked records instead (preserves original evidence classification).
- **Files**: `graph_builder.py`, `structural_graph.py`, `models.py`
- **Dependencies**: P0.6
- **Tests required**: full new unit test suite for both modules per `05_testing_metrics_audit.md`'s gap list — this is the single highest-value test-coverage addition in the whole roadmap
- **Metrics affected**: edge precision/recall, relation-type F1 (new metrics, but this change is a prerequisite for measuring them meaningfully)
- **Migration risk**: medium-high — this is a schema change; requires updating every consumer of `node["kind"]`/`edge["relationship"]`
- **Effort**: 1–2 weeks

### P1.6 — Bipartite matching for label↔geometry association
- **Problem**: today's greedy per-node nearest-neighbor pick allows unconstrained many-to-one fan-in with no global optimum, and doesn't resolve conflicts when two labels both want the same nearest geometry.
- **Change**: replace the greedy `nearest_label`/`nearest_geometry` loops with a Hungarian-algorithm (or similar) bipartite assignment per page/region, retaining top-k alternatives per node rather than collapsing to one.
- **Files**: `graph_builder.py`
- **Dependencies**: P1.2 (needs a spatial index to build the candidate cost matrix efficiently), P1.4 (region membership bounds the matching problem to a tractable size)
- **Tests required**: fixture with 2 labels competing for 1 geometry object; assert the matching resolves the conflict instead of both silently pointing at it
- **Metrics affected**: association top-k recall, edge precision
- **Migration risk**: medium
- **Effort**: 1 week

### P1.7 — Leader-aware association
- **Problem**: a leader/arrow is just another competing node in nearest-neighbor search; there's no "resolve through the leader to its far endpoint" logic.
- **Change**: detect leader endpoints explicitly (near end = label side, far end = target side) and use the far endpoint, not the leader's own centroid, as the association candidate.
- **Files**: `geometry_extractor.py` (leader endpoint identification), `graph_builder.py` (use far endpoint in nearest-neighbor search)
- **Dependencies**: P1.1
- **Tests required**: fixture with a label connected via a leader to a member 200pt away (outside today's naive radius) — assert correct association
- **Metrics affected**: association top-k recall
- **Migration risk**: low-medium
- **Effort**: 3–5 days

### P1.8 — Consolidate the 4-7x duplicated normalization/family-list/confidence-banding logic
- **Problem**: normalization rules, family-prefix lists, and confidence-level banding are each independently reimplemented 3-7 times across the codebase (`02_logic_inventory.md`).
- **Change**: one canonical module per concept, imported everywhere.
- **Files**: `normalization.py`, `entity_taxonomy.py`, `feature_extractor.py`, `wildcard_matcher.py`, `exact_section_predictor.py`, `correction_engine.py`, `confidence_engine.py`, `contracts.py`, `contract.py`, `predictionContract.js`
- **Dependencies**: none, but touches many files — do incrementally, one concept at a time
- **Tests required**: existing tests should continue passing; add a test asserting all consumers agree on family-prefix membership
- **Metrics affected**: maintainability, not accuracy directly — but reduces future drift risk
- **Migration risk**: low per-change if done incrementally
- **Effort**: 3–5 days total across all instances

## P2 — Learned improvements

### P2.1 — Build a hand-annotated geometry/graph ground-truth set
- **Problem**: zero ground truth exists for geometry extraction correctness or graph edge correctness (`05_testing_metrics_audit.md`) — a prerequisite for any learned component and for meaningfully measuring the P1 improvements above.
- **Change**: hand-annotate a modest set (dozens to low-hundreds) of real drawing pages with correct geometry objects, correct label-to-geometry associations, and correct relation edges.
- **Files**: new `backend/training/geometry_graph_ground_truth/` dataset + a small annotation format spec
- **Dependencies**: none — can start immediately, in parallel with P1
- **Tests required**: this *is* the test data; wire it into the new metric suite from `05_testing_metrics_audit.md`
- **Metrics affected**: enables node/edge precision-recall, association top-k recall, connected-component accuracy
- **Migration risk**: none (purely additive)
- **Effort**: ongoing, front-load 1-2 weeks for tooling + first batch

### P2.2 — Tabular learned edge classifier
- **Problem**: today's edge-generation thresholds (8° angle, 90/70/55pt distance gates, fixed confidences 0.72-0.82) are hand-tuned with no documented derivation.
- **Change**: once P2.1's ground truth exists, train a gradient-boosted-tree classifier (reusing the existing `training_service.py` RF/SVM/XGBoost comparison pattern) on engineered edge features (distance, angle, bbox overlap, kind pair) to replace hand-tuned thresholds.
- **Files**: new `services/engineering/edge_classifier.py`, reusing `training_service.py` patterns
- **Dependencies**: P2.1, P1.5 (typed edges give cleaner training labels)
- **Tests required**: held-out accuracy vs. the deterministic baseline; must beat it to justify the added complexity
- **Metrics affected**: edge precision/recall
- **Migration risk**: medium — introduces a model artifact into a previously fully-deterministic path; needs a fallback to the rule-based version if the model is unavailable (mirroring `model_predictor.py`'s existing fallback pattern)
- **Effort**: 1-2 weeks once ground truth exists

### P2.3 — Learned association ranker
- **Problem**: `exact_section_predictor._score_candidates`'s rerank weights (0.68/0.05/0.18/0.09 + orientation nudges) are hand-tuned, as is `correction_engine`'s 6-weight blend.
- **Change**: once enough labeled correction/approval history accumulates, fit a small learned reranker (logistic regression or gradient-boosted trees over the same features) and compare against the hand-tuned baseline.
- **Files**: `exact_section_predictor.py`, `correction_engine.py`
- **Dependencies**: sufficient approved-dataset volume; P2.1 not strictly required for this one (uses label-approval history, not geometry ground truth)
- **Tests required**: A/B comparison against current heuristic on held-out data
- **Metrics affected**: top-1/top-k accuracy
- **Migration risk**: medium
- **Effort**: 1-2 weeks

### P2.4 — Fix confidence calibration (make it actually fire)
- **Problem**: `calibration.py`'s isotonic regression is fully implemented but structurally never fires — `dataset_manager.APPROVED_COLUMNS` doesn't record `ranking_score`/`correct`, so `calibrate_score()` always returns `(None, False)`.
- **Change**: extend the approved-dataset schema to record the `ranking_score` that produced each approval and an explicit correct/incorrect label; backfill if feasible.
- **Files**: `dataset_manager.py`, `calibration.py`
- **Dependencies**: none
- **Tests required**: assert calibration fires and produces a genuine `final_confidence` once ≥50 real labeled rows exist
- **Metrics affected**: calibration (ECE/reliability), user trust in displayed confidence
- **Migration risk**: low — purely additive schema field
- **Effort**: 2-3 days
- **Note**: this is arguably P0/P1-adjacent (it's a bug fix for an existing, already-integrated feature, not new ML) — sequenced here because it depends on dataset-schema coordination, but should not wait for the rest of P2

### P2.5 — GNN experimentation
- **Problem**: N/A — no current evidence this is needed.
- **Change**: **explicitly deferred.** Revisit only after P2.1 (ground truth) exists at meaningful scale (hundreds+ annotated pages) and P2.2 (tabular classifier) has been tried and shown to leave a real, measured gap. Do not start this in parallel with P1 — the deterministic graph output feeding it isn't trustworthy yet (`06_research_findings.md`'s readiness assessment).
- **Effort**: not estimated — out of scope until prerequisites are met

## Smallest useful slice to improve geometry-to-label association without rewriting the pipeline

**P0.2 (deterministic IDs) + P0.3 (diagnostics) + P1.2 (spatial index) + P1.7 (leader-aware association)**, in that order. This sequence:
- Requires no schema changes visible to the frontend or API contract
- Directly fixes the two concrete association failure modes this audit found (windowed-loop spatial blindness, leader-vs-target-member confusion)
- Produces measurable before/after diagnostics (P0.3) to prove the improvement without needing the full P2.1 ground-truth investment first
- Is achievable in roughly 1–1.5 weeks total, touching only `geometry_extractor.py` and `graph_builder.py`
