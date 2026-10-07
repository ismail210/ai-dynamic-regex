# Drawing Summary — engineering validation audit

Date 2026-10-07. Audit only. No production code, quantity rule, prediction contract, fixture, or existing user file was changed.

## Verdict

**USEFUL WITH REVIEW. Not ready as a drawing-set navigator. Not ready to drive takeoff or BBX.**

The summary is already useful when the question is "what does the column schedule say, and do the named levels agree?" It is not useful when the question is "what sheets are in this set, and which one do I open next?" The data for that second question is already extracted. The screen does not show it.

## What was measured

The current deterministic Drawing Summary was built for four PDFs by `extract_engineering_document` with the legend-profile cache redirected to `/tmp`. The model rewrite was off. Counts below are from `profile_digest.json` in this folder.

| Project | PDF | Pages |
| --- | --- | --- |
| Burrville | `backend/uploads/Burrville ES - ST.pdf` | 29 |
| OSSE | `/Users/hibareda/Desktop/Testing Projects/OSSE - ST.pdf` | 26 |
| Struct.pdf (Furley) | `backend/uploads/Struct.pdf` | 24 |
| Brandywine Structural4 | `backend/uploads/Structural4__3aa51f661bdf.pdf` | 43 |

The screen an engineer sees, in order, is: a one-paragraph orientation, items needing attention, steel column schedules and plates, steel mark definitions, levels (only when a schedule level exists), notation rules, then supporting non-steel schedules behind expanders. Family occurrence chips and the page-makeup sentence sit in a collapsed "extraction details" block.

`drawing_intelligence.sheet_index` is filled for every page of all four sets (122/122 pages have a sheet id and a title). `DrawingSummaryPanel.jsx` never reads `sheet_index`.

## Is it useful today?

Yes, for a narrow job. A steel reviewer can see column sections, base-plate marks or sizes, schedule-printed grid locations, and level elevations with their sources. OSSE keeps LEVEL 2 as a conflict (`55'-10"` on S-602-O versus `55'-2"` on S-122-O) instead of picking one. Concrete, pier, footing, and wall schedules are kept out of the steel list. The orientation says schedule rows are definitions, not installed quantities.

## Is it safe?

Safe as a display. It does not change predictions or quantities. It is not safe as the only thing an engineer reads before opening the set, because two visible sentences are wrong:

- Burrville orientation scope: "No explicit issue/revision/phase markings detected." Every title block prints `50% DESIGN DEVELOPMENT` and `4/7/2026`.
- Brandywine orientation: "permit set." The title-block issue on all 43 sheets is `65% DESIGN DEVELOPMENT`, `28 JANUARY 2025`. `FTG PERMIT` is one revision-table row, not the issue of the set.

Page roles are also unsafe to navigate by. They are inferred from page text, not from the title that was just read. Brandywine classifies 24 of 43 sheets as notes/legend, including foundation plans S-110 through S-113 and the section sheets. Burrville classifies `TYPICAL DETAILS` as notes, a schedule, or a floor framing plan, and classifies `SECTIONS` as unclassified or framing. OSSE classifies the parking second-floor plan S-102-O as roof framing, and classifies concrete-detail sheet S-502-O as a column schedule.

## Strongest capabilities

1. Title-block sheet id, title, issue phrase, issue date, scale field, and revision rows. Audited earlier at 56/56 sheet ids on a wider sample, and present here on all 122 pages. Not displayed.
2. Column-schedule rows with section, plate, and printed location (Burrville 121 rows, Brandywine 105, OSSE 26 steel plus 74 precast, Furley 6 marks with base-plate sizes).
3. Level evidence that keeps a conflict (OSSE LEVEL 2) and records agreement when the numbers match (Burrville roofs and floors; Brandywine LEVEL 2 and LEVEL 3).
4. Steel versus non-steel separation (OSSE precast `C1 - 24"x24"`, Furley piers and footings, Brandywine pier schedule).
5. Furley mark map: C1–C6 and L1–L4 to exact sections, with plates on the column rows.

## Biggest weaknesses

1. The engineer never sees the sheet list, so the summary does not answer "what is in this set?"
2. The page-role sentence and several "column schedule on page N" lines point at the wrong kind of sheet.
3. Issue and revision are extracted, then the orientation uses a different, weaker detector and contradicts them.
4. There is no plan-to-detail or plan-to-section object. Callouts captured here are mostly the words `TYP`, `SECTION`, and `SEE PLAN`, not `D/S401`.
5. There is no grid registry and no ledger of where a mark occurs on a plan. Schedule locations are not the same thing as a plan grid intersection.
6. Family chips such as Burrville "wide-flange 801×" count text hits, including details and notes. They are not a takeoff. They are easy to misuse if that block is opened.

## What to build next

Show the sheet index that already exists, and drive navigation from the sheet title, not from page-keyword categories. Then build reference objects (the printed bubble and its target view). Do not start with a model. The titles, issues, and revision rows are printed.

## Ready for broader use?

As a column-schedule and level-conflict review panel, yes, with the two issue sentences corrected or hidden until they use the sheet index. As a substitute for opening the drawing index, no.

## Ready to support takeoff?

No. The quantity rule stays: printed labeled callouts count; a schedule row does not; geometry does not. The summary does not list occurrences, so an estimator still cannot check the count against the plans from this screen. The 801× / 1588× chips must not be exported as quantities.

## Ready to support BBX?

No. BBX here means the Drawing Review label box and member box. The summary does not attach sheet id, view, grid, or level to a prediction. Member-box geometry remains a separate, non-quantity overlay. An external fabrication exchange (PowerFab, SDS/2, and similar) has no contract in this repository.
