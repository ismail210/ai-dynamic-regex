# Issues

Only items checked against a rendered page or against the PDF text layer after a render disagreed. Quantity impact uses `schedule_mark_map` from the in-memory extract. Plate and grid-location rows were not in that map unless noted.

## Confirmed defects

### 1. Furley Struct.pdf page 2 — inspection notes merged into bearing-plate cells

- Severity: HIGH for the schedule text. No quantity impact found.
- Printed (crop `renders/struct_p2_bp4_crop.png`): BP4 `6"x8"x3/4"`, BP5 `6"x10"x1"`, BP6 `4"x10"x1 1/4"`, remarks blank except BP7 `SEE S/S502`.
- Extracted `size_text` / `plate_text` for BP4–BP6 includes sentences from the adjacent inspection tables (`PLACEMENT OF REINFORCEMENT`, `SI - DENOTES SPECIAL INSPECTOR`, `TYPE OF INSPECTION`) plus the real plate size.
- The same bleed hits several ICF lintel rows (CL1, CL3, CL4, CL6, CL6A).
- `schedule_mark_map` contains C1–C6 and L1–L4 only. BP and CL marks are absent. `catalog_valid` is false on the plate rows.
- Next action: keep the ruled-table reader inside the schedule border. Do not add these strings to the mark map.

### 2. Springhill pages 26–27 — three plate cells are not dimensions

- Severity: MEDIUM. No quantity impact found.
- Extracted `plate_text`: `11"x"1x188"x"1x188" "**` on 3 rows.
- No matching word was found by searching `11"` on those pages. The surrounding real plate words are forms such as `1/4"x18"x18"` and `3/4"x18"x18"`.
- The mark map for this PDF is empty.
- Next action: reject a plate string that is not a dimension instead of storing it.

## Partial results (not counted as failures)

### 3. Brandywine pages 42–43 — tight feet-inch band labels are not split

- Severity: MEDIUM for the level-band fields. No quantity impact.
- The sheet prints level lines LEVEL 4 `42'-0"` through LOWER LEVEL `-5'-0"`. Those five pairs are extracted correctly as level lines.
- Row labels such as `14'-0" LEVEL 1` have no spaces around the dash. `printed_name` is the entire label, `printed_elevation` is null, and `prefix_status` is `absent` (50 and 49 rows).
- `pairing` is `unpaired`, so the two parts are not stored as one canonical level. Burrville and Springhill, which print a spaced datum (`29' - 0"`, `14' - 0"`), do split `printed_elevation` and `printed_name` and also stay `unpaired`.

### 4. Brandywine location cells — many left uncertain

- Severity: MEDIUM. No quantity impact. Grid-location rows are excluded from the mark map.
- 14 rows keep a printed offset such as `C-8(-4'-4")` with `direction` null.
- 62 of 112 location rows are `uncertain`, including overflow fragments like `) O.6'-18'`.

### 5. Furley Struct.pdf page 2 — masonry pier size stored as a plate width

- Severity: MEDIUM. No quantity impact. MP marks are not in the mark map.
- MP16 is extracted with `plate_status` `present` and width `16"`. The schedule column is vertical bars (`1-#5`), not a plate.

### 6. Burrville page 28 — extra `level_span` evidence missing

- Severity: LOW. `level_band` pairing on that page is still `unpaired` with `29' - 0"` and `UPPER LEVEL`, which matches the drawn lines.

## Correct behavior worth keeping

- Brandywine BP1–BP9 plate thickness, width, and length match the schedule. Washer diameters (BP1 `2 3/4"`, BP8 `2 3/4"`, and the other seven rows in the cropped washer column) stay in `plate_accessories`.
- Combined cells such as Struct.pdf C1 `14"x14"x3/4"` keep the printed string and leave thickness, width, and length null.
- CL5 and CL9 stay `unresolved` and out of the mark map.
- L5 (`12F16-IB` precast) is not given a steel section.
- Springhill `W10X45` on page 26 matches a high-zoom crop.
- Springhill `14' - 0" FIRST FLOOR` is stored as elevation `14' - 0"` and name `FIRST FLOOR` with pairing `unpaired` (the elevation belongs to SECOND FLOOR's line).

## Not defects

- Empty upper bands and `SEE PLAN` cells that do not become catalog sections.
- Detail titles containing "BASE PLATE" on Ketcham page 9. That page is not a column schedule.
