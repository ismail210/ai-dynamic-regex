# Burrville — Drawing Summary engineering assessment

PDF: `backend/uploads/Burrville ES - ST.pdf`. 29 pages. Summary status SUCCESS. Sheet-index layout `right_column`, 29/29 pages in the title-block slot.

## What the summary contains

Every sheet id and title was read from the title block, including `S-101B`, `S-103C`, and `S-502`. Issue on every sheet is `50% DESIGN DEVELOPMENT`, date `4/7/2026`. Revision tables are empty. Scales are the title-block field: `As indicated` on 18 sheets, `3/4" = 1'-0"` on the detail and section sheets that print it, `3/16" = 1'-0"` on the elevations, `1/8" = 1'-0"` on the column schedules. Sheet `S-003` prints no scale.

The screen does not show that list. The first sentence is: "29-page structural set with a steel column schedule on S501; concrete schedules are kept with the supporting information." The scope sentence is: "No explicit issue/revision/phase markings detected."

The column schedule on S-501 and S-502 has 121 steel entries. Locations are printed grid strings such as `A-6.5`, `A-7`, and `D(-3' - 10 5/8")-H(-1' - 4")`. Plates: 61 read (for example `1"x18"x18"` base plate), 57 not shown, 3 blank. There is no mark map. Grade beam, spread footing, and concrete pier schedules on S-101A are supporting, non-steel.

Levels from the schedule agree with plan datums:

| Level | Schedule | Plan |
| --- | --- | --- |
| UPPER ROOF | 44'-6" S-501 | S-104 top of deck 44'-6" |
| MAIN ROOF | 29'-0" | S-103A top of deck 29'-0" |
| UPPER LEVEL | 14'-6" | S-102A top of slab 14'-6" |
| GROUND LEVEL | 0'-0" | S-101A top of slab 0'-0" |

Top-of-steel notes on S-102A, S-103A, and S-104 are unresolved. Bracketed beam tags such as `W27X84 [88]` are unresolved because no framing key defines the bracket. That is the correct abstention.

## What it gets right

- Sheet ids and titles, when read from the profile rather than from the screen.
- Column section, plate size, and schedule location as a review list, with the explicit statement that rows are not quantities.
- Level names tied to elevations, and agreement checked against the plan datum instead of a guessed height.
- Footings and piers kept out of the steel list.
- The note that S-202 holds references and the definitions live on S-501.

## Value

**HIGH.** Column schedule rows (section, plate, location). The four level elevations and the fact they match the plans. The unresolved `[88]` bracket.

**MEDIUM.** Supporting footing, pier, and grade-beam schedules as navigation to non-steel tables. `50% DD` / `4/7/2026` once it is actually shown.

**LOW.** Family chips (801 wide-flange text hits, 83 HSS, 60 angles). `TYP` / `SEE PLAN` callout hits (307 callouts, dominated by those words).

**MISLEADING.** "No explicit issue/revision detected" while every sheet is 50% DD. Page roles: S-101A (foundation and first-floor plan) classified as a schedule; S-201, S-204, S-207, S-208 (typical details) classified as notes; S-203 (typical details) classified as floor framing; S-301 and S-311 (sections) unclassified; S-401 and S-402 (elevations) classified as unlabeled framing. Schedule insights call page 15 (S-202 typical details) and page 18 (S-205 typical details) column schedules. The orientation sheet id `S501` drops the hyphen the title block prints (`S-501`).

## What is missing

A sheet list the engineer can scan. A foundation / framing / section / detail grouping taken from the titles above. Detail and section bubbles (`SEE SECTION` is counted as text, not linked to a view). Plan grid lines, as distinct from the schedule's location string. Where each `W` on S-102 occurs. Scope shown as `50% DESIGN DEVELOPMENT`, not as silence.

## Add to the summary

- One row per sheet: id, title, page, issue, date, scale field.
- Groups built from those titles: foundation and first floor (S-101), upper floor (S-102), roof (S-103, S-104), details (S-201–S-208), sections (S-301–S-322), elevations (S-401–S-402), column schedules (S-501–S-502).
- The four levels, already correct, next to that index.
- Unresolved top-of-steel and unresolved brackets, already detected, kept as review.

## Do not add

- A quantity from the 121 schedule rows or from the 801 text hits.
- A decision that "existing" tags (6 hits, renovation flag false) remove anything from scope.
- A guessed meaning for `[88]`.
- Grid names parsed out of dimensions. The offset in `D(-3' - 10 5/8")-H(-1' - 4")` must stay an offset on grids D and H, which is how that one string is already stored.
