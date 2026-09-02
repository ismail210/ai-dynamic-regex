# Phase 2 Geometry & Association Report

Same representative pages as Phase 1. Same measurement script (`backend/scripts/measure_phase1_association.py`). No fusion / ranker / GraphSAGE / MobileNet encoding.

Raw Phase 2 JSON: `docs/validation/phase2_association_measurements.json`  
Phase 1 baseline: `docs/validation/phase1_association_measurements.json`

**No section/takeoff accuracy claim.** Counts below are association/geometry/scale/runtime only.

---

## 1. Scope

| Document | Pages (unchanged) |
| --- | --- |
| ST (`uploads/ST.pdf`) | 1, 3, 5, 8 |
| Struct (`uploads/Struct.pdf`) | 1, 3, 5, 8 |
| GCDC (`uploads/GCDC Building 4 - ST1__47dc7ef27f6e.pdf`) | 1, 5, 21, 25 |
| Burrville (`uploads/Burrville ES - ST.pdf`) | 1, 3, 5, 8 |
| K1200 (`uploads/1200 K_Permit_Bid_Dwgs - Structural.pdf`) | 1, 3, 22, 23 |

842 section-like labels in both runs.

---

## 2. Fix A — Geometry Cap

**Change:** keep the 250-per-page bound. Default strategy is now `structural_first`: drop page-frame boxes and specks, then fill the 250 slots with long thin strokes instead of `max(area, perimeter)` (which ranked sheet fills first).

### Before (Phase 1, `length_aware`)

| document | page | raw | dropped | retained |
| --- | ---: | ---: | ---: | ---: |
| ST | 8 | 41,501 | 41,251 | 250 |
| Struct | 8 | 9,227 | 8,977 | 250 |
| GCDC | 21 | 4,016 | 3,766 | 250 |
| Burrville | 8 | 3,586 | 3,336 | 250 |
| K1200 | 22 | 11,260 | 11,010 | 250 |

ST p8 retained kinds (objects after merge): line 40, polyline 16, rectangle 72, leader 60, dimension 36.

### After (`structural_first`)

| document | page | raw | dropped | retained | page-frames excluded |
| --- | ---: | ---: | ---: | ---: | ---: |
| ST | 8 | 41,501 | 41,251 | 250 | 0 |
| Struct | 8 | 9,227 | 8,977 | 250 | 0 |
| GCDC | 21 | 4,016 | 3,766 | 250 | 0 |
| Burrville | 8 | 3,586 | 3,336 | 250 | 1 |
| K1200 | 22 | 11,260 | 11,010 | 250 | 0 |

ST p8 retained kinds: line 39, polyline **68**, rectangle 27, dimension 35, symbol 2.

### Interpretation

The cap **still drops 41,251 / 41,501** drawings on ST p8. Runtime stays bounded (geometry 1.7s → 2.0s on ST). What changed is **which 250 survive**: more polylines (16 → 68), fewer rectangles (72 → 27). That is a recall mix change inside a fixed budget, not a recall of all CAD strokes.

**Not claimed:** “all structural members are now kept.” Most hatch/member fragments are still discarded.

Graph edge count rose on Struct (18,566 → 101,060) and Burrville (22,962 → 56,887) because retained geometry is more linear/connectable. K1200 edges fell (99,884 → 51,870) after huge rectangles stopped dominating association geometry.

---

## 3. Fix B — Dimension Filtering

**Change:** `nearest_geometry_candidates` never offers `geometry_kind=dimension` as a member target. If nothing else is in range, the label is unresolved.

### Before

210 / 842 labels → `dimension`  
Burrville p8: 62 / 81 → dimension, 81 / 81 distance 0

### After

**0 / 842** labels → `dimension`

| document | dimension targets P1 | P2 | orphans P1 | orphans P2 |
| --- | ---: | ---: | ---: | ---: |
| ST | 28 | 0 | 31 | 14 |
| Struct | 31 | 0 | 18 | 1 |
| GCDC | 69 | 0 | 4 | 62 |
| Burrville | 62 | 0 | 0 | **50** |
| K1200 | 20 | 0 | 4 | 4 |
| **Total** | **210** | **0** | **57** | **131** |

### Interpretation

The Burrville pattern is fixed as specified: overlapping dimension geometry no longer wins. **50 Burrville labels are now orphans** — those cases had no remaining structural candidate in radius after dimensions were excluded. That is the intended “unresolved” outcome, not a silent wrong member.

GCDC orphans 4 → 62 for the same reason (69 dimension associations removed).

Remaining associations moved into line/polyline (Struct lines 3 → 46; ST polyline 18 → 58).

---

## 4. Fix C — Huge Rectangle Filtering

**Change:** skip page-spanning boxes (existing `_is_area_shaped`) **and** fat rectangles/paths/symbols with `min_side > 24pt` and `max_side > 8 × association radius`. Small plates stay eligible. Leaders are resolvers, not member targets.

### Before

K1200: **171** rectangle association targets (164 with `target_length > 800`). Example: `HSS6X6X3/8`, leader_resolved, dist 0, length ≈ 3327 pt.

### After

