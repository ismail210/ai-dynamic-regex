# Next extraction roadmap

Ordered by what the four projects showed, not by model capability. Each phase is display and evidence. The takeoff rule does not change in any of them: labeled callouts count, schedule rows do not, geometry does not, incomplete labels stay incomplete.

## Phase A — Put the sheet index on the summary

The index is already produced for all 122 pages. The work is to render it and to stop the orientation from contradicting it.

- Sheet id, title, title status, page, issue, issue date, scale field, revision rows.
- Role label from the title: foundation, framing, roof, section, elevation, detail, schedule, notes, loading, braced frame.
- Delete or stop showing the page-keyword makeup sentence.
- Orientation may say "50% design development" or "bid set" or "65% design development" only by quoting `issue`.
- Brandywine `FTG PERMIT` stays a revision row.
- Furley plan elevations render as local notes even though there is no schedule level.
- OSSE duplicate parking level is shown once the two source rows are confirmed identical; until then both rows stay, marked as a possible double read.

Acceptance: an engineer can answer "what sheets exist and what is the issue?" from the summary alone, and the answer matches the title block on these four PDFs. No quantity number changes.

## Phase B — Views and references

- View title, view number, and view scale, from printed viewport titles. Sheet scale stays a different field.
- A reference object for a printed bubble or a note such as `N/S502`.
- Target sheet is found only by equality with the sheet index, including `-O` and letter suffixes.
- Target view is found only by a printed view title with that number. Otherwise status is `not_matched`.
- No "this detail governs this member."

Acceptance: Furley `D/S401` and `N/S502` resolve to a sheet, and the view match is either a printed title or an explicit miss. A sample of Burrville and Brandywine `SEE SECTION` / `SEE DETAIL` notes is either linked or left unmatched. Precision is judged on a human sample. Quantity unchanged.

## Phase C — Occurrence ledger and grids

- For each schedule mark, search plan text for that mark and record sheet hits. Furley C1–L4 are the first test. Zero hits stays "not found," not a quantity of zero.
- Grid bubbles on plan views only. Reject any token that is a feet-inch dimension.
- A member gets a grid intersection only when its label and two bubbles are in the same view and the geometry of that intersection is measured. Otherwise `grid_not_read`.
- Compare the ledger total to the current labeled-callout total. Report the difference. Do not replace the total.

Acceptance: the ledger does not change takeoff output. Feet-inch strings accepted as grid names: zero.

## Phase D — Only after A–C are on screen

- BBX: add sheet id from the index onto the existing label box. View, grid, and level only when those statuses are `read`. Member-box status stays `present`, `absent`, or `ambiguous`. The member box never creates a quantity.
- Plate-size chase for Brandywine BP1–BP9: follow a printed reference from the column cell to a plate schedule or a titled detail. If the reference is missing, the size stays unresolved.
- Do not open an external fabrication export. There is no BBX contract of that kind in this repository.

## Not scheduled

- A model to classify sheets. The titles are printed.
- A model to choose between conflicting elevations.
- A model to complete angles, plate thicknesses, or joist counts.
- Geometry-based member identity.
- Automatic scope exclusion from the words existing, demo, alternate, future, or permit.

## Why this order

The engineer’s first question on these four sets is which sheet to open, and at what issue. That answer is already extracted and currently hidden, while a weaker sentence sometimes gives the wrong issue. Showing it is cheaper and safer than any new extractor. References and occurrences are the next real gap, and they are printed text plus the index. Grids and BBX come after, because a location without a sheet and a view is how a dimension becomes a false grid.
