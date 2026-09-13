# GHX / Drawings Real-World Experiment — Phase 0D

**Experiment ID:** `ghx_real_drawings_phase0d_2026-09-12`  
**Date:** 2026-09-12  
**Mode:** READ-ONLY investigation (no production code changes, no GH rewrite, no ML flags)

---

## 1. Experiment verdict

**BLOCKED**

Success criterion **E** is met: live Grasshopper execution is currently impossible on this machine, and the exact missing dependencies are identified below. Criteria A–D were **not** measured (no inventing / simulating `RH_OUT`).

**GH LIVE RUN = BLOCKED**

---

## 2. Files and project used

### 2.1 Newly uploaded drawings folder (Step 1 inventory)

| Field | Value |
|---|---|
| Exact path | `/Users/hibareda/Desktop/DWGs` |
| Structure | Flat (no subfolders) |
| File count | **13** |
| File types | **100% `.dwg`** |
| PDF | 0 |
| DXF | 0 |
| 3DM | 0 |
| GH / GHX | 0 |
| Other geometry | 0 |

**Project grouping:** single project — **“New bldg - St”** (structural sheets), filenames:

| Sheet (from filename) | File |
|---|---|
| p8 Ground floor foundation | `New bldg - St_p8_GROUND_FLOOR_FOUNDATION_PLAN.dwg` |
| p9 First floor framing | `New bldg - St_p9_FIRST_FLOOR_FRAMING_PLAN.dwg` |
| p9 First floor framing (edited) | `New bldg - St_p9_FIRST_FLOOR_FRAMING_PLAN_edited.dwg` |
| p10 Second floor framing | `New bldg - St_p10_SECOND_FLOOR_FRAMING_PLAN.dwg` |
| p11 Third floor framing | `New bldg - St_p11_THIRD_FLOOR_FRAMING_PLAN.dwg` |
| p12 Fourth floor framing | `New bldg - St_p12_FOURTH_FLOOR_FRAMING_PLAN.dwg` |
| p13 Roof framing | `New bldg - St_p13_ROOF_FRAMING_PLAN.dwg` |
| p15 Column schedule | `New bldg - St_p15_COLUMN_SCHEDULE.dwg` |
| p17 Braced frame elevations | `New bldg - St_p17_BRACED_FRAME_ELEVATIONS.dwg` |
| p19 Gravity brace (+ scaled) | `New bldg - St_p19_GRAVITY_BRACE.dwg`, `..._scaled.dwg` |
| p20–22 Sections | `New bldg - St_p20-21-22_SECTIONS.dwg` |
| p23 Sections | `New bldg - St_p23_SECTIONS.dwg` |

Large drawing files were **not** copied into the repo.

### 2.2 Selected project (Step 3)

**Selected:** `New bldg - St` (only project present under `/Users/hibareda/Desktop/DWGs`).

**Why:**

1. Real structural / framing content (multiple floor framing plans + roof + column schedule + braces).
2. Manageable sheet count (13 DWGs; target framing subset p9–p12).
3. Clear framing-plan naming (beam-label / beam-curve association is the intended GH use case).
4. River Road / Burrville DD / SOME were preferred in the June PDF index, but **those projects have no colocated Rhino/GH geometry in this upload**; this folder is the only new CAD set provided for Phase 0D.

**Intended sheets for a future live GH run (not executed):**

- `..._p9_FIRST_FLOOR_FRAMING_PLAN.dwg` (prefer over `_edited` unless Mike specifies)
- `..._p10_SECOND_FLOOR_FRAMING_PLAN.dwg`
- optionally `..._p11_THIRD_FLOOR_FRAMING_PLAN.dwg`

### 2.3 Related artifacts inspected (not GH workflow)

