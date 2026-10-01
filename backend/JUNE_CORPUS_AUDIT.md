# JUNE CORPUS AUDIT — Phase 0B

**Date:** 2026-09-12  
**Scope:** Read-only inventory + architecture validation of the local June corpus.  
**Corpus root (OBSERVED):** `backend/Testing Projects/`  
**Machine manifest:** `backend/testing_projects_manifest.json`  
**No production code, flags, models, OCR/VLM/LLM, takeoff, Excel, GHX, or commits were changed.**

---

## FINAL VERDICT

**PASS**

The real June folder was successfully inventoried and audited without production changes.

---

## A. REAL JUNE CORPUS STATUS

### Observed inventory

| Metric | Value |
|---|---|
| Project folders | **13** |
| PDF files | **19** |
| Opens successfully | **19 / 19** |
| Unreadable | **0** |
| Total pages | **2,364** |
| Total bytes | **~2.21 GB** |
| SHA-256 duplicate groups | **0** |
| Native text present (sampled) | **19 / 19** |
| Filename hint = architectural | **11** |
| Filename hint = structural | **0** |
| Filename hint = mechanical / plumbing / ID | **6** (Crystal Dr binders/addenda) |
| Filename hint = unspecified | **2** (SOME DD set; Burrville DD; William Winchester bid set — see notes) |

> Prior Phase 0 assumed “40+ structural-steel PDFs.” **OBSERVED count is 19 PDFs**, and **none are named as Structural/ST binders**. Several combined/bid sets still contain structural sheets inside (verified below).

### Project folders (OBSERVED)

1. `02 - MARS Arcadia`  
2. `03 - The Field School`  
3. `04 - Thomas ES`  
4. `18 - River Road`  
5. `20 - 2100 Crystal Dr` (nested Contract Drawings + Addendum 01)  
6. `34 - Fairwood ES`  
7. `35 - Fort Lincoln Park`  
8. `41 - SOME`  
9. `47 - William Winchester ES`  
10. `51 - Burrvile ES` (folder spelling OBSERVED)  
11. `54 - Duckworth ES`  
12. `55 - Springhill Lake`  
13. `57 - Hart MS`

### Sampling method (declared)

- SHA-256 over full file bytes for every PDF.  
- Page count via PyMuPDF for every PDF.  
- Text: stratified page sample + extra structural-keyword pages on large sets; full text when ≤60 pages.  
- Drawings: ≤8 pages/PDF `get_drawings()` counts (cheap enough; still shows dense-page problem).  
- **Additional full-text spot-check** (not in first sample pass) on River Road, SOME, Hart MS, Burrville DD, Springhill Arch for incomplete-angle context and stricter W/HSS/L patterns.

Do **not** treat coarse `W`/`L` regex tallies on Arch/Mech sets as steel takeoff counts — many are false positives (levels, windows, tags). Prefer the strict spot-check section below.

### PDF table (summary)

Full hashes/sizes/page samples: see `testing_projects_manifest.json`.

| Project | File (short) | Pages | ~MB | Filename discipline hint |
|---|---|---:|---:|---|
| MARS Arcadia | `_VOL 1.2 ARCHITECTURE_BID UPDATE.pdf` | 138 | 211 | architectural |
| Field School | `04 Architectural - Combined File - Copy.pdf` | 79 | 276 | architectural |
| Thomas ES | `Arch.pdf` | 100 | 185 | architectural |
| River Road | `A-…Addendum A - 4400 Base Bldg Dwgs.pdf` | 215 | 90 | architectural |
| Crystal Dr | Arch / ID / Mech / Plumbing binders + addenda (7 PDFs) | 66–181 | 39–120 | arch / ID / mech / plumbing |
| Fairwood ES | `Arch.pdf` | 112 | 110 | architectural |
| Fort Lincoln | `Arch.pdf` | 77 | 62 | architectural |
| SOME | `2025-12-18_100 DD SET-current (1).pdf` | 99 | 88 | unspecified |
| William Winchester | Bid Set Drawings | 88 | 94 | unspecified |
| Burrville | `Burrville_DD Pricing Set_260317.pdf` | 248 | 197 | unspecified |
| Duckworth | `Arch-Duckworth ES.pdf` | 123 | 135 | architectural |
| Springhill Lake | `Arch - Springhill Lake.pdf` | 120 | 47 | architectural |
| Hart MS | `Arch-Hart MS (GMP).pdf` | 135 | 101 | architectural |

Unusually large: Field School ~289 MB; Burrville DD ~206 MB; Thomas ~194 MB.

MuPDF warned on Thomas ES (`no XObject subtype` / `object is not a stream`) but the file still opened and text extracted.

