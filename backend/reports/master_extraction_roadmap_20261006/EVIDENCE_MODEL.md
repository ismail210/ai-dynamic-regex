# Evidence model

Every extracted value carries a source. Every relationship carries an evidence level. Status is explicit; nothing is filled silently.

## Evidence record

```text
Evidence {
  kind: printed_text | vector_shape | table_cell | title_block | reference_bubble | leader | grid_axis | computed
  page, sheet_id?, view_id?, bbox
  raw_text?            # exactly as printed
  method               # e.g. "ruled_table", "word_cluster", "stacked_bubble"
  confidence?          # only when it comes from a real score
}
Value {
  value | null
  status: read | resolved | reference | unresolved | conflict | not_shown | not_applicable
  evidence: Evidence[]
  conflicts?: Value[]  # kept side by side, never merged
}
```

This matches the conventions already in production: `level_evidence` statuses, plate status in `column_schedule`, and `context_scope` reasons. It is a naming discipline, not a new framework.

## Safety gates

1. **Gate 1 — printed-only values.** Sizes, thicknesses, plate dimensions, elevations, and grid names come from printed text in the source. Never invented, never completed.
2. **Gate 2 — catalog verification.** A section goes into the takeoff only if it is catalog-valid (AISC). AISC verifies and never selects.
3. **Gate 3 — scope.** Only `object_scope = takeoff` predictions count. Detail sheets, typical details, schedule cells, notes, and dimensions are excluded. Scope exclusions (existing, demolition, alternate) require review before they take effect.
4. **Gate 4 — one printed occurrence, one count.** Schedule rows never add a quantity. `TYP x N` multiplies only when N is printed. Repeated-detail links and geometry never count. Duplicate suspects are flagged, not removed silently.
5. **Gate 5 — explicit relationships.** A link may only change a value when it is E2 (same printed mark, single definition). E1 references are navigation. E3–E9 are review evidence only.
6. **Gate 6 — conflicts stay visible.** Two different values for the same thing (elevations, sections for one mark, plate sizes) stay side by side as a conflict until a human decides.
7. **Gate 7 — measured promotion.** No new path affects production predictions or quantities without a before/after run on the benchmark PDFs. Quantity totals must be unchanged, or every change must be explained, and the reference tests must pass. Promotion is a decision, not automatic.

## What NOT to do

- Do not match unlabeled PDFs to Excel or to each other.
- Do not invent sizes or thicknesses.
- Do not semantically complete labels.
- Do not guess `L4x4 → L4X4X1/4`.
- Do not let a geometry primitive automatically become a beam or column.
- Do not use nearest-neighbor leader semantics without evidence.
- Do not let a schedule row automatically create quantity.
- Do not count duplicates.
- Do not silently resolve conflicting elevations.
- Do not treat unit tests as proof of drawing accuracy.
- Do not treat one project's behavior as universal.
- Do not replace deterministic extraction with an LLM without benchmark evidence.
