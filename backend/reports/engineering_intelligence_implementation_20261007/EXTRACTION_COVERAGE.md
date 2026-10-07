# Extraction coverage — after this checkpoint

Measured on Burrville (29), OSSE (26), Struct.pdf (24), and Brandywine Structural4 (43). Sheet titles are the Phase 1 index, re-checked by a fresh extract on 7 October 2026.

| Capability | Coverage on these four sets | Status used |
| --- | --- | --- |
| Sheet id, title, issue, date, scale, revision rows | 122/122 pages carry a sheet-index record. Ids matched the prior index, including `S-122-O` | `read` / `not_shown` / `none_printed` as before |
| Sheet role from the title | 120 `read`, 2 `review` | `read` or `review` |
| View title | Whole-line titles only. Burrville 45 `read` / 20 `sheet_title`. OSSE 36 / 18. Struct.pdf 2 / 22. Brandywine 15 / 35 | `read` is a printed title. `sheet_title` means no separate viewport title. The box is the title line |
| Cross-sheet reference | Burrville 88 ambiguous. OSSE 84 ambiguous, 3 `target_sheet_only`, 1 `target_missing`. Struct.pdf 16 `target_sheet_only`, 24 ambiguous. Brandywine 175 ambiguous | `target_view_found` is 0. `N/S502` does not invent view N. `4/S-401` is not rewritten as `S-401-O` |
| Grid candidates | 80 stored on each set, status `candidate` | Capped sample, not a bubble survey. Feet-inch strings are dimensions |
| Building levels and conflicts | OSSE Level 2 still keeps `55'-10"` and `55'-2"` | `conflict`. Neither value is selected |
| Occurrences | Text hits with `quantity` null. Burrville 15 seen / 1 not seen. OSSE 26 / 1. Struct.pdf 46 / 4. Brandywine 4 / 0 | Not a takeoff count. Grid and level on the hit are empty |
| Schedules | Existing readers, pointed at from the new object | Not a new parser. A row is not an occurrence |
| Notes | OSSE 73, Brandywine 35, Burrville 0, Struct.pdf 0 | Numbered lines on general-notes sheets only |
| Dimensions | Burrville 266, OSSE 660, Struct.pdf 317, Brandywine 835 whole lines | A dimension does not create a member. A bare number is not a dimension |
| Incomplete labels | Burrville `L6X3`, `L4X3` and the OSSE and Brandywine pairs stay unfinished | `review_required`. Thickness is not filled in |
| Detail boundaries and geometry facts | Not measured | unsupported |

`read` views and `candidate` grids are not resolved engineering facts. Ambiguous `SEE PLAN` notes are not resolved targets.