---

## B. What Bassam’s reports got right

(Validated against **this** corpus + current repo; OBSERVED vs prior proxy.)

1. **Native PDF before OCR** — All 19 PDFs have substantial native text. OCR is not the first bottleneck.  
2. **Normalization vs repair vs completion vs association must stay separate** — Real incomplete angles appear next to complete ones (River Road); treating “completion” as TF-IDF nearest neighbor remains unsafe.  
3. **Dense vector pages** — Sampled pages routinely show **10⁴–10⁶** drawings vs production `_DENSE_PAGE_CAP = 450`. PDF geometry association is starved by design.  
4. **JSON sidecar / GH downstream first** — Repo still has **no** `drawing_semantics.json` and **no** GHX wiring; Rhino 3DM adapter is deferred stub.  
5. **Abstention for incomplete L/2L** — Still required; Phase 1 safety probes pass on this tree.  
6. **Do not use Excel as semantic GT** — Unchanged policy; no Excel in this corpus folder.

---

## C. What the June corpus disproves or does not support

| Claim / hope | Corpus finding |
|---|---|
| “40+ structural-steel PDFs” ready for steel takeoff validation | **Not supported.** 19 PDFs; **0** named Structural/ST; many Arch/Mech/ID/Plumbing. |
| OCR engines needed immediately | **Not supported** on this set (native text everywhere sampled). |
| Unicode `×` steel labels common | **Not observed** in samples (`unicode_multiply_hits = 0` in inventory pass). |
| Incomplete `2L4X4` common in June folder | **Not observed** in spot-checks (complete `2L4X4X3/8` appears on Burrville). |
| Arch PDFs are useless for steel | **Partially false.** River Road + Burrville DD + SOME contain real S-content / steel callouts. Springhill **Arch** alone has **0** strict steel designations. |
| Raising PDF dense-page caps unlocks trustworthy member bbox | **Not supported as next step.** Caps would need 100–1000× increase; prior Analyze timeouts; leaders/noise dominate. Supports **GH as stronger geometry source** hypothesis. |
| GNN / VLM / LambdaMART enablement justified by June folder alone | **Not supported yet** — first need a steel-sheet subset + human labels. |

---

## 3. Structural-steel content (OBSERVED)

### Strict spot-check (full-text on 5 PDFs)

| PDF | Strict W-like | HSS-like | Complete L-like | Notes |
|---|---:|---:|---:|---|
| River Road addendum | 206 | 47 | 63 | Real framing/details; **real incomplete** `L4X4` / `L5X3` / `L3X3` |
| SOME DD set | 253 | 0 | 12 | Framing sheets present; incomplete regex mostly **false positive** on `L5X3-1/2X…` |
| Hart MS Arch | 0 | 0 | 9 | Incomplete hits are **arch room/tag tokens** (`L85 x14`, etc.) |
| Burrville DD Pricing | 845 | 78 | 58 | Strong structural content; incomplete regex hits are **half-leg false positives** |
| Springhill Arch | 0 | 0 | 0 | Arch-only for steel purposes despite coarse `L` tallies |

### Incomplete L / 2L

**Real incomplete steel angles (OBSERVED examples — River Road):**

| Page | Label | Context (abbrev.) | Completion class |
|---|---|---|---|
| 23 | `L4X4` | Near rebar / bent bars note | **Unsupported** from that snippet alone |
| 33 | `L4X4` | Curtain wall / arch reference | **Unsupported** |
| 34 | `L4X4` | Same sheet as `L4X4X3/8 PERIMETER ANGLE` | **Possible evidence-supported** if scoped to perimeter role — must stay review / SOURCE_VERIFIED, not auto |
| 34 | `L3X3` | “L3X3 KICKER NOT SHOWN…” | Incomplete / note language — **not** auto-complete |
| 38 | `L5X3` | “PERIMETER ANGLE (BEYOND)” | **Unsupported** without linked schedule/detail |
| 41 | `L4X4` | Metal deck / joist opening | **Unsupported** |

**False-positive incomplete detections (OBSERVED):**

- SOME / Burrville: `L5X3` / `L4X3` carved out of **`L5X3-1/2X5/16`** (thickness present).  
- Hart MS: architectural tags, not angles.

**Safety implication:** Detector must keep half-leg complete forms catalog-valid (Phase 1 already covers `L5X3-1/2X5/16`). Coarse corpus regex counts overstate incomplete frequency.

### Other signals (inventory sample — treat as weak)

- Legends / schedules / TYP language: common across Arch sets.  
- Rotated text: present on all sampled PDFs.  
- Brackets: present.  
- Bent/cap/connection plate keywords: sporadic.  
- OCR-like `W8XI0` / `U+FFFD`: **not** observed as a pattern.

