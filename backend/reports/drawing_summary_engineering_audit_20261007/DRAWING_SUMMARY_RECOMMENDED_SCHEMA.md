# Recommended Drawing Summary schema

Not implemented. This is the shape the four projects justify. Every row keeps a source page and a status. New fields are additive. None of them change a prediction or a quantity.

## Set

- `issue`: the title-block issue phrase. Burrville `50% DESIGN DEVELOPMENT`. OSSE `Permit Submission`. Furley `BID SET`. Brandywine `65% DESIGN DEVELOPMENT`.
- `issue_date`: the date beside that phrase, not a seal date and not a revision date.
- `page_count`
- `orientation`: one sentence that may quote only those fields. It must not say "permit set" unless the issue phrase says permit. It must not say "no issue found" when `issue` is filled.

## Sheets

One record per page, from `sheet_index`, which already exists.

- `sheet_id` exactly as printed (`S-122-O`, `S101A`, `S-101B`)
- `title`
- `title_status`: `read` or `read_unlabeled`
- `page`
- `scale_field` and `scale_candidates` when the graphic bar differs (Brandywine S-000)
- `revision_rows`: number, description, date. Empty stays empty. Blank numbers stay blank.
- `role`: a label derived from the title words (foundation plan, framing plan, section, elevation, detail, schedule, notes, loading). Not from a keyword hunt over the whole page.
- `role_status`: `from_title` or `unclassified`

## Levels

Shown even when the only evidence is a plan note.

- `name`, `elevation`, `surface` (slab, deck, steel, footing), `source_sheet`, `source_kind` (schedule or plan)
- `comparison`: agrees, differs, unmatched
- When the schedule name and the sheet title differ, both are shown. Brandywine LEVEL 4 at 42'-0" and S-140 HIGH ROOF at 42'-0" stay two labels with one agreeing number.
- A conflict is a row, not a choice.

## Definitions

What the schedules define. Not how many exist.

- Column, lintel, plate, joist, brace: mark or location string, section, plate mark, plate size or `size_not_printed`
- `location_on_schedule`: the printed cell, or `not_printed`
- `material`: steel, precast concrete, or the non-steel schedule kind
- Non-steel tables listed as tables (title, sheet, printed row count), not as steel marks

## Notation

- Framing-key parts with the printed label, as on OSSE
- Project bracket legend
- Unresolved bracket tags (`[88]`, `[10]`) with no invented meaning

## References

Not in the current summary. When added:

- `printed` (the bubble or the note)
- `source_sheet`
- `target_sheet_id` and `target_sheet_status`: found or not in the index
- `target_view`: found title, or `not_matched`
- No field named "governs"

## Occurrences

Not in the current summary. When added, each row is evidence:

- `label` or `mark`
- `sheet_id` from the index
- `view` if the view index exists, otherwise `view_not_read`
- `grid` only from a bubble registry, otherwise `grid_not_read`
- `level` only from the level register, with the comparison status
- `quantity_effect`: always `none` until a separate gate says otherwise

## Review

- Conflicts, unresolved plates, unresolved brackets, unmatched levels, references whose view was not found
- Scope words (existing, demo, alternate, future, permit) as flags with the sheet, never as a taken-out list

## Hidden from the default screen

- Family text-hit counts
- Page-keyword categories
- Callout hits that are only `TYP`, `SIM`, or `SEE PLAN`
- Geometry member boxes

Those can remain in a diagnostic expander. They are not the summary.