| Path | Notes |
|---|---|
| `/Users/hibareda/Desktop/Estima 3D/ST.pdf` | Present; relationship to “New bldg - St” **unproven** |
| `/Users/hibareda/Desktop/Estima 3D/Struct.pdf` | Present; relationship **unproven** |
| `/Users/hibareda/Desktop/Estima 3D/*.pptx` | Product decks only; no `RH_OUT` contract export |
| `backend/JUNE_CORPUS_AUDIT.md` §6 | Documents same unresolved `RH_OUT` questions; no live capture |
| `backend/services/engineering/geometry_adapters.py` | `3dm` / `dwg` / `dxf` adapters are **deferred** (`NotImplementedError`) |

---

## 3. Environment capability

| Question | Answer |
|---|---|
| Was Rhino available? | **No runnable Rhino.app found** under `/Applications` or user search. Leftover support data exists at `~/Library/Application Support/McNeel/Rhinoceros/8.0/` (suggests Rhino 8 was once installed), but **no executable / app bundle** was located for this experiment. |
| Was Grasshopper available? | **No** (requires Rhino; no GH plugin / definition located). |
| Was the GHX/GH actually executed? | **No.** |
| Inspection-only? | **Yes — inspection-only.** |

### Exact missing dependencies (blocker list)

1. **Workflow file:** no `.gh` / `.ghx` anywhere under Desktop / Documents / Downloads (maxdepth search) or Spotlight `*.gh` / `*.ghx`.
2. **Runtime:** no Rhino application available to open DWG → GH.
3. **Exported evidence:** no prior `RH_OUT:*` JSON / CSV / 3DM capture for BeamTxt / BeamCrv / BeamElementID.
4. **Same-sheet PDF for coordinate pairs:** DWG folder has **0 PDFs**; Estima PDFs are adjacent but not verified as the same sheets.

**Do not treat this section as a live run.**

---

## 4. RH_OUT inventory

**Not captured.** Live outputs were not produced.

| Output | Item count | DataTree | Sample | Observed relationships |
|---|---|---|---|---|
| `RH_OUT:BeamTxt` | n/a | n/a | n/a | UNRESOLVED |
| `RH_OUT:BeamCrv` | n/a | n/a | n/a | UNRESOLVED |
| `RH_OUT:BeamTxtUnpaired` | n/a | n/a | n/a | UNRESOLVED |
| `RH_OUT:BeamElementID` | n/a | n/a | n/a | UNRESOLVED |
| `RH_OUT:PlanText` | n/a | n/a | n/a | UNRESOLVED |
| `RH_OUT:PlanCrv` | n/a | n/a | n/a | UNRESOLVED |
| `RH_OUT:PlanColumnClosed` | n/a | n/a | n/a | UNRESOLVED |
| `RH_OUT:MiscBeamCrv` | n/a | n/a | n/a | UNRESOLVED |

Repo documentation mentions these names as **open questions only**; that is **not** evidence of tree structure or pairing.

---

## 5. BeamTxt ↔ BeamCrv answer

**UNRESOLVED**

Hypothesis A (`BeamTxt[i]` ↔ `BeamCrv[i]`) was **not tested**. No DataTree paths, indices, or geometry types were recorded. Same-index / same-branch / one-to-many claims would be speculation.

---

## 6. BeamElementID stability

**UNKNOWN**

No run-1 / run-2 comparison possible without live execution.

---

## 7. Coordinate experiment

**NOT DETERMINABLE**

No Rhino/Grasshopper geometry coordinates were produced. DWGs alone do not yield a calibrated PDF↔Rhino correspondence without (a) colocated PDF page of the same sheet and (b) Rhino model space points for shared references. Estima `ST.pdf` / `Struct.pdf` were **not** used to invent transform parameters.

**COORDINATE RELATIONSHIP: NOT DETERMINABLE**

---

## 8. Architecture impact

Classifications below use **this experiment + prior Phase 0B/0C audit evidence**. Items that depend on unproven GH pairing remain **UNRESOLVED** for reuse decisions.

### WHAT WE NO LONGER NEED TO BUILD IN PYTHON

*(Conditional on a future proven GH contract — **not authorized by this run**.)*

