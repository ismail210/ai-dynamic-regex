# Extraction taxonomy

**Level A** — printed, extractable reliably. **Level B** — evidence-backed relationship; expose evidence; may need review. **Level C** — engineering judgment; never decided automatically.

**Qty** says whether the item may affect a quantity: **No**; **Excl** (may only exclude or flag, never add); **Yes, gated** (may count only through the existing labeled-callout path after the gates in `EVIDENCE_MODEL.md`).

**Today**: **Y** exists; **P** partial or pilot; **N** missing.

## A. Sheet identity

| Item | Engineering question | Level | Qty | Today | Evidence needed |
| --- | --- | --- | --- | --- | --- |
| Sheet number (project grammar: `S101A`, `S2.01`, `S-122-O`) | Which sheet is this page? | A | No | P | Title-block region word; unique per page |
| Sheet title | What does it show? | A | No | P | Title-block field next to `DRAWING TITLE` or largest title text |
| Discipline (S, A, C, M) | Is it structural? | A | Excl | P | Sheet prefix + title block |
| Project name / number | Which job? | A | No | N | Title block (OSSE `W3793`) |
| Issue / submission / date | Which issue? | A | No | N | Title block (OSSE `Submission 10/12/2023`) |
| Revision number / description / delta | Is it superseded? | A | Excl | N | Revision table rows |
| Drawn / checked / designed by | Reviewer context | A | No | N | Title block |
| Sheet scale | Can anything be measured? | A | No | Y | `drawing_scale`; per-view scale overrides sheet scale |
| Consultant / engineer of record | Who answers RFIs | A | No | N | Title block |

## B. Drawing classification and regions

| Item | Question | Level | Qty | Today | Evidence |
| --- | --- | --- | --- | --- | --- |
| Page category (framing, foundation, schedule, details, notes…) | What kind of sheet? | A/B | Excl | Y (one per page) | Title text + content signals |
| View (region) with its own title, number, scale | What drawings are on this sheet? | A for title; B for extent | Excl | N | View-title bubble (number over own sheet id) + title words + `SCALE:`; extent from borders / whitespace |
| View type (plan, section, detail, elevation, schedule, notes, key plan) | How should its labels be treated? | B | Excl | N | View title words; schedule table bbox |
| Title block / revision block / notes / legend region | What is not drawing content? | A/B | Excl | P | Position + keywords |
| Match lines, continuation | Is this plan split across sheets? | A | No | N | `MATCH LINE` text (Burrville 2, Springhill 2) |
| Key plan / area | Which part of the building? | B | No | P | `view_scope` |
| Mixed-content sheet | Do several types share a page? | B | Excl | P | More than one view type on one page |

## C. References

| Item | Question | Level | Qty | Today | Evidence |
| --- | --- | --- | --- | --- | --- |
| Detail / section bubble `D/S401`, stacked or inline | Where is this condition drawn? | A | No | N | Number word over sheet word inside a circle, or an inline `n/Sxxx` |
| Target sheet exists in PDF | Can we navigate? | A | No | N | Sheet index |
| Target view exists with the same number | Can we open the exact detail? | B | No | N | View-title bubble on the target sheet with the same label |
| Section cut direction / extent | Which way is the section cut? | B | No | N | Cut-line geometry and arrows |
| `SEE ARCH`, `SEE SCHEDULE`, `SEE PLAN` | Information lives elsewhere | A | No | P | Text; `SEE PLAN` is handled for levels |
| `TYP`, `SIM` | Does this apply to other places? | A for text; C for scope | Excl (TYP x N only when printed) | P | Printed note; multiplier only if `x N` is printed |
| Reference governs a specific member | Does detail D apply to beam B12? | B/C | No (review) | N | Reference printed at the member, or a leader to it |

## D. Grids and location

