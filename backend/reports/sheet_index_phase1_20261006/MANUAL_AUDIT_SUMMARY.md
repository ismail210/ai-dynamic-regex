# Phase 1 manual ground-truth audit

Audit date: 2026-10-06. Audit only. Production code, tests, fixtures, Phase 1 result files, caches, and git state were not changed. Phase 2 was not started.

## 1. Scope and methodology

The audit covers the 40 Phase 0 ground-truth pages and the 16 holdout pages named in `render_title_blocks.py`. Each checklist row is tied to a source PDF, a 1-based page number, and one rendered title-block image:

| Sample | Image | How the page was chosen |
| --- | --- | --- |
| Ground truth | `renders/tb_<project>_p<page>.png` | The 40 rows in `GROUND_TRUTH.csv`. The render path on each fixture row matches that filename. |
| Holdout | `renders/ho_<project>_p<page>.png` | Pages 10 and 20 (Furley), 3 and 15 (Burrville), 10 and 30 (Brandywine), 10 and 20 (Springhill), 2 and 20 (OSSE), 8 and 30 (Yellow Spring), 8 and 19 (Washington Latin), 3 and 12 (Fort Davis). |

`pdf_path` is the drawing-set path recorded in the ground truth (for example `07 - FEMS & OSSE/OSSE - ST.pdf`). The pixels were read from the local files used to make the renders: `backend/uploads/` for Furley, Burrville, Brandywine, and Springhill, and `/Users/hibareda/Desktop/Testing Projects/` for OSSE, Yellow Spring, Washington Latin, and Fort Davis.

For every page the title-block crop was read. Sheet ID, sheet title, issue phrase, issue date, and scale were taken from that crop. Revision tables that sit above the Perkins Eastman title block (Burrville, Brandywine, Springhill, Fort Davis) or in the Yellow Spring PRINTS ISSUED block were clipped from the PDF page and read separately. Washington Latin, OSSE, and Furley revision tables are inside the title-block crops.

`expected_sheet_id` for a ground-truth page is the fixture value. It matches `GROUND_TRUTH.csv` on all 40 pages. For a holdout page it is the value recorded in `ALL_PAGES.csv`. `observed_sheet_id` is the identifier printed in the sheet-number cell of the crop. The two columns are equal because the printed cell matched the recorded value, after the image was read.

A field is `pass` only where the printed text was read from a crop or PDF clip. No page is marked verified from the CSV alone. `pending_human_review` was not needed: every audited page had a readable crop, and every revision table that the reader reports was framed and read.

The sheet-number location was also checked in display space. For each of the 56 pages, the largest text line equal to the printed sheet ID falls inside the photographed crop (center about x 0.94–0.97, y 0.93–0.98). Yellow Spring pages are stored with `/Rotate 90` and display size 3024 × 2160; after the display transform the sheet number still sits in that same corner, and the crop text is upright. The parser's numeric `source_bbox` was not drawn on top of the pixels.

This visual audit is separate from the automated evaluator. The evaluator's 40/40 score and the earlier full test run were not re-executed here.

## 2. Pages reviewed

| Group | Reviewed | Pending |
| --- | ---: | ---: |
| Ground truth | 40 | 0 |
| Holdout | 16 | 0 |
| Total | 56 | 0 |

## 3. Sheet-ID accuracy

Independently verified sheet IDs: **56/56** pass, 0 fail, 0 unresolved.

The observed value is the sheet-number cell, including hyphens, dots, letter suffixes, and the OSSE building suffix. Detail bubbles, grid marks, dimensions, and match-line notes were not used. On pages that also print the same identifier elsewhere (section cuts and detail references), the title-block instance is the large type at the stable corner above; the smaller copies were left as references.

## 4. Ground truth and holdout

| Group | Sheet ID | Title | Issue / revision | Date | Scale | Rotation / box | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ground truth (40) | 40/40 | 40/40 | 40/40 | 40/40 | 40/40 | 40/40 | 40/40 |
| Holdout (16) | 16/16 | 16/16 | 16/16 | 16/16 | 16/16 | 16/16 | 16/16 |
| Total (56) | 56/56 | 56/56 | 56/56 | 56/56 | 56/56 | 56/56 | 56/56 |

## 5. Field results

**Titles.** Labeled titles were read from DRAWING TITLE, SHEET TITLE, or Title:. Furley's seven audited titles are printed vertically with no label (`read_unlabeled`). That status matches the sheet. Project names, consultant lists, and Washington Latin's DRAWING TYPE `ARCHITECTURAL` were not taken as the sheet title.

**Issue and revision.** The issue phrase is the text nearest the sheet number (BID SET, 50% DESIGN DEVELOPMENT, 65% DESIGN DEVELOPMENT, FINAL CONSTRUCTION DOCUMENTS, Permit Submission, 100% CONSTRUCTION DOCUMENTS, 50% CONSTRUCTION DOCUMENTS). Yellow Spring prints no issue phrase in the title block; the reader leaves issue empty, and `1 / BID SET / 03/20/25` stays in PRINTS ISSUED. Revision rows were read per sheet. They are not copied from sheet 1:

