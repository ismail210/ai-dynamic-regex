# Next engineering phase

Pair a reference letter with the view number printed beside it, when that number is its own text line. Do not start a model.

## Why this is next

`N/S502` on Furley already resolves to sheet `S502` with status `target_sheet_only`. `4/S-401` is `target_missing` and is not rewritten as `S-401-O`. The missing step is the printed view number that sits next to the detail title as a separate line. Until that line is read, `target_view_found` stays 0, which is the honest status.

## Acceptance

- A view number is taken from a short text line adjacent to a printed `DETAIL` or `SECTION` title, with a box for both lines.
- `target_view_found` is set only when that adjacent line matches the reference label.
- If the adjacent line is missing or more than one line matches, the status stays `target_sheet_only` or `ambiguous`.
- `4/S-401` remains `target_missing` when the index id is `S-401-O`.
- Family hits, column entries, and the mark map stay at the numbers in `REGRESSION_REPORT.md`.
- `QuantityEngine` stays unchanged.

## Do not schedule

- A model for view titles or sheet role.
- Choosing between OSSE Level 2 elevations `55'-2"` and `55'-10"`.
- Completing angle thickness or plate thickness.
- Treating a line as a beam or a rectangle as a column.
- Promoting grid candidates to confirmed grids without a bubble.
- Dropping sheets because they say existing, demo, alternate, future, or permit.
