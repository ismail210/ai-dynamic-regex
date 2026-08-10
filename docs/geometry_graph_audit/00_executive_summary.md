# 00 — Executive Summary

This audit covers the entire Estima3D repository (`backend/` FastAPI service, `frontend/` React app), with deep focus on geometry processing and graph/relationship construction as requested. Full detail is in files `01`–`09` and `algorithm_registry.csv` in this directory. This summary states conclusions; it does not repeat the evidence — see the linked files for file:line citations.

## What is currently implemented (one paragraph)

Estima3D extracts vector geometry from PDF drawings via PyMuPDF (raw, unscaled PDF-point coordinates, no unit/scale normalization anywhere), classifies each path by shape syntax and size (line/polyline/curve/rectangle/circle, plus narrow leader/dimension heuristics — no beam-vs-grid-line-vs-hatch distinction exists), and separately extracts text tokens. A graph (`graph_builder.py` → `structural_graph.py`) links text and geometry nodes via nearest-neighbor search and bbox-topology rules, then reclassifies nodes semantically by regex over nearby text. That graph's *topology* is not read back for prediction — only five scalar aggregates (degree, structural links, graph consistency) flow into a softmax-attention-weighted fusion of six evidence modalities (text/OCR/layout/geometry/graph/engineering-rules) that selects the final AISC section label; the catalog itself never overrides this selection, only verifies it. Confidence calibration exists in code but is structurally inert today (the training dataset schema lacks the columns needed to fit it). Four of the ten graph/matching-related backend modules are fully built but unreachable from any router — dead code in the live path.

## The five most important geometry findings

1. **No coordinate/unit/scale normalization exists anywhere.** Every geometric threshold in the codebase — leader length, dimension length, symbol-size cutoff, grid-index cell sizes — is a raw-PDF-point magic number. `GeometryDocument.units="pdf_points"` is honestly labeled but never used downstream. Behavior silently drifts across drawings plotted at different scales. (`03_geometry_audit.md §2-5`)
2. **A dense-page drawing cap has a real correctness bug**: when a page exceeds 250 raw drawings, the code keeps the largest-bbox-area 250 — but axis-aligned lines have bbox area of exactly 0, so clean orthogonal beam/column/grid lines are the *first* to be silently dropped on complex CAD-exported pages, opposite of the code's own stated intent. (`03_geometry_audit.md §7`)
3. **No collinear/fragmented line merging exists.** A member split into multiple path fragments by a CAD export becomes multiple unrelated geometry objects with no reconciliation step. (`03_geometry_audit.md §6`)
4. **Geometry classification carries no structural semantics.** Beams, grid lines, dimension lines, borders, and hatch strokes are distinguished only by later text-proximity regex matching, never by the geometry's own shape/length/orientation/layer. (`03_geometry_audit.md §8`)
5. **Pairwise geometric relationships (parallel, intersects, contains, connected) are computed over a list-order-windowed loop, not a spatial index** — on any page exceeding ~60 geometry objects, spatially-adjacent pairs that happen to be far apart in PDF-extraction order are silently never compared. (`03_geometry_audit.md §10, 13`)

## The five most important graph findings

1. **The graph's topology never reaches the final prediction — only five scalar numbers do.** `GeometryFeatureProvider` (the thing that actually supplies geometry evidence for ranking) runs its own independent nearest-neighbor search, bypassing `graph["edges"]` entirely. Which specific geometry a label was graph-linked to (beam vs. leader vs. detail box) is computed but never used. (`04_graph_audit.md §9`, worked example)
2. **Four of ten graph/matching modules are dead code in production** (`matching_engine.py`, `suggestion_engine.py`, `validation_engine.py`, `object_confidence.py`) — feature-complete, only reachable from tests. This needs a product decision (wire in or delete), not more engineering in isolation. (`04_graph_audit.md §9`, roadmap P0.5)
3. **Leaders are not resolved through to their target.** A leader/arrow competes as an ordinary node in nearest-neighbor search; if it's centroid-closer to a label than the true target member, the label's one association edge points at the leader. (`04_graph_audit.md §4`, worked example)
4. **Association is greedy single-best, not globally optimal, and non-exclusive.** Each node picks its own nearest neighbor independently with no bipartite constraint, allowing unconstrained many-to-one fan-in with no conflict detection, and no alternative hypotheses survive at the graph layer once a nearest match is picked. (`04_graph_audit.md §4, §6`)
5. **The same relationship (e.g. "connected_to") is computed by two independent code passes with different thresholds and different fixed confidences, and the same geometric fact is deliberately emitted under two different relation names** (`intersection`+`intersects`, `containment`+`inside`, `connected`+`connected_to`) — any consumer checking only one name gets a partial, inconsistent picture of connectivity. Node/edge IDs are also non-deterministic (unseeded UUID4), so identical documents produce different `graph.json` on every run. (`04_graph_audit.md §2, §7, §12`)

