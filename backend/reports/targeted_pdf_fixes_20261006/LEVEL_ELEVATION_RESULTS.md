# Level and elevation results

Parsing and pairing stay separate. `_split_transposed_level_label` only reads a single leading feet-and-inches datum. `attach_level_bands` sets `pairing` from the schedule’s drawn level lines. A name and an elevation in one printed string are not paired with each other unless one drawn line prints both.

The datum pattern now allows optional spaces around the dash, an optional leading minus, and an optional inch fraction: `14'-0"`, `14' - 0"`, `-5'-0"`, `13'-6 3/4"`. It still requires a foot mark and an inch quote. `14'`, `A-14`, `W14X22`, and `1"x18"x18"` do not split. Two datums, or a datum that is not at the start, stay `unresolved`.

## Real PDFs

Re-extract is in `extract_brandywine.json`, `extract_burrville.json`, and `extract_springhill.json`.

| Project | Printed band | printed_elevation | printed_name | pairing | elevation_of | name_of |
| --- | --- | --- | --- | --- | --- | --- |
| Brandywine page 42–43 | `14'-0" LEVEL 1` | `14'-0"` | `LEVEL 1` | unpaired | LEVEL 2 | LEVEL 1 |
| Burrville | `29' - 0" UPPER LEVEL` | `29' - 0"` | `UPPER LEVEL` | unpaired | MAIN ROOF | UPPER LEVEL |
| Springhill | `14' - 0" FIRST FLOOR` | `14' - 0"` | `FIRST FLOOR` | unpaired | SECOND FLOOR | FIRST FLOOR |

Before this change, Brandywine kept the whole string as `printed_name`, with `printed_elevation` null, because the old pattern required spaces around the dash (`14' - 0"`). Pairing was already `unpaired`. After the split, pairing is still `unpaired`. The drawn lines put `14'-0"` on LEVEL 2 and the name LEVEL 1 on the line below. `level` stays null. That is the established band contract: the text between two lines is the upper line’s elevation and the lower line’s name.

Burrville and Springhill already split. Their pairing did not change. All 50 sampled Brandywine bands that carry these labels are `unpaired`. No band was forced to `paired`.

## What the tests lock

- Compact `14'-0" LEVEL 1` splits and stays unresolved until a drawn line says otherwise.
- Spaced `29' - 0" UPPER LEVEL` and `14' - 0" FIRST FLOOR` split the same way.
- One drawn line that prints both parts → `paired`, and `level` is that line.
- Upper elevation plus lower name on two lines of the same block → `unpaired`, `level` null.
- The same texts on different blocks stay `unresolved`.
- Zero `0'-0"` and negative `-5'-0" LOWER LEVEL` split.
- Incomplete `14'` and non-elevations do not split.

`column_level_endpoints` counts did not change: Brandywine 96 complete and 1 gap, Burrville 54 complete.