---

## 4. Bassam four-operation model vs corpus

| Operation | Present in June folder? | Evidence | Frequency |
|---|---|---|---|
| **NORMALIZATION** | **PARTIALLY SUPPORTED** | Spacing / case variants expected; Unicode `×` **not** observed in sample | Unknown without labeled set |
| **REPAIR** | **NOT OBSERVED** as dominant | No clear `W8XI0`-class corruption in samples | Low / not testable yet |
| **COMPLETION** | **SUPPORTED (rare, high-risk)** | River Road incomplete `L4X4` with nearby `L4X4X3/8` | Few verified pages |
| **ASSOCIATION** | **PARTIALLY SUPPORTED as need; PDF geom weak** | Labels + dense vectors exist; member bbox trust **not** established | Hard under cap 450 |

### Completion split (required)

| Class | Meaning | June example | Policy |
|---|---|---|---|
| **A. Evidence-supported** | Explicit drawing link (same detail/schedule/note scope) | River Road p34 incomplete `L4X4` near `L4X4X3/8 PERIMETER ANGLE` — **candidate only after human SOURCE_VERIFIED scope** | Review / future DLP — **do not auto-apply** |
| **B. Unsupported inference** | Catalog similarity / global map | `L4X4` → `L4X4X1/4` because catalog has it | **Abstain** (Phase 1) |

---

## 5. Geometry assumptions (repo + corpus)

### Current code (OBSERVED)

| Component | Status |
|---|---|
| `geometry_extractor.py` | PRODUCTION; `_DENSE_PAGE_CAP = 450`; `structural_first` |
| `geometry_adapters.py` | PDF live; Rhino/DXF/DWG **DeferredCadAdapter** |
| `geometry_normalizer.py` | Collinear merge |
| `spatial_association.py` | PRODUCTION (default on) |
| `graph_builder` / structural graph | PRODUCTION topology |
| `member_geometry.py` | UNCOMMITTED dirty tree; evidence-only; null when unresolved |
| PDF rewrite / `drawing_semantics.json` | NOT PRESENT |

### Corpus geometry evidence

- Vector drawings: **yes** on sampled pages.  
- Dense-page: **extreme** — examples include ~146k, ~460k, even **~1.2M** drawings on a single sampled page.  
- After cap 450: **>99% of primitives dropped** on those pages.  
- Leader prevalence: prior Burrville framing QA + current dense Arch/Mech pages make leader-dominated retention likely; not re-run full kind classification here (expensive).  
- **Trustworthy member-level bbox from PDF alone: NO** for this corpus at current caps.  
- **Hypothesis “Grasshopper should remain the stronger geometry source”: SUPPORTED** by dense-page evidence + deferred Rhino adapter + no live GH contract in-repo.

Do **not** raise caps or implement member geometry in this phase.

---

## 6. Grasshopper / GHX — unresolved questions

**OBSERVED in repo:** no `.ghx` files; no `RH_OUT:*` / `BeamTxt` / `BeamCrv` symbols in `docs/` or backend services; geometry adapter documents Rhino 3DM as deferred/`NotImplemented`.

Therefore these remain **UNRESOLVED without a live Grasshopper run** (do not pretend solved):

1. Does `BeamTxt[i]` correspond to `BeamCrv[i]`?  
2. What is the actual GH data-tree structure?  
3. Is `BeamElementID` stable between runs?  
4. Exact payloads for:  
   `RH_OUT:BeamTxt`, `BeamCrv`, `BeamTxtUnpaired`, `PlanText`, `PlanCrv`, `PlanColumnClosed`, `MiscBeamCrv`, `BeamElementID`  
5. PDF-page ↔ Rhino coordinate transform?

**What one real GH run must capture:** paired lists + tree paths + IDs across two runs + a coordinate cross-check on ≥3 known members.

---

## 7. Phase 1 safety check (this working tree)

Focused probes + tests (2026-09-12), **no code changes:**

| Input | section | completion_status | takeoff_eligible |
|---|---|---|---|
| `L4X4` | `L4X4` | missing_thickness | False |
| `L4X4,` | `L4X4` | missing_thickness | False |
| `L4X4@length` | `L4X4` | missing_thickness | False |
| `2L4X4` | `2L4X4` | missing_thickness | False |
| `2L4X4,` | `2L4X4` | missing_thickness | False |
| `L4X4X1/4` | `L4X4X1/4` | complete | True |
| `L4X4X3/8` | `L4X4X3/8` | complete | True |
| `L5X3-1/2X5/16` | `L5X3-1/2X5/16` | complete | True |
| `L3X3X5/16,` | `L3X3X5/16` | complete | True |
| `L2X2X10` / `L2x2x10` | `L2X2X10` | complete | False |

