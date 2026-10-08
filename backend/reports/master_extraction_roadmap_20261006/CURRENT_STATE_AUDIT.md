# Current state audit

Every row names the module that implements the capability today and the evidence for its current quality. "Pilot" means the capability exists but is evidence-only and is not wired into quantities.

## Pipeline as it runs

1. `routers/documents.py` `POST /api/documents` stores the PDF only.
2. `POST /api/documents/{id}/extract` → `services/pdf_parser.extract_document_structure` (PyMuPDF words, lines, blocks, rotation, layers) → `document_intelligence.enrich_document_structure` (reading order, tables, schedules, title-block candidates, diagnostics) → `token_extractor` (engineering tokens) → `schedule_grid.attach_schedule_grid` (ruled tables via `schedule_tables.read_ruled_tables`, word-cluster fallback, mark map, level bands) → `context_scope.annotate_takeoff_scope` → legend / project context profile (`legend_profile_hook`) → Drawing Intelligence profile (`drawing_intelligence.build_drawing_intelligence`). Extraction version `3.27-pier-wrap`.
3. `POST /api/documents/{id}/analyze` → geometry (`geometry_extractor`, `geometry_normalizer`, `member_geometry`), graph (`graph_builder`, `structural_graph`), then `prediction/orchestrator.predict_from_context`, the only inference entry. Then `explanation_engine` (v2 contract) and validation.
4. `POST /api/takeoff/generate` → `takeoff/quantity_engine.QuantityEngine` → `takeoff_exporter`.

## Capability audit

| Area | Module(s) | Status | Evidence / known limits |
| --- | --- | --- | --- |
| Native text, words, blocks, rotation | `pdf_parser`, `pdf_pages` | Production | All 8 benchmark PDFs have a text layer on every page; no low-text pages in the census. Yellow Spring: all 40 pages rotated. |
| OCR | `document_intelligence.repair_ocr_text`; no raster OCR pass | Partial | Native text is enough on all 8 benchmarks. Raster-only drawings not covered. |
| Title block | `document_intelligence._title_blocks` | Weak | Returns a text blob and a fixed confidence (0.88 / 0.65) from a lower-right band or keyword. Sheet number, title, date, revision, and project number are not parsed fields. |
| Sheet id per page | `drawing_intelligence._sheet_ids`, `context_scope.drawing_title_by_page` | Partial | Works on the reference projects. Fixture: Yellow Spring p5 S2.01, p8 S2.04, p13 S2.09. The census shows the grammar varies: `S101A`, `S2.01`, `S-122-O`. The tallest-word rule fails on OSSE. |
| Drawing scale | `drawing_scale`, `view_scale` | Production / pilot | Per-view scale with status. On Brandywine overall sheets the view says `1"=20'-0"` and the title block says `1/8"=1'-0"`; that stays uncalibrated. Nothing is measured on an NTS view. |
| Page classification | `drawing_intelligence._classify_pages`, `document_prior`, `legend_profile`, `context_scope` | Production, page-level only | Regex categories: index, roof framing, floor framing, column plan, foundation, bracing, schedule, elevation/section, details, notes. One category per page. Mixed-content sheets are only flagged as uncertain. |
| Region / view detection | `detail_regions.cluster_page_regions` (x-gap), R&D 2D clustering | Weak / R&D | `DETAIL_PAGE_EXTENTS_PROTOTYPE.md`: x-gap does not split stacked details; 2D clustering is R&D only. View titles are not used as anchors. |
| Detail / section references | `context_scope` (typical-detail sheet demotion), `repeated_detail_linker` (review-only condition linker), regex flags in `document_intelligence`, `drawing_intelligence._DETAIL_REF_RE` | Missing as objects | No reference object. Census (this report): 1,171 cross-sheet bubbles whose target sheet is in the PDF; 1,168 have a matching view title on the target sheet. |
| Grids | `column_trace` (`_bubbles`, `_axes`, `_crossing`), `schedule_grid.parse_column_location`, `column_schedule` | Pilot | Grid names keep decimals and primes (`A.3'`, `K.2'-13'`). There is no per-sheet grid registry. A grid is not tied to a counted callout. |
| Levels / elevations | `level_evidence.levels_view`, `schedule_grid.attach_level_bands` | Production evidence | Reference test passes on OSSE, Yellow Spring, Washington Latin, and Fort Davis. Conflicts kept (OSSE LEVEL 2). Split ≠ pairing (Brandywine). SEE PLAN resolved only from a single plan value. |
| Schedules | `schedule_tables`, `schedule_grid`, `column_schedule`, `multimodal/schedule_ingestion` | Production | Ruled-first. Covers lintel, column, bearing plate, base plate, ICF lintel, pier, footing, wall, and Revit transposed schedules. Pier, footing, and wall are non-steel. Mark map conflict guard exists behind a flag (off). |
| Plates / accessories | `schedule_grid._interpret_plate`, `plate_grammar`, `column_schedule` | Production evidence | Headed dimensions. Plate washer and anchor rod are kept separate from plate thickness (Brandywine BP1). Overlapping duplicate text is fixed (Springhill). `plate_count_per_member` is a hint only. |
| Mark → plan use | `SCHEDULE MARK MAP` prediction source in `quantity_engine` | Production | A plan callout `L1` gets its section from the map and is counted as a labeled callout. There is no ledger of expected vs detected occurrences. |
| Incomplete labels | orchestrator `is_incomplete_angle_missing_thickness`, `hss_completion` (review), `hss_review_enrichment` | Production | Abstain / review. Burrville has no printed chain that would resolve `L4X4` (`BURRVILLE_INCOMPLETE_L_EVIDENCE_INVESTIGATION.md`). |
| Project drawing language | `project_rules`, `project_rule_resolver`, `legend_llm_provider` | Gated | Only `LABEL_SUBSTITUTION` is auto-eligible, behind gates. Other rule types are informational. |
| Typical / repeated details | `repeated_detail_linker` | Review only | `requires_review=true`, `takeoff_eligible=false`. |
| Scope existing / new / demo / alternate | `drawing_intelligence._existing_new`, `_scope_signals` | Signals only | Census: OSSE has 16 alternate and 3 demolition mentions. Washington Latin and Fort Davis have many `NEW`. Scope does not split quantities. |
| Revisions | none | Missing | Census: Washington Latin has 32 revision-like strings. The others have 0–1. |
| Geometry | `geometry_extractor`, `member_geometry`, `spatial_index`, `graph_builder`; R&D G7–G9 | Production for display only | `member_geometry` docstring: "never feeds takeoff". G9 `ASSOCIATION_STILL_NOT_READY`; final `PRODUCTION_NO_GO`. Generalisation beyond Burrville not shown. |
| Leaders | `column_trace._leader_ends`; leader→target ranking stopped | Pilot | `FINAL_ACCURACY_GAP_AUDIT`: leader→target signal 0.7% reliable. Stopped as a ranking input. |
| Dimensions | `feet_inch_filter`, `annotation/anonymous_dimension_*` | Filter + R&D | Dimensions are filtered out of steel tokens. Dimension → target attachment is not production. |
| Quantity | `quantity_engine` | Production, conservative | Counts eligible labeled callouts. Schedule cells never count alone. Explicit `TYP x N` multiplier capped at 20. Repeated-detail and geometry inference excluded. |
| Explainability | `prediction/contract.py`, `explanation_engine` | Production | v2 contract is shared by Review Queue, Validation, and Prediction Details. |
| Drawing Summary | `drawing_intelligence` + `DrawingSummaryPanel.jsx` | Production | Definitions, interpretation rules, column locations, levels and elevations, level bands, unresolved items. No sheet / view organisation. |
| BBX overlay | `BboxHighlight.jsx`, `predictionContract.js` (`member_geometry.bbox`) | Production | Text box always shown. Member box only when `member_geometry.available`. |
| LLM | `drawing_summary_llm` (optional, grounded), `legend_llm_provider` (fail-safe) | Optional | Neither can change a prediction or quantity. |
| ML | exact-section model, XGB ranker (not enabled), Graph v2 (do not enable), GraphSAGE / learned fusion (off) | Mostly off | `FINAL_ACCURACY_GAP_AUDIT` explains each decision. |

