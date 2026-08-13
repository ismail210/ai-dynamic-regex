# Real-Project Archive Inventory (Phase 2.5)

Sanitized summary of `PDF & Excel (1).zip` (not committed — SHA-256 of the archive and every extracted file, plus the project-name-to-ID mapping, live only in the git-ignored `backend/training/ml_association/real_project_pilot/working_notes/` directory on this machine). This document intentionally omits real project names and filenames.

## Archive integrity

- `zipfile.testzip()`: **OK**, no corruption, not encrypted.
- 52 raw entries; after removing macOS resource-fork artifacts (`__MACOSX/`, `.DS_Store`) and one Excel autosave lock file (`~$...xlsm`), **14 real content files** remain across **7 project folders**.

## Project-level summary

| Sanitized ID | PDF pages | PDF size | Excel sheets | Excel size |
|---|---|---|---|---|
| project_001 | 39 | 18.4 MB | 12 | 250 KB |
| project_002 | 29 | 1.8 MB | 12 | 234 KB |
| project_003 | 81 | 44.9 MB | 12 | 670 KB |
| project_004 | 23 | 3.3 MB | 7 | 186 KB |
| project_005 | 17 | 5.5 MB | 6 | 166 KB |
| project_006 | 45 | 13.3 MB | 12 | 621 KB |
| project_007 | 28 | 2.4 MB | 11 | 670 KB |

**Totals**: 7 PDFs, 7 Excel workbooks, 7 projects inferred (one PDF + one Excel per folder, 1:1), **262 total PDF pages**.

## PDF characteristics (from PyMuPDF metadata + first/middle/last-page sampling)

All 7 PDFs are **born-digital / vector** (not scanned) — every sampled page across every project returned nonzero `get_drawings()` counts and nonzero extractable text, consistent with CAD-exported structural drawing sets rather than scanned raster sheets. No encrypted or unreadable PDF was found.

Page rotation: every sampled page across all 7 PDFs reported `rotation=0` at the PyMuPDF page level. This does not rule out visually-rotated *details* drawn within an unrotated page (common for structural sheets with rotated partial plans) — page-level rotation and in-page rotated content are different things; the page-profile step (below) does not attempt to detect the latter.

## Excel characteristics

Every workbook uses a **strikingly consistent sheet-naming convention** across all 7 projects: `ProjectHome`, `Parameter` (where present), `StructuralColumnSchedule`, `StructuralFramingSchedule`, `StructuralConnectionSchedule`, `BasePlateSchedule`, `StructuralPlateSchedule`, `StructuralBracingSchedule`, `StructuralJoistSchedule`, `StructuralDeckSchedule`, `MomentConnectionSchedule`, `Summary`, `Proposal`, `Count_per_Sheet`, `Steel Elements Summary`, `_ChartData` (subset varies by project). This consistency strongly suggests all 7 workbooks are outputs of the **same estimating tool/template** (name not asserted here — not verifiable from sheet names alone, and not material to this audit).

**Classification (see `real_project_excel_assessment.md` for the full, per-sheet reasoning)**: these are **possible reference data / prior production outputs**, not automatically treated as confirmed ground truth. Row counts are substantial (schedules ranging from a few dozen to several thousand rows), consistent with genuine per-project takeoffs rather than placeholder/template data.

## Confirmed pre-existing artifacts in this repository

Two of the extracted PDFs' SHA-256 prefixes **exactly match** document IDs already present in `backend/training/` from before this session (`doc_9414716bffc67596` and `doc_0d910a43b4a021e3`, per `document_registry.py`'s `doc_{sha256[:16]}` convention) — i.e., at least two of these real projects (project_002 and project_005) had already been run through the production Estima3D pipeline at some earlier point, independent of this pilot. This is noted for completeness; this pilot's own runs (below) do not depend on or reuse those prior artifacts.

## Data-handling confirmation

- Extracted files live only under `backend/training/ml_association/real_project_pilot/extracted/`, which is covered by a new, verified `.gitignore` rule (`git check-ignore` confirmed before any extraction occurred).
- The archive itself was not modified, moved, or renamed.
- No file was uploaded anywhere or sent to an external API.
- The project-name↔sanitized-ID mapping exists only in the ignored `working_notes/` subdirectory, never in this file or any other committed document.
