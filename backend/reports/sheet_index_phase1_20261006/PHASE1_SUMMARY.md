# Sheet Index — Phase 0 + Phase 1 summary (2026-10-06)

Nothing was committed, pushed or deployed.

## Results

| Measure | Pages | Correct | Wrong | Unresolved |
|---|---|---|---|---|
| Sheet id, Phase 0 ground truth | 40 | 40 (100%) | 0 | 0 |
| Sheet id, holdout pages (manual, not in the fixture) | 16 | 16 (100%) | 0 | 0 |
| Title, ground truth | 40 | 40 | 0 | 0 |
| Issue + issue date, ground truth | 40 | 40 | 0 | 0 |
| Scale, ground truth (`null` where not printed) | 40 | 40 | 0 | 0 |
| Revision rows, inspected pages | 23 | 23 | 0 | 0 |
| Legacy `_sheet_ids`, ground truth | 40 | 35 | 5 | 0 |

The 98% target is met: 56/56 pages across both sets. Sheet-id false positives
(an id read where none is printed): 0/56. False negatives (a printed id not
read): 0/56.

Across all 233 pages of the 8 PDFs, every page gets a sheet id read from the
slot, with no duplicates (`ALL_PAGES.csv`). Pages outside the 56 are not
verified against ground truth.

The legacy reader's 5 misses are the OSSE pages: it reads `S122` for
`S-122-O`, dropping the building suffix. It does this on all 26 OSSE pages and
agrees with the new reader everywhere else.

**Caveat:** the 40 ground-truth pages were also used while building the
reader, so 40/40 is development-set accuracy. The 16 holdout pages are the
independent check, and 16 is a small sample.

## What changed (source)

| File | Change |
|---|---|
| `services/engineering/sheet_index.py` (new) | Reads sheet id, title, issue, issue date, revision rows and scale per page from the title block, with status, evidence, candidates and display-space boxes. |
| `services/engineering/drawing_intelligence.py` | One additive profile key, `"sheet_index": sheet_index(document)`, plus its import. |
| `services/engineering/legend_profile.py` | `EXTRACTOR_VERSION` bumped from `v6l-level-bands` to `v6m-sheet-index` so cached profiles are rebuilt with the new key (same convention as v6f–v6l; see QUANTITY_REGRESSION.md). |
| `tests/test_sheet_index.py` (new) | 16 synthetic cases. |
| `tests/test_sheet_index_reference_set.py` (new) | All 40 ground-truth pages verbatim through `build_drawing_intelligence`, an explicit OSSE p10 `S-122-O` test, and the rotated Yellow Spring pages. Skips when the PDFs are absent. |
| `tests/fixtures/sheet_index/ground_truth.json` (new) | Phase 0 fixture. |

## How the reader works

No project coordinates and no project-specific answers. Everything is learned
from the set itself, in display space (`page_space`), so `/Rotate` pages read
as shown.

1. **Slot.** Find sheet-number-shaped lines in the outer band (right 30% or
   bottom 15%). The largest such line on each page votes; the median position
   across the set is the slot. Each page takes the largest id within ±4% of
   the slot. Detail callouts (`4/S-401-O`), grid bubbles, and bigger sheet
   numbers elsewhere are not in the slot.
2. **Block.** Text that repeats at the same relative position on ≥60% of
   sheets is boilerplate. Its spread decides the layout (right column or
   bottom strip). The block edge comes from walking out from the sheet number
   until a gap larger than 3% of the page, which keeps stamps and viewport
   titles beside the block out of it.
3. **Fields.** A label (`DRAWING TITLE`, `SHEET TITLE`, `Title:`, `SCALE`,
   `DATE`) and its value to the right or just below. Without a title label,
   the title is the largest sheet-specific text, marked `read_unlabeled`. Two
   near-equal candidates give `ambiguous`, with both kept as candidates.
4. **Issue.** The issue phrase nearest the sheet number. The issue date comes
   from a DATE field, else the date printed beside the issue phrase. Seal
   dates and plot timestamps are not used.
5. **Revisions.** Rows under a DESCRIPTION + DATE header, as printed. No
   precedence logic.
6. **Scale.** Only a title-block SCALE field value. Graphic-bar captions
   (`SCALE : 1/8" = 1'-0"`) are kept as `caption` candidates. Never inferred
   from geometry; viewport scales are left for later phases.

Statuses: `sheet_id_status` (read | unresolved, with candidates);
`title_status` (read | read_unlabeled | ambiguous | unresolved);
`issue_status`; `scale_status` (read | ambiguous | not_shown);
`revision.status` (read | none_printed | not_shown).

## What did not change

