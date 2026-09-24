# Struct.pdf — Extraction Completeness QA (Civil / Construction)

**Document:** Estima3D `Struct.pdf` (`doc_889d35dfc3cfc3d5`, 24 pages)  
**Artifacts:** `backend/training/engineering_artifacts/doc_889d35dfc3cfc3d5/multimodal/`  
**Date:** 2026-09-23  
**Interactive report:** open canvas `struct-pdf-qa-extraction-report.canvas.tsx`

## Verdict

**Cached analyzed run is stale.** Re-run extract/analyze on Struct to refresh Results.

## Code fixes landed

| Gap | Fix |
| --- | --- |
| C6 plan marks stuck as context | Keep schedule-resolved bare marks takeoff-eligible off schedule-grid pages |
| Lintel plate assembly | `schedule_assembly` sidecar (plate text/role + 2/end hint) |
| L5 precast as angle L | `schedule_non_steel_mark` abstention; no family L |
| BP1–BP7 / CL* | Extracted as tokens; resolved via schedule → plate/angle; **shown in Results** (`takeoff_eligible`); schedule-table rows tagged `schedule_member` so qty stays 0 |
| Schedule-mark qty | `SCHEDULE MARK MAP` is a labeled QE source; schedule_cell still qty 0 |

## Still out of scope / intentional

- Base/cap plates on column schedule as separate BOM lines (sidecar on C* only today)
- Explicit catalog match still unlabeled for QE (product decision)
- Page gate remains OFF; no LLM path