K1200: **0** rectangle targets. Winning kinds: line 220, polyline 20.

All documents:

| document | rectangle targets P1 | P2 | rectangle length>800 P1 | P2 |
| --- | ---: | ---: | ---: | ---: |
| ST | 35 | 29 | 10 | **0** |
| Struct | 16 | 29 | 1 | 12 |
| GCDC | 20 | 8 | 0 | 0 |
| Burrville | 2 | 0 | 0 | 0 |
| K1200 | 171 | **0** | 164 | **0** |

### Interpretation

The Phase 1 K1200 failure is gone. ST huge-rectangle associations (length>800) also went to 0.

Struct rectangle **count** rose (16 → 29) but these are mostly modest plates/symbols still allowed. 12 Struct targets have length>800 **and** kind=rectangle: they are **not** both-fat-and-page-long enough to hit the new strip rule (min side ≤ 24). **Remaining failure:** long thin rectangles can still win.

Legitimate plates: `test_plate_like_rectangle_is_kept` (36×20 rectangle) still associates.

---

## 5. Fix D — Scale / NTS

**Change:** `resolve_page_scale` never copies another page. NTS with no local scale → unknown (`scale_source=nts`). Local title-block scale still wins on a notes page that also says NTS (ST p3, GCDC p5). `page_association_radius` no longer inherits document-level scale.

| Document | Page | Before | After | Source / reason |
| --- | ---: | --- | --- | --- |
| K1200 | 1 | `1"=1'-0"` inherited from p3 | **none** | `nts` |
| ST | 1 | `1/8"=1'-0"` inherited from p3 | **none** | `unknown` |
| Struct | 1 | `SCALE:1/8"=1'-0"` inherited | **none** | `unknown` |
| GCDC | 1 | `1/8"=1'-0"` inherited from p5 | **none** | `unknown` |
| Burrville | 1, 3 | inherited from p2 | **none** | `unknown` |
| ST | 3 | `1/8"=1'-0"` (page also NTS) | `1/8"=1'-0"` | `page_scale` + `is_nts=true` |
| K1200 | 22, 23 | `1/8"` | `1/8"` | `page_scale` |

Association radius on unknown/NTS pages is the historical **160 pt** default, not another sheet’s scale.

---

## 6. Overall Before/After

| Metric | Phase 1 | Phase 2 | Change |
| --- | ---: | ---: | --- |
| Dimension targets | 210 | 0 | −210 |
| K1200 rectangle targets | 171 | 0 | −171 |
| K1200 rectangle length>800 | 164 | 0 | −164 |
| Orphan labels | 57 | 131 | +74 (mostly former dimension-only) |
| Cross-region associations | 0 | 0 | none |
| NTS fallback (K1200 p1) | inherited `1"` | unknown / nts | fixed |
| ST p8 drawings dropped | 41,251 | 41,251 | cap size unchanged |
| ST p8 polylines retained (objects) | 16 | 68 | mix improved |
| Sampled-path extract+geom+graph (ST) | 10.3+1.7+0.3 s | 9.6+2.0+0.3 s | similar |
| Struct graph edges | 18,566 | 101,060 | denser linear graph |
| Full Analyze prediction time | not measured this run | not measured this run | — |

Heuristic class `G_dimension_target`: 210 → **0**.  
`D_leader_or_hatch`: 245 → 66 (remaining filled/small rectangles, not the 3327 pt K1200 case).

---

## 7. Regression Tests

| File | Result |
| --- | --- |
| `tests/test_dense_page_geometry_cap.py` (incl. page-frame vs long lines) | pass |
| `tests/test_association_target_filters.py` (dimension + huge rect / plate / unresolved) | pass |
| `tests/test_spatial_index.py` (leader is not a member target) | pass |
| `tests/test_drawing_scale_and_regions.py` (NTS inherit, local NTS+scale, no document leak) | pass |
| Backend suite excluding TestClient/httpx gaps | **675 passed**, 1 skipped |

---

## 8. Remaining Failures (observed after fixes)

1. **Cap still discards ~99% of ST p8 drawings** (41,251 dropped). Structural mix inside 250 is better; total recall is not.
2. **Orphans increased** (57 → 131), concentrated on Burrville (50) and GCDC (62) where the previous “winner” was a dimension.
3. **Struct still associates some long rectangles** (12 with length>800). Filter requires a fat min-side; thin sheet strips can pass.
4. **66 `D_leader_or_hatch` heuristic hits remain** (filled rectangles that are plate-sized or not oversized).
5. **Struct graph pairwise edges grew ~5×** (18k → 101k); graph_ms 0.4s → 1.9s on that sample.
6. **Legend/notes callouts** (ST p3 `W16x26` typical) were not in this Phase 2 scope.

---

## 9. Recommended Next Step

**Phase 3 gold set on these same pages**, especially Burrville p8 orphans and K1200 line associations, so we can score association correctness — not another cap increase. Raising 250 → N without labels would trade memory/edges (already 101k on Struct) for unmeasured recall.

If engineering continues before gold labels: tighten long-thin rectangle furniture (Struct length>800) using page coverage, not a global cap bump.
