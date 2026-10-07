# BBX integration — current vs required contract

## What BBX means here

No file in the repository uses the word BBX. Earlier work in this project used it for the **bounding-box overlay** in Drawing Review: a red box on the printed label text and a green box on the drawn member geometry. That is the contract described below.

If BBX also names an external estimating or fabrication system, it has no contract in this repository. Earlier notes list candidates (Tekla PowerFab, Tekla Structures, SDS2, StruM.I.S, Bluebeam) as an open question. That is listed in `OPEN_ENGINEERING_QUESTIONS.md`. No external contract is invented here.

## Current fields

Per prediction, serialized by `prediction/contract.py` and read by `frontend/src/lib/predictionContract.js`:

| Field | Meaning | Source |
| --- | --- | --- |
| `bbox` / `bounding_box` | Label text box, page points, top-left origin | Extraction |
| `page_number` | 1-based page | Extraction |
| `member_geometry.available` | Whether a member box exists | `member_geometry.py` |
| `member_geometry.bbox` | Member box | Merged line / polyline strokes |
| `member_geometry.geometry_id`, `source_primitive_ids` | Trace back to strokes | `member_geometry.py` |
| `member_geometry.association_method` | How it was linked, or the reason it was not | `member_geometry.py` |
| `member_geometry.confidence` | Association score | `member_geometry.py` |
| `section`, `family`, `confidence`, `top_candidate_sections`, `why_selected`, `why_rejected`, evidence blocks | v2 explanation | orchestrator / explanation engine |
| `takeoff_eligible`, `object_scope`, `prediction_source` | Quantity eligibility | `context_scope`, orchestrator |

Takeoff export row (`takeoff_exporter`): `Mark`, `Family`, `Section`, `Shape`, `Entity`, `AISC Type`, `Database Match`, `AISC Confirmed`, `Avg Confidence`, `Confidence Level`, `Quantity`, `Quantity Method`. The export is per section. It has no per-occurrence rows.

## Missing fields

| Field | Use | Can be added safely | Migration needed | Optional | Never auto-filled without evidence |
| --- | --- | --- | --- | --- | --- |
| `sheet_id` per occurrence | Where it is | Yes (sheet index) | No (additive) | No | — |
| `view_id`, `view_title` | Which drawing on the sheet | Yes, when the view title is printed | No | Yes | View extent when no border |
| `grid_location` | Human location | Yes, when printed (schedule) or computed with status | No | Yes | Computed "between grids" without axes in the same view |
| `level` | Floor | Yes, from plan title ↔ level evidence, with status | No | Yes | Level picked from two conflicting sources |
| `schedule_row_ref` | Link to the defining row | Yes (mark map) | No | Yes | — |
| `reference_refs` | Detail / section bubbles near the occurrence | Yes, as listed evidence | No | Yes | "Governs this member" |
| `plates` / `accessories` | Base or bearing plate per mark | As a definition reference only | No | Yes | Plate count per occurrence |
| `review_reason` | Why it needs a human | Yes | No | Yes | — |
| `member_box_status` | `present` / `absent` / `ambiguous` / `not_applicable` | Yes (from `member_geometry`) | No | No | — |
| Per-occurrence export rows | Downstream audit | Yes, as a new sheet in the workbook | Workbook format change | Yes | — |
| `material` / grade | Downstream | From printed notes | No | Yes | Default grade by family |
| Length / weight | Fabrication | Not now | Yes | — | Any measured length on an NTS or uncalibrated view |

## Rules for the overlay

- The red text box is always the printed label. It is never moved.
- The green member box appears only when `member_geometry.available` is true. A null box is shown as "no member box", not as a guess.
- A member box never changes `section` or `Quantity`. That is already true (`member_geometry` docstring) and stays true.
- G8/G9 shadow candidates stay out of production until a non-Burrville package passes ownership review (`GEOMETRY_RESEARCH_MEETING_SUMMARY.md`).
