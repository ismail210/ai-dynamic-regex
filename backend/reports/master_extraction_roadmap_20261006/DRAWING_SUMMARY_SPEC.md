# Drawing summary specification

Three views of the same evidence: **Sheet summary** (what is on each sheet), **Takeoff summary** (what was counted and why), and **Review summary** (what needs a human). Every line has a source button (page + box). The existing Drawing Summary sections (definitions, rules, levels, unresolved) remain; they are regrouped under sheets.

## Sheet summary (per sheet)

```text
S101A — <sheet title from title block>      page 3      issue "11/14/2022 BID SET"      scale per view
Views:      1 plan (title + scale)    [view extents: pending]
Levels:     plan title "FIRST FLOOR"  → schedule level "FIRST FLOOR" (name match)
Grids:      read from bubbles: 1…12, A…L         [grid registry: pending]
References: D/S401 → S401 view D "SECTION" (found)
            … n more, k unresolved
Schedules:  none on this sheet
Members:    labels read (exact): W…, HSS…;   marks resolved via schedule: L1, L2
Review:     incomplete labels, conflicts, unresolved references
```

The fields are filled today only where a module exists. Sheet title, view list, references, and grids show "pending" until Phases 1–4 land. They never show a guessed value.

## Takeoff summary

Per section (the current export) plus per occurrence (new, optional):

| Section | Qty | Method | Occurrences (sheet / view / grid / level) | Source |
| --- | --- | --- | --- | --- |
| *(illustrative layout — no measured values)* | | | | |
| `<section>` | `<n>` | labeled callout | `<sheet> / <view> / <grid or unresolved> / <level or unresolved>` | page, box |
| `<section>` via mark `<L1>` | `<n>` | schedule mark map | `<sheet> …` | schedule row + plan labels |

Always shown:

- "Quantity = eligible labeled callout count; not a verified physical count."
- Excluded categories with counts: detail sheets, schedule cells, incomplete labels, scope review, duplicates.

## Review summary

- Incomplete labels (`L4X4`, HSS without wall), each with page and box.
- Conflicts (OSSE LEVEL 2 `55' - 10"` vs `55'-2"`).
- Unresolved references (target sheet missing or target view not found).
- Marks defined but never seen on a plan; plan marks without a definition.
- Scope signals waiting for a decision (alternates, existing, demolition).
- Missing member box (BBX absent) when the reviewer expects one.

## Example from real project evidence (Furley)

```text
Sheet S101A (page 3)   issue: 11/14/2022 BID SET
  Title: title-block words read "… FOUNDATION … SLAB … AREA A" — order not parsed yet → shown as unresolved title
  Reference D/S401 → sheet S401 (page 19), view "D SECTION, SCALE 1"=1'-0"" — found
  Text near the cut: "REFRIGERATOR/FREEZER TOP OF SLAB = -0'-6""
Sheet S002 (page 2) — schedules
  Mark map (12): C1 HSS6X6X1/2, C2 HSS7X7X3/8, C3 HSS8X8X1/2, C4 W10X49, C5 HSS12.750X0.375,
                 C6 HSS12X8X5/8, L1/L1A W8X21, L2/L2A W8X28, L3 W16X36, L4 W24X62
  Lintel rows CL6A, CL8: printed loose angle 5"x5"x3/8" → L5X5X3/8 (row section; not a mark-map entry)
  CL5, CL7, CL9: printed text is not one exact catalog section → no section assigned (review)
  MP piers: masonry width kept as printed; not a plate; non-steel
Review:
  Plan occurrences per mark (C1…L4): pending occurrence ledger
```
