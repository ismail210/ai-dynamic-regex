# Detail-Page Extents Prototype (R&D — Step 3)

**Status:** Controlled prototype — **not** production association.  
**Date:** 2026-09-17  
**Harness:** `backend/scripts/rd_geometry_integration/`  
**Outputs:** `docs/validation/rd_geometry_integration/step3_*.json`, `renders/`

---

## 1. Pages tested

| Page | Sheet role | Why |
|------|------------|-----|
| **8** | Structural plan (control) | Dense framing; baseline for “single logical drawing” behavior. |
| **18** | Detail sheet | S‑205 / incomplete‑L evidence; expected multi-detail layout. |
| **24** | Dense detail sheet | S‑321 roof details; many L4X4\* callouts. |

PDF: Burrville ES - ST (`doc_0d910a43b4a021e3`).

Terminology used: **`detail_region_candidate`** — not claimed as verified “details.”

---

## 2. Candidate region methodology

Two methods compared:

### A. Production X-gap clustering (existing)

`services.engineering.detail_regions.cluster_page_regions`

- Sorts text+geometry by **X center**.
- Splits when horizontal gap &gt; `max(80, 0.12 × page_width)`.
- **Does not** split stacked vertical details.

### B. R&D 2D gap clustering (experimental only)

`scripts/rd_geometry_integration/regions_analysis.cluster_regions_2d_rd`

- Single-linkage on centers in **2D**.
- Gap ≈ `max(60, 0.08 × min(page_w, page_h))`.
- Downsamples dense geometry (top 400 longest strokes) for stability.
- Union bbox per cluster → `detail_region_candidate`.

Production code was **not** modified.

---

## 3. Signals used

From the PDF / artifacts only:

- Page width/height  
- Vector object bboxes (`geometry.json`)  
- Engineering token bboxes (`document.json`)  
- Drawing density (item counts)  
- Gaps / separation between candidate region bboxes  
- Heuristic quality flags (title-block / full-page merge risk)

**Not** assumed: every rectangle is a detail border; fixed title-block corner.

---

## 4. Region examples (measured)

From `step3_regions.json`:

| Page | Production X-gap regions | R&D 2D regions |
|------|-------------------------:|---------------:|
| 8 | **1** (flagged near-full-page merge) | **6** |
| 18 | **1** (near-full-page) | **12** |
| 24 | **1** (near-full-page) | **13** |

Production always returned a **single sheet-wide candidate** on these pages — consistent with X-only clustering.

R&D 2D produces multiple candidates, but many are **geometry-only fragments** (0 text) — false-split risk.

Debug overlays: `docs/validation/rd_geometry_integration/renders/p{8,18,24}_regions.png`.

---

## 5. Containment results

R&D regions with both text and geometry exist (examples):

- p18: region with 10 text + 82 geometry; another with 7 text + 20 geometry.  
- p24: region with 12 text + 61 geometry.

These are **promising detail_region_candidates**, not verified details.

---

## 6. Gap / separation results

Neighbor records store `sep_x` / `sep_y` between non-overlapping candidate bboxes.

Useful as evidence of separation; **not** proof of architect-intended detail boundaries (no title callout OCR gating in this prototype).

---

## 7. Cross-detail contamination examples

Probe: unconstrained nearest retrieval vs **same-region constrained** retrieval using R&D 2D regions.

| Page | Region count | Cross-region tops | Blocked by constraint |
|------|-------------:|------------------:|----------------------:|
| 8 | 6 | 0 | 0 |
| **18** | 12 | **2** | **2** |
| 24 | 13 | 0 | 0 |

On **page 18**, unconstrained proximity picked a geometry whose region id ≠ label region in 2 cases; the region constraint **blocked** those tops (examples in `step3_contamination.json`).

On page 24, despite 13 candidates, this short probe did **not** observe cross tops — either labels/geo fell in same candidates, or nearest stroke stayed local. **Sparse evidence**, not a pass.

---

## 8. False-positive cases

- **Production:** 1 region covering nearly the whole page (`near_full_page_false_merge_risk`) — useless as a cross-detail filter.  
- **R&D 2D:** many small geometry-only clusters (false splits / noise).  
- **Header band:** some candidates flagged `top_band_header_risk`.

---

## 9. False-negative cases

- True multi-detail sheets may still be **under-segmented** if whitespace &lt; gap threshold (clusters glue).  
- Detail titles / callout bubbles not used as seeds — regions may omit human-recognized detail frames.  
- Page 24 contamination probe found **0** cross tops — either good locality or insufficient test sensitivity.

---

## 10. Ambiguous cases

- Overlapping candidate bboxes after union.  
- Plan page (p8) also splits into 6 R&D regions — **over-segmentation of a single framing plan** is possible; region constraints on plans may be harmful.

---

## 11. What appears reliable

- **Diagnosis:** production X-gap clustering is **not** sufficient for vertically arranged detail sheets (always 1 region here).  
- **Direction:** 2D spacing can produce **multiple** `detail_region_candidate`s and, on at least one page, **block a few cross-region nearest hits**.  
- Quality flags for full-page / title-band risk are cheap and useful.

---

## 12. What remains unsafe

- Treating R&D clusters as true “details.”  
- Turning on region constraints in production association without GT.  
- Using plan-page 2D splits as hard filters.  
- Ignoring leaders / notes inside clusters.  
- Any path from region geometry → section size completion.

---

## 13. Recommended next experiment

1. **Seed regions from detail titles / view labels** (text patterns like `DETAIL`, `TYP`, sheet callouts) then grow by containment — still R&D.  
2. **Human-mark 2–3 detail frames** on p18/p24; score IoU vs production vs R&D 2D.  
3. Keep region filter **optional evidence** in a future association candidate generator — behind a non-production flag.  
4. Do **not** replace `detail_regions.py` until IoU vs human frames is measured.

---

## Verdict (honest)

**Question:** Can we constrain geometry to the correct drawing/detail region well enough to justify the next association implementation?

**Answer:** **Not yet as a hard constraint.**  

- We **can** show that the **current** production region method **fails** to separate multi-detail sheets (1 region / page).  
- We **can** show a **weak positive**: experimental 2D candidates + same-region filter blocked **2** cross-detail nearest hits on p18.  
- Evidence is **too thin** (and false-split risk too high) to ship region gating into production association.

**Safe next build:** improve **candidate generation** (retrieval + optional soft region features + leader awareness) for review/R&D comparison — not automatic association replacement.
