# Brandywine Structural4 — Drawing Summary engineering assessment

PDF: `backend/uploads/Structural4__3aa51f661bdf.pdf`. 43 pages. Summary status SUCCESS. Sheet-index slot 43/43.

## What the summary contains

Titles and ids are read: `S-000` GENERAL NOTES through `S-601` COLUMN SCHEDULE, including `S-111` FOUNDATION PLAN - AREA A, `S-134` LEVEL 3 FRAMING PLAN - AREA D, `S-200` BRACED FRAME ELEVATIONS, `S-302` SECTIONS. Issue on every sheet is `65% DESIGN DEVELOPMENT`, `28 JANUARY 2025`.

Revision rows differ by sheet, and the numbers are blank:

| Sheets | Rows |
| --- | --- |
| 25 sheets | `65% DD` `01/28/2025` only |
| 17 sheets | `FTG PERMIT` `12/11/2024`, then `65% DD` `01/28/2025` |
| S-000 only | also `35% DD` `11/22/2023` |

Scale field is `As indicated` on 36 sheets. S-000 prints `1" = 1'-0"` in the SCALE field while a graphic bar on that sheet reads `1/8" = 1'-0"` (confirmed in the sheet-index audit). S-003 prints `1" = 30'-0"` in the field. Those field values are not plan scales.

The orientation says "43-page structural set (permit set) with a steel column schedule on S600." Calling this a permit set is wrong. The issue is 65% design development. `FTG PERMIT` is a revision description. The scope detector reports a "permit set stamp" on pages 1, 2, 3, 4, 5, 6, 11, and 16, which are sheets whose revision table contains the words FTG PERMIT. That is a revision row, not an issue stamp.

The column schedule on S-600 and S-601 has 105 steel entries. Plates are marks, not sizes: 102 `resolved` to a mark such as `BP8` or `BP1`, 3 not shown. The unresolved list says BP1 through BP9 could not be read as a defined size. So the summary knows the column calls for BP8 and does not know what BP8 is. That is the right split, and it is useful. Locations are schedule strings such as `A-9`, `A.1'-18`, and `T'(-2'-0")-9'(2'-9")`. Anchor-rod notes on S-601 are captured (templates before concrete, 1/2" minimum projection, grout before the second tier).

Levels on S-600:

| Schedule level | Elevation | Match |
| --- | --- | --- |
| LEVEL 2 | 14'-0" | S-120, top of slab 14'-0", top of steel 13'-6 3/4", agrees |
| LEVEL 3 | 28'-0" | S-130, 28'-0" / 27'-6 3/4", agrees |
| LEVEL 4 | 42'-0" | matched to S-140, whose sheet title is HIGH ROOF FRAMING PLAN - OVERALL, elevation agrees |
| LEVEL 1 | 0'-0" | no plan match |
| LOWER LEVEL | -5'-0" | no plan match |

S-140's title is not "Level 4." The elevation agreement is real. The names are not the same word. An engineer needs both names on screen. There is no sheet titled LEVEL 4 or LEVEL 1.

Page roles ignore those titles. 24 of 43 sheets are `notes_legend`, including S-110 through S-113 (foundation plans), S-120 (level 2 overall), S-130 (level 3 overall), S-140 (high roof overall), and S-300 through S-302 (sections). S-202, braced-frame elevations, is classified foundation. Schedule insights call pages 6, 11, 16, and 21 column schedules; those pages are S-110, S-120, S-130, and S-140, the overall plans. Page 27 (S-202, braced-frame elevations) is "semantics unclear," which is at least honest. Page 31 (S-400 enlarged framing plans) and page 38 (S-513 moment-frame details) are also called column schedules.

One concrete pier schedule on S-500 is supporting. Connection-design notes ("by others," sealed calculations) are in the notes list.

## What it gets right

- The sheet index, including per-sheet revision differences and blank revision numbers.
- Column section plus plate mark, and the separate admission that BP1–BP9 have no size.
- LEVEL 2 and LEVEL 3 elevations checked against the overall framing plans, slab and steel both kept.
- Offsets in location strings kept as offsets.
- Anchor-rod notes as notes.
- "By others" and connection-engineer language not turned into a member.

## Value

**HIGH.** S-600 / S-601 rows: section, BP mark, location, and "plate size not read." LEVEL 2 and LEVEL 3 with both slab and steel elevations. The revision table once it is shown as revisions, not as the issue.

**MEDIUM.** Braced-frame sheet ids S-200 and S-201. Foundation-detail and steel-detail titles. Steel grades A992 / A36 / A500 Gr.B.

**LOW.** 1588 wide-flange text hits. `SEE PLAN` counted 95 times without a target.

**MISLEADING.** "Permit set." The page-role sentence that 24 sheets are notes. Column-schedule labels on the overall plans and on the enlarged plans. A sheet scale of `1" = 1'-0"` or `1" = 30'-0"` if it is ever shown without the graphic-bar candidate beside it. Treating LEVEL 4 and "HIGH ROOF" as the same name without showing both.

## What is missing

The sheet list, grouped the way the titles already read: general (S-000–S-004), foundation (S-110–S-114), level 2 (S-120–S-124), level 3 (S-130–S-134), high roof (S-140–S-143), braces (S-200–S-202), sections (S-300–S-302), details, column schedules (S-600–S-601). Plate schedules or details that actually dimension BP1–BP9, found by reference, not guessed. LEVEL 1 and LOWER LEVEL left unmatched on purpose. Grid lines on the area plans. Joist marks, which the roof-joist loading plan (S-004) implies and the summary does not list as a schedule of joists.

## Add

- Sheet index with issue `65% DESIGN DEVELOPMENT` / `28 JANUARY 2025`, and revision rows underneath, including blank numbers and `FTG PERMIT` as a revision.
- Column rows and the BP unresolved list, already the best part of this summary.
- Level table with sheet title and schedule name both visible when they differ (HIGH ROOF versus LEVEL 4).
- Scale field and graphic-bar candidate as two lines when they differ.

## Do not add

- A permit-scope flag that drops or keeps steel because the revision table says FTG PERMIT.
- A size for BP8 invented from a typical detail without a printed link.
- A quantity of columns from 105 rows or from 102 plate marks.
- A level elevation chosen when LEVEL 1 and LOWER LEVEL have no plan.
- Joist counts from the loading plan without a printed joist designation on a schedule row or a plan label.
