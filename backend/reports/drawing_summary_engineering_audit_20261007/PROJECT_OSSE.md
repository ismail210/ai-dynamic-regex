# OSSE — Drawing Summary engineering assessment

PDF: `/Users/hibareda/Desktop/Testing Projects/OSSE - ST.pdf` (same set as `07 - FEMS & OSSE/OSSE - ST.pdf`). 26 pages. Summary status SUCCESS. Sheet-index slot 26/26.

## What the summary contains

Sheet ids keep the building suffix: `S-122-O`, `S-401-O`, `S-602-O`. Titles are the title-block text, including the printed spelling `SUPERSTURCTURE SECTIONS`. Issue on every sheet is `Permit Submission`, `10/12/2023`. Only page 2 (S-001-O) has a revision row: number `2`, `PERMIT REVISION 2`, `04/19/2024`. No sheet scale is printed. This matches the earlier visual audit of these title blocks.

The orientation says "26-page structural set (permit set, numbered revision) with a steel column schedule on S602." That issue statement is the best of the four projects. The sheet id in the sentence drops `-O` (`S602` instead of `S-602-O`) because the orientation uses the legacy sheet-id reader.

S-602-O is two schedules. OSSE PARKING - GCS: 74 entries, material precast concrete, size `C1 - 24"x24"`, plates not shown. OSSE BUILDING - GCS: 26 steel entries (for example `W8X31` at `R14-RA.2`). The summary puts the precast group with supporting information and the steel group in the steel column list. That split is the right engineering distinction. Neither group is a quantity. Nine plate checks are `no_quantity_printed`.

Levels on S-602-O:

| Level | Schedule | Plan |
| --- | --- | --- |
| T.O. SLAB LEVEL 2 | 55'-10" | S-122-O second floor, top of slab 55'-2". **Conflict, kept.** |
| T.O. SLAB LEVEL 1 | 38'-0" | S-121-O first floor 38'-0", agrees |
| T.O. ROOF | 69'-4" | S-123-O, plan name OFFICE ROOF, 69'-4", agrees, qualifier kept |
| T.O. PARKING DECK SLAB | 50'-0" | no plan match |
| T.O. SLAB LOW RAMP | 41'-9 5/8" | no plan match |
| T.O. PARKING LOWER DECK | 33'-0" | no plan match, and the same level is listed twice |

Top-of-steel on S-122-O and S-123-O is unresolved. The framing key on S-001-O is read from leaders: `[35]` shear studs, `c=1 1/4"` camber, `<+12'-3">` top of steel relative to datum. The example numbers are not quantities. Legend brackets `[ ]` `{ }` `( )` `< >` are stored as bottom of footing, top of pier, bottom of base plate, and top of framing. Grid-location offsets such as `(-6")` and `(5' - 4")` are offsets, not elevations.

Concrete wall, pier, retaining wall, footing, shear wall, and concrete beam schedules on S-601-O are supporting. The beam table reports 6 printed rows, 5 unread, which matches the earlier finding that precast beam rows stay outside steel definitions.

## What it gets right

- `S-122-O` and the rest of the `-O` series, in the profile.
- Permit submission versus revision 2, in the profile. The visible scope line at least says permit set and numbered revision, and it limits the revision stamp to page 2.
- LEVEL 2 left in conflict with both sources.
- OFFICE kept on the roof match.
- Precast parking columns separated from building steel.
- Framing-key parts tied to printed leader labels.
- Bracket notation not applied to grid offsets.

## Value

**HIGH.** The LEVEL 2 conflict. The steel versus precast split on S-602-O. The framing key. Sheet ids with `-O`, once shown.

**MEDIUM.** Parking levels with an explicit "no plan match." Concrete schedules on S-601-O as a contents list. Steel grades A992, A572 Gr.50, A500 Gr.C, A36. Moment-connection notes on S-505-O.

**LOW.** 280 / 155 / 29 family text-hit chips. Callouts that are the word `TYP.` or `{ 30' - 2" } , TYP`.

**MISLEADING.** Page 19 (S-502-O, concrete typical details) is described as a column schedule. Page 20 (S-503-O, masonry typical details) is described as a beam schedule. S-102-O, "OSSE PARKING SECOND FLOOR PLAN," is classified roof framing. S-121-O, the facility foundation and first-floor plan, is classified notes/legend. S-506-O, steel typical details, is classified floor framing. S-401-O, superstructure sections, is unclassified. The orientation sheet id drops `-O`. `T.O. PARKING LOWER DECK` appears twice; an engineer can think there are two decks at 33'-0".

## What is missing

The sheet list on the screen, with the suffix. A single revision line: page 2, revision 2, 04/19/2024, description PERMIT REVISION 2, distinct from the 10/12/2023 issue date and from the seal date. Target views for section cuts. Which parking grid a precast C1 sits on, beyond the one schedule cell. A statement that parking levels were not found on a plan, as a review item, without inventing a match.

## Add

- Sheet index rows, ids exactly as printed.
- Issue `Permit Submission 10/12/2023` on the set, and revision 2 only on S-001-O.
- The level table already built, including the conflict and the empty parking matches. Collapse the duplicate 33'-0" row only after a human confirms it is the same schedule line read twice.
- Framing key as notation, already present. Keep it.

## Do not add

- A chosen LEVEL 2 elevation.
- A steel quantity for precast C1, or a plate quantity where none is printed.
- A stud count taken from the `[35]` in the key example.
- An automatic "existing" or "demo" exclusion (9 existing tags, 3 demo tags, renovation flag correctly false).
- A grid id parsed from `30' - 2"` or from `(5' - 4")`.
