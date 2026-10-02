# GHX Research Report

**Date:** 2026-09-21  
**Context:** Follow-on to G7–G9 + G8-era human review (`PRODUCTION_NO_GO`). Exploratory only.  
**Companion inventory:** `GHX_RESEARCH_INVENTORY.md`  
**Prior experiment:** `backend/GHX_REAL_DRAWINGS_EXPERIMENT.md` (Phase 0D, verdict **BLOCKED**)

**Production safety:** No production association/extraction changes; G8/G9 untouched; historical gold untouched; no G10.

---

## 1. Executive Summary

After searching the repository and re-checking the Phase 0D CAD folder, **no `.ghx` / `.gh` Grasshopper definition files and no live `RH_OUT` captures were available to inspect.** What exists is:

- Phase 0D documentation proving a live GH run was **blocked** (empty `grasshopper_output`).
- Python adapters (`GrasshopperGeometryEvidenceProvider`, pairing/fusion helpers) that consume an **already-captured** dict — they do **not** parse GHX XML and were never executed against real Estima outputs in this environment.
- External **DWG** sheets for “New bldg - St” (including p8 foundation), which are AutoCAD drawings, **not** GHX component graphs.

Therefore this investigation **cannot** show that GHX component representation contains information that materially improves PDF geometry extraction, G8 candidates, ownership, association, or ambiguity handling. Aspirational field names in docs/code are **not** measured evidence.

**Recommendation:** `GHX_RESEARCH_NOT_ACTIONABLE`

---

## 2. GHX Inventory

See `GHX_RESEARCH_INVENTORY.md` for the full table.

| Class | Count / status |
| --- | --- |
| `.ghx` / `.gh` in repo | **0** |
| Live RH_OUT captures | **0** |
| Phase 0D evidence JSON | 1 (blocked stub; empty arrays) |
| GHX-related Python adapters/tests | Present (synthetic fixtures only) |
| External DWGs (`/Users/hibareda/Desktop/DWGs`) | 13 DWG; **0 GHX** |
| User-noted file | `New bldg - St_p8_GROUND_FLOOR_FOUNDATION_PLAN.dwg` (~285 KB, AutoCAD 2018+) — **not GHX** |

---

## 3. Available Information

### 3.1 From actual `.ghx` files

**None.** Component GUID, hierarchy, inputs/outputs, wires, referenced Rhino objects, layers, transforms, and component-to-geometry relationships **could not be read** because no definition file is present.

### 3.2 Fields documented as *expected* in a future RH_OUT capture (aspirational)

These appear in `GrasshopperGeometryEvidenceProvider` / Phase 0D / architecture docs. **Exists in a real capture?** → **No (UNRESOLVED / not measured).**

| Field | Exists in repo capture? | Example (code/docs only) | Potential geometry value |
| --- | --- | --- | --- |
| Component GUID (GH definition) | No | — | Would identify definition version; **NO_EVIDENCE** from files |
| Component name/type (GH graph) | No | Stakeholder names (e.g. PointGrouping) cited as UNKNOWN in-repo | **NO_EVIDENCE** |
| Component hierarchy / wires | No | — | **NO_EVIDENCE** |
| `RH_OUT:BeamCrv` points/length | No live; synthetic in tests | `[{"points":[[0,0],[10,0]],"length":10,"element_id":"e1"}]` | *If captured:* member-scale curves |
| `RH_OUT:BeamTxt` | No | Named in Phase 0D table as UNRESOLVED | *If captured:* text side of pairs |
| `RH_OUT:BeamElementID` | No | UNRESOLVED; stability UNKNOWN | *If captured + stable:* ownership ID |
| `RH_OUT:BeamTxtUnpaired` | No | UNRESOLVED | *If captured:* abstention signal |
| `RH_OUT:PlanColumnClosed` / `PlanCrv` / `MiscBeamCrv` | No | Mapped in provider `_OUTPUT_TO_TYPE` | Typed geometry *if* captured |
| Explicit `*_paired_text` / shared `element_id` | No live | Provider refuses list-index pairing | *If captured:* association evidence |
| Layer / object attributes from GH | No | — | **NO_EVIDENCE** |
| PDF↔Rhino transform | No | `coordinate_relationship: NOT_DETERMINABLE` | Required bridge; **absent** |
| Route / association_origin (primary vs recovery) | No | Architecture recommends exporting; not present | Critical for silver vs heuristic; **NO_EVIDENCE** |

