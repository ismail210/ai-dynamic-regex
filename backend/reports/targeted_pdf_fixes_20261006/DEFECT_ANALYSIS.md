# Defect analysis

## Springhill plate cells

PDF: `backend/uploads/ST - Springhill Lake__f6ddc4a7e233.pdf`, page 27 (PyMuPDF index 26).

The ruled table’s `extract()` returned `11"x"1x188"x"1x188" "**` for three cells. The words inside those cell rectangles are two copies of `1"x18"x18"` whose boxes overlap by most of their area, plus `**`. Example for the first cell, rectangle about `(504.8, 582.0, 577.1, 618.1)`:

| Word | Box |
| --- | --- |
| `1"x18"x18"` | `(512.9, 596.0, 559.0, 605.6)` |
| `1"x18"x18"` | `(517.9, 596.0, 564.1, 605.6)` |
| `**` | `(561.6, 596.0, 569.1, 605.6)` |

`table.extract()` interleaves the two copies character by character. The same pattern is on N-20 and N.2-12.

Cause: duplicate overlapping text spans, not a wrong plate size and not a neighboring column. A cell with only one word is left as extracted, so a malformed string is not replaced by a guess.

Correction: `schedule_tables._collapse_overlapping_copies`. After `extract()`, a word is dropped only when the same text already kept in that cell covers at least half of its box. The kept words are joined in reading order.

| Location | Before | After | Plate status |
| --- | --- | --- | --- |
| M-20 | `11"x"1x188"x"1x188" "**` | `1"x18"x18" **` | unresolved → present, dimensions `1"`, `18"`, `18"`, notes `**` |
| N-20 | same garbage | `1"x18"x18" **` | same |
| N.2-12 | same garbage | `1"x18"x18" **` | same |

The rendered crop `renders/springhill_p27_plate_cells.png` shows `1"x18"x18" **` in the plate row. The garbage string is gone from the re-extract (`garbage count 0`). The trailing stars were already accepted for a single `*`; the plate-size pattern now allows more than one star so `**` stays a note and not part of the dimension. `_interpret_plate` already put a single plate match’s remainder into `notes`.

Code: `backend/services/engineering/schedule_tables.py`.

## Furley schedule contamination

PDF: `backend/uploads/Struct.pdf`, page 2 (S002).

`find_tables` already returns a tight bearing-plate table whose BP4 cell is `6"x8"x3/4"`. Production was keeping the word-cluster row. BP and CL rows are auxiliary marks, and a cluster row for the same mark replaces the ruled row. Clustering groups every word on the same baseline. Inspection-table words at x about 172–1400 share that baseline with the schedule at x about 2018.

The non-auxiliary path already ignores words left of MARK or right of the rightmost header. The auxiliary path did not. `_words_in_header_span` applies that same window before the BP/CL split. MARK is at x 2013.7, SIZE at 2091, REMARKS at 2171. Inspection words fall left of MARK minus 48 points. `SEE S/S502` stays inside the remarks window.

| Mark | Before | After | Drawing |
| --- | --- | --- | --- |
| BP4 | `c. PLACEMENT OF REINFORCEMENT AND CONNECTORS c. PERIODIC 6"x8"x3/4"` | `6"x8"x3/4"` | `6"x8"x3/4"` |
| BP5 | `SI - DENOTES SPECIAL INSPECTOR 6"x10"x1"` | `6"x10"x1"` | `6"x10"x1"` |
| BP6 | `TYPE OF INSPECTION 4"x10"x1 1/4"` | `4"x10"x1 1/4"` | `4"x10"x1 1/4"` |
| BP7 | `7"x9"x3/4"` | `7"x9"x3/4"`, notes `SEE S/S502` | size `7"x9"x3/4"`, remarks `SEE S/S502` |
| CL1 | inspection sentence plus the lintel row | `STANDARD WALL WITH 2-#5 AT HEAD LOOSE ANGLE 5"x5"x3/8" REFER TO DETAIL` | those are the printed cells on that line |
| CL5 | `STEEL DECK STANDARD WALL WITH 2-#6 AT HEAD N/A N/A` | `STANDARD WALL WITH 2-#6 AT HEAD N/A N/A` | concrete core, brick type N/A, angle size N/A |
| CL3, CL4, CL6, CL6A | inspection sentences mixed in | the schedule’s own line only | matches the ICF crop |
| CL7, CL9 | already unresolved | still unresolved | angle size is N/A |

`renders/struct_p2_bearing_plate.png` and `renders/struct_p2_icf_lintel.png` match those readings. CL6A, CL8, and CL9 also print a second line (`#4 STIRRUPS AT 12"o.c.`). That line is not on the mark’s baseline, so it is still omitted. It was omitted before this fix as well.

A short SIZE cell that contains `N/A` and no plate or angle dimension no longer becomes a plate display. Headed plates such as Brandywine BP1–BP9 still resolve, because their dimension text is parsed before that check. CL5 would otherwise have become a plate sentence once `STEEL DECK` was removed and the remaining text fell under the 40-character fallback.

Code: `backend/services/engineering/schedule_grid.py` (`_words_in_header_span`, `_short_unparsed_display`).

Mark map before and after, 12 entries, identical:

`C1 HSS6X6X1/2`, `C2 HSS7X7X3/8`, `C3 HSS8X8X1/2`, `C4 W10X49`, `C5 HSS12.750X0.375`, `C6 HSS12X8X5/8`, `L1 W8X21`, `L1A W8X21`, `L2 W8X28`, `L2A W8X28`, `L3 W16X36`, `L4 W24X62`.

BP, CL, and L5 are not in the map.
