# Column-Schedule Gold Review Guide

For the steel-literate reviewer approving `docs/project_rule_phase2/gold_annotation/`. Every record in that folder is a **proposal** prefilled by `backend/scripts/build_column_schedule_gold_package.py` from PDF word coordinates and table ruling lines. Nothing is gold until a human changes one or both review statuses.

## What is in the package

| File | Content |
|---|---|
| `package_manifest.json` | Pages, roles (development / exclusion), template family, sheet id, image list. Held-out projects: Ketcham, Sidwell (not included on purpose). |
| `<doc>_p<page>_prefill.jsonl` | One proposal per record (JSON Lines). Edit these, or the CSV. |
| `annotations_prefill.csv` | All records in one sheet (list/dict fields are JSON-encoded). |
| `images/<doc>_p<page>_page.png` | Full page at 100 dpi. |
| `images/<doc>_p<page>_<schedule>_crop.png` | Schedule crop at 200 dpi. Red boxes mark each proposed cell; the red number is the record's position in that page's JSONL (`record_id` suffix). |

`images/` is git-ignored: the images are copies of client drawings. Regenerate them locally with the script (PDF folder via `ESTIMA3D_PROJECT_RULE_ROOT`).

Validate the package without approving anything:

```powershell
backend/venv/Scripts/python.exe backend/scripts/validate_column_schedule_gold_package.py docs/project_rule_phase2/gold_annotation
```

| Page | Role | Template family | Proposals |
|---|---|---|---|
| Burrville p.28 (S-501) | development | Perkins Eastman / Yun, S-501 layout | 64 (2 tables; 3 empty locations) |
| GCDC p.77 (S05.01_4) | development | Gensler / IMEG, S05 layout | 102 (1 table, 54 locations, up to 2 segments each) |
| Springhill p.26 (S-501) | development | Perkins Eastman / Yun, S-501 layout (same family as Burrville) | 64 (2 tables) |
| H5 p.7 / p.8 (S-100 / S-101) | exclusion | VSW | 11 + 11 (EXISTING COLUMN SCHEDULE, repeated on two sheets) |
| H5 p.23 (S-800) | exclusion | VSW | 10 (column REINFORCING schedules) |

Burrville and Springhill share one drafting template, so the development set covers **two** template families.

## Two independent approvals

Every record has `extraction_review_status` and `physical_review_status`. Allowed states for either field are `PENDING_REVIEW`, `APPROVED`, `CORRECTED`, `REJECTED`, and `UNSURE`.

- Extraction review covers the schedule region, title/type, location, printed level interval, raw cell, canonical section, catalog validity, and printed lifecycle.
- Physical review covers member extent, continuation/inheritance, number of physical segments, and whether schedule evidence can be linked to plan occurrences.
- It is valid to set extraction to `APPROVED` or `CORRECTED` while leaving physical review `UNSURE`.
- The matrix parser remains blocked until every development-page record has extraction status `APPROVED` or `CORRECTED`. Physical review may remain `UNSURE` at that gate.

All 262 committed records start with both statuses at `PENDING_REVIEW`. Prefill values are not approvals.

## Review workflow per record

1. Find the record's red number on the crop.
2. Correct any field that is wrong. Leave a field `null` or `unknown` when the drawing does not say; never guess.
3. Set `extraction_review_status` after checking the extraction fields:
   - `APPROVED`: the proposal is correct as written.
   - `CORRECTED`: you edited at least one field.
   - `REJECTED`: the record is not a schedule cell (a stray label, duplicate artifact, etc.).
   - `UNSURE`: the drawing is ambiguous; explain in `reviewer_notes`.
4. Independently set `physical_review_status`. Use `UNSURE` when extraction is clear but extent, continuation, segment count, or plan linkage is not.
5. **Add** a record for any cell the proposal missed. Copy a neighbour, set `proposal_method: "reviewer_added"`, and assign a new `record_id` with an `R` suffix. New records also begin pending in both layers.

## Field rules

