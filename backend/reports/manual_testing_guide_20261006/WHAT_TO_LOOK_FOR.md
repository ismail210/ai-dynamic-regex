# What to look for

## Raw text, normalized text, and parsed dimensions

Raw text is what the PDF printed, including quotes and stars. Normalized text is the catalog spelling of a real steel section, such as `HSS6X6X1/2`. Parsed dimensions are the separate thickness, width, and length read from a plate cell.

Example: Springhill M-20 prints `1"x18"x18" **`. The raw cell is that string. The parsed dimensions are 1 inch, 18 inches, and 18 inches. The stars stay a note. They are not a fourth dimension.

Example: Furley MP16 prints `16"` in the WIDTH column and `1-#5` in VERTICAL REINFORCEMENT. `16"` is the raw width. It is not a plate thickness, and the missing length is not filled in.

## A valid schedule row and an unresolved row

A valid steel row has a mark and a complete section that is printed, such as Furley C1 = `HSS6X6X1/2`.

An unresolved row is one the sheet does not finish. Furley CL5 prints `N/A` for the angle. The result stays unresolved. CL9 prints the stirrup line and still has `N/A` for the angle, so the stirrup text is kept and the angle stays unresolved.

## A grid location and a steel section mark

`M-20` and `A.3'-19` are places on the grid. `W12X40` and `HSS6X6X1/2` are steel sections. A location row can show a plate size or a section beside it. That row is not added to the steel mark list unless the existing rules already accept the section. MP16 is a masonry pier mark, not a steel section mark.

## Splitting a level label is not the same as pairing it

Brandywine prints `14'-0" LEVEL 1` on one band. The reader splits that into the elevation `14'-0"` and the name `LEVEL 1`. On this schedule the elevation belongs to the line above, LEVEL 2, and the name belongs to the next level down. Drawing Summary should say **two levels**. It should not say that LEVEL 1 is at `14'-0"`.

## A schedule row is not a quantity

Drawing Summary says a definition tells you how to read a mark on a plan. It is not an installed member and not a quantity. Takeoff counts labeled callouts after analysis. Finding MP16 or a stirrup note in the schedule must not add a piece to Takeoff.

## Duplicate PDF text

Some cells are drawn twice, a few points apart. Springhill's `1"x18"x18"` was one of those. The overlapping copy is removed, so the size appears once. If the same word is printed in two places that do not overlap, both copies stay. A messy string with no overlapping pair is left unresolved rather than repaired.

## Overlapping tables

Furley page 2 has several schedules side by side. A note or the next title, such as `LINTEL SCHEDULE` or `ICF NOTES`, must stay out of the row above. CL7 must not receive CL6A's stirrup line. BP7 must stay `7"x9"x3/4"` and must not absorb the ICF notes.

## OSSE LEVEL 2

The building schedule prints T.O. SLAB LEVEL 2 as `55' - 10"`. Plan S122 prints top of slab `55'-2"`. The difference is 8 inches. Both stay visible. The chip **differs from the schedule** means a person has to decide which drawing governs. LEVEL 1 at `38'-0"` matches on the schedule and on S121, and that agreement stays.

## How to spot an extra quantity

On Takeoff, compare the section rows with the 12 Furley sections in MT-13. An error looks like:

- a new row for MP16, MP24, MP32, or an N/A lintel
- a plate count created from a pier width
- a bar quantity created from `#4 STIRRUPS AT 12"o.c.`
- the same member counted once from the schedule and again from the plan when the schedule row was only a definition
- C1 or another known section changing spelling

## What a passing test does not prove

A pass on one row does not validate the rest of the sheet. A passing reference check on OSSE, Yellow Spring, Washington Latin, or Fort Davis does not validate every page of that project. The old 383/414 tracing number was not found as a reproducible run, so it is not a score you can claim from this test.

## Comparison

| PDF value | Extracted value | Expected behavior | Pass/Fail criteria |
| --- | --- | --- | --- |
| MP16 width `16"` and bars `1-#5` | width `16"`, bars `1-#5`, unresolved | Width is not a plate. Bars stay text. | Fail if a length or thickness appears, or if MP16 is a steel mark. |
| CL6A second line `#4 STIRRUPS AT 12"o.c.` | same phrase on CL6A, angle still `L5X5X3/8` | Second line stays with CL6A. | Fail if CL7 contains that stirrup line, or if the angle changes. |
| M-20 `1"x18"x18" **` | one size plus notes `**` | Overlapping duplicate removed. | Fail if the size is doubled or a dimension is dropped. |
| `14'-0" LEVEL 1` | split, pairing not one level | Elevation stays with LEVEL 2. | Fail if the screen says LEVEL 1 is at `14'-0"`. |
| OSSE LEVEL 2 `55' - 10"` and plan `55'-2"` | both kept, chip differs | Human must resolve. | Fail if one number replaces the other. |
| C1 `HSS6X6X1/2` | same section | Control row. | Fail if C1 changes. |
| CL5 angle `N/A` | unresolved, no section | No invented thickness. | Fail if an angle size appears. |
