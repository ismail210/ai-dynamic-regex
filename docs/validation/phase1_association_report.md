# Phase 1 — Association measurement on real sheets

**Status:** STOP at Phase 1 gate. No Phase 2 code changes.

**How measured:** `backend/scripts/measure_phase1_association.py` calls the live extract → geometry → detail-region → graph path. Fusion, GraphSAGE, MobileNet encoding, and the XGB ranker were not run. Geometry was extracted only for sampled pages (existing `extract_geometry` skip when a page has no engineering tokens).

**Raw numbers:** `docs/validation/phase1_association_measurements.json`  
**Crops:** `docs/validation/phase1_samples/<doc>/`

Heuristic association classes are **not** human A–G labels. Visual review covers the 30 crops plus the sidecar JSON. Counts below are from execution unless marked otherwise.

---

## Files inspected (existing entry points)

| Concern | File | Functions |
| --- | --- | --- |
| Analyze orchestration | `backend/services/multimodal/pipeline.py` | `run_multimodal_pipeline` |
| Staged API Analyze | `backend/services/staged_pipeline.py` | `run_extraction_stage`, `run_analysis_stage` |
| Text / OCR / tokens | `backend/services/extraction_engine.py` | `extract_engineering_document` |
| Geometry | `backend/services/engineering/geometry_extractor.py` | `extract_geometry` (dense cap 250, then merge) |
| Geometry adapter | `backend/services/engineering/geometry_adapters.py` | `extract_geometry_document` |
| Scale | `backend/services/engineering/drawing_scale.py` | `detect_page_scales`, `detect_drawing_scale`, `page_association_radius` |
| Detail regions | `backend/services/engineering/detail_regions.py` | `assign_detail_regions`, `cluster_page_regions` |
| Fragment merge | `backend/services/engineering/geometry_normalizer.py` | `merge_collinear_fragments` |
| Graph / nearest member | `backend/services/engineering/graph_builder.py` | `build_graph` (`nearest_geometry` via STRtree) |
| Leader-aware candidates | `backend/services/engineering/spatial_index.py` | `nearest_geometry_candidates` |
| Spatial tokens | `backend/services/multimodal/spatial_association.py` | `build_spatial_association_tokens` |
| Context / leaders | `backend/services/annotation/context_evidence.py` | `build_context_evidence` |
| Section eval (token→class only) | `backend/scripts/evaluate_pipeline.py` | holdout on `approved_dataset.csv` |

**Data flow used for measurement**

```
PDF → extract_engineering_document
    → detect_page_scales / detect_drawing_scale  (full document)
    → extract_geometry_document (tokens filtered to sample pages)
    → assign_detail_regions
    → build_graph  (nearest_geometry edges = production association)
```

---

## Dataset

| Document | PDF | Total pages | Pages analyzed | Notes |
| --- | --- | ---: | --- | --- |
| ST | `uploads/ST.pdf` | 23 | 1, 3, 5, 8 | Page 8 is a dense framing sheet |
| Struct | `uploads/Struct.pdf` | 24 | 1, 3, 5, 8 | Labels concentrated on page 8 |
| GCDC | `uploads/GCDC Building 4 - ST1__47dc7ef27f6e.pdf` | 81 | 1, 5, 21, 25 | 45MB. First sample (p3/p10) had almost no section labels; replaced with p21/p25 after a token histogram |
| Burrville | `uploads/Burrville ES - ST.pdf` | 29 | 1, 3, 5, 8 | Labels on page 8 |
| K1200 | `uploads/1200 K_Permit_Bid_Dwgs - Structural.pdf` | 39 | 1, 3, 22, 23 | Additional dense permit set. Early pages are not framing; p22 has 169 section labels |

Burrville was available. Springhill exists only as a hashed copy and was not required once K1200 was included.

---

## Scale findings

