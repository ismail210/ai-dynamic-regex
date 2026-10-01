# Burrville Geometry Human Gold Review

**Project:** Burrville ES - ST (`doc_0d910a43b4a021e3`)  
**Reviewer:** `human_gold_rd`  
**Date:** 2026-09-17  
**Status:** First human-gold set. R&D-only. Production association, GHX, Semantic Review, takeoff, ML, and VLM were not changed.

Gold records: [`review_kit/gold_outcomes.jsonl`](review_kit/gold_outcomes.jsonl)  
Per-group copies: [`review_kit/decisions/`](review_kit/decisions/)  
Machine summary: [`review_kit/gold_metrics.json`](review_kit/gold_metrics.json)

## 1. Review scope

| Item | Value |
|------|--------|
| Labels reviewed | **75 / 75** |
| Document | Burrville ES - ST, `doc_0d910a43b4a021e3` |
| Pages | p8 framing plan (50) · p18 S-205 details (14) · p24 S-321 sections (11) |
| Evidence | Isolated `renders/assoc_token_*.png` crops (all 75 present), Review Kit pages, G1 candidate lists, production `nearest_geometry` as **reference only** |

Artifacts inspected (not treated as ground truth): `comparison.html`, `review_kit/index.html`, `golden_pages.json`, `g1_rows.jsonl` / `step2_rows.jsonl`, `step2_summary.json`, `step3_regions.json`, `step3_contamination.json`, `docs/GEOMETRY_PHASE_CHARTER.md`, `docs/GEOMETRY_PHASE_G1_RESULTS.md`, `backend/scripts/rd_geometry_integration/retrieval.py`, `compare.py`.

Kit schema used (extended, not replaced):

- `review_label`: `direct_target` | `no_valid_target` | `ambiguous_requires_adjudication` | `unavailable`
- `reviewed_target_geometry_ids` / `selected_geometry_id` only when associated
- Extra R&D fields: `decision`, `reason`, `error_bucket`, `leader_required`, `candidate_geometry_ids`, `production_geometry_id`

`unavailable` was added to the Review Kit form because the original select list could not record insufficient-evidence cases. Existing `gold_outcomes.jsonl` is no longer wiped when the kit is regenerated.

G1/G4 agreement and the production pick were **not** used as correctness.

## 2. Human decision counts

| Decision | Count | Kit `review_label` |
|----------|------:|--------------------|
| Associated | **8** | `direct_target` |
| Ambiguous | **2** | `ambiguous_requires_adjudication` |
| No valid member | **65** | `no_valid_target` |
| Unavailable | **0** | `unavailable` |
| **Total** | **75** | |

No duplicate token IDs. Every associated record has exactly one selected geometry that exists in that label’s R&D candidate list. Ambiguous and no-valid-member records have empty target lists.

Of the 65 no-valid-member labels:

| Subset | Count |
|--------|------:|
| Visible member on the drawing, but that geometry is not in the candidate set | **58** |
| Schedule/table text with no member to associate (p18 splice table) | **7** |

## 3. Candidate recall

**Population:** the 8 human-associated labels only.  
Ambiguous, unavailable, and no-valid-member labels are **excluded** from the denominator.

| Metric | Hits / N | Rate |
|--------|----------|------|
| Recall@1 | 8 / 8 | **1.00** |
| Recall@3 | 8 / 8 | **1.00** |
| Recall@5 | 8 / 8 | **1.00** |

Recall@K = share of human-associated labels whose selected geometry appears in the R&D top-K candidate list.

This measures **ranking given that a human-usable candidate was retrieved**. It does **not** measure retrieval coverage. Coverage is the 58 visible-member misses in §9.

## 4. Production vs human gold

Production `nearest_geometry` is a **reference**, not ground truth.

Among the 8 human-associated labels, production’s geometry id matches gold on **6 / 8 (0.75)**.

