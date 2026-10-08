# Extraction gap analysis

Ranked from the four projects measured on 2026-10-07. Safety: A printed and unambiguous, B evidence with review, C do not automate. Quantity impact is "none" unless a later, separate gate is named. Nothing here is a change to the current takeoff rule.

## Ranked next extractions

| Priority | Extraction | Why it matters | Evidence source | Safety | Takeoff impact | Phase |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Show the sheet index that is already built | 122/122 pages have id, title, issue, date, scale, revisions. The screen shows none of it. Burrville's visible sentence says no issue was found. | Title block, already in `sheet_index` | A | None | Next, display only |
| 2 | Page role from the sheet title | Keyword roles mis-label foundation plans, sections, and details on all four sets. Brandywine: 24/43 called notes. The titles are already correct. | Sheet title just read | A for the title; the role is a label of that title, not a new inference | None | Same phase |
| 3 | Issue and revision as separate fields on the summary | Brandywine 65% DD versus FTG PERMIT. OSSE permit date versus revision 2 on page 2 only. Burrville 50% DD on every sheet. | Title block and revision table, already read | A | None. Do not include or exclude scope from these words | Same phase |
| 4 | Reference objects: bubble or "SEE DETAIL N/S502" to a target sheet, view unmatched until found | Furley text already cites N/S502. Burrville and Brandywine are full of SEE SECTION / SEE DETAIL with no target. The summary stores TYP and SEE PLAN. | Printed bubble or note, then sheet index | B. Target sheet can be A when the id matches. "This detail governs this beam" is C | None | After the index is visible |
| 5 | View title, number, and scale inside the sheet | Sheet scale is often "As indicated" or, on Brandywine S-000, a field that is not the plan scale. The real scale is on the view. | Printed view title and SCALE under that title | A for the printed view title and scale. The view box is B | None. A later exclusion of detail-view labels needs its own gate | With references |
| 6 | Occurrence ledger: schedule mark or explicit label, sheet, and "not located" when the schedule has no location | Furley C1–C6 and L1–L4 have definitions and zero locations. Burrville and Brandywine locations are schedule strings, not plan hits. | Schedule row plus plan text search for that mark | B. A hit is evidence. A miss stays "not found," not a zero quantity | None until a gate compares the ledger to the existing labeled-callout count and does not change it | After views exist, so a detail-sheet hit is not a plan occurrence |
| 7 | Grid registry per plan view | Needed before "W12X40 at B/4" is honest. Schedule strings like `A-7` and `D(-3'-10 5/8")-H(...)` are not a grid map. Feet-inch text must be rejected as a grid name. | Grid bubbles and axis labels on the plan | A for the printed bubble name. Intersection of a member is B | None | After views, so bubbles in the title block and in details are not the plan grid |
| 8 | Level register that always renders, with conflicts and unmatched levels | OSSE LEVEL 2 conflict is the model. Furley elevations are extracted and hidden because there is no schedule level. Brandywine LEVEL 4 agrees in number with a sheet titled HIGH ROOF. | Schedule level lines and plan datum notes, already partially built | A for each printed number and its source. Pairing a schedule name to a differently worded sheet title is B | None. Never pick one side of a conflict | Can ship with the sheet index, using data already produced |
| 9 | Plate definition versus plate mark | Brandywine resolves BP8 as a mark and correctly fails to read a size. Furley already has sizes on C1–C6. The summary should say "mark only" versus "size read." | Plate schedule or the column cell | A | None. A mark is not a count of plates | With the column schedule display |
| 10 | Scope flags as review, not as inclusion | Existing, demo, alternate, future, and permit words appear on these sets and do not name the steel to keep. Brandywine's permit detector is already a false positive. | Title block, revision row, note | B as a flag. C as a takeoff decision | None | With issue/revision display |

## The thirty areas, against these four sets