| document | page | scale_value | scale_source | nts | on this page | fallback | other-page leak possible |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| ST | 1 | `1/8" = 1'-0"` | `document_fallback:title_block` | false | no | **yes** | **yes** (from p3) |
| ST | 3 | `1/8" = 1'-0"` | title_block | **true** | yes | no | no |
| ST | 5 | `3/64" = 1'-0"` | title_block | false | yes | no | no |
| ST | 8 | `SCALE 3/32" = 1'-0"` | title_block | false | yes | no | no |
| Struct | 1 | `SCALE:1/8" = 1'-0"` | fallback p3 | false | no | **yes** | **yes** |
| Struct | 3,5,8 | `SCALE:1/8" = 1'-0"` | title_block | false | yes | no | no |
| GCDC | 1 | `1/8" = 1'-0"` | fallback p5 | false | no | **yes** | **yes** (no tokens/geometry) |
| GCDC | 5 | `1/8" = 1'-0"` | title_block | **true** | yes | no | no |
| GCDC | 21,25 | `1/8" = 1'-0"` | title_block | false | yes | no | no |
| Burrville | 1,3 | `1/8" = 1'` | fallback p2 | false | no | **yes** | **yes** |
| Burrville | 5,8 | `SCALE: 1/8" = 1'-0"` | title_block | false | yes | no | no |
| K1200 | 1 | `1" = 1'-0"` | fallback p3 | **true** | no | **yes** | **yes** |
| K1200 | 3 | `1" = 1'-0"` | title_block | false | yes | no | no |
| K1200 | 22,23 | `SCALE: 1/8" = 1'-0"` | title_block | false | yes | no | no |

**OBSERVED**

- Per-page scale **does** work on later framing sheets (ST p8 is 3/32", not the p3 1/8").
- Page 1 never had its own scale on these five PDFs. Document fallback copies a later title-block scale. That is a real leak **risk**, especially K1200 p1 (`NTS` on the page, fallback is `1"=1'-0"` from p3 while framing sheets are `1/8"`).
- `NTS` can coexist with a parsed architectural scale on the same page (ST p3, GCDC p5). Current parser only ignores NTS when **no** `X" = Y'` is in the same blob.
- ST p5 has a detected scale but **zero geometry**: no engineering tokens, so `extract_geometry` skips the page.

**NOT YET VERIFIED:** whether applying p3’s scale to p1 changes any takeoff length (p1 had 0 section labels on ST/Struct/GCDC/Burrville).

---

## Region findings

| document | page | regions | section labels | geometry | coverage | orphan labels | orphan geometry |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ST | 8 | 1 | 117 | 228 | 1.0 | 0 | 0 |
| Struct | 8 | 2 | 76 | 249 | 1.0 | 0 | 0 |
| GCDC | 21 | 2 | 160 | 198 | 1.0 | 0 | 0 |
| GCDC | 25 | 1 | 147 | 220 | 1.0 | 0 | 0 |
| Burrville | 8 | 1 | 81 | 233 | 1.0 | 0 | 0 |
| K1200 | 22 | 3 | 169 | 243 | 1.0 | 0 | 0 |

**OBSERVED:** `region_coverage = 1.0` whenever items exist. Clustering assigns every token/object to some region. It does **not** mean details are split correctly. Dense framing sheets are often a **single page-wide region**.

**Cross-region association count: 0 / 842** sampled section labels (`cross_region` on `nearest_geometry` edges).

**NOT OBSERVED:** labels in region A linked to geometry in region B. That failure mode cannot fire if the page is one region.

---

## Merge findings

Measured **after** the dense-page cap (merge never sees dropped drawings).

| document | input fragments (sampled pages) | output objects | clusters merged | fragments consumed | short leftover `<12pt` | suspicious leader/dimension merge |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ST | 641 | 588 | 32 | 85 | 0 | 0 |
| Struct | 1000 | 995 | 5 | 10 | 0 | 0 |
| GCDC | 750 | 667 | 45 | 128 | 0 | 0 |
| Burrville | 750 | 720 | 23 | 53 | 0 | 0 |
| K1200 | 1000 | 975 | 21 | 46 | **89** (page 3 only) | 0 |

**OBSERVED:** merge runs and is conservative. No measured merge of `leader`/`dimension` kinds into a member (`suspicious_merges = 0`).

**NOT OBSERVED (on remaining objects):** over-merge of leaders into members.

**NOT YET VERIFIED visually:** whether the 32 ST merges are the correct physical members. Under-merge is likely **because the cap already threw away fragments**, not because the merge gap is wrong.

---

## Association findings

**842** section-like labels on sampled pages. Production pick = first `nearest_geometry` graph edge.

### Heuristic counts (machine, complete)