### 3.3 From DWG (external)

| Field | Exists? | Notes |
| --- | --- | --- |
| Native CAD geometry | Yes (file present) | Not readable via in-repo adapters (`NotImplementedError`) |
| GHX components | No | DWG is not a Grasshopper definition |
| Link to Burrville PDF / G8 candidates | No | Different project; no colocated PDF in DWG folder |

---

## 4. Mapping to Current Pipeline

### Current production

`PDF → geometry extraction → member candidates → text-to-member association → ambiguity abstention → Drawing Review`

### Research

`PDF → G8 representation (shadow) → G9 association (shadow)` → **`PRODUCTION_NO_GO`**

| Stage | GHX could help? | Classification | Evidence basis |
| --- | --- | --- | --- |
| **A. Geometry extraction** | Unknown — would need Rhino-quality curves + calibrated PDF frame | **NO_EVIDENCE** | No RH_OUT coords; transform NOT_DETERMINABLE; DWG adapters unimplemented |
| **B. Candidate generation** | Hypothesized in architecture (cleaner member curves vs PDF giants) | **NO_EVIDENCE** | No BeamCrv capture to compare to G8 compounds |
| **C. Candidate typing** | Provider *maps* output names → types **if** capture exists | **NO_EVIDENCE** | Mapping is code contract only; no live typed outputs |
| **D. Ownership** | `element_id` stability required | **NO_EVIDENCE** | `beam_element_id_stability: UNKNOWN`; 0 runs |
| **E. Association** | Explicit pairing + fuse-with-PDF designed in code | **NO_EVIDENCE** | `BeamTxt↔BeamCrv` UNRESOLVED; no pairs captured |
| **F. Ambiguity** | Unpaired lists / multi-candidate export *if* instrumented | **NO_EVIDENCE** | Not captured; parallel-bay C cases are PDF-side |
| **G. Validation** | Silver reference vs G8/G9 *after* capture + human check | **NO_EVIDENCE** | Architecture forbids GHX as GT; no reference file exists |

**Important:** Adapter code readiness ≠ proven GHX capability. Classification stays **NO_EVIDENCE** until a real capture exists.

---

## 5. Known Failure Modes

| Problem | GHX evidence | Could help? | Confidence | Why |
| --- | --- | --- | --- | --- |
| 1. Giant/compound strokes | None | **NO_EVIDENCE** | — | No BeamCrv to show member-scale alternatives |
| 2. Short strokes | None | **NO_EVIDENCE** | — | Not measured |
| 3. Segmented compounds | None | **NO_EVIDENCE** | — | G8 segmentation is PDF-side R&D; no GHX link |
| 4. LINE vs SEGMENT ranking (D-case) | None | **NO_EVIDENCE** | — | No tip/route provenance from GH |
| 5. Tip proximity | None | **NO_EVIDENCE** | — | No leader/tip fields captured |
| 6. Parallel-bay ambiguity (C) | None | **NO_EVIDENCE** | — | Would need multi-candidate + sheet alignment |
| 7. Stale historical gold (B) | None | **NO_EVIDENCE** | — | Gold universe issue; GHX not involved |
| 8. Candidate ownership | None | **NO_EVIDENCE** | — | Element ID stability unknown |
| 9. Missing/ambiguous green Member boxes | None | **NO_EVIDENCE** | — | Production abstention is PDF `member_geometry`; GHX not wired |

---

## 6. Evidence

### 6.1 Attempted bridge trace (required)

Desired chain:

`GHX component → referenced geometry → geometry ID → member/candidate → PDF geometry → text label → association`

**Result: bridge cannot be established.**

