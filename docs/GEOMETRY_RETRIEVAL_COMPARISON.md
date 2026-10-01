# Geometry Retrieval Comparison (R&D — Step 2)

**Status:** Controlled prototype — **not** production association.  
**Date:** 2026-09-17  
**Harness:** `backend/scripts/rd_geometry_integration/`  
**Outputs:** `docs/validation/rd_geometry_integration/`

---

## 1. Existing geometry capabilities (audit)

| Capability | Location | Reused? |
|------------|----------|---------|
| PDF vector drawings via `page.get_drawings()` | `services/engineering/geometry_extractor.py` | Yes (via artifacts) |
| Geometry adapter / document dict | `services/engineering/geometry_adapters.py` | Yes |
| Collinear fragment merge | `services/engineering/geometry_normalizer.py` | Indirect (in artifacts) |
| Text words/dict/spans/bbox/rotation | `services/pdf_parser.py` | Yes (document.json) |
| Production nearest association | `graph_builder` + `spatial_index.nearest_geometry_candidates` → `nearest_geometry` edges | Comparison baseline |
| Detail region X-gap clustering | `services/engineering/detail_regions.py` | Audited; insufficient alone for vertical details |
| Semantic `GeometryEvidence` / associations | `services/semantic/models.py`, `GEOMETRY_EVIDENCE_CONTRACT.md` | Contract reference only |
| `geometry_preview` on predictions | multimodal feature providers | Not required for this harness |
| ML association / GraphSAGE / XGB | `services/ml_association` (shadow; **not wired**) | **Not used** |

**Artifact source:** `backend/training/engineering_artifacts/doc_0d910a43b4a021e3/multimodal/`  
(`document.json`, `geometry.json`, `graph.json` for Burrville ES - ST).

No duplicate extractor was written. Retrieval scores existing geometry objects.

---

## 2. Existing association outputs available for comparison

From `graph.json`:

- Edges with `relationship == "nearest_geometry"` (text node → geometry node).
- Meta may include `leader_resolved`, `association_sources`, `candidate_count`.
- Geometry nodes expose `source_id` / kind / bbox for alignment with `geometry.json` objects.

Production still collapses to **one** nearest edge per label. This harness compares that single target to a **top‑K retrieval list**.

---

## 3. New retrieval representation

Each candidate (R&D contract):

| Field | Meaning |
|-------|---------|
| `geometry_id` | Stable id from production geometry object |
| `page_number` | Same-page only |
| `geometry_kind` | Raw PDF kind (`line`, `polyline`, `leader`, …) |
| `geometry_role` | Always **`unknown`** in this prototype |
| `bbox`, `center` | From artifact |
| `orientation`, `length` | When present on object |
| `source_primitive` | layer / region_id / source_format |
| distances / overlap / iou | Retrieval features |
| `evidence_status` | `candidate` / `retrieved` |

**Explicitly not done:** promoting `line` → `beam` / `column` / `brace` because a W‑label is nearby.

---

## 4. Retrieval features investigated

Deterministic features (no ML):

1. Same-page constraint  
2. Center-to-center distance  
3. Point-to-bbox distance  
4. Bbox intersection / IoU  
5. Orientation delta (when both sides have orientation)  
6. Local top‑K neighborhood (default K=5, max bbox distance 150 pt)  
7. Optional same-region filter (used in Step 3)

**No winner chosen.** Ranking for the harness uses `(bbox_distance, center_distance, −iou)`.

---

## 5. Golden pages

| Page | Role | Why selected |
|------|------|----------------|
| **8** | Structural plan | Burrville framing plan already used in `docs/validation` phase1/phase2 association samples; dense W labels. |
| **18** | Detail sheet | S‑205 incomplete‑L evidence page; brace / L4X4\* details. |
| **24** | Dense detail sheet | S‑321 roof details; many L4X4\* callouts. |

Source PDF: `backend/uploads/Burrville ES - ST.pdf` (`doc_0d910a43b4a021e3`).  
**Not** a full-corpus run.

---

## 6. Comparison results (summary)

