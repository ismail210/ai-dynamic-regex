# OSSE — after sheet navigation

PDF: `/Users/hibareda/Desktop/Testing Projects/OSSE - ST.pdf`. 26 pages.

## What an engineer can use now

Issue on every sheet is `Permit Submission`, date `10/12/2023`. The orientation says that, and the column schedule is `S-602-O`. It previously said “permit set” and `S602`.

Sheet `S-001-O` still carries revision row `2 / PERMIT REVISION 2 / 04/19/2024`. That row is not the issue.

Roles that are `read` include foundation and floor plans (S-101-O, S-121-O), the south-stair part plan (S-103-O), floor plans (S-102-O, S-122-O), roof plan (S-123-O), elevations (S-221-O, S-222-O), sections including the printed title `SUPERSTURCTURE SECTIONS` (S-401-O), concrete / masonry / steel details, and schedules (S-601-O, S-602-O). Loading plans are S-003-O.

## Left as review, on purpose

| Sheet | Title | Why |
| --- | --- | --- |
| S-002-O | DESIGN TABLES | The title does not say notes, plan, section, detail, or schedule |
| S-104-O | NORTH STAIR & ELEVATOR PLANS AND ELEVATIONS | The title names both a plan and an elevation |

No role was chosen for those two.

Column entries remain 100. Family hits remain W 280, HSS 155, L 29, C 8. The Level 2 conflict (`55'-10"` on the schedule and `55'-2"` on S-122-O) is unchanged and still unresolved.

## Intelligence layer on this set

36 printed view titles and 18 sheet-title fallbacks. `4/S-401-O` is `target_sheet_only` on sheet `S-401-O`. `4/S-401` is `target_missing`; the missing `-O` is not filled in. 84 other references are `ambiguous`. The Level 2 warning stays open: schedule `55'-10"` on S602 and plan `55'-2"` on S122. Neither is selected. 73 numbered notes. 26 mark text hits and 1 not seen, with `quantity` null. Two incomplete labels stay unfinished.

## Still missing

View 4 is not a printed title on S-401-O, so the reference is not `target_view_found`. A view number on S-122-O is still not a segmented viewport. Parking versus building is still a schedule label.
