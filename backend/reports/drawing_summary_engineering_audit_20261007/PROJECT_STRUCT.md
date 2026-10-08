# Struct.pdf (Furley) — Drawing Summary engineering assessment

PDF: `backend/uploads/Struct.pdf`. 24 pages. This is the Furley structural set. Summary status SUCCESS. Sheet-index slot 24/24.

## What the summary contains

Titles are unlabeled and vertical. The reader marks them `read_unlabeled` and still gets the sheet title: `S001` GENERAL NOTES, `S101A` FOUNDATION AND SLAB ON GRADE PLAN - AREA A, `S401` FOUNDATION SECTIONS, `S505` FRAMING SECTIONS. Issue on every sheet is `BID SET`, `11/14/2022`. No revision rows. No sheet scale in the title block. The orientation says "bid set" and points at a column schedule and lintel, column, bearing-plate, and ICF-lintel marks on S002. That sentence is fair.

The visible column schedule is six marks:

| Mark | Section | Base plate |
| --- | --- | --- |
| C1 | HSS6X6X1/2 | 14"x14"x3/4" |
| C2 | HSS7X7X3/8 | 16"x16"x3/4" |
| C3 | HSS8X8X1/2 | 16"x16"x3/4" |
| C4 | W10X49 | (with the other three, all six plates are status `read`) |
| C5 | HSS12.750X0.375 | |
| C6 | HSS12X8X5/8 | 20"x14"x1-1/4" on C6 |

Listed locations on these rows are 0. The schedule defines the mark. It does not say where the mark sits. The mark map has the same 12 steel marks: C1–C6 as above, L1/L1A W8X21, L2/L2A W8X28, L3 W16X36, L4 W24X62. Lintels, bearing plates, and ICF lintels are separate definitions. Three ICF rows are `no steel`. Masonry pier (5), spread footing (6), wall footing (6), and concrete pier (3) schedules on S002 are supporting, not steel plates.

There is no schedule level, so the Levels section of the screen does not open. Eleven plan elevations are still extracted and then hidden by that gate. They are local slab notes, not a building level list: S101A top of slab `-0'-3"` and `-0'-6"`; S101B also `+1'-4"`; S102A top of slab `14'-8"` and a derived top of steel `14'-3"`; S102C top of slab `19'-4"`. Seven notes say a parenthetical `(0.00')` means top of steel, on the roof and second-floor sheets. Bracketed beam tags such as `W14x22 [10]` stay unresolved: no framing key.

Useful notes that are captured as rules, not as links: HSS columns get a 5/8" cap plate unless noted otherwise; bearing-plate size applies to each end; lintel bottom is 8" above the opening unless noted otherwise; a continuous angle refers to detail N/S502.

The page-makeup sentence, in the collapsed block, does not match the titles. S101A and S101B (foundation plans) are notes/legend. S301 and S303 and S304 (typical details) are notes. S302 (typical details) is a schedule. S401 (foundation sections) is unclassified. S501 (framing sections) is notes. S504 (framing sections) is unlabeled framing. The schedules narrative says "No structural schedules identified," which is false, but that sentence is hidden when it begins with "No". The column schedule itself is shown.

## What it gets right

- Bid set and the date, in the profile, and "bid set" in the orientation.
- Unlabeled titles still read as the sheet title.
- C1–C6 sections and base-plate sizes, and L1–L4 in the mark map.
- Piers and footings not turned into steel plates.
- Cap-plate and lintel notes kept as rules.
- Incomplete bracket notation left unresolved.
- Detail pointer text such as `REFER TO DETAIL N/S502` survives as note text.

## Value

**HIGH.** The six column definitions with plate sizes. The lintel and bearing-plate definitions. The mark map as a dictionary, not a count. The cap-plate and lintel position notes.

**MEDIUM.** Sheet titles and `BID SET 11/14/2022`, once listed. The `(0.00')` = top of steel notes. Local slab elevations, once shown as local notes rather than as the building's level list.

**LOW.** 991 wide-flange text hits, 106 angles, 59 HSS. `SIM.` callouts.

**MISLEADING.** Page roles for the foundation plans, detail sheets, and section sheets, as listed above. Treating the slab spots `-0'-6"` and `+1'-4"` as if they were the project's floor elevations. They are depressions and local tops on the foundation sheets. Family chips if anyone reads "991×" as pieces.

## What is missing

Where C1 through L4 occur on S101 and S102. Grid bubbles on those plans. The section cut `D/S401` resolved to the view `D SECTION` on S401 (checked by eye in the earlier roadmap; not an object in this summary). View scales, which are on the views, not in the title block. A sheet list. The plan elevations, which are extracted and then not rendered because there is no schedule level.

## Add

- Sheet index, titles flagged `read_unlabeled` so the engineer knows there was no DRAWING TITLE label.
- Column and lintel definitions, already shown, plus "locations not printed on this schedule."
- Plan elevations as local notes with sheet and raw text, not as a level register.
- The N/S502 reference as a link candidate, status "target sheet known, target view not yet matched."

## Do not add

- A count of C1 from the schedule.
- A thickness filled in for an incomplete angle.
- A plate count taken from a pier width. That mistake was already corrected; the pier schedule must stay non-steel.
- A single building elevation invented by averaging `-0'-3"`, `-0'-6"`, and `+1'-4"`.
- Geometry that turns a line on S101A into a beam.
