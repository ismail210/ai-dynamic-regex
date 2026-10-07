# Gaps remaining

Measured after the 7 October 2026 extract of Burrville, OSSE, Struct.pdf, and Brandywine. Counts are in `four_project_intelligence.json`.

| Rank | Gap | What is true now | What is still missing |
| --- | --- | --- | --- |
| 1 | View number on its own line | `SECTION A` is a view. `N/S502` finds sheet S502 | The letter N is not on the same line as `SECTION` or `DETAIL`, so `target_view_found` is 0 on all four sets. The box is the title line, not a view extent |
| 2 | Source view of a reference | The source sheet and the printed text are stored | `source_view` is empty. The bubble is not placed inside a plan view |
| 3 | Confirmed grids | Feet-inch strings are rejected. Short labels on plan sheets are stored as `candidate` | The list is capped at 80 and was full on every set. No circle or bubble test. No grid is attached to a mark |
| 4 | Occurrence location | Whole-word hits off the definition sheet, with `quantity` null | Grid and level on each hit are empty. A hit is not a takeoff count. Marks that are only a section size (`W12X40`) are not in the ledger |
| 5 | Notes that are not numbered | OSSE 73 and Brandywine 35 numbered lines | Burrville and Furley general notes are not in the `1.` form, so the count is 0 |
| 6 | Schedule readers | Existing column and supporting schedules are pointed at, not replaced | No new lintel, pier, footing, or wall reader. A schedule row is still not an occurrence |
| 7 | Incomplete angles | `L4X3` and `L6X3` stay `review_required` | No schedule cross-reference is proposed, even when a unique thickness might exist. That is intentional |
| 8 | Detail boundaries | Not measured | Geometry is still evidence, not a member and not a view outline |
| 9 | Collapsed extraction block | Hidden from the main navigation when a sheet index exists | Older page-keyword schedule hints can still call a detail sheet a column schedule inside that block |

Do not automate: member identity from geometry, completing `L4x4`, inventing plate thickness, picking one side of the OSSE Level 2 conflict, or treating `FTG PERMIT`, existing, demo, alternate, or future as out of scope.