| Field | Rule |
|---|---|
| `location_or_grid_raw` | Exactly as printed in the "Column Locations" row. `_normalized` is the same without spaces (`4.A-4.15. 8` → `4.A-4.15.8`); fix it if glyph fragments were split wrongly. |
| `level_raw` / `level_normalized` | **Where the label sits**, between two printed level datums. This is extraction evidence, not the member's physical extent. |
| `raw_cell_text` | Exactly as printed. |
| `canonical_section` | AISC designation only if the printed text is complete and catalog-valid. Never complete a missing dimension. |
| `lifecycle_status` | `new`, `existing`, `reinforcing` or `demolition` **only if printed** (title, cell, note tag such as `(E)`). Otherwise `unknown`. Do not infer "new" from absence. |
| `physical_semantics` | See below. |
| `member_extent` | Physical-review field: the segment extent read from the drawn column line, e.g. `FIRST FLOOR (0' - 0") -> ROOF (28' - 0")`; `null` until reviewed. |
| `continuation_inheritance` | Physical-review field: record explicit continuation or inheritance only; otherwise `unknown`. |
| `physical_segment_count` | Physical-review field: number of physical segments supported by the drawing, or `null` when unsure. |
| `plan_corroboration_status` | Whether a matching plan/detail occurrence corroborates this schedule evidence: `linked`, `not_found`, `ambiguous`, or `unknown`. Do not infer a link from section equality alone. |
| `explicit_quantity` | Only a count printed in the schedule (e.g. `(2)`). Never derive it from the drawing. |
| `count_candidate` | Leave `false`. Count policy is a separate business decision (see below). |
| `exclusion_reason` | Why the record must not become a new-work member, or `null`. |

## What one column segment is

A segment is **one continuous rolled member of one section**, between two points where the drawing shows a change: a splice symbol, a change of section, or the column's top or bottom. Annotate one record per segment:

- **One label, one column line from base to top, no splice:** one segment. `physical_semantics = "candidate_member_segment"`; `member_extent` = base level → top level (this may span several level intervals).
- **Two labels on the same location** (common on GCDC: lower and upper sections, with a splice symbol at a level): two segments, each with its own extent.
- **One label, but the line continues through a splice symbol:** decide whether the splice starts a new segment with the same section. If the drawing doesn't say, mark the second part `physical_semantics = "continuation"` and explain in `reviewer_notes`.

## Blanks, ditto marks, merged cells, continuation

- **Empty location** (no label, no column line; `exclusion_reason: "no_section_label_found"`): keep the record, set `physical_semantics = "not_applicable"`, and say "no column at this location" in the notes.
- **Location with a column line but no label:** do not copy a neighbour's section. Keep `canonical_section = null`, `physical_semantics = "unknown"`, and note "drawn column, section not printed".
- **Ditto / "SIM" / "SAME AS …":** record the text verbatim in `raw_cell_text`. Fill `canonical_section` only if the referenced cell is unambiguous on this sheet, and describe it in the notes (e.g. "ditto of A-7").
- **A label spanning merged cells or several locations:** one record per location it applies to. Explain in the notes.
- **Continuation arrows or lines across a level:** they extend the segment. Update `member_extent`; do not create a new record.

## Existing, reinforcing, new

- `existing` (e.g. H5 "EXISTING COLUMN SCHEDULE", `(E)` tags): the member is already built. `exclusion_reason = "existing_condition"`. **Never a new-work member.**
- `reinforcing` (e.g. H5 p.23 "COLUMN REINFORCING SCHEDULE"): the W section named is the **host** column being reinforced; the new steel is the plates or angles described. `exclusion_reason = "reinforcement_of_host_member"`. **Never a new column.**
- `demolition`: the member is removed. Exclude it.
- `new`: only when printed as new, or when the whole sheet is explicitly new work. If unsure, use `unknown`.

## Repeated schedules on several sheets

The same schedule can appear on two sheets (H5 pp. 7 and 8), or one building can be split across sheets (Burrville p.28 and p.29 are different wings). For each development page:

- Review each sheet on its own; don't merge sheets in the annotation.
- If a later sheet repeats earlier rows, set `reviewer_notes = "repeat of <sheet>/<record_id>"`. The parser must deduplicate them; the gold must not.
- If repeated sheets disagree, annotate both exactly as printed and add `"CONTRADICTION: …"` to the notes. Do not pick one unless the drawing gives explicit revision precedence (revision cloud, "SUPERSEDES", issue date); cite it if so.

## Recording uncertainty

Use `UNSURE` together with a specific note, e.g. "label straddles datum; could be lower or upper segment", or "line extent unclear at parapet". An `UNSURE` record is scored separately and is never treated as gold truth.

## Not decided here

Whether an approved column schedule may later act as (1) semantic evidence only, (2) a source of candidate member segments that need plan corroboration, or (3) an authoritative quantity source is a **business and takeoff-policy decision**. The annotation records what the drawing says; it does not decide what gets counted. Keep `count_candidate = false`.
