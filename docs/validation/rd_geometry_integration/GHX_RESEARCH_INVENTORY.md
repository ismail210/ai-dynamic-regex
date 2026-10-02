# GHX Research Inventory

**Date:** 2026-09-21  
**Scope:** Repository + previously documented external CAD folder (`/Users/hibareda/Desktop/DWGs`)  
**Mode:** Read-only inspection — no production changes, no GH execution, no simulated RH_OUT

---

## 1. Search summary

| Search | Result |
| --- | --- |
| `*.ghx` / `*.gh` in repo | **0 files** |
| `estima3d_web_plan.ghx` | **Not in repository** (named in docs only) |
| Live `RH_OUT:*` JSON/CSV/3DM captures | **None** |
| Rhino / Grasshopper runtime (re-check) | **Not available** for this investigation |
| Docs/`ghx_geometry_audit.md`, `ghx_semantic_manifest.json` | **Referenced in code comments; files not present** |

**Conclusion of inventory:** There are **no Grasshopper component definition files** to inspect. What exists is (a) Phase 0D blocked-run documentation, (b) Python adapters that consume a *hypothetical* already-captured `RH_OUT` dict, (c) external `.dwg` sheets that are **not** GHX.

---

## 2. Files discovered

### 2.1 In-repository GHX-named artifacts

| Path | Type | Approx. size | What it represents | Actual geometry? | Component metadata? | Geometry refs? | IDs/relationships? | Usability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `backend/GHX_REAL_DRAWINGS_EXPERIMENT.md` | Markdown report | ~10 KB | Phase 0D (2026-09-12) blocked live-run investigation | No | No (lists missing deps) | No | Documents UNRESOLVED RH_OUT names | Indirect — status / blockers only |
| `backend/ghx_real_drawings_phase0d_evidence.json` | JSON stub | ~2.3 KB | Machine-readable Phase 0D verdict | No — all output arrays empty | No | No | `relationship_type: unknown` | Indirect — proves capture did not happen |
| `docs/GEOMETRY_ASSOCIATION_SENIOR_ARCHITECTURE_RESEARCH.md` | Architecture research | ~32 KB | How GHX *should* fit as silver/reference | No live data | Aspirational RH_OUT field list | Speculative | Speculative pairing rules | Indirect — design intent, not evidence |
| `docs/GEOMETRY_ASSOCIATION_DATASET_SCHEMA.md` | Schema | (docs) | GHX IDs never ML targets | No | Policy | Policy | `ghx_reference` naming | Indirect — policy constraints |
| `docs/GEOMETRY_ASSOCIATION_EXPERIMENT_PLAN.md` | Plan | (docs) | Do not claim “better than GHX” | No | No | No | No | Indirect |

### 2.2 In-repository code that *mentions* GHX / Grasshopper

| Path | Type | Approx. size | What it represents | Actual geometry? | Component metadata? | Usability |
| --- | --- | --- | --- | --- | --- | --- |
| `backend/services/semantic_preprocessor/geometry_evidence.py` | Python provider | ~5.7 KB | `GrasshopperGeometryEvidenceProvider` maps **already-captured** dict → `GeometryEvidence` | Only if caller supplies capture (tests use synthetic) | Output-name → type map (`BeamCrv`, `PlanColumnClosed`, …) | Indirect — consumer of captures; **does not parse `.ghx`** |
| `backend/services/semantic_preprocessor/association.py` | Python | ~7.6 KB | `associate_via_ghx_pairing`, `fuse_candidates` | No | Explicit pair dicts only | Indirect — association fusion rules |
| `backend/services/semantic_preprocessor/coordinate_transform.py` | Python | (module) | PDF ↔ model-space transform helpers | No | No | Indirect — needed if GH coords exist |
| `backend/services/engineering/geometry_adapters.py` | Python | (module) | `3dm` / `dwg` / `dxf` adapters | Deferred | N/A | **`NotImplementedError`** — not usable |
| `backend/tests/test_semantic_preprocessor_geometry_evidence.py` | Tests | ~3.5 KB | Synthetic `RH_OUT:BeamCrv` fixtures | Synthetic only | Synthetic `element_id` | Test-only |
| `backend/tests/fixtures/geometry_evidence/synthetic_geometry_evidence_fixtures.json` | Fixture | (small) | Explicitly **not** live RH_OUT | Synthetic | Synthetic | Must not treat as real GHX |
| `backend/services/semantic/models.py` | Models | (large) | `GeometryEvidence`, `GeometryProvider.GRASSHOPPER` | Schema only | `source_output` e.g. `RH_OUT:BeamCrv` | Contract shape only |

**There is no GHX XML/JSON parser** for Grasshopper definition files in this repository. The provider explicitly states it does **not** call Rhino.Compute and does **not** execute GHX.

### 2.3 External CAD folder (not GHX; same Phase 0D source)

Path: `/Users/hibareda/Desktop/DWGs` (outside repo; **not copied in**)

| File | Type | Approx. size | Notes |
| --- | --- | --- | --- |
| `New bldg - St_p8_GROUND_FLOOR_FOUNDATION_PLAN.dwg` | AutoCAD DWG 2018+ | ~285 KB | User-referenced; **DWG ≠ GHX component file** |
| `New bldg - St_p9_FIRST_FLOOR_FRAMING_PLAN.dwg` (+ edited) | DWG | ~245–257 KB | Phase 0D intended first live sheet |
| `New bldg - St_p10` … `p13`, `p15`, `p17`, `p19`, sections | DWG | 44–660 KB | Framing / schedule / brace / sections |
| **Totals** | 13 DWGs | — | **0 PDF, 0 DXF, 0 3DM, 0 GH/GHX** in folder |

DWG content was not reverse-engineered for this inventory. In-repo CAD adapters for DWG remain unimplemented. DWGs alone do not expose Grasshopper component GUIDs, DataTrees, or RH_OUT pairings.

### 2.4 Adjacent non-GHX artifacts (Estima folder)

| Path | Notes |
| --- | --- |
| `/Users/hibareda/Desktop/Estima 3D/ST.pdf`, `Struct.pdf` | Present; **relationship to “New bldg - St” DWGs unproven** (Phase 0D) |
| `*.pptx` in Estima folder | Product decks; no RH_OUT contract export |

---

## 3. What each category means for this research

| Category | Present? | Implication |
| --- | --- | --- |
| Grasshopper definition (`.gh` / `.ghx`) | **No** | Cannot inspect component GUID/name/IO/wires |
| Live or archived RH_OUT capture | **No** | Cannot inspect curves, IDs, or text↔curve pairs |
| Synthetic RH_OUT in tests | Yes | Proves adapter API shape only |
| External DWG drawings | Yes (outside repo) | Possible *future* GH input; not component metadata |
| Production PDF `member_geometry` path | Yes (separate) | Unrelated to GHX files; G8/G9 remain shadow |

---

## 4. Inventory verdict

**No directly usable GHX component files were found.**

Everything GHX-related in-repo is either:

1. A **blocked experiment record** (empty outputs), or  
2. An **adapter/contract** waiting for a capture that does not exist, or  
3. **Architecture/policy prose** describing aspirational RH_OUT fields.

External **DWG** sheets exist for “New bldg - St” (including the user-noted p8 foundation plan) but are **not** Grasshopper component definitions and cannot substitute for GHX inspection.
