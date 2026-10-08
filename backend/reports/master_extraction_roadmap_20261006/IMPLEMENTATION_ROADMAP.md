# Implementation roadmap

This plan builds on the existing code. Each phase is quantity-neutral unless it says otherwise. Every phase ends with a before/after run on the benchmark PDFs: quantity totals and the mark map must be unchanged, and the reference-set tests (`tests/test_column_schedule_reference_set.py`) must pass with `ESTIMA3D_TESTING_PROJECTS` set.

## Phase 0 — Benchmark ground truth for structure (not members)

- **Objective**: human-verified answers for sheet ids, view titles, and references, so the phases below can be measured.
- **Files**: `backend/tests/fixtures/drawing_set/` (new JSON), alongside `fixtures/column_schedule/reference_levels.json`.
- **Prerequisites**: none.
- **Work**:
  - Per project, record 5 pages: sheet id and title as printed.
  - Record 10 references: label, source page, target sheet, target page.
  - Record 3 view titles per detail sheet.
  - Cover all 8 projects, including Yellow Spring (rotated) and OSSE (`S-122-O`).
- **Tests**: a fixture loader; skip when PDFs are absent (same pattern as the reference set).
- **Real-PDF validation**: the user checks crops.
- **Success**: about 40 pages, 80 references, and 60 views verified.
- **Rollback / safety**: test data only.

## Phase 1 — Sheet index

- **Objective**: page → sheet id, title, issue/date, scale, discipline, each with source and status.
- **Files**: `services/document_intelligence.py` (`_title_blocks`), `services/drawing_intelligence.py` (`_sheet_ids`), `services/context_scope.py` (`drawing_title_by_page`), `services/drawing_scale.py`.
- **Prerequisites**: Phase 0.
- **Work**:
  - Locate the title-block region: right or bottom band, densest box with sheet-id grammar, consistent across pages.
  - Learn the project's sheet-id grammar from the set itself (`S101A`, `S2.01`, `S-122-O`).
  - Pick the id inside the title-block region. Do not rely on the tallest word; that fails on OSSE.
  - Handle rotated pages through rotation-aware coordinates.
- **Tests**: unit tests for the grammars; the Phase 0 fixture.
- **Real-PDF validation**: all 8 PDFs, every page; list duplicates and unresolved pages.
- **Success**:
  - At least 98% of pages have the correct sheet id against Phase 0.
  - Distinct ids equal the page count, except true duplicates.
  - Unresolved pages are explicit.
- **Rollback / safety**: additive field in the drawing-intelligence profile. No prediction or quantity input.

## Phase 2 — Reference objects

- **Objective**: structured detail and section references with resolution status.
- **Files**: `services/drawing_intelligence.py` (new `references` section in the existing profile), with the parsing helper beside it. Reuse `_DETAIL_REF_RE`. The census scripts in this folder are the prototype.
- **Prerequisites**: Phase 1.
- **Work**:
  - Detect stacked bubbles: a label above a sheet id inside a circle, using vector circles as `column_trace._bubbles` does.
  - Detect inline `n/Sxxx`.
  - Separate own-sheet view titles from cross-sheet references.
  - Resolve each reference to `target_view_found`, `target_sheet_only`, `target_missing`, or `ambiguous`.
  - Handle rotated pages.
- **Tests**: unit tests on synthetic words; precision and recall on the Phase 0 sample.
- **Real-PDF validation**:
  - The census counts are the baseline (1,171 cross-sheet / 1,168 view found).
  - Render 10 random references per project.
- **Success**:
  - Precision of at least 95% on the human sample.
  - The Yellow Spring stacked bubbles are found.
  - OSSE resolves with no false "missing" targets.
- **Rollback / safety**: profile-only; no quantity input. Gate 5.

## Phase 3 — View index and extents

- **Objective**: each view title (number, title, scale) plus an extent box with a status.
- **Files**:
  - `services/detail_regions.py`, extended from x-gap clustering to title-anchored 2D extents
  - `services/view_scale.py`
  - `services/view_scope.py`
  - `services/context_scope.py`, which consumes view type only after promotion