| Hop | Status |
| --- | --- |
| GHX component | **Missing** — no `.ghx` |
| Referenced geometry / RH_OUT | **Empty** — Phase 0D `grasshopper_output` arrays all `[]` |
| Geometry identity | **Unavailable** |
| Map to G8 / production `member_*` | **Not attempted** (nothing to map; would be manufacture) |
| Map to Burrville PDF text | **No shared project evidence** with “New bldg - St” DWGs |
| Association | **UNRESOLVED** (Phase 0D §5) |

No name-similarity mappings were invented.

### 6.2 Concrete repository facts

1. `backend/ghx_real_drawings_phase0d_evidence.json`: `"verdict": "BLOCKED"`, `"gh_or_ghx_found": false`, empty outputs.  
2. `GrasshopperGeometryEvidenceProvider` docstring: does not execute GHX; no Rhino.Compute client in repo.  
3. `associate_via_ghx_pairing` only uses **explicit** pairs; never list-index alignment.  
4. `geometry_adapters` DWG/3DM: `NotImplementedError`.  
5. G8/G9 reports explicitly left GHX untouched; association gate remains `PRODUCTION_NO_GO` on the **PDF** path.

### 6.3 User-attached DWG

`/Users/hibareda/Desktop/DWGs/New bldg - St_p8_GROUND_FLOOR_FOUNDATION_PLAN.dwg` is a real AutoCAD drawing (~285 KB). It is **inventory evidence for CAD availability**, not evidence of GHX component content or PDF association improvement.

---

## 7. Limitations

1. **No definition file** → cannot audit Grasshopper components, GUIDs, or internal matching logic.  
2. **No RH_OUT capture** → cannot measure curve quality, pairing, or ID stability.  
3. **No PDF↔Rhino calibration** for the DWG set → cannot overlay GH curves on Drawing Review even if curves appeared tomorrow without extra work.  
4. **Project mismatch risk** — Burrville G8/G9 work vs “New bldg - St” DWGs; linking them without sheet identity would be invalid.  
5. **Policy constraint (already documented)** — even after capture, GHX is at best **silver/reference**, never default ground truth, and must not become ML targets.  
6. **Dependency / data-quality risk** — introducing GHX later adds Rhino runtime, definition versioning, export provenance, and dual coordinate frames.

---

## 8. Recommendation

# `GHX_RESEARCH_NOT_ACTIONABLE`

**Reasoning (conservative):**

- Q1–Q6 cannot be answered affirmatively from repository evidence (all **NO_EVIDENCE** / blocked).  
- Q7: Yes — using GHX later **would** introduce runtime, export, and coordinate-frame dependencies (documented in Phase 0D + architecture).  
- Q8: There is **not** enough *content evidence* from GHX files to justify a G8/G9-enhancement experiment now; the blocker is missing inputs, not a measured GHX benefit.

This does **not** claim GHX will never help. It claims: **with the files we have, we cannot justify GHX-based geometry/association work.**

---

## 9. Proposed Next Experiment

**Not applicable** (recommendation is not positive).

For operational completeness only — **dependency acquisition already recorded in Phase 0D**, not a claim of GHX integration value:

> Obtain the Estima Grasshopper definition (`.gh` / `.ghx`) and a machine with Rhino+Grasshopper; run once on a framing DWG; dump raw `RH_OUT` DataTrees; then re-evaluate this report. Until that capture exists, do not plan G8/G9/GHX fusion experiments.

---

## Answers to required questions

| # | Question | Answer |
| --- | ---: | --- |
| Q1 | Authoritative member/geometry info? | **Unknown / unproven** — no capture |
| Q2 | Reliable map GHX → PDF geometry? | **No** — bridge not established |
| Q3 | Improve G8 candidates? | **NO_EVIDENCE** |
| Q4 | Improve association? | **NO_EVIDENCE** |
| Q5 | Reduce ambiguity? | **NO_EVIDENCE** |
| Q6 | Independent validation source? | **NO_EVIDENCE** (aspirational silver only after capture + human check) |
| Q7 | New dependency / data-quality problem? | **Yes**, if introduced later |
| Q8 | Enough evidence to justify experiment? | **No** (for association/G8 enhancement) |
