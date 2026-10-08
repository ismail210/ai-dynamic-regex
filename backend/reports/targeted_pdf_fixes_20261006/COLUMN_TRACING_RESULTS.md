# Column tracing

Interface used: `trace_column` in `backend/services/engineering/column_trace.py`, after `extract_document_structure` and `attach_schedule_grid`. No output was written outside this report directory. The trace return value is evidence. It is not applied to quantities.

PDF: `backend/uploads/Structural4__3aa51f661bdf.pdf` (Brandywine Structural4).

## Runs

| Location | Schedule | Result |
| --- | --- | --- |
| A-9 | S600 page 42, section HSS6X6X1/4, grids A and 9 | `traced`. No plan names LEVEL 1 or states its elevation. Ends unresolved, between level lines. |
| A.1'-18, A.2'-12, A.2'-13.1 | same schedule | `traced`, no plan intersection |
| A.3'-19 | S600 page 42, section W12X40, grids `A.3'` and `19` | `traced`, with plan candidates. Not visually confirmed as that grid. |

`column_trace_attempts.json` and `column_trace_hit.json` hold the machine output. `column_trace_brandywine.json` is the first A-9 run from the full re-extract.

## A.3'-19 evidence

Summary: levels spanned LEVEL 4, LEVEL 3, LEVEL 2, LEVEL 1. A column symbol was reported on LEVEL 4, LEVEL 3, and LEVEL 2. `logical_stack_only` is true: the note says the observations do not establish how many fabricated pieces the stack is. Top end is LEVEL 4 at `42'-0"`, taken from the schedule’s drawn level line. Bottom end stays unresolved because the schedule draws it between two lines and the trace does not snap it. LEVEL 1 has no plan.

Candidates:

| Sheet | Page | View | Scale | Symbol |
| --- | --- | --- | --- | --- |
| S140 | 21 | OVERALL LEVEL 4 FRAMING PLAN | printed `1" = 20'-0"`; title block `1/8" = 1'-0"`; not calibrated | small mark near grid 19 |
| S142 | 23 | LEVEL 4 FRAMING PLAN - AREA B | printed `1/8" = 1'-0"`, calibrated about 0.75 points per inch from grid dimensions | column mark at a beam intersection near bubble 19 |
| S130 | 16 | LEVEL 3 overall | same scale conflict as S140 | same overall geometry |
| S132 | 18 | LEVEL 3 area B | `1/8" = 1'-0"`, calibrated | column mark |
| S120 | 11 | LEVEL 2 overall | same scale conflict as S140 | same overall geometry |
| S122 | 13 | LEVEL 2 area B | `1/8" = 1'-0"` | no column symbol |

Crops: `renders/trace_S140_LEVEL_4.png`, `trace_S142_LEVEL_4.png`, `trace_S122_LEVEL_2.png`, and the LEVEL 3 / LEVEL 2 twins.

## Visual comparison

On S142 the candidate sits at a beam crossing under grid bubble 19. The crop does not show bubble `A.3'`. Nearby text recorded by the tracer on the overall sheets is `19`, `A.4'`, and `18`, not `A.3'`. A beam tag `W21X48` is described as a leader ending at the column. That is a beam mark, not the schedule section W12X40, and it was not written back as the member section.

On S122 there is no column symbol. The nearby text is beam marks (`W12X26`, `W12X16`, `W10X12`) and camber notes. That candidate is not a confirmed column.

Overall sheets quote two different scales (`1" = 20'-0"` on the view and `1/8" = 1'-0"` in the title block) and are not calibrated. No length was computed.

Conclusion: tracing executed. The A.3'-19 result is **ambiguous**. It was not accepted as a verified column identity. It did not change `schedule_mark_map` or endpoint counts.

The reference traces in `tests/test_level_reference_set.py` still skip. Their PDFs are the missing project files listed in `ISSUES.csv`.