## Work by owner

- **User**: levels and elevations (`level_evidence`), column schedule phase 1 and level phase 2, column trace pilot, view scale, offsets, the recent PDF fixes (Springhill duplicate spans, BP/CL header-span clip, compact level split, pier width, wrapped ICF lines), Drawing Summary, reports under `backend/reports/`.
- **Bassam** (`origin/main` up to `9522744`): ruled schedule reader integration, per-view scale evidence, offset placement, continuation notes. `docs/levels_phase2/INTEGRATION.md` records the integration.
- **Geometry R&D**: `docs/validation/rd_geometry_integration/` G7–G10. Production untouched.

## Known open defects and unresolved cases

| Case | State |
| --- | --- |
| OSSE LEVEL 2 `55' - 10"` vs `55'-2"` | Conflict kept; human decision |
| Brandywine `A.3'-19` trace | Ambiguous; nearby bubble reads `A.4'` |
| Brandywine `14'-0" LEVEL 1` | Split, not paired, by design |
| Washington Latin THIRD / FOURTH FLOOR | SEE PLAN, unresolved because the plans give two values |
| Fort Davis levels | No elevation printed |
| Brandywine `D-13(18'-2")` | Appears in two schedule blocks as `W12X40` and `W12X50`; pre-existing |
| Furley MP piers | Width kept raw; not a plate |
| Historical 383/414 | Not reproducible |
| Default full suite | Eight reference-PDF tests skip unless `ESTIMA3D_TESTING_PROJECTS` points at a tree with the fixture paths |