| Class | Count | Meaning in this script |
| --- | ---: | --- |
| ASSOCIATED_UNVERIFIED | 321 | Has a non-dimension, non-filled target; not classified further |
| D_leader_or_hatch | 245 | Target `kind` leader **or** filled path/rectangle |
| G_dimension_target | 210 | Target `kind == dimension` |
| F_orphan | 57 | No `nearest_geometry` edge |
| E_parallel_candidate | 9 | Nearby similar-orientation member and not leader-resolved |
| C_cross_detail | 0 | Different `region_id` |

`leader_resolved` on the winning edge: ST 22, Struct 27, GCDC 5, Burrville **58**, K1200 **239**.

Distance **0.0** (label center inside target bbox): Burrville **81/81**, K1200 **230/244**, GCDC 79/317.

Target kinds among associated labels:

| Target kind | ST | Struct | GCDC | Burrville | K1200 |
| --- | ---: | ---: | ---: | ---: | ---: |
| rectangle | 35 | 16 | 20 | 2 | **171** |
| dimension | 28 | 31 | 69 | **62** | 20 |
| polyline | 18 | 0 | **144** | 5 | 0 |
| line | 10 | 3 | 1 | 12 | 16 |
| symbol | 1 | 0 | 79 | 0 | 19 |
| leader | 1 | 0 | 0 | 0 | 0 |
| arc | 0 | 8 | 0 | 0 | 13 |

### Visual sample (crops — not the full 842)

| Example | Heuristic | Visual |
| --- | --- | --- |
| ST p3 `W16x26` on a **notes diagram** (“BEAM SIZE” / NON-COMPOSITE BEAM) | D, filled rectangle, dist 0 | **G other / legend** — not a framing member |
| ST p8 many parallel `W18x46` / `HSS8x8` | E | **E plausible** — parallel members; pick is unverified |
| Burrville p8 `W21X44` | G dimension, dist 0 | **G confirmed pattern** — label bbox sits on classified dimension geometry |
| K1200 p22 `HSS6X6X3/8` | D, filled **rectangle**, dist 0, `leader_resolved`, target length **3327 pt** | **D** — leader resolved onto a huge filled rectangle (sheet furniture / border), not a 6×6 post |
| GCDC p21 `W10x22` | ASSOCIATED_UNVERIFIED, polyline 2139 pt | **A plausible** — label sits on a beam in a bay; not proven to be the exact object |
| Struct p8 `HSS12x8x1/2` | D | **B or D** — vertical HSS among parallel HSS; filled-target heuristic, member identity unverified |

Human A–G for the **full** 842 is **NOT YET VERIFIED**. Do not treat heuristic 245 as “245 hatch errors.”

---

## Dense-page cap (measured here, not a guess)

Cap threshold = 250 drawings/page (`geometry_extractor.py`).

| document | page | raw drawings | dropped by cap | retained ~objects |
| --- | ---: | ---: | ---: | ---: |
| ST | 3 | 5,381 | 5,131 | 236 |
| ST | 8 | **41,501** | **41,251** | 228 |
| Struct | 8 | 9,227 | 8,977 | 249 |
| GCDC | 21 | 4,016 | 3,766 | 198 |
| Burrville | 8 | 3,586 | 3,336 | 233 |
| K1200 | 22 | 11,260 | 11,010 | 243 |

**OBSERVED:** every dense framing page in this sample hits the cap. ST p8 keeps ~0.6% of drawings. Merge and association only see the survivors. This is the strongest geometry failure in the sample.

Whether the 250 keepers are the structural members vs hatch is **NOT YET VERIFIED** object-by-object; the volume dropped is measured.

---

## Performance findings

Sampled-page path (not full Analyze). Prediction / validation **not run** in this script.

| document | extract_ms | scale_ms | geometry_ms | regions_ms | graph_ms | graph nodes | graph edges |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ST | 10,250 | 237 | 1,746 | 109 | 329 | 717 | 9,992 |
| Struct | 16,976 | 356 | 1,770 | 198 | 436 | 1,121 | 18,566 |
| GCDC | 31,596 | 650 | 2,036 | 191 | 352 | 1,001 | 14,476 |
| Burrville | 13,038 | 298 | 738 | 126 | 556 | 819 | 22,962 |
| K1200 | 18,390 | 252 | 1,853 | 207 | **3,421** | 1,228 | **99,884** |

**OBSERVED**

- Text extraction dominates this measurement (10–32s), because scale provenance needs the **full** PDF.
- Geometry on 4 pages is ~0.7–2.0s.
- Graph time jumps with edge count (K1200 ~100k edges / 3.4s).

