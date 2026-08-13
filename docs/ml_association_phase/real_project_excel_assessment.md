# Real-Project Excel Ground-Truth Assessment (Phase 2.5)

Per the pilot spec: **Excel content is not automatically treated as ground truth.** This document records what linkage keys were checked, what was found, and how each possible linkage is classified. No training or metric computation in this pilot uses any of this data as confirmed truth — see `real_project_pilot_results.md`.

## What the workbooks contain

All 7 workbooks share the same estimating-tool-generated structure (`real_project_inventory.md`): `ProjectHome`, `StructuralFramingSchedule`, `StructuralColumnSchedule`, `StructuralConnectionSchedule`, `BasePlateSchedule`, `StructuralPlateSchedule`, and (project-dependent) `StructuralBracingSchedule`, `StructuralJoistSchedule`, `StructuralDeckSchedule`, `MomentConnectionSchedule`, plus `Summary`/`Proposal`/`Count_per_Sheet`/`_ChartData` rollup sheets.

**`ProjectHome` contains contact/business information** (company name, estimator name, email, phone) in every project — confirmed by direct inspection of one workbook. **This is genuinely sensitive and is not reproduced anywhere in this document or any other committed file.** Any future automated processing of these workbooks must explicitly exclude `ProjectHome`'s contact fields from any output.

Each schedule sheet (Framing/Column/Connection/BasePlate/Plate) is row-per-instance, with a consistent core column set present in **all 7 projects**: `Type` (AISC-style designation, e.g. `W8X10`, `HSS8X8X1/2` — the same text format the PDF pipeline extracts), `Comments` (short text, observed values are sheet-number-shaped, e.g. `S-101`), `Length`, `Weight`/`Overall Weight`. Roughly half the projects (001, 006, 007) additionally carry a detailed cost/labor breakdown (`Cost`, `GPR`, `PE Stamp`, `Fabrication`, `Installation`, `Delivery`, `Crane`, etc.); the other four (002, 003, 004, 005) instead carry `Mark` (a coarse category tag, e.g. `"Framing"`, `"Miscellaneous Column"` — **not** a unique per-instance beam/column mark like `"B1"`/`"C3"`) and `ElementID` (present on some sheets, e.g. `StructuralFramingSchedule`, but empty/absent on others, e.g. `StructuralColumnSchedule`, in the one project inspected in detail).

## Linking-key investigation (concrete, verified on one project; pattern present but not re-verified on the other 6)

**Investigated in depth**: project_004 (one Excel + its paired PDF).

| Candidate key | Present? | Verification performed | Classification |
|---|---|---|---|
| Sheet number (`Comments` field, e.g. `S-101`) → PDF page | Yes, in every schedule row | Regex-scanned every PDF page's extracted text for `S-\d{3}`-shaped tags. **Confirmed**: PDF page 7 contains `S-100` in its text, page 8 contains `S-101`, page 9 contains `S-102`, etc. — the sheet numbers referenced in the Excel `Comments` column do appear, verbatim, as text on the PDF pages, in ascending order matching page order. | **Strong inferred match** — not "verified direct" because each page's text lists *several* sheet-number tags at once (its own number plus cross-referenced detail/schedule sheets shown in callouts, e.g. page 8's text contains `S-101, S-200, S-400, S-500, S-700` together), and this pilot inferred "this page's own sheet number is the first/lowest one" rather than parsing an authoritative title-block field. That inference held consistently for the pages checked, but was not independently confirmed against a title-block region extraction. |
| Unique member mark (e.g. `B1`, `C3`) | **No** | `Mark` column values observed were coarse categories (`"Framing"`, `"Connections"`, `"Miscellaneous Column"`), not unique per-instance tags. Multiple rows share identical `Type`+`Comments`+`Length`+`Weight` (e.g. two `W8X10`/`S-101` rows differing only by `ElementID`). | **Unusable as ground truth** for row-to-specific-geometry linkage — cannot distinguish which of several identical instances on the same sheet a given row refers to. |
| `ElementID` | Inconsistently present (populated on `StructuralFramingSchedule`, empty on `StructuralColumnSchedule` in the one project checked) | Not cross-referenced against anything in the PDF (no visible per-instance ID printed on drawings was found or expected) | **Unusable as ground truth** — even where present, nothing in the PDF carries the same identifier to link back to. |
| Grid coordinates | **No** | No grid-coordinate column exists in any inspected schedule | Not applicable |
| Detail ID / takeoff item ID | **No** dedicated column beyond `Comments` (sheet number) | — | Not applicable beyond the sheet-number key already assessed |
| `ProjectHome` per-shape rollup (`Type`, `Count`, `Total Length`, `Total Weight`) | Yes, in every project | Not cross-checked against extracted label counts in this pass | **Weak inferred match** — a whole-document plausibility check ("does the PDF contain roughly this many instances of this shape") at best; not a per-label or per-page ground truth source |

## What this means for Phase 3+

- **Page-level linkage (sheet number ↔ PDF page) is real and usable** as a coarse validation signal — e.g., confirming that shapes the schedule attributes to sheet S-101 do in fact appear as detected steel labels on the PDF page corresponding to S-101 — but this pilot did not build that cross-reference into an automated check, and it would need the title-block sheet-number field extracted reliably (not currently implemented anywhere in the pipeline — see `docs/geometry_graph_audit/09_open_questions.md` Q4's sibling gap for scale text, same root cause: no title-block field extraction exists).
- **No spreadsheet data in this archive can serve as row-level (specific-geometry) ground truth** without additional, currently-absent identifying information. This confirms the pilot spec's default posture was correct: **do not join Excel rows to PDF labels automatically.**
- **No training occurred on any inferred spreadsheet match** in this phase, consistent with the guardrails.

## Recommendation

If page-level (sheet-number) linkage is pursued in a future phase, it must be built as its own small, independently-tested feature (extract a page's own sheet number from its title block or header text; verify sheet-number-to-page uniqueness across a project; only then use it as a coarse label-presence check) rather than assumed reliable from this pilot's spot-check alone.
