# Real-Project Error Taxonomy (Phase 2.5)

Every issue found while running the Phase 1/2 pipeline against 7 real projects (262 pages) and manually inspecting a sample of the generated reviewer exports. Categorized per the pilot spec's fixed category list. Each entry states whether it was fixed in this phase (experimental/reviewer path only, per the guardrails) or documented as a blocker for a future phase.

## 1. Candidate-generation issue — leader stroke selected as final target (FIXED: partially; root cause documented, not eliminated)

**Finding**: the current production heuristic (`graph_builder.build_graph`'s greedy `nearest_geometry` edge) selected a **leader stroke itself** — not a real structural member — as its final association for a label, in **243 of 843 heuristic-selected label groups across the 11 real pilot pages sampled (28.8%)**. Directly visually confirmed: rendering the source page around one such label showed the current heuristic's pick (orange highlight) sitting on empty space next to a leader stroke, while the experimental leader-resolved candidate (green highlight) correctly landed on a real vertical member the leader was pointing at.

**Status**: This is a **production-code defect** (`graph_builder.py`'s greedy nearest-geometry logic, exactly the failure mode `docs/geometry_graph_audit/04_graph_audit.md §4` predicted from static analysis alone) — not something this phase's guardrails permit fixing (no production prediction/graph changes allowed). The experimental `spatial_index.py` candidate generator already resolves through leaders correctly (Phase 1) and was not the source of this specific defect; it is, however, the mechanism that makes the defect *visible and measurable* for the first time. **Not fixed. Quantified and documented as the single most important real-data finding of this pilot.**

## 2. Candidate-generation issue — page-spanning filled region treated as "zero distance" (FIXED, experimental path only)

**Finding**: a large filled rectangle (a sheet border/title-block frame, `geometry_kind="rectangle"`, bbox spanning ~2556 x ~2056 units against a 160-unit search radius) was returned by the experimental candidate generator as a plausible candidate — and even as a **leader-resolved target** — for numerous unrelated labels on the same real page. Root cause: `spatial_index.query_within_radius(..., use_bbox_distance=True)` reports 0 distance for any point *inside* a bbox, and a page-spanning bbox contains almost every point on the page.

**Fix applied**: `spatial_index._is_area_shaped()` now excludes any geometry candidate whose bounding box is large in **both** dimensions relative to the search radius (both width and height exceed `4 × max_distance`) from being offered as a direct candidate or a leader-resolution target. A genuinely long-but-thin member (large in only one dimension) is explicitly preserved by this filter — verified with a synthetic regression test (`test_spatial_index.py::AreaShapedFalsePositiveTests`) reproducing the exact real-data geometry (border bbox vs. a long thin real member).

**Scope discipline**: this fix lives entirely in `spatial_index.py`, the experimental, not-production-wired module. It does not touch `geometry_extractor.py`'s classification of the rectangle (still classified `"rectangle"`, correctly — the object genuinely is a rectangle; the defect was in how the experimental candidate generator *used* proximity to it, not in its extraction).

## 3. Performance issue — redundant full-page SVG re-render per label group (FIXED)

**Finding**: `review_export.write_group_export()` called `render_page_svg()` once per label group. A real dense page with 235 label groups therefore re-opened the source PDF and re-rendered the identical ~7.8 MB base-page SVG 235 times per export run (470 times across the pilot's twice-per-page determinism check) — this is what caused the pilot's first pipeline run to hit a 5-minute timeout, and separately would have written ~5.6 GB of near-duplicate SVG content for one page alone.

**Fix applied**: `render_page_svg()` is now `functools.lru_cache`d (`maxsize=256`) keyed on `(pdf_path, page_number)` — a pure function with no side effects, so caching introduces no staleness risk within one process. Verified: re-running the same dense real page after the fix showed 234 cache hits / 1 real render (was 235 real renders), export time dropped from a >5-minute timeout to 4.74 seconds. Regression test: `test_ml_association_export_performance.py`, using a synthetic 150-group single-page fixture (no real/confidential file needed to reproduce the mechanism).

## 4. Reviewer-visualization issue — SVG files remain large; extreme-aspect-ratio crops are impractical (DOCUMENTED, not fixed)

**Finding, part A**: even after the caching fix, each exported group's SVG still embeds a full independent copy of the base page (multi-megabyte). 108 exported groups across 11 real pages consumed 658 MB on disk (2 runs × ~3 MB average per SVG) — workable for this bounded pilot, but would not scale gracefully to exporting every group on every page of a full real project (some single pages have 200+ groups).

**Finding, part B**: the reviewer export's crop region is computed as the bounding box of the label plus all its candidates. When a candidate is a genuinely long, thin member (e.g., a ~2088-unit-long vertical line), this crop degenerates into an extremely tall, narrow image (observed: 1499×10800 pixels at 5x zoom for one real group) — impractical for a human reviewer to view as a single image.

**Not fixed in this phase**: both are real, valid findings, but fixing them properly means changing the export *architecture* (e.g., a shared base-page asset referenced by many group JSON files instead of one-SVG-per-group, and/or a fixed-aspect-ratio crop with a scroll/pan affordance or a secondary "full member" thumbnail) — a bigger design decision better made with reviewer-workflow input, not a small contained patch. Recommended as a concrete Phase 3-adjacent follow-up.

## 5. Extraction issue — fraction-suffixed labels split into two tokens (DOCUMENTED, not fixed — production code)

**Finding**: on a real page, the identical physical label appears in the extracted-token stream as **both** a complete token (e.g. an HSS designation ending `.../16`) **and** a truncated token missing the fraction denominator (the same designation without the trailing `/16`), each counted multiple times (6 occurrences of each form on one page). The same pattern recurred for a second designation on the same page, and a third pair (`HSS8X8X1/2` vs `HSS8X8X1`) on a different real project's page. This is very likely caused by the "/" character in fraction-bearing labels (e.g. `X1/2`) triggering a token-boundary split somewhere in the shared text/token extraction path.

**Status**: this is a **production text-extraction defect** (shared by both the live pipeline and this experimental package, since both consume the same `token_extractor`/`pdf_parser` output) — out of scope for this phase's guardrails (no production extraction changes permitted). Documented here as a concrete, reproducible, real-data example for `annotation_guidelines.md`'s "incomplete or damaged labels" category and flagged as a production bug worth a dedicated fix outside this roadmap.

## 6. Region-segmentation issue — no detail/region boundary concept (DOCUMENTED, unchanged from Phase 2)

**Finding**: confirmed again on real data — `region_id` is `None` on every one of the 1,253 real label groups built during this pilot, and several real pages (e.g. `pilot_04`/`pilot_05`, both dense detail-heavy pages from the same project) visibly contain multiple distinct details per sheet with no way for the pipeline to tell them apart. No fix attempted (same reasoning as Phase 2: this is a substantial new capability, not a contained bug fix — tracked as roadmap item P1.4).

## 7. Coordinate-system issue — none found

**Finding**: all 262 real pages report `rotation=0` at the PDF-page level, so the rotation-handling code path (Phase 1) was not exercised by real page-level rotation. No coordinate-system misalignment was observed in any manually-inspected export. Rotation coverage remains synthetic-only (`docs/ml_association_phase/unresolved_questions.md` item 6).

## 8. Schema issue — none found

Every real page processed cleanly through the Phase 2 schema (`AssociationCandidateRow`/`LabelGroup`/pydantic validation) with zero validation errors across 1,253 real label groups and 262 pages of extraction. No schema field proved unable to represent real data.

## 9. Domain ambiguity — see `unresolved_questions.md`'s Phase 2.5 questionnaire (items 13-24)

Not resolved here; genuine cases requiring expert judgment were logged, not guessed at.

## Summary table

| # | Category | Real-data severity | Fixed this phase? |
|---|---|---|---|
| 1 | Candidate-generation (production) | High — 28.8% of heuristic picks affected | No (production code, out of scope) |
| 2 | Candidate-generation (experimental) | High — false positive on multiple pages before fix | Yes |
| 3 | Performance | High — caused a hard pipeline failure (timeout) | Yes |
| 4 | Reviewer-visualization | Medium — usable for this pilot, not for full-scale review | No (documented, needs design decision) |
| 5 | Extraction (production) | Medium — corrupts a subset of fraction-bearing labels | No (production code, out of scope) |
| 6 | Region-segmentation | Known, unchanged | No (roadmap P1.4) |
| 7 | Coordinate-system | None observed | N/A |
| 8 | Schema | None observed | N/A |
| 9 | Domain ambiguity | Ongoing | N/A — logged as questions |