## The highest-risk current algorithm

**The 250-drawing dense-page cap in `geometry_extractor.py` (§2 above).** It is the single finding in this audit that is both (a) a clear, unambiguous logic bug — not a design tradeoff — and (b) most likely to silently degrade exactly the documents this system is meant to handle well: complex, CAD-exported structural sheets with many orthogonal members. It has zero test coverage (the only geometry test fixture has 3 shapes total) and produces no diagnostic signal when it fires, so it could be actively harming production accuracy today without anyone knowing.

## The best immediate improvement

**Fix the 250-drawing cap's sort key (`08_prioritized_roadmap.md` P0.1), paired with adding coverage diagnostics (P0.3) and making graph node/edge IDs deterministic (P0.2).** All three are small (well under a week combined), require no schema or API changes, and directly address the highest-risk bug plus the "we can't currently tell when coverage silently degrades" observability gap that makes every other geometry/graph problem harder to detect and prioritize.

## The strongest medium-term research direction

**Replace the ad hoc uniform grids and list-order-windowed pairwise loops with a real spatial index (STRtree/R-tree), then add bipartite (Hungarian) matching for label-to-geometry association, before considering anything learned.** This is not a GNN recommendation — the data volume and graph-ground-truth quality needed for a GNN don't exist yet, and the deterministic graph output itself is currently unreliable enough (list-order-dependent, non-deterministic IDs, duplicate relation names) that training a learned model on it today would mean learning to reproduce its artifacts rather than true structure. The right sequence is: fix the deterministic graph (P1), build a hand-annotated ground-truth set in parallel (P2.1), then evaluate a much cheaper tabular learned edge classifier before ever considering a GNN. Full reasoning in `06_research_findings.md`.

## What should not be changed yet

- **Confidence calibration mechanics** (`calibration.py`) — the isotonic-regression implementation itself is sound; the blocker is a dataset-schema gap (P2.4), not the algorithm. Don't rewrite it; extend the approved-dataset schema instead.
- **The attention-fusion scoring approach** (`modular_fusion.py`) — it's a reasonable, explainable, deterministic-inference design (softmax over log-prior × quality). The problems found are in what feeds it (unreliable graph aggregates, duplicated upstream scoring logic), not the fusion mechanism itself.
- **Any move to GNNs or LLM-based geometric reasoning** — explicitly not warranted yet; see research direction above and the guardrails in `06_research_findings.md`.
- **The four dead graph/matching modules should not be silently deleted without a decision** — they represent real, non-trivial engineering effort and may reflect intended-but-unfinished integration; a product decision is needed first (P0.5).

## Reports created

`docs/geometry_graph_audit/`: `00_executive_summary.md` (this file), `01_workflow_map.md`, `02_logic_inventory.md`, `03_geometry_audit.md`, `04_graph_audit.md`, `05_testing_metrics_audit.md`, `06_research_findings.md`, `07_target_architecture.md`, `08_prioritized_roadmap.md`, `09_open_questions.md`, `algorithm_registry.csv`.

## Blockers / unanswered questions

See `09_open_questions.md` for the full list (23 items). The most consequential for planning: (1) whether the four dead graph/matching modules are intentionally staged or orphaned — blocks P0.5; (2) whether a hand-annotated geometry/graph ground truth already exists somewhere unexamined — blocks sequencing of P2.1; (3) domain-expert input on acceptable association-error tolerance in dense connection details — shapes how aggressively P1.4/P1.6 should be tuned. No production code was modified during this audit, per the guardrails.
