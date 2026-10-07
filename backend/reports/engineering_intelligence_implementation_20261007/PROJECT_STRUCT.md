# Struct.pdf (Furley) — after sheet navigation

PDF: `backend/uploads/Struct.pdf`. 24 pages.

## What an engineer can use now

Issue on every sheet is `BID SET`, date `11/14/2022`. Sheet ids have no hyphen (`S001`, `S101A`, `S002`). Titles are `read_unlabeled`: the words are printed and the title block does not label them “drawing title”. The summary says so on each row.

| Role | Sheets |
| --- | --- |
| General notes | S001 |
| Schedule | S002 inspection tables and schedules |
| Foundation plan | S101A–S101D slab on grade |
| Framing plan | S102C, S102D second floor |
| Roof plan | S102A, S102B low roof, and S103A–S103D |
| Detail | S301–S304 |
| Section | S401 foundation sections, S501–S505 framing sections |

`FRAMING SECTIONS` is a section, not a framing plan. `LOW ROOF FRAMING` is a roof plan.

There is no schedule level list, so elevations printed on the plans are in the main summary and are labeled as local plan notes.

Mark map remains 12 (C1–C6, L1–L4). Column entries remain 6. Family hits remain W 991, L 106, HSS 59, C 20, WT 1.

## Intelligence layer on this set

`N/S502` on S102A resolves to sheet `S502` with status `target_sheet_only`. View N is not invented. 16 references are sheet-only and 24 are ambiguous (`SEE PLAN` with no sheet). Only 2 interior titles qualified (`FLOOR FRAMING` on S102C, `PLAN` on S304); 22 sheets contribute only the sheet title, because detail letters are not on the title line. 46 mark text hits and 4 marks not seen. `quantity` is null. The mark map is still 12. Grid candidates are capped at 80 and are not confirmed bubbles.

## Still missing

View N on S502, and view D on S401, as printed titles next to the letter. The plan bubble is not placed inside a source view. Grid and level on each mark hit are empty.
