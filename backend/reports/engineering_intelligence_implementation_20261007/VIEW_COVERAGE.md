# View coverage

A view is `read` only when the whole text line is a view title. `SECTION A` qualifies. A bare `SECTION` qualifies only when a scale line sits under it. Otherwise the sheet contributes one `sheet_title` view taken from the title block, and that status means “no separate viewport title was found.”

The box is the title line. `boundary_status` is `title_only` or `sheet_title`. It is not a measured view extent.

| Project | `read` viewport titles | `sheet_title` only | Examples of `read` |
| --- | --- | --- | --- |
| Burrville | 45 | 20 | `SECTION A` on S-201 |
| OSSE | 36 | 18 | `ELEVATION` with scale `1/4" = 1'-0"` on S-103-O |
| Struct.pdf | 2 | 22 | `FLOOR FRAMING` on S102C. Detail letters such as N on S502 are not on the same line as a title, so they are not views |
| Brandywine | 15 | 35 | `PLAN` on S-300 |

`sheet_title` is navigation context, not a segmented viewport.
