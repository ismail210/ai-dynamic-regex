# Evidence checklist

For each manual test, save the following in this folder or next to your notes. Do not include access keys, passwords, or `.env` values in a screenshot.

- [ ] Test ID from `MANUAL_TEST_CASES.csv`
- [ ] PDF file name and page number
- [ ] Crop or photo of the printed cell, including the column headers
- [ ] Screenshot of the Drawing Summary row, or of Takeoff if the test is MT-15
- [ ] For MP rows: the matching object in `furley_page2_checked_rows.json`, because Drawing Summary does not list masonry piers
- [ ] For a level test: the **Levels and elevations** row and, for Brandywine, the **How the schedule's printed level labels read** line
- [ ] Mark-list check: C1 through C6 and L1 through L4 still match `EXPECTED_RESULTS.md` when the PDF is Furley
- [ ] Quantity check: Takeoff section rows, and a note that a schedule definition was not counted by itself
- [ ] Status: PASS, FAIL, or UNRESOLVED
- [ ] If FAIL or UNRESOLVED: what the sheet prints and what the screen shows

Suggested file names: `MT-01-pdf-cell.png`, `MT-01-screen.png`.

Before and after for this build:

- Pier width used to be treated as a present plate. It is now unresolved, with the bars kept separately. See MT-01 and MT-02.
- CL6A, CL8, and CL9 were missing the second line. That line is now in the source text. See MT-03.
- OSSE LEVEL 2 and Brandywine `A.3'-19` should look the same as before: still unresolved.
