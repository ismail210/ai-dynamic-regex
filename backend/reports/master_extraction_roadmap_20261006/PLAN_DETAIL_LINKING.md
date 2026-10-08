# Plan ↔ detail ↔ section ↔ schedule linking

## What the drawings show

Every benchmark set prints detail and section callouts as a bubble: a label (number or letter) over the target sheet number. The target view prints the same bubble with its **own** sheet number under the view title.

Example, checked by eye (`renders/furley_p3_callout_D_S401.png`, `renders/furley_p19_view_D_S401.png`):

- Source: Furley S101A, page 3. Section cut bubble `D` over `S401`, next to `REFRIGERATOR/FREEZER TOP OF SLAB = -0'-6"`.
- Target: S401, page 19. View bubble `D` over `S401`, title `SECTION`, `SCALE: 1" = 1'-0"`.

Census on the text layer (scripts in this folder; JSON in `callout_resolution.json`):

| Project | Cross-sheet bubbles, target sheet in PDF | Matching view number on target | Own-sheet view titles | Notes |
| --- | --- | --- | --- | --- |
| Furley | 259 | 259 | 137 | |
| Burrville | 144 | 144 | 46 | |
| Brandywine | 245 | 242 | 164 | 3 not found |
| Springhill | 225 | 225 | 110 | |
| OSSE | 48 | 48 | 75 | 8 more point at `S-121-O`, `S-122-O`, `S-123-O`… These sheets exist; own-sheet detection picked the wrong word on those pages. Needs title-block sheet identity. |
| Yellow Spring | 11 | 11 | 166 | Rotated pages; stacked detection did not run correctly; inline refs only |
| Washington Latin | 151 | 151 | 117 | |
| Fort Davis | 88 | 88 | 112 | |

Limits: automatic counts. One chain was visually confirmed. A stacked number over a sheet id can also be a grid or another label; precision needs a human sample (Phase 1 acceptance). The census proves the target view **exists**. It does not prove which member the view governs.

## Objects

```text
Sheet        { sheet_id, page, title, scale, discipline, revision, source }
View         { view_id, sheet_id, label, title, scale, bbox?, type, source }
Reference    { ref_id, source_sheet, source_view?, bbox, label, target_sheet, kind: detail|section|elevation|see_note,
               resolution: target_view_found | target_sheet_only | target_missing | ambiguous, evidence[] }
Occurrence   { occurrence_id, mark_or_section, sheet, view, bbox, grid_location?, level?, source }
Link         { from, to, relation, evidence_level, evidence[], review_required }
```

## Evidence levels

| Code | Evidence | Example | May affect quantity |
| --- | --- | --- | --- |
| E1 | Printed reference with an exact target | `D/S401` and view `D` on S401 | No; navigation and review |
| E2 | Same printed mark in a schedule and on a plan | Plan `L1`, schedule `L1 W8X21` | Yes, gated: the existing `SCHEDULE MARK MAP` path counts plan occurrences only |
| E3 | Leader from a label or bubble to a member stroke | Bubble with a leader ending on a beam | No, until measured. Leader → target was 0.7% reliable as a ranking signal. |
| E4 | Same view / region | Label and detail bubble inside one view | No; context only |
| E5 | Same sheet | Two items on S101A | No |
| E6 | Same grid / level | Both at C.8 on LEVEL 2 | No; supporting evidence only |
| E7 | Geometric proximity | Nearest member to a label | No |
| E8 | Semantic similarity | "Both are brace details" | No |
| E9 | Engineering inference | "This connection probably uses detail 3" | Never automatic (Level C) |

Only E2 may change a quantity, and only through the path that already exists. E1 is Level A for the reference and the target view. E1 + E3 + E4 together can become a **review proposal**: "detail D/S401 is cut through this condition". It never adds a plate or bolt quantity.

## Linking schedules to plans

```text
Schedule row (mark, section, plate, notes, source box)
  → Mark map entry (only catalog-valid steel; existing contract)
  → Plan occurrences of the mark (sheet, view, bbox, grid, level)
  → Counted callouts (existing QuantityEngine; one per printed occurrence; TYP x N only when printed)
  → Evidence per count
```

Track, per mark:

- `defined_in` — schedule rows; more than one with different sections is a conflict and drops out of the map behind `drop_conflicts`
- `detected_occurrences` — plan labels counted
- `expected_occurrences` — only when the schedule prints a count or a location list (column schedules list locations; that list is evidence, never a quantity)
- `unmatched_listed_locations` — listed locations with no plan occurrence
- `duplicate_suspects` — two counted labels within the same view and the same box area
- `definition_only` — defined, never seen on a plan. Report it; do not count it.

## Incomplete labels across sheets

`L4x4` on a plan and `L4X4X1/4` in a schedule are a **cross-reference candidate**, not a completion. The candidate requires:

1. the same mark or a printed reference at the plan label, and
2. a single schedule or detail definition, with no other `L4X4X…` in scope.

Even then it stays review-only: Level B, quantity No, until a human accepts it. Burrville has no such chain. This must not become an automatic quantity.

## What never links automatically

- A detail to a member only because they share a sheet, a grid, or a nearby box.
- A typical detail to every member of a family.
- A beam tag at the end of a leader near a column (Brandywine `W21X48` near `A.3'-19`) to that column's section.
- Two elevations from different sources (OSSE).