- QuantityEngine, quantity eligibility, prediction orchestrator and contract.
- Mark map, schedule grid, tokens, the legacy `_sheet_ids`, and the
  `DRAWING_INTELLIGENCE_VERSION`.
- Training files. Every tracked file under `backend/training/` is
  byte-identical to the snapshot taken before this work. The pre-existing
  modifications listed in git status are untouched.
- No reference objects, view extents, grid registry, occurrence ledger, BBX,
  ML/LLM features, or geometry semantics. Phase 2 was not started.

## Tests

- `tests/test_sheet_index.py`: 16 passed. Covers:
  - a normal sheet
  - alphanumeric, dotted and hyphenated ids
  - a rotated page
  - detail/callout references
  - "largest number is not the sheet number"
  - multiple dates (seal date, plot timestamp, revision dates)
  - a viewport title different from the sheet title
  - unlabeled and ambiguous titles
  - an unresolved page with candidates
  - empty revision table, scale field vs caption, sheet number on the scale row
  - empty document
- `tests/test_sheet_index_reference_set.py`: 3 passed, 40 subtests (real PDFs).
- `test_drawing_intelligence`, `test_context_scope`, `test_quantity_engine`: passed.
- `test_level_reference_set` + `test_column_schedule_reference_set` (real
  PDFs): 14 passed, 1 failed. The failure is pre-existing; see "Pre-existing
  issues".
- Full backend suite: **1853 passed, 23 skipped** (earlier baseline 1837 / 20;
  +16 new tests, +3 real-PDF tests skipped without `ESTIMA3D_TESTING_PROJECTS`).
- Quantity regression: IDENTICAL on all 8 PDFs (QUANTITY_REGRESSION.md).

## Manual validation: 2 holdout pages per project (not in the fixture)

Answers to the 8 questions. For every page:

- **Rotation handled?** Yes. Yellow Spring is `/Rotate 90`; all other pages are rotation 0.
- **Detail number selected by mistake?** No.
- **Dimension selected by mistake?** No.
- **Quantity changed?** No (see QUANTITY_REGRESSION.md).