| Item | Question | Level | Qty | Today | Evidence |
| --- | --- | --- | --- | --- | --- |
| Grid identity (`19`, `A.3'`, `K.2'`, `C.8`) | Name of the grid line | A | No | P | Bubble text inside a circle |
| Grid line geometry per view | Where is it? | B | No | P (`column_trace._axes`) | Long line through a bubble centre |
| Grid intersection location string `C.8-8.9` | Where is this column? | A when printed; B when computed | No | P | Printed in a schedule; or the crossing of two axes |
| Between-grids location of a label | Where is this beam? | B | No | N | Label bbox vs axes in the same view |
| Offset from grid (`(-4'-4")`) | Exact position | A for value; B for direction | No | P | Printed; direction is unresolved unless drawn |
| Grid vs dimension vs elevation (`26'-11 5/8"`, `A-9`, `14'-0"`) | What kind of token? | A | Excl | P | Foot/inch marks; bubble context |

## E. Levels and elevations

| Item | Question | Level | Qty | Today | Evidence |
| --- | --- | --- | --- | --- | --- |
| Level name in schedule | Which floors exist? | A | No | Y | Schedule row label |
| Printed elevation | At what height? | A | No | Y | Same cell or line |
| Name ↔ elevation pairing | Which elevation belongs to which name? | B | No | Y (drawn lines only) | Drawn level line printing both |
| Plan value (TOS, TOSL, `EL.`) | What the plan says | A | No | Y | Plan note |
| Datum / reference elevation | Relative vs true elevation | A | No | Y | Burrville `14'-6"` = `112'-0"` |
| Conflict schedule vs plan | Which is right? | C | No | Y (kept) | Human decides; OSSE LEVEL 2 |
| Column top / bottom level | Column extent | B | No (future length) | P | Schedule tier lines; trace |

## F. Members

| Item | Question | Level | Qty | Today | Evidence |
| --- | --- | --- | --- | --- | --- |
| W / S / M / HP / C / MC / WT / ST / HSS / pipe / L / 2L, printed complete | What section? | A | Yes, gated | Y | Exact catalog form |
| Incomplete (`L4x4`, `W18`, `HSS6`, `PL`) | What is missing? | A (as printed) | No | Y (review) | Never completed |
| Mark (`B12`, `L1`, `C3`) | Which schedule row? | A | Via map, gated | Y | Mark map |
| Plates (base, bearing, cap, stiffener, connection, bent) | Plate size | A when headed | No (hint only) | Y / P (bent) | Headed dimensions; bent plates need their own schema |
| Anchor rods, bolts, welds | Connection hardware | A when printed | No (future, separate line) | P (in plate rows) | Schedule columns |
| Joists, deck | Joist / deck designation | A | Future, separate family | P | Joist and deck schedules; `17K`-style marks |
| Concrete, masonry, footings, piers, walls | Non-steel | A | No (steel takeoff) | Y (non-steel kinds) | Schedule kind |
| Reinforcement text (`#4 STIRRUPS AT 12"o.c.`) | Rebar | A as text | No | Y as text | Never a steel quantity |
| Misc. metals (lintels, loose angles) | Lintel members | A | Yes, gated | Y | Lintel / ICF schedules + plan marks |

## G. Schedules

Schedule identity, header (including two-row and grouped headers), rows, mark, section, dimensions, material, notes, level tiers, location, accessories, source page, crop box, and unresolved fields — **A** for printed cells; **B** for header association in merged or overlapping tables. Covered today for lintel, column, plate, ICF, pier, footing, wall, and Revit transposed schedules. Missing: beam, girder, brace, joist, deck, and connection schedules as named kinds; schedules continued on another page.

## H. Dimensions

| Item | Level | Qty | Today |
| --- | --- | --- | --- |
| Dimension value | A | No | Y (filtered) |
| Dimension endpoints / extension lines | B | No | N |
| Dimension target member | B/C | No | N |
| Plate / bolt / weld / bar spacing inside a detail | A as text | No | P |

## I. Notes, specifications, scope, revision

| Item | Level | Qty | Today |
| --- | --- | --- | --- |
| Steel grades (`A992`, `A500`, `A36`, `F1554`, `A325`) | A | No (attribute) | P (`_structural_notes` grades) |
| Weld, bolt, coating, fireproofing, inspection notes | A as text | No | P |
| Existing / new / demolition | A as text; B per member | Excl, with review | Signals only |
| Alternates / phases / base bid / add–deduct | A as text; C for scope decisions | Excl, with review | Signals only |
| Revision clouds / deltas | B (geometry) | Excl, with review | N |