- **Prerequisites**: Phases 1–2. `docs/DETAIL_PAGE_EXTENTS_PROTOTYPE.md`.
- **Work**:
  - Anchor views at own-sheet view-title bubbles.
  - Take the extent from drawn borders, falling back to whitespace partition. Mark the result `bordered`, `partitioned`, or `unresolved`.
- **Tests**: Phase 0 view boxes; overlap metrics.
- **Real-PDF validation**: render the extents on 2 detail sheets and 1 mixed sheet per project.
- **Success**:
  - At least 90% of views have an IoU ≥ 0.8 against human boxes.
  - No plan view is classified as a detail view on the benchmark set.
- **Rollback / safety**: shadow first. Scope uses it only behind a flag, with a takeoff before/after (Gate 7).

## Phase 4 — Grid registry per view

- **Objective**: grid names and axes per plan view; the location of each counted callout as a printed or computed string with status.
- **Files**: `services/column_trace.py` (`_bubbles`, `_axes`, `_crossing`), `services/engineering/schedule_grid.py` (`parse_column_location`).
- **Prerequisites**: Phase 3 (views).
- **Work**:
  - Promote bubble and axis detection from the trace pilot to a per-view registry.
  - Keep feet-inch values out of the grid grammar.
  - Produce `between C.8 and D, at 9` only when both axes lie in the same view.
- **Tests**: existing column-trace tests plus new ones for primes and decimals.
- **Real-PDF validation**: grid lists for 2 plans per project, checked by eye.
- **Success**:
  - At least 98% of printed grid names are read.
  - No dimension string is accepted as a grid.
- **Rollback / safety**: evidence only.

## Phase 5 — Occurrence ledger

- **Objective**: per mark or section, the defining rows, plan occurrences (sheet, view, grid, level), duplicate suspects, and definition-only marks.
- **Files**:
  - `services/takeoff/quantity_engine.py`, read-only reuse of its eligibility
  - `services/engineering/schedule_grid.py` (mark map)
  - `services/drawing_intelligence.py` (output)
- **Prerequisites**: Phases 1, 3, 4. The level link already exists in `level_evidence`.
- **Work**:
  - Build the ledger from the same eligible predictions the engine counts.
  - Compare against listed locations where schedules print them.
- **Tests**: the ledger count equals the QuantityEngine count for every section; synthetic duplicates are flagged.
- **Real-PDF validation**: Furley mark map C1–L4. Check each mark's occurrences by eye on two plans.
- **Success**:
  - The ledger and the takeoff agree exactly.
  - Every definition-only mark is listed.
- **Rollback / safety**: no quantity change (Gate 4).

## Phase 6 — Summary by sheet and view, plus BBX fields

- **Objective**: the Sheet, Takeoff, and Review summaries (`DRAWING_SUMMARY_SPEC.md`), and BBX per-occurrence fields (`BBX_INTEGRATION.md`).
- **Files**:
  - `frontend/src/components/DrawingSummaryPanel.jsx`
  - `frontend/src/lib/predictionContract.js`
  - `prediction/contract.py`, additive fields only
  - `takeoff_exporter.py`, an optional occurrence sheet
- **Prerequisites**: Phases 1–5.
- **Tests**: Vitest component tests; contract tests; exporter tests.
- **Real-PDF validation**: browser check on Furley and OSSE.
- **Success**:
  - Every line has a working source button.
  - "pending" or "unresolved" is shown instead of a guess.
- **Rollback / safety**: additive UI; the existing v2 contract shape is unchanged.

## Phase 7 — Scope, revision, and accessories (review-gated)

- **Objective**: scope tags (existing, demolition, alternate) and revisions per sheet or view as review flags; plate and anchor-rod lines as definitions linked to marks.
- **Files**: `drawing_intelligence` scope signals, `column_schedule` plates, a new title-block revision parser.
- **Prerequisites**: Phases 1–3. Human decisions from `OPEN_ENGINEERING_QUESTIONS.md`.
- **Success**:
  - Flags are shown with quoted text.
  - No exclusion happens without acceptance.
- **Rollback / safety**: Gates 3 and 6.

## Phase 8 — ML only where measured gaps remain

Title-block field locator, view detector, or geometry association. Each needs a frozen holdout, a comparison against the deterministic baseline, and an `ml-audit` before any use. See `AI_ML_LLM_ROADMAP.md`.