Nothing can be struck from the Python backlog **based on Phase 0D live evidence**, because no GH outputs were observed.

Prior dense-PDF evidence still **supports the hypothesis** that PDF-only member curve extraction is weak on vector-heavy sheets (`_DENSE_PAGE_CAP`), so **reimplementing a full beam detector in Python remains a bad primary strategy** — but that is architectural judgment from PDF limits, not proven GH reuse.

### WHAT PYTHON MUST STILL OWN

| Task | Class |
|---|---|
| Final text semantic interpretation | **KEEP IN BACKEND** |
| Normalization | **KEEP IN BACKEND** |
| Repair | **KEEP IN BACKEND** |
| Completion (drawing-local evidence only) | **KEEP IN BACKEND** |
| Incomplete L/2L abstention / takeoff eligibility | **KEEP IN BACKEND** |
| Catalog verification (never selection) | **KEEP IN BACKEND** |
| Excel as comparison/reference only | **KEEP IN BACKEND** |

Safety rules unchanged: GH association of geometry to a nearby longer label does **not** authorize semantic completion of incomplete marks.

### WHAT REQUIRES COMBINED EVIDENCE

| Task | Class |
|---|---|
| Text-to-beam proximity | **NEEDS COMBINED EVIDENCE** (when GH available) |
| Orientation / closest-point / midpoint-endpoint | **NEEDS COMBINED EVIDENCE** (candidate from GH; backend validates semantics) |
| Unpaired text detection | **NEEDS COMBINED EVIDENCE** (if `BeamTxtUnpaired` proven) |
| Member bbox for review overlay | **NEEDS COMBINED EVIDENCE** (PDF page space ↔ model space after calibration) |

### WHAT REMAINS UNRESOLVED

| Task | Class |
|---|---|
| Beam curve extraction (reuse GH vs PDF) | **UNRESOLVED** until live `BeamCrv` capture |
| Structural geometry filtering | **UNRESOLVED** |
| Text candidate filtering | **UNRESOLVED** |
| Stable element identity (`BeamElementID`) | **UNRESOLVED** |
| DataTree pairing contract | **UNRESOLVED** |
| PDF ↔ Rhino affine feasibility | **UNRESOLVED** / **NOT DETERMINABLE** this run |

### Explicit non-goals preserved

- Incomplete `L` / `2L` must not auto-complete  
- Catalog existence ≠ missing-dimension evidence  
- Excel ≠ predictor  
- Unlabeled geometry ≠ takeoff truth  
- Experimental ML / GraphSAGE / learned fusion / VLM / production LLM flags remain off  

---

## 9. Recommended next task

**ONE next task only:**

Obtain Mike’s Estima Grasshopper definition (`.gh` / `.ghx`) **and** a machine with runnable Rhino+Grasshopper; run it **unchanged** once on `New bldg - St_p9_FIRST_FLOOR_FRAMING_PLAN.dwg`, dump raw DataTrees for `RH_OUT:BeamTxt`, `BeamCrv`, `BeamTxtUnpaired`, and `BeamElementID` (paths + indices preserved, no flatten), then repeat the dump once for a stability diff — without wiring into production.

---

## Appendix A — What was actually executed

1. Inventoried `/Users/hibareda/Desktop/DWGs` (13 DWGs, flat, one project).  
2. Searched Desktop / Documents / Downloads / Spotlight for `.gh` / `.ghx` / `.3dm` / `RH_OUT` exports — **none found**.  
3. Checked `/Applications` and filesystem for `Rhino*.app` — **not found**; McNeel support folder remnant only.  
4. Confirmed in-repo geometry adapters defer `3dm`/`dwg`/`dxf`.  
5. Did **not** run Grasshopper, simulate outputs, modify production Python, or commit.

## Appendix B — Experimental JSON

See `backend/ghx_real_drawings_phase0d_evidence.json` — blocked stub only (empty `grasshopper_output`; no fabricated pairs).