- Brandywine page 1: blank number, `35% DD` 11/22/2023, `FTG PERMIT` 12/11/2024, `65% DD` 01/28/2025. Pages 4 and 43 omit `35% DD`. Pages 10, 20, 30, and 35 have only the blank-number `65% DD` row.
- Springhill pages 1, 5, 22, and 28: five numbered rows, including `4 FTG PERMIT 2026/03/20`. Pages 10, 14, and 20 have four rows; number 4 is `FINAL CONSTRUCTION DOCUMENTS` and `FTG PERMIT` is absent. The date `2026/1/16` is printed without a zero.
- Washington Latin page 18 (`S-301`) has only revision `2 / ADDENDUM 2 / 12/15/2023`. Pages 1, 12, 23, and holdout page 8 have revisions 1 and 2. Pages 5 and 19 have an empty table.
- Burrville and Fort Davis audited tables are empty (No. / Description / Date). Furley DATE/DESCRIPTION tables inside the crop are empty. OSSE change tables are empty except holdout page 2.

**Dates.** The issue date is the date beside the issue phrase, or the labeled DATE cell on Yellow Spring (`03/20/25`). Plot timestamps under the Yellow Spring block (`3/17/2025 9:26:xx AM`) were not used. On OSSE holdout page 2 the seal reads `06/13/2024`; the issue date remains `10/12/2023` beside Permit Submission, and `04/19/2024` stays on revision 2. On the OSSE ground-truth pages the seal also reads `10/12/2023`, the same day as the issue-date cell; the cell next to Permit Submission is the one recorded.

**Scale.** The SCALE / DRAWING SCALE field was used. Graphic-bar captions that differ from the field (`SCALE : 1/8" = 1'-0"` on Brandywine and Springhill, `3/4"` on Springhill page 28 and the section sheets) stay candidates. Fort Davis page 1 and page 3 print `1 : 1`. Furley and OSSE print no sheet scale. No scale was inferred from geometry.

**Rotation and boxes.** Seven sets are unrotated right-column blocks. Washington Latin is an unrotated bottom strip. Yellow Spring is `/Rotate 90`; the crops read horizontally, and the sheet-number line lands in the lower-right of display space inside the crop.

**Evidence.** The crop or revision clip contains the text that was recorded. OSSE page 10 clips the left edge of "Tech. Coord.: Approver"; the title, `S-122-O`, Permit Submission, and the date cell are complete.

## 6. Discrepancies

No field on the 56 pages disagreed with the drawing. `discrepancy_description` is empty and `severity` is `none` on every checklist row.

The following were checked because they are easy to mis-assign, and the recorded field is the one the drawing supports:

- **OSSE page 10.** Sheet number is `S-122-O`. The `-O` suffix is in the sheet-number cell. Title is `OSSE FACILITY SECOND FLOOR PLAN`. Change table is empty.
- **OSSE page 15.** Title is printed `SUPERSTURCTURE SECTIONS`. Sheet number is `S-401-O`.
- **OSSE page 2 (holdout).** Revision row is number `2`, description `PERMIT REVISION 2`, date `04/19/2024`. Issue remains Permit Submission `10/12/2023`. Seal date `06/13/2024` is a different field.
- **Yellow Spring pages 1, 5, 8, 13, 25, 30, 40.** Sheet numbers `S0.01`, `S2.01`, `S2.04`, `S2.09`, `S3.11`, `S3.16`, `S4.06`. DATE `03/20/25` is the issue date. PRINTS ISSUED is revision `1 / BID SET / 03/20/25`. A wrong clip of page 5 showed detail `1 / S3.15` and grid bubbles; those are not the sheet number. The sheet number on that page is `S2.01`.
- **Furley page 3 and holdout page 10.** Sheet numbers `S101A` and `S102D`. Titles are unlabeled and vertical. Grid bubbles `EX4`, `EX5`, `EX6`, `2`, and `3` sit beside the title column and were not selected. `GP #22137` is the project number.
- **Brandywine page 1.** SCALE field is `1" = 1'-0"`. The graphic bar above it reads `SCALE : 1/8" = 1'-0"`. Revision numbers are blank.
- **Washington Latin page 18.** DRAWING TITLE is `FOUNDATION SECTIONS`. DRAWING TYPE `ARCHITECTURAL` is a different label. The revision table contains only row 2.

## 7. High-risk cases

No high-risk page needs an engineering decision before Phase 2. `requires_human_decision` is `no` on all 56 rows.

The cases above were the ones most likely to swap a reference, a stamp, a bar caption, or a viewport title for a sheet field. Each one matched the recorded sheet index after the crop was read.

## 8. Limitations and recommendations

- Viewport titles that sit outside the title-block crop (Furley page 19 "D SECTION", Fort Davis wind-diagram view titles) were not re-photographed in this pass. The sheet title inside the title block was read. Those outside titles are not the recorded sheet title.
- The display-space position of the printed sheet-ID string was checked against the crop window. The parser box was not overlaid on the raster.
- The legacy `_sheet_ids` reading still drops the OSSE `-O` suffix (the Phase 1 summary's 35/40). That is a different field. The sheet index keeps `S-122-O` and the other `-O` numbers. Phase 2 should consume `sheet_index`, not the legacy IDs.
- This audit did not re-run quantity regression or the test suite. The earlier fresh-cache regression reported quantity totals unchanged aside from the additive sheet-index flag. That result is not part of this visual count.
- Revision content differs by sheet inside Brandywine and Springhill. A later phase should keep that per-page table and not promote one sheet's revisions onto the set.

## 9. Recommendation

**READY FOR PHASE 2**

Sheet identity, title, issue, revision, date, scale, and title-block placement were visually confirmed on 40/40 ground-truth pages and 16/16 holdout pages, with no failing or unresolved field. Phase 2 (reference objects) should wait until this audit is reviewed and explicitly approved. It was not started here.
