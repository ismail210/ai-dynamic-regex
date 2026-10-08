# Executive summary — Estima3D extraction master plan

Date 2026-10-06. Audit only. No production code, test, training file, or baseline was changed for this report. Nothing was committed, pushed, or deployed.

## Where we are

Estima3D reads a structural PDF well at the **label** level and at the **schedule** level. It does not yet understand the **drawing set as a network of sheets, views, and references**.

What it does reliably today:

- Reads printed steel labels (`W12X40`, `HSS6X6X1/2`, `L5X5X3/8`) and keeps them exact. Measured on 8 cached documents: 7,088 of 7,198 rows with a proxy answer were correct (98.47%). The remaining errors are mostly angles (`FINAL_ACCURACY_GAP_AUDIT.md`).
- Refuses to finish an incomplete label. `L4x4` stays `L4X4` and goes to review. HSS without a wall thickness goes to review.
- Reads schedules as tables: ruled tables first, word clusters as a fallback, Revit transposed column schedules, base and bearing plates with their own dimension headings, piers and footings kept as non-steel. It builds a mark → section map. On Furley the map has 12 steel marks.
- Reads level names and elevations as **sourced evidence**. It keeps conflicts visible: OSSE LEVEL 2 shows `55' - 10"` from the schedule and `55'-2"` from the plan, side by side.
- Counts only labeled callouts. A schedule row by itself never becomes a quantity, and geometry never creates one. The takeoff total is labeled as "not true physical quantity".
- Shows a Drawing Summary with definitions, rules, levels, and unresolved items, each with a source page button.

What it cannot do yet:

- It has no reliable **sheet index**. It does not reliably say "page 10 is sheet S-122-O, SECOND FLOOR FRAMING PLAN, issued 10/12/2023".
- It does not turn **detail and section bubbles** into objects. It does not say "this cut on S101A points to section D on S401".
- It does not split a page into **views**. Each view has its own title, scale, and scope.
- It has no document-level **grid registry**. Grids are only read inside the column-trace pilot and inside schedule location text.
- It does not keep a **ledger of where each schedule mark occurs** on the plans.
- It does not read revision, issue, or bid-alternate scope as structured data.

## The biggest opportunity, with evidence

A text-and-coordinate census across the eight benchmark PDFs found 1,171 cross-sheet detail or section bubbles. These are printed number-over-sheet callouts such as `D / S401`, whose target sheet exists in the same PDF. On 1,168 of them, the target sheet also carries a view titled with the same number. The three exceptions are on Brandywine.

One chain was checked by eye. Plan S101A (page 3) has a section cut `D / S401`. Sheet S401 (page 19) has a view titled `D SECTION, SCALE 1" = 1'-0"`. The renders are in `renders/`.

This means **sheet-to-sheet and plan-to-detail navigation can be built from printed text and coordinates alone**, with no AI model. That is the foundation for:

- a drawing summary an estimator can navigate
- a review screen that shows *why* a member has a plate or connection
- later, safe plan ↔ detail ↔ schedule evidence chains

Limits of this census:

- It is automatic and has not been human-verified beyond one chain.
- It ran on the text layer. Yellow Spring is fully rotated, so its stacked bubbles were not detected; only 11 inline references there.
- OSSE numbers sheets `S-122-O`. The simple "tallest sheet number on the page" rule picked the wrong word on several OSSE pages. Sheet identity must come from the title block, not font size.
- The census proves a target *view title* exists. It does not prove which member the detail governs.

## What will improve takeoff most

1. A sheet index, a reference index, and a view index. These tell the system which view a label sits in, so detail-sheet labels stay out of quantities for the right reason, and plan labels carry sheet, view, and level.
2. An occurrence ledger for every schedule mark: where it appears on plans, how many times, and on which grids. That turns "12 marks defined" into "L1 appears 9 times on S101A and S102A, at these grids".
3. Grid identity and grid-intersection location for each counted callout.

None of these change a quantity by themselves. They make each counted item explainable and reviewable, and they expose missing or duplicated occurrences.

## What will improve BBX

In this project, BBX means the bounding-box overlay in Drawing Review: a red text box for the printed label and a green member box for the drawn geometry. The text box is reliable. The member box comes from `member_geometry`. Geometry research G7–G9 ended at `PRODUCTION_NO_GO` for a new association policy.

The near-term gain is not a new geometry model. It is to attach the **sheet, view, grid, and level** to each box, and to say plainly when the member box is absent or ambiguous. See `BBX_INTEGRATION.md`.

## What will make the drawing summary useful

Organise it by **sheet → view**, not by token type. For each sheet show the title, levels, grids, schedules, detail references (resolved or unresolved), members found, plates, and warnings. Every line links to its page and box. See `DRAWING_SUMMARY_SPEC.md`.

## What enables plan ↔ detail linking

Order: sheet index → reference objects → view extents → member-in-view.

The first three are mostly printed facts (Level A). Saying that a detail **governs** a specific member requires a printed reference at that member, or a leader to it. That is Level B with review. Choosing between conflicting sources is Level C, a human decision.

## Top 10 improvements (ranked)

Full fields are in `PRIORITY_MATRIX.csv`. None of the ten adds a new quantity path.

1. **Sheet index.** Gives every piece of evidence a sheet name. Unlocks references, the summary, and BBX context. Builds on `_title_blocks`, `_sheet_ids`, and `drawing_scale`. Quantity: No. Test against Phase 0 human sheet ids. Accept at ≥ 98% of pages correct, with the OSSE `S-122-O` form read.
2. **Reference objects.** Navigation and plan ↔ detail evidence. Census baseline: 1,171 cross-sheet / 1,168 target views found. Quantity: No. Accept at ≥ 95% precision on a human sample, with rotated Yellow Spring covered.
3. **Occurrence ledger.** Explains every count and exposes missing, duplicate, and definition-only marks. Builds on the QuantityEngine eligibility and the mark map. Quantity: No. Accept when the ledger total equals the takeoff total for every section.
4. **View index and extents.** Scope per view instead of per page. Builds on `detail_regions` and `view_scale`. Quantity: exclusion only, behind a flag, with a before/after run. Accept at ≥ 90% IoU ≥ 0.8.
5. **Grid registry per view.** Builds on the `column_trace` bubbles and axes. Quantity: No. Accept at ≥ 98% of grid names, with zero feet-inch values accepted as grids.
6. **Location string per occurrence** (sheet, view, grid, level, each with a status). Quantity: No.
7. **BBX per-occurrence fields**: `member_box_status`, context, and review reason. Quantity: Never.
8. **Plan → detail review proposals.** Needs E1 + E3 + E4 together. Review only.
9. **Scope and revision flags.** Exclusion only after human acceptance.
10. **Incomplete-label cross-reference candidates.** Review only. Never completed.

Exact next implementation task: **Phase 0 + Phase 1**.

- Record human-verified sheet ids for 5 pages per project.
- Then make the sheet index read the sheet id from the title-block region using the project's own sheet-id grammar, rotation aware, as an additive field of the Drawing Intelligence profile.
- Measure it on all 8 PDFs; quantity totals must be unchanged.

## Rules that stay

No invented sizes or thicknesses. No `L4x4 → L4X4X1/4`. No geometry primitive becomes a beam. No nearest-leader semantics without evidence. No schedule row becomes a quantity. No double counting. No silent conflict resolution. A unit test is not proof of drawing accuracy.