1. **Sheet index.** Built, audited, invisible. Highest value. A.
2. **View index.** Not built. Required because one sheet (Burrville S-101, Brandywine area plans) holds the plan plus schedules or several views. B once the title is printed.
3. **View title.** Not separated from the sheet title. A when printed under a viewport.
4. **View number.** Not built. The Furley `D` in `D/S401` is this. A when printed.
5. **View scale.** Not built. Sheet-level scale is the wrong object on three of the four sets. A when printed on the view.
6. **View bounding box.** Not built. B. Do not invent a box from whitespace.
7. **Plan / detail / section classification.** The current classifier is not reliable (see each project file). Replace it with the sheet title. A.
8. **Detail and section reference objects.** Not built. Callout text is TYP and SEE PLAN. B.
9. **Plan to detail relationship.** Not built. A matching sheet id is not a resolved view. B, and "governs this member" is C.
10. **Grid registry.** Not built. High value on Burrville, Brandywine, and Furley plans. A for bubble text.
11. **Grid intersection per occurrence.** Not built. C if inferred from a nearby dimension. B only when the member label sits on a grid crossing that was read from bubbles.
12. **Level per occurrence.** Partial. Schedule levels exist. A label on a plan is not yet stamped with the plan's level. B.
13. **Member occurrence ledger.** Not built. The 801× and 1588× chips are not this. B.
14. **Mark definition versus occurrence.** Partial and good on Furley (definition with location count 0) and Brandywine (BP mark without size). Keep that split. A.
15. **Duplicate occurrence detection.** Not built. OSSE lists T.O. PARKING LOWER DECK twice; that is a duplicate level read, not a duplicate member. C for members until the ledger exists.
16. **Defined but not seen.** Not built. Furley is the test: 12 marks defined, plan hits not listed. B, reported as "not searched" until search exists, then "not found."
17. **Schedule-to-plan relationship.** Partial for levels (OSSE, Burrville, Brandywine). Not built for marks. B.
18. **Member tier / stack.** Not built. Brandywine's grout note mentions a second tier. The column schedules are graphical stacks but the summary does not show tiers. B, from printed tier lines only.
19. **Scope and revision flags.** Revision text is extracted and then mis-summarized. A for the printed row. B for a review flag. C for exclusion.
20. **Construction notes.** A few are captured (anchor rods, cap plates, "by others"). Not a note register. A for a printed note tied to a sheet. Do not promote every note.
21. **Structural notes.** Steel grades and a handful of typical-connection titles. Useful, incomplete. A.
22. **General notes.** Sheets are identified (S-001, S-000, S001). Their paragraphs are not structured. Low value to extract in full. Leave them as "open this sheet."
23. **Dimensions.** Not a summary object. Must not become grids or quantities. A only as the printed string next to a member when a leader is unambiguous. Otherwise C.
24. **Connection information.** Moment-connection titles on OSSE and "connection engineer by others" on Brandywine. Not a connection schedule. B as a note. C as a piece of hardware.
25. **Base and bearing plates.** Furley sizes are high value. Brandywine marks without sizes are high value because they stay unresolved. A.
26. **Detail boundaries.** Not built. B as a box around a titled view. C as "the members inside."
27. **Leader and arrow evidence.** Used once, well: the OSSE framing key. Do not generalize to "this leader hits this beam" without the same printed-label test. B for the key pattern. C in general.
28. **Geometry evidence.** Not in the summary. Prior geometry work is not cleared for quantities. Keep as optional review graphics. C for identity.
29. **Drawing-set relationships.** The sheet list is the relationship. It exists and is hidden. A.
30. **Cross-sheet navigation.** The reason to build items 4 and 5. Not available today.

## What deterministic methods already solve

Sheet id, title, issue, date, revision rows, column-schedule cells, plate mark versus plate size, level number plus source, and the OSSE framing key. No model is required to put those on screen or to label a page from its title.

## Where a model would still be premature

Choosing which elevation wins, deciding permit versus 65% DD, completing BP sizes, assigning a leader to a beam, and counting from geometry. These four sets do not show a residue that rules cannot mark as unresolved. They show fields that are already extracted and not shown, and fields that should stay unresolved.