**Prior full Analyze (ST, all pages, after MobileNet gate, persist=false):** wall **61.4s**, 633 predictions. Geometry encoding skipped. That run is **not** this sample.

**NOT MEASURED here:** fusion `prediction_ms`, validation, OCR-vs-annotation split inside extract.

---

## Top failure modes

Ranked by **measured frequency or measured drop volume**, not by speculation.

| Rank | Failure mode | Evidence | Severity | Example |
| ---: | --- | --- | --- | --- |
| 1 | Dense-page cap discards almost all CAD strokes on plan sheets | ST p8: 41,251 / 41,501 dropped; all five docs cap on plan pages | **high** | ST p8, K1200 p22 |
| 2 | Label associated to `dimension` geometry | 210 / 842 heuristic; Burrville 62/81 and **81/81 dist=0** | **high** | Burrville p8 `W21X44` → `geom_9fef0becefac` kind=dimension |
| 3 | Label / leader associated to large filled rectangle | K1200 171 rectangle targets; one crop target length 3327 pt, dist 0, leader_resolved | **high** | K1200 p22 `HSS6X6X3/8` |
| 4 | Page-1 (and other no-scale pages) inherit another page’s title-block scale; NTS not blocking that fallback | 5/5 docs; K1200 p1 is NTS + `1"` fallback vs later `1/8"` | **medium** (high if lengths are computed on those pages) | K1200 p1 |
| 5 | Orphan section labels (no nearest_geometry) | 57 / 842; ST 31/124 | **medium** | ST sampled pages |
| 6 | Detail clustering is too coarse (often 1 region / sheet) | coverage 1.0; **0** cross-region errors | **medium** (hides C) | ST p8, Burrville p8 |
| 7 | Legend/notes section callouts treated like members | visual ST p3 `W16x26` on “BEAM SIZE” typical | **medium** | ST p3 |

---

## Which failures justify Phase 2 engineering

Frequent enough in **this** sample:

1. Dense-page cap on real plan sheets (measured drop counts).
2. Prefer structural line/polyline over `dimension` and over page-sized filled rectangles (measured target-kind + visual).
3. Scale fallback policy for pages with no local scale / with NTS (measured provenance).

**Do not** start with: retuning fragment-merge gap, or “cross-detail association,” until regions actually split details.

---

## NOT OBSERVED

- Cross-detail (`C`) associations: **0**.
- Merge of leader/dimension kinds into members: **0** (`suspicious_merges`).
- Short leftover strokes on plan pages (only K1200 p3, a `1"` scale sheet).
- MobileNet encoding cost (gated / not invoked).
- Ranker / VLM effects (not run).

---

## Phase 3 (started as inspection only — gold set **not** created)

Existing human review store `approved_dataset.csv` columns: `token, class, category, source, approved_at, unknown_id, ranking_score, correct, eval_split`.

**Missing** vs required record: `document_id`, `page_number`, `label_bbox`, `expected_member` / `geometry_id`, `member_role`, `region_id`, `scale_*`, `association_correct`, `length_correct`.

`evaluate_pipeline.py` scores **token → class** (and extraction/review/confidence). It does **not** score association or length.

Historical **~26% top-1** (`docs/accuracy_work/phase1_correctness_report.md`, `evaluate_pipeline.py` on approved CSV, 85 holdout / 960 train rows) remains a **section-only, leakage-sensitive** baseline. It is **not** this Phase 1 association measurement and is **not** replaced by the 842-label heuristic table.

---

## Phase 1 gate answers

1. **Files inspected:** table above.
2. **Measurements:** JSON + tables in this report (executed 2026-09-02).
3. **Top real failure modes:** cap; dimension targets; filled-rectangle / leader targets; scale fallback + NTS; orphans; coarse regions.
4. **Drawing examples:** ST p8 cap; Burrville `W21X44`; K1200 `HSS6X6X3/8` rectangle 3327 pt; ST p3 legend `W16x26`.
5. **Justify engineering:** (1)(2)(3) above.
6. **Not observed:** cross-region links; leader-into-member merge.

**NEXT STEP (Phase 2, not started):** only after you accept this report — cap / association target filtering / scale fallback, with regression tests and a re-run of **these same pages**.

**NOT YET VERIFIED:** full Analyze prediction time on GCDC; human A–G for all 842 labels; takeoff length accuracy.
