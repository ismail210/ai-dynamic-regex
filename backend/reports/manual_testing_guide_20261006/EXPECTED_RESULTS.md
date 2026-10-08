# Expected results

Values below were read from the PDFs or from the existing reference fixture `backend/tests/fixtures/column_schedule/reference_levels.json`, which was built from rendered sheets. They were not taken from the code under test alone.

| Test | Expected source text | Expected parsed values | Status | In steel mark list | Affects quantities | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| MT-01 MP16 | WIDTH `16"`, bars `1-#5` | width `16"`; length empty; thickness empty; bars `1-#5` | unresolved | no | no | Remarks blank. Not shown as a steel definition in Drawing Summary. |
| MT-02 MP24 | `24"` and `2-#5` | same split | unresolved | no | no | |
| MT-02 MP24A | `24"` and `2-#5 EACH FACE` | same split | unresolved | no | no | |
| MT-02 MP32 | `32"` and `3-#5` | same split | unresolved | no | no | |
| MT-02 MP32A | `32"` and `3-#5 EACH FACE` | same split | unresolved | no | no | |
| MT-03 CL6A | wall line, `5"x5"x3/8"`, `#4 STIRRUPS AT 12"o.c.`, `WELDED TO PLATE`, `(2)-#5 CONTINUOUS TOP` | angle `L5X5X3/8` | angle present; bars are text only | no | no new quantity | Stirrup text is not a bar count. |
| MT-03 CL8 | same pattern with `2-#8` and `(2)-#7 CONTINUOUS TOP` | angle `L5X5X3/8` | angle present | no | no new quantity | |
| MT-03 CL9 | `N/A` angle and `#4 STIRRUPS AT 12"o.c.` | no angle | unresolved | no | no | No `WELDED TO PLATE` on this row. The brick cell is N/A. |
| MT-03 neighbor CL7 | `STANDARD WALL WITH 2-#7 AT HEAD N/A N/A` | no stirrup text | unresolved | no | no | Must not inherit CL6A. |
| MT-04 M-20 N-20 N.2-12 | `1"x18"x18" **` | 1", 18", 18"; notes `**` | present as a printed plate size | no | no | Grid locations. Duplicate overlap was on the text layer. |
| MT-05 BP4 | `6"x8"x3/4"` | those three dimensions | present | no | definition only | |
| MT-05 BP5 | `6"x10"x1"` | those three dimensions | present | no | definition only | |
| MT-05 BP6 | `4"x10"x1 1/4"` | those three dimensions | present | no | definition only | |
| MT-05 BP7 | `7"x9"x3/4"` | those three dimensions | present | no | definition only | Note on the sheet can say SEE S/S502. ICF notes must stay out. |
| MT-06 CL5 | `N/A` angle | no section | unresolved | no | no | |
| MT-07 `14'-0" LEVEL 1` | the printed band | elevation `14'-0"`; name `LEVEL 1`; not one paired level | unpaired | n/a | no | Fixture: LEVEL 2 is `14'-0"` and LEVEL 1 is `0"`. |
| MT-08 OSSE LEVEL 2 | schedule `55' - 10"`; plan S122 `55'-2"` | both kept | conflict, not resolved | n/a | no automatic choice | LEVEL 1 `38'-0"` agrees. |
| MT-09 Yellow Spring | four rotated level names | `42'-0"`, `30'-8"`, `15'-4"`, `0'-0"` | second floor agrees `15'-4"` | n/a | no | One reference test passed. Not every sheet. |
| MT-10 Washington Latin | all six levels say SEE PLAN | SECOND `330'-0"`; FIRST `314'-0"`; ROOF `372'-9"` | THIRD and FOURTH unresolved | n/a | no | Do not use masked `314' - 0"` or `372' - 6"` as schedule levels. |
| MT-11 Fort Davis | HIGH ROOF, LOW ROOF, 2ND, FOUNDATION | elevations empty | no computed difference | n/a | no | |
| MT-12 A.3'-19 | schedule section W12X40; grids written as `A.3'` and `19` | trace ambiguous | not confirmed | no new mark | no | Nearby bubbles include `A.4'` and `19`, not a confirmed `A.3'`. |
| MT-13 C1 | column schedule section | `HSS6X6X1/2` | accepted section | yes | only from a plan callout, not from the schedule row alone | Control row. |
| MT-14 CL5 | `N/A` | no invented angle | unresolved | no | no | Same rule if you see `L4x4` without a thickness. |
| MT-15 quantities | 12 steel sections listed in the guide | mark list unchanged | pier plate hint is not a takeoff | MP and CL out | no new takeoff row from these fixes | Live Takeoff was not regenerated in the automated run. Record the number you see. |

Furley steel mark list that must stay:

`C1 HSS6X6X1/2`, `C2 HSS7X7X3/8`, `C3 HSS8X8X1/2`, `C4 W10X49`, `C5 HSS12.750X0.375`, `C6 HSS12X8X5/8`, `L1 W8X21`, `L1A W8X21`, `L2 W8X28`, `L2A W8X28`, `L3 W16X36`, `L4 W24X62`.
