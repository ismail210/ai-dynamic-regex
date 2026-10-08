# Warning coverage

Warnings stay `open`. Nothing is dismissed to clean the summary.

| Warning | Where it fired |
| --- | --- |
| Level conflict | OSSE `T.O. SLAB LEVEL 2`: schedule `55'-10"` on S602 and plan `55'-2"` on S122. Neither value is selected |
| Unresolved reference | `SEE PLAN` / `SEE SECTION` with no sheet (`ambiguous`); `N/S502` and `4/S-401-O` (`target_sheet_only`); `4/S-401` (`target_missing`). The warning list stores 30 of this type per set. `reference_count` is the full count (88, 88, 40, 175) |
| Ambiguous sheet | OSSE `DESIGN TABLES` and `NORTH STAIR & ELEVATOR PLANS AND ELEVATIONS` |
| Incomplete label | Printed angle text with no thickness, left unfinished |
| Defined but not seen | Schedule marks with no whole-word hit on another sheet. Absence is not a quantity of zero |

Scope words (existing, alternate, demolition, future, temporary) are flags with status `review`. They are not warnings that remove work, and they are not takeoff exclusions.
