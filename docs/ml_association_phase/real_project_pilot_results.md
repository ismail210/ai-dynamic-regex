# Real-Project Pilot Results (Phase 2.5)

Master summary. Companion documents: `real_project_inventory.md`, `real_project_page_profile.md`, `real_project_pilot_manifest.json`, `real_project_excel_assessment.md`, `real_project_error_taxonomy.md`, `real_project_annotation_status.md`, `phase3_readiness_decision.md`.

## Corpus

- **7 PDFs, 7 Excel workbooks, 7 projects** (1:1 PDF/Excel per project), all born-digital/vector, none encrypted or corrupted.
- **262 total PDF pages.**
- Page types (heuristic classification): 77 structural framing plan, 64 general notes, 38 detail sheet, 25 unknown, 23 member schedule, 17 section/elevation, 9 connection schedule, 6 architectural/non-structural, 3 title/cover.
- Vector vs. scanned: **262/262 (100%) vector/born-digital**, 0 scanned pages found in this archive.

## Pilot pages selected

**11 real pages processed** (of 13 planned selections; 2 categories — rotated page, scan-heavy page — had no naturally-occurring example in this corpus and were explicitly documented as unavailable rather than fabricated). Full justification per page in `real_project_pilot_manifest.json`. All 7 projects are represented at least once.

## Extraction reliability

**Zero extraction failures or exceptions across all 262 real pages of all 7 real PDFs** — the unmodified production extraction path (`pdf_parser.extract_document_structure` → `geometry_extractor.extract_geometry` → `graph_builder.build_graph`) ran to completion on every page. Total extraction runtime across the corpus: ~114 seconds for all 262 pages (~0.02–1.25s/page depending on density).

## Dense-page cap frequency (real data)

**The 250-drawing cap triggered on 229/262 pages (87.4%)** — the normal case for this corpus, not an edge case. Raw per-page drawing counts ranged up to 53,146 (median 4,970).

## Graph-window trigger frequency (real data)

- **60-object window: 233/262 pages (89.0%).**
- **350-node semantic window: 0/262 pages (never).**
- On the 11 pilot pages specifically, direct STRtree-vs-windowed-loop measurement (`spatial_index.coverage_report`) showed the production windowed loop achieves **1.7%–17.2% recall of the spatially-complete relationship set, averaging 7.4%** — i.e. on a typical real dense page, roughly 92.6% of genuinely-close geometry pairs are never compared for PARALLEL/PERPENDICULAR/INTERSECTS/CONTAINS/CONNECTED relationships. This sharpens both Phase 1's synthetic-fixture estimate (10.8%–19%) and the original deep-research report's synthetic experiment with real, worse numbers.

## Labels and label groups

- **8,356 regex-matched steel labels detected across 177/262 pages (67.6%)** in the full-corpus page profile.
- **1,253 total label groups built across the 11 pilot pages** (full population, not just the exported review batch).
- **Average 7.84 candidates/group, median 10** (top_k cap) — candidate generation finds substantial real content.
- **44/1,253 groups (3.5%) have zero real candidates** (no-valid-target-only) — candidate coverage is generally good at `max_distance=160`, `top_k=10`.

## Candidate-generation findings — headline result