From `docs/validation/rd_geometry_integration/step2_summary.json` (75 sectionish labels):

| Status | Count | Meaning |
|--------|------:|---------|
| agreement (+ agreement with crowded neighborhood) | **47** | Production `nearest_geometry` target appears in new top‑K |
| disagreement | **8** | Production target not in new top‑K |
| ambiguous (incl. near-ties) | **34** | Crowded neighborhood or unclear sole match |
| extra_candidates_only | **9** | Retrieval found candidates; no `nearest_geometry` edge matched that token |
| missing_retrieval | **0** | — |
| unavailable | **0** | — |

Page 8 alone: 39/50 agreement-family, 7 disagreement.

Raw rows: `step2_rows.jsonl`.

---

## 7. Agreement cases

Example (page 8, `W21X44` / `token_p8_427`):

- Production: `nearest_geometry` → `geom_edbfa26d671d` (`line`, leader-resolved meta).
- New top‑1: same `geometry_id`, `bbox_distance=0`, overlap &gt; 0.
- Role still **`unknown`** — evidence only.

These cases show **PDF geometry retrieval can recover the same object id** the current graph already chose, without inventing member semantics.

---

## 8. Disagreement cases

Eight labels where production’s chosen geometry id was **not** in the new top‑K.

Likely drivers (descriptive, not ranked as “bugs”):

- Production uses **leader-endpoint resolution**; simple bbox proximity may prefer the leader stroke or a different nearby line.
- Dense framing: many overlapping long lines under one label.
- Token↔edge join misses when text node `source_id` mapping fails → counted as `extra_candidates_only` instead.

**Do not** treat disagreement as “new method is better” without human ground truth.

---

## 9. Ambiguous cases

High rate of **near-ties** (second candidate within ~8 pt of top). On plans, several members sit inside overlapping stroke neighborhoods.

Retrieval can **surface candidates**; it cannot safely pick a single member without additional evidence (leader, region, human, or verified GT).

---

## 10. Failure / limitation cases

- **Leaders:** ~half of Burrville geometry objects are classified `leader`; raw nearest-bbox without leader logic is unsafe as a sole association.
- **No semantic role:** kind=`line` must not become beam/column.
- **No completion:** retrieval must never fill `L4X4` → `L4X4X1/4`.
- **Artifact dependency:** harness reads existing multimodal outputs; it does not prove live extract parity on every PDF.
- **ID join:** comparison quality depends on aligning graph `source_id` with `token_id` / `geometry_id`.

---

## 11. What geometry retrieval can safely provide

- Same-page **candidate shortlists** for a label bbox.  
- Deterministic **distance / overlap / orientation** features for later ranking or review UI.  
- A **comparison mirror** against production `nearest_geometry` for R&D.  
- Evidence that many plan labels already agree with production’s chosen stroke id.

---

## 12. What it cannot safely provide

- Authoritative member type (beam/column/brace).  
- Ground-truth association without human labels.  
- Guaranteed leader→member resolution (needs explicit leader logic — already partially in production `spatial_index`).  
- Replacement for GHX / Grasshopper geometry.  
- Any change to steel section text / completion.

---

## 13. Recommended next experiment

1. Keep retrieval as **candidate generation only**.  
2. Add a **leader-aware retrieval branch** that mirrors (but does not replace) `spatial_index` leader resolution — still R&D.  
3. Combine with **Step 3 region constraints** once regions are trustworthy on detail sheets.  
4. Human-label a **tiny** set (tens of labels on p8 + p18) before any “accuracy %” claim.  
5. Mike continues Step 1 (corrected PDF → converter stream) in parallel — out of scope here.

---

## Verdict (honest)

**Partially yes:** PDF geometry objects + simple proximity features are sufficient to **retrieve shortlists** that often **agree** with current `nearest_geometry` on a Burrville plan page.

**Not yet:** reliable enough to **replace** or auto-trust as association. Ambiguity and leader cases remain first-class failure modes. Next association work should consume candidates + regions + leader logic — not nearest-bbox alone.