| Token | Text | Gold geometry | Production match |
|-------|------|---------------|------------------|
| `token_p8_340` | W21X44 | `geom_095898d74240` | yes |
| `token_p8_397` | W12X19 | `geom_90463060295d` | yes |
| `token_p8_398` | W12X16 | `geom_485e0c733148` | yes |
| `token_p8_421` | W14X22 | `geom_5f6b0423ca08` | yes |
| `token_p8_427` | W21X44 | `geom_edbfa26d671d` | yes |
| `token_p8_432` | W16X26 | `geom_edbfa26d671d` | yes (same extracted wall stroke as p8_427) |
| `token_p8_395` | W16X31 | `geom_cf1c1b4a4515` | **no** — production is giant polyline `geom_3e2826b140f9` |
| `token_p8_396` | W16X31 | `geom_0b5ef1f9c497` | **no** — production is the same giant polyline |

On the other 67 labels, production cannot be scored as correct: 65 have no valid member in the candidate set (or are schedule text), and 2 are abstentions.

The three G1 **disagreement** labels (`token_p8_348` W30X90, `token_p8_353` W18X35, `token_p8_372` W10X15) are all human **no_valid_member**. Production and R&D select different wrong/neighbor/giant-polyline geometry; the member the label sits on is in neither pick.

G1 “agreement” was frequently agreement on a **giant bay polyline** or a nearby wall/infill, not on the labeled member.

## 5. R&D vs human gold

Among the 8 human-associated labels:

| Metric | Result |
|--------|--------|
| R&D top-1 = gold | **8 / 8** |
| Recall@3 | **8 / 8** |
| Recall@5 | **8 / 8** |

This is not a claim that R&D association is generally more accurate than production. The associated population is 8 labels on p8 where a compact member stroke was retrieved (wall beams, EJ wall lines, small infills). On the remaining 67 labels R&D did not present a human-selectable member.

## 6. Error buckets

Buckets describe the **drawing/review** failure, not a production-vs-R&D winner. A case may involve more than one mechanism; one primary bucket is stored per record.

| Bucket | Count | What it means |
|--------|------:|----------------|
| `missing_retrieval` | 42 | Member (or plate/angle/brace) is visible; none of the candidates is that geometry |
| `parallel_member_confusion` | 16 | Same retrieval miss, in a dense parallel-joist bay (overlay lands on wall / neighbor / giant polyline) |
| `schedule_table_not_member` | 7 | p18 splice-schedule cells; no member exists to associate |
| `crowded_neighborhood` | 2 | Drawing itself does not uniquely identify one member |
| Leader selected as member | **0** | No gold record treats a leader stroke as the structural member |

Representative examples:

- **Missing retrieval / nearest-distance:** `token_p8_348` W30X90 sits on the diagonal girder; green is the S-311 box; production is polyline `geom_59a6f49b264f` covering the bay.
- **Parallel joists:** `token_p8_381` / `token_p8_430` / `token_p8_431` W18X35 labels sit on distinct joists; overlays follow the W21X44 wall beam.
- **Leader / detail:** `token_p18_1186` WT7X19 leader points to the WT under the beam; green is the W-beam top flange.
- **Leader / detail:** `token_p24_1360` L4x4x3/8 CONT leader points to the small roof/wall angle; green is the long wall face.
- **Schedule:** `token_p18_1143`–`token_p18_1151` are STEEL COLUMN SPLICE table rows.
- **Crowded:** `token_p8_367` opening/stair/infill node; `token_p8_424` wall-kink W16X26[20] vs adjacent infill.

Production/reference mismatch on associated gold: `token_p8_395`, `token_p8_396` (see §4).

## 7. Leader analysis

| Fact | Count |
|------|------:|
| Associated labels that required leader evidence | **0 / 8** (all direct: label on member on p8) |
| No-valid-member labels whose correct member is indicated by a leader | **18** (7 on p18 details + 11 on p24) |
| Gold records that select a leader as the structural member | **0** |