**The current production heuristic (`graph_builder.build_graph`'s greedy single-pick `nearest_geometry` edge) selected a leader stroke itself — not a real structural member — as its final association in 243 of 843 heuristic-selected label groups across the 11 real pilot pages (28.8%), measured population-wide, not just on a curated sample.** This is a direct, quantified, real-data confirmation of the exact failure mode `docs/geometry_graph_audit/04_graph_audit.md §4` predicted from static code analysis alone, and was additionally confirmed by direct visual inspection of a rendered page crop (see `real_project_error_taxonomy.md` #1) showing the production pick sitting on empty space beside a leader stroke while the experimental candidate generator's leader-resolved alternative correctly landed on the real member the leader pointed at.

No confirmed-correct recall@K (recall@1/3/5/10 against reviewed truth) can be reported — **no human review occurred in this phase** (see `real_project_annotation_status.md`), so there is no ground truth yet to measure recall against. Reporting a recall number here would violate the pilot spec's own instruction not to present percentages without a real numerator/denominator of *reviewed* truth.

## STRtree vs. production nearest-geometry comparison

Beyond the raw pairwise-relationship recall above, the experimental candidate generator's leader-resolution logic surfaced real, better alternatives to the production heuristic's pick in a large fraction of leader-involving groups (all 243 leader-mis-selected cases above are, by construction, cases where the experimental generator's leader-resolved candidate is available as an alternative in the same group). Whether the experimental generator's *top pick* would out-perform production requires a global-resolution/ranking step this pilot does not implement (that is squarely Phase 4+ scope).

## Leader issues

Two distinct, real leader-related findings (`real_project_error_taxonomy.md` #1-2):
1. Production selects the leader stroke itself as final target in 28.8% of its selections (not fixed — production code).
2. The experimental generator's leader-endpoint resolution was, before a same-day fix, vulnerable to resolving onto a page-spanning filled region (sheet border) rather than a real member, because bbox-distance queries treat "inside a huge bbox" as zero distance (fixed — experimental path only, regression-tested).

## Rotation issues

None found — all 262 real pages have page-level rotation 0. Rotation handling remains verified only via Phase 1's synthetic fixtures. Export was still confirmed to succeed on synthetic rotated pages during this phase's regression testing (`test_ml_association_review_export.py`).

## Region-contamination issues

Not directly measurable — no region/detail-segmentation layer exists anywhere in the pipeline (confirmed again on real data: `region_id` is `None` on all 1,253 real label groups). Multiple real pages (e.g. the two detail pages selected, from the same project) visually contain several distinct details per sheet with no way for the system to separate them.

## Reviewer-export usability

- **Determinism: 100%** — every one of the 108 exported groups (across both `run1`/`run2` exports, all 11 pages) produced byte-identical SVG and JSON output across repeated runs.
- **Coordinate alignment**: visually confirmed correct on manually-inspected samples — label and candidate highlight boxes aligned precisely with the actual drawn text/geometry in the rendered crops.
- **Performance**: fixed a real defect that caused a full pipeline timeout on a dense real page (see `real_project_error_taxonomy.md` #3) — after the fix, all 11 pages' full export (10 groups each, twice for determinism) completed in well under 2 seconds per page.
- **File size**: 658 MB for 108 groups × 2 runs (~3 MB/SVG average) — workable for this bounded pilot, not yet scalable to exporting every group on every dense real page (documented, not fixed — needs an architecture decision).
- **Crop usability**: good for typical groups; degenerates to an impractically tall/narrow image when a candidate is an extremely long, thin member (documented, not fixed).

## Excel / ground-truth status

See `real_project_excel_assessment.md` in full. Summary: a page-level (sheet-number) linkage between Excel schedule rows and PDF pages was **confirmed traceable** on one project (sheet numbers referenced in the spreadsheet's `Comments` column appear verbatim in the corresponding PDF page's text), classified **strong inferred match**. No row-level (specific-geometry) linkage is possible with the data present — classified **unusable as ground truth** for that purpose. **No spreadsheet data was used as training or evaluation truth in this phase.**

## Processing runtime summary

| Stage | Time |
|---|---|
| Full-corpus page profiling (262 pages, 7 projects) | ~114 seconds total |
| Per-pilot-page label-group build (11 pages) | 0.01–1.44 seconds each |
| Per-pilot-page export, 10 groups, before perf fix | timed out (>5 min on the densest page) |
| Per-pilot-page export, 10 groups, after perf fix | 0.09–1.2 seconds each |

## All code fixes made this phase

1. `spatial_index.py`: excluded area-shaped (both-dimensions-large) geometry from candidate generation and leader resolution (`_is_area_shaped`). Regression-tested with a synthetic fixture reproducing the real bbox geometry.
2. `review_export.py`: cached `render_page_svg()` per `(pdf_path, page_number)` to eliminate O(groups) redundant PDF renders. Regression-tested with a synthetic 150-group single-page fixture.
3. `.gitignore`: added `backend/training/ml_association/real_project_pilot/` before any archive extraction occurred (verified with `git check-ignore` before use).

No production code (`services/multimodal/`, `services/prediction/`, `services/engineering/graph_builder.py`'s selection logic, `services/engineering/geometry_extractor.py`'s classification/cap logic) was modified in this phase.

## All remaining blockers

1. **No reviewed ground truth exists yet** — `real_project_annotation_status.md`. The 108-group prioritized batch is ready for a human reviewer; none has reviewed it yet.
2. **Leader-as-target production defect** (28.8% of heuristic selections) is real, quantified, and unfixed — it is production code, out of scope for this phase's guardrails, but should be the top candidate for Phase 3+'s "repaired deterministic baseline" comparison arm.
3. **Fraction-suffix label-splitting extraction defect** is real and unfixed (production code, out of scope) — see `real_project_error_taxonomy.md` #5.
4. **Reviewer-export scalability** (file size, extreme-aspect-ratio crops) needs an architecture decision before exporting whole real projects, not just a bounded pilot batch.
5. **No region/detail-segmentation layer** — confirmed still absent on real data; multi-detail-per-sheet pages cannot be disambiguated.
6. **Excel linkage is sheet-level only and only spot-checked on one of seven projects** — not yet built into any automated check.

See `phase3_readiness_decision.md` for the overall recommendation.