Tests: `test_incomplete_angle_abstention.py` + `test_format_catalog_equivalence.py` → **28 passed**.

Experimental flags untouched (remain off).

---

## 8. Priority matrix (driven by **this** corpus)

| Pri | Problem | Corpus evidence | Current capability | Gap | Recommended action | Safety risk | Justified now? |
|---|---|---|---|---|---|---|---|
| **P0** | Corpus not steel-first | 0 ST-named PDFs; Arch/Mech/ID dominate | Manifest exists | Missing Structural binders / sheet filter | Freeze steel-relevant subset + request ST PDFs for projects that only have Arch | Low | **Yes** |
| **P0** | Incomplete-L safety already landed but uncommitted risk remains | River Road real `L4X4` | Dirty Phase 1 | Protect on branch | Commit/protect Phase 1 when user asks (not this phase) | High if lost | Ops |
| **P1** | Sheet/discipline filter | Arch sets mix S-content | Weak | Auto S-sheet discovery | Deterministic sheet/title filter before Analyze | Low | Yes (small) |
| **P1** | Normalization / grouping on steel pages | Rotated text; brackets; River Road labels | Fragment grouper | Rotation/bracket gaps | After steel subset frozen | Low | After P0 subset |
| **P1** | Evidence-based completion design only | River Road p34 candidate | Abstain only | SOURCE_VERIFIED scope rules | Spec + fixtures; **no auto-complete** | Critical if auto | Spec yes; code later |
| **P2** | `drawing_semantics.json` contract | Stakeholder/GH need | Absent | Schema | Schema-only after subset | Low | Soon |
| **P2** | GH live contract probe | Dense PDF geom fails | Deferred adapter | Unknown RH_OUT | One instrumented GH run | Low | Yes when Mike access |
| **DEFER** | Raise dense-page cap / PDF member bbox | Caps fail by orders of magnitude | Cap 450 | Trust | Prefer GH geometry | High perf | **No** |
| **DEFER** | OCR / VLM / GNN / LambdaMART enable | Native text; no repair-dominant set | Flags off | — | Keep off | High | **No** |
| **DEFER** | Corrected PDF rewrite | No accepted decision stream | Absent | Vector wipe risk | After sidecar + review | Very high | **No** |
| **REJECT** | `L4X4`→thickness via catalog; Excel-as-GT | River Road multi-thickness neighborhood; Burrville history | Abstain | — | Never | Critical | — |

---

## 9. Recommended next steps

### D. What we should implement next

1. **Steel-relevant validation subset** from this corpus (page-level): River Road structural sheets, Burrville DD S-pages, SOME framing pages — plus request missing dedicated ST PDFs.  
2. **Sheet/discipline classifier** (deterministic) so Arch/Mech/Plumbing binders are not mistaken for steel takeoff corpora.  
3. **Semantic operation contract (schema only)** once subset is frozen.  
4. **One live GH RH_OUT capture** to answer §6.

### E. What we should NOT implement

- OCR stack, VLM, GNN, enabling ML ranker/fusion/GraphSAGE  
- Auto completion of incomplete L/2L  
- PDF rewrite  
- Raising dense-page caps to chase member bbox  
- Treating Arch `L*`/`W*` regex tallies as takeoff gold  

### F. Exact recommended next task (one)

**Build a frozen steel-relevant page index for this June folder** (CSV/JSON: `project`, `pdf_sha256`, `page`, `sheet_id_if_any`, `why_included`) covering River Road + Burrville DD + SOME structural pages only — **read-only indexing, no production behavior change** — and list which of the 13 projects still lack any Structural PDF so June can supply them.

That unblocks honest Phase-1-of-Bassam work without pretending Arch binders are ST sets.

---

## Safety reminders (unchanged)

- Never `L4X4` → `L4X4X1/4` from catalog alone.  
- Never invent `2L` from single-L.  
- Excel = comparison only.  
- Unlabeled geometry ≠ takeoff truth.  
- Experimental flags stay off.

---

## Artifacts / git

| Artifact | Role |
|---|---|
| `backend/testing_projects_manifest.json` | Machine inventory (hashes, pages, samples) |
| `backend/JUNE_CORPUS_AUDIT.md` | This report |
| `backend/Testing Projects/**` | PDFs — **do not commit** |

Production sources were **not** modified for Phase 0B. Pre-existing dirty tree (Phase 1 safety, member_geometry, frontend, training dirt) preserved.