| Project | Page | Printed sheet no. | Extracted | Title correct? | Issue / revision correct? | Evidence |
|---|---|---|---|---|---|---|
| Furley | 10 | S102D | S102D ✓ | SECOND FLOOR FRAMING - AREA D ✓ (unlabeled) | BID SET 11/14/2022 ✓; table empty ✓ | `renders/ho_furley_p10.png` |
| Furley | 20 | S501 | S501 ✓ | FRAMING SECTIONS ✓ | ✓ | `renders/ho_furley_p20.png` |
| Burrville | 3 | S-003 | S-003 ✓ | STATEMENT OF SPECIAL INSPECTIONS FORM ✓ | 50% DESIGN DEVELOPMENT 4/7/2026 ✓; SCALE blank → not_shown ✓ | `renders/ho_burrville_p3.png` |
| Burrville | 15 | S-202 | S-202 ✓ | TYPICAL DETAILS ✓ | ✓; scale As indicated ✓ | `renders/ho_burrville_p15.png` |
| Brandywine | 10 | S-114 | S-114 ✓ | FOUNDATION PLAN - AREA D ✓ | 65% DESIGN DEVELOPMENT 28 JANUARY 2025 ✓; scale As indicated (bar caption 1/8" kept as candidate) ✓ | `renders/ho_brandywine_p10.png` |
| Brandywine | 30 | S-302 | S-302 ✓ | SECTIONS ✓ | ✓ | `renders/ho_brandywine_p30.png` |
| Springhill | 10 | S-113B | S-113B ✓ | ROOF FRAMING PLAN - PART B ✓ | FINAL CONSTRUCTION DOCUMENTS 06 APRIL 2026 ✓ | `renders/ho_springhill_p10.png` |
| Springhill | 20 | S-321 | S-321 ✓ | SECTIONS ✓ | ✓; field 3/4" = 1'-0" chosen over two bar captions ✓ | `renders/ho_springhill_p20.png` |
| OSSE | 2 | S-001-O | S-001-O ✓ | SPECIAL INSPECTIONS, LEGEND, ABBREVIATIONS AND NOTATIONS ✓ | Permit Submission 10/12/2023 ✓; revision `2 04/19/2024 PERMIT REVISION 2` ✓; seal date 06/13/2024 not used ✓ | `renders/ho_osse_p2.png` |
| OSSE | 20 | S-503-O | S-503-O ✓ | MASONRY TYPICAL DETAILS ✓ | ✓; table empty ✓ | `renders/ho_osse_p20.png` |
| Yellow Spring | 8 | S2.04 | S2.04 ✓ | PARTIAL ROOF FRAMING PLAN - AREA A ✓ | no issue phrase in block → issue null; DATE 03/20/25 ✓; plot timestamp ignored ✓ | `renders/ho_yellowspring_p8.png` |
| Yellow Spring | 30 | S3.16 | S3.16 ✓ | SECTIONS ✓ | ✓; scale 3/4" = 1'-0" ✓ | `renders/ho_yellowspring_p30.png` |
| Washington Latin | 8 | S-100 | S-100 ✓ | GROUND FLOOR FOUNDATION PLAN ✓ | 100% CONSTRUCTION DOCUMENTS / JANUARY 12, 2024 ✓; revisions 1 ADDENDUM 11/29/2023, 2 ADDENDUM 2 12/15/2023 ✓ | `renders/ho_washlatin_p8.png` |
| Washington Latin | 19 | S-401 | S-401 ✓ | GRAVITY BRACE ✓ | ✓; revision table empty → none_printed ✓ | `renders/ho_washlatin_p19.png` |
| Fort Davis | 3 | S003 | S003 ✓ | SPECIAL INSPECTIONS ✓ | 50% CONSTRUCTION DOCUMENTS 2025/06/18 ✓; scale "1 : 1" as printed ✓ | `renders/ho_fortdavis_p3.png` |
| Fort Davis | 12 | S202 | S202 ✓ | FOUNDATION SECTIONS ✓ | ✓; scale 1/2" = 1'-0" ✓ | `renders/ho_fortdavis_p12.png` |

Low-resolution full-page renders are next to each crop (`ho_*_full.png`).
On the holdout pages for Furley, Burrville, Brandywine, Springhill, Yellow
Spring and Fort Davis, the revision tables sit above the crop and were not
re-read. Their reading matches the same table on that project's
ground-truth pages.

## Limitations

- **Ground truth not human-checked yet.** It was read from renders by the AI
  agent, not by a person. Each record names its render.
- **Dev set overlap.** The fixture pages were used during development, so the
  holdout (16 pages) is the only independent measure.
- **One title-block family per PDF.** The slot is learned from the set. A PDF
  that mixes families (for example, combined architectural and structural
  sets) could leave the minority pages `unresolved`. They are reported with
  candidates, not guessed. Single-page PDFs have no repeated boilerplate, so
  the block falls back to the outer band.
- **Text layer only.** Sheet numbers that are outlined vectors or raster
  images are not read; there is no OCR.
- **Unlabeled titles** (Furley) are the largest sheet-specific text, marked
  `read_unlabeled`, never `read`.
- **Issue.** Yellow Spring prints no issue phrase in the block, so `issue` is
  null and only the DATE field is read. Its PRINTS ISSUED table rows are
  exposed as revision rows.
- **Not yet used by anything.** `sheet_index` is display/evidence only. The
  legacy `_sheet_ids` still feeds the existing views, and it still drops
  OSSE's `-O`. Switching consumers is a later-phase decision.
- **No frontend display** was added (not requested).

## Pre-existing issues (not caused by this work)

- `test_column_schedule_reference_set::test_burrville` fails on entry
  `H.4'-5.8'` (no entry found; the nearby location reads as a merged
  `G(-3' - 2")-5.8(5' - 5 7/8")`). It still fails with `sheet_index` stubbed
  out, so it is independent of Phase 1. Most likely it comes from the
  pre-existing uncommitted schedule changes.
- `git diff --check` reports trailing whitespace (CRLF) in pre-existing
  modified training CSVs (`approved_dataset.csv`, `history.csv`,
  `unknown_tokens.csv`, `upload_log.csv`). My files have no whitespace issues.
- 7 of 8 PDFs produce 0 takeoff rows, and Furley has 1420 predictions where
  the docs say 1436 (QUANTITY_REGRESSION.md).
- Running the backend suite and my first baseline wrote **new gitignored
  cache files** under `backend/training/legend_profiles/` and
  `backend/training/engineering_artifacts/`. These are runtime caches, not
  tracked training files, and no existing tracked file changed. They were left
  in place.

## Report files

- `PHASE1_SUMMARY.md`
- `GROUND_TRUTH.csv`
- `SHEET_INDEX_RESULTS.csv`
- `ALL_PAGES.csv`
- `evaluation_summary.json`
- `QUANTITY_REGRESSION.md`
- `COMMANDS.md`
- `regression_*.json/.log`
- `renders/`
- scripts: `render_title_blocks.py`, `probe_lines.py`, `evaluate.py`, `all_pages.py`, `quantity_regression.py`
- `pdf_root/`: symlinks only