On p18/p24 the drawing association is typically **leader → small angle / plate / brace / WT**. Retrieval returned wall faces, hatch, dimension boxes, joist webs, or nothing (`token_p18_1178` has n=0). The leader is evidence of association, not the member.

## 8. Detail-page observations

**p18 (S-205):** 0 associated. 7 splice-table W labels are not member callouts. Remaining 7 are leader callouts (plates, L4X4X1/4 braces, WT7X19) whose targets are missing or replaced by nearby non-members.

**p24 (S-321):** 0 associated. All 11 L-section labels are leader callouts to small clip/hanger/DSA angles. Overlays consistently land on long wall/hatch/joist-web primitives.

Title-seeded region frames were visible on the region renders; they were **not** used as a hard association gate and are not claimed production-ready.

## 9. Missing retrieval

**58** labels have a visible structural member (or plate/angle/brace) on the drawing whose geometry is **absent from the R&D candidate set**. These are retrieval failures, not ranking failures.

They are **not** counted in Recall@K.

Breakdown:

| Page | Visible-member misses | Typical missed object |
|------|----------------------:|------------------------|
| p8 | 40 | Joist-scale lines, girders (W30X90, W21X50, W21X44[30]), short W10X15 infill joists, opening frames |
| p18 | 7 | Splice plate, cap plates, embed plate, L-brace, WT |
| p24 | 11 | Small L clips / hangers / DSA angles |

`token_p8_355` W10X15: **zero** R&D candidates (G1 status `missing_retrieval`).

A recurring p8 mechanism: production and R&D bbox-overlap a **giant bay polyline** (`geom_59a6f49b264f`, `geom_3e2826b140f9`, …). Those polylines were **not** accepted as the labeled member.

`token_p8_427` and `token_p8_432` share one extracted wall stroke (`geom_edbfa26d671d`) for collinear W21X44[50] then W16X26[18]. Gold associates both labels to that existing primitive; it does not invent a split.

## 10. Ambiguity

Abstention is preserved.

| Token | Text | Why abstain |
|-------|------|-------------|
| `token_p8_367` | W14X22 | Opening / stair / W12X16 infill node; overlay is the neighboring infill |
| `token_p8_424` | W16X26 | Wall-kink label could be the wall beam or the adjacent small infill |

These are drawing-limited, not “pick the nearest line.”

Unavailable = 0 because every label had a renderable crop.

## 11. Recommendation

Based **only** on this human-gold set:

**Retrieval is insufficient.** Ranking is not the limiter on the 8 labels that were actually associable (Recall@1 = 1.00 on that set of 8). Fifty-eight visible members never entered the candidate list.

Next technical experiment should stay **deterministic retrieval**, still R&D-shadow, still unwired:

1. Stop treating giant bay polylines as member candidates.
2. Retrieve joist-scale segments on framing plans (the line the label sits on), not only wall beams and infills.
3. On detail sheets, retrieve the small geometry a **leader actually points to** (clip angles, plates, braces, WT stems)—without selecting the leader itself.
4. Keep abstention for crowded nodes (`token_p8_367`, `token_p8_424`) and for schedule text.

Do **not** start an offline ML association model on this gold set. Candidate recall among associated labels is high because those labels are exactly the cases where a compact stroke was already retrieved; the missing 58 are a candidate-generation problem. ML ranking cannot recover a geometry that was never retrieved.

Do **not** productionize this retrieval, replace `nearest_geometry`, or wire the sidecar into Semantic Review.

## QC

- 75 unique `token_id`s, no extras, none missing vs `g1_rows.jsonl`
- Associated: 8, each with `selected_geometry_id ∈ candidate_geometry_ids`
- Ambiguous: 2, empty targets
- No valid member: 65, empty targets
- Unavailable: 0
- Compiler: `backend/scripts/rd_geometry_integration/compile_human_gold.py`
