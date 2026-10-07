# Reference coverage

A sheet token must start with `S` and a digit. `W/ SPEC` and `T/ SLAB` are not references.

| Project | ambiguous | target_sheet_only | target_missing | target_view_found |
| --- | --- | --- | --- | --- |
| Burrville | 88 | 0 | 0 | 0 |
| OSSE | 84 | 3 | 1 | 0 |
| Struct.pdf | 24 | 16 | 0 | 0 |
| Brandywine | 175 | 0 | 0 | 0 |

`target_view_found` is 0 on these four sets. The view letter is not printed on the same line as `DETAIL` or `SECTION`, so the sheet can be found and the view cannot.

Examples:

- Furley `N/S502` on S102A → sheet `S502`, status `target_sheet_only`. View N is not invented.
- OSSE `4/S-401-O` → sheet `S-401-O`, status `target_sheet_only`.
- OSSE `4/S-401` → `target_missing`. The missing `-O` is not filled in.
- Burrville and Brandywine `SEE PLAN` / `SEE SECTION` / `SEE DETAIL` with no sheet → `ambiguous`.

None of these edges change a quantity.
