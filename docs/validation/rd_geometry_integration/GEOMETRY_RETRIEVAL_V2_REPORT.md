# Geometry Retrieval V2 — Burrville R&D

**Status:** Isolated candidate-generation experiment. Not production.  
**Document:** Burrville ES - ST (`doc_0d910a43b4a021e3`)  
**Labels:** same 75 human-gold records (p8 / p18 / p24)  
**Gold:** [`review_kit/gold_outcomes.jsonl`](review_kit/gold_outcomes.jsonl) — **unchanged** (sha256 `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`)  
**Harness:** `backend/scripts/rd_geometry_integration/retrieval_v2.py` + `run_retrieval_v2.py`  
**Outputs:** [`v2_rows.jsonl`](v2_rows.jsonl) · [`v2_summary.json`](v2_summary.json) · [`v2_renders/`](v2_renders/)

This experiment answers: **can deterministic retrieval put the geometry humans already identified into the candidate set?**  
It does **not** answer which system is better than production `nearest_geometry`.

## 1. Objective

Candidate **retrieval coverage**, not ranking quality, not production agreement, not ML feasibility.

Human gold is the evaluation reference. The 75 decisions were not rewritten.

Two populations:

| Population | N | What is scored |
|------------|--:|----------------|
| A. Human-associated | 8 | Exact `selected_geometry_id` Recall@1/@3/@5 |
| B. Visible member, absent from baseline candidates | 58 | Coverage of a retrieved local/leader-target stroke. **No gold geometry id exists** — gold was not invented |

## 2. Baseline

Current R&D retrieval (`retrieval.py` / G1) and human gold ([`HUMAN_GOLD_REVIEW_REPORT.md`](HUMAN_GOLD_REVIEW_REPORT.md)):

- 75 reviewed: 8 associated, 2 ambiguous, 65 no-valid-member (58 visible-member misses + 7 p18 splice-schedule cells)
- Associated Recall@1/@3/@5 = **8/8**
- The limiter is **candidate coverage**, not ranking on those 8

### Baseline retrieval audit (inspected, not modified)

| # | Finding |
|---|---------|
| 1. Primitives retrieved | Production `geometry.json` objects: line, polyline, path, arc, curve. Leaders scored then excluded as targets when `exclude_leader_as_target=True`. Rectangles are **not** leader-hop targets. Centerline is collapsed to first/last of ≤16 points. |
| 2. Filtering | Same page; drop dimension/symbol; `bbox_distance > 150` unless overlap; optional same-region (off in G1). |
| 3. Distance | Sort key is **bbox_distance** then center_distance. A label **inside** a giant polyline bbox scores **d = 0**. Perpendicular-to-stroke is computed but not used to rank. |
| 4. Orientation | `orientation_delta_deg` is stored, not used to rank. |
| 5. Bbox overlap | Overlap/IoU recorded; overlap bypasses the max-distance gate, which is how bay polylines survive. |
| 6. Limits | `top_k=5`, `max_distance=150`, leader hop uses 3 nearby leaders and far **bbox corner** (same idea as production `spatial_index`). |
| 7. Why giant polylines survive | Production `merge_collinear_fragments` stitches collinear strokes into bay-scale polylines (`geom_59a6f49b264f`, `geom_3e2826b140f9`, …). Bbox-overlap ranking then prefers them. |
| 8. Why small segments are missed | Dense-page cap (`_DENSE_PAGE_CAP = 450`) keeps long strokes first. Short joists are dropped or classified as **leader** (length 8–72) or **dimension** (nearby numeric section text). V2 cannot retrieve a primitive that was never extracted. |
| 9. Why leader targets are missed | Hop queries the far bbox corner, not chained arrow tips; rectangles/plates are excluded from the member-kind set. |
| 10. Layer | **Extraction + segmentation + filtering**, not ranking. On the 8 associated labels ranking already recovers gold @1. |

p8 geometry.json: 435 objects (270 classified `leader`, 72 `line`, 12 `polyline`).

## 3. V2 design

New file only. `retrieval.py` is unchanged. No production imports.

### Segment-level member retrieval

Polylines keep **all points** (not first/last). Consecutive segments are derived (`geom_id::seg_i`). Long strokes the label actually projects onto can emit a local window (`::local`) of ~160 pt. Role remains `unknown`. No beam/column/brace labels.

### Giant-polyline suppression

Generic features only (no Burrville geometry ids, no `if page == 18`):

- extent, area, ratio vs median local extent, bbox containment without small perpendicular distance, whether a smaller local stroke exists

Giants are **not** deleted globally. If the label sits on the stroke (perp ≤ 18, on-segment), a local window is kept. If the label is only inside a huge bbox, the full primitive is dropped from the shortlist.

### Leader-target retrieval

BFS from label-adjacent leaders, join endpoints within 12 pt, cap chain length/span so a page-wide union is not built.

Output evidence:

```json
{
  "leader_geometry_id": "...",
  "target_point": [x, y],
  "target_geometry_ids": ["..."]
}
```

The leader is **never** the member (`leader_as_member = 0`). The candidate is geometry near the tip (including rectangles).

### Small detail retrieval

Rectangles are eligible. Short lines are eligible. Linear primitives production-tagged `dimension` or `leader` may be reclassified as stroke candidates **only when they are not a callout of this label** (length ≥ 40, thin bbox). That is a geometry-feature reinterpretation of existing primitives, not section-size completion.

## 4. Human-gold evaluation

75 labels. Gold file was not written by this run.

| Decision | N | Gold geometry id |
|----------|--:|------------------|
| Associated (`direct_target`) | 8 | `selected_geometry_id` scored |
| Ambiguous | 2 | none (abstain) |
| No valid member, visible member | 58 | **none — not invented** |
| Schedule / not a member | 7 | none |
| Unavailable | 0 | — |

`review_followup`: none. V2 disagreement with gold was not used to change gold.

## 5. Retrieval coverage (Population B — the 58)

**Baseline exact-id coverage = 0/58 by construction** (those records have empty `reviewed_target_geometry_ids`).

Two coverage measurements, neither called “accuracy”:

| Metric | V2 | Meaning |
|--------|----|---------|
| Proxy local-coverage | **30 / 58** | A non-giant on-stroke candidate (perp ≤ 28) or a leader-target small geometry is in the v2 shortlist |
| Still missing (proxy) | **28 / 58** | No such candidate |
| Baseline proxy (same definition on G1 top-5) | 24 / 58 | Shows the proxy is loose: humans already rejected those lists |
| **New local/leader-target id absent from baseline** | **9 / 58** | A *new* primitive entered the shortlist |

The **9** new ids: `token_p8_351`, `token_p8_359`, `token_p8_384`, `token_p8_411`, `token_p18_1169`, `token_p18_1173`, `token_p18_1178`, `token_p18_1188`, `token_p24_1361`.

Visual QA of representative “recovered” crops (p8_359, p18_1162, p24_1361) shows **nearby wrong geometry** (bay windows, column flanges, joist webs/hatch), not a confirmed human member stroke. The 30/58 proxy is therefore an **upper bound**, not a claim that 30 human-observed members are now in the set.

**Answer to the experiment question:** deterministic v2 from existing `geometry.json` primitives did **not** demonstrably put the human-observed member into the candidate set for most of the 58. The dominant gap remains **missing or mis-segmented extraction**, not shortlist ranking.

## 6. Existing associated population (Population A)

8 associated labels. Exact gold geometry id.

| | Recall@1 | Recall@3 | Recall@5 |
|--|---------:|---------:|---------:|
| Baseline G1 | **8/8** | **8/8** | **8/8** |
| V2 | **8/8** | **8/8** | **8/8** |

No retrieval regression on the already-associable set. An earlier ranking bug (leader-target sort band beating an on-stroke member) dropped Recall@1 to 7/8; v2 now ranks strong local on-segment strokes ahead of leader hops. That is ranking inside the shortlist, not a coverage change.

Failure class on these 8: **RETRIEVED** (gold in v2, rank 1). **RANKING_FAILURE = 0** at top-1.

## 7. Leader results

Gold: 18 no-valid-member labels are leader-driven (7 p18 + 11 p24). Associated labels requiring a leader: 0.

| Measure | Count |
|---------|------:|
| Leader-required labels | 18 |
| Leader chain detected | **6** |
| Target geometry retrieved (some non-leader near tip) | **6** |
| Target geometry missing | **12** |
| Leader returned as member | **0** |

By page:

- **p18:** 5/7 leaders detected with a tip candidate (`token_p18_1186` WT7X19 missed; `token_p18_1178` brace had no leader chain). Overlay for `token_p18_1162` shows the purple leader, but green candidates are the **column**, not the splice plate.
- **p24:** **1/11** (`token_p24_1361`). Overlay shows the hop landing on **joist web / hatch**, not the L4 hanger at the curtain wall. The other 10 p24 L-clips remain retrieval failures.

Invariant **leader_as_member = 0** held.

## 8. Giant-polyline results

| Measure | Count |
|---------|------:|
| Baseline top-1 extent ≥ 400 pt | **13** |
| V2 replaced with local window or smaller-extent candidate | **12** |

Human gold on those 13 is `no_valid_member` (no gold id). Suppression **stops the giant from winning bbox-overlap**, but the replacement is often another wall/infill/local window of the same bay outline — still not the labeled joist/girder.

Examples:

| Token | Baseline top-1 (giant) | V2 top-1 | Human gold |
|-------|------------------------|----------|------------|
| `token_p8_348` W30X90 | `geom_59a6f49b264f` extent 843 | local window of the same bay polyline (extent 335) | still missing — girder stroke not retrieved |
| `token_p8_337` W21X44 | `geom_3e2826b140f9` extent 658 | nearby EJ wall `geom_0b5ef1f9c497` | still missing |
| `token_p8_359` W18X40 | `geom_59a6f49b264f` | smaller line `geom_9027619e697a` | new id vs baseline; overlay still a bay window, not a confirmed joist |

A giant polyline is not always wrong; on the associated set, compact wall strokes were already correct. Giants are wrong when they **conflict with the labeled member**, which is the 58-miss pattern.

## 9. Detail-page results

| Page | Associated | Visible misses | Proxy recovered | Leader detected | Schedule not-member | Notes |
|------|----------:|---------------:|----------------:|----------------:|--------------------:|-------|
| p8 framing | 8 | 40 | 23 | 0 | 0 | Joist/girder strokes mostly unextracted or classified leader/dimension |
| p18 S-205 | 0 | 7 | 6 | 5/7 | 7 | Leader hops fire; targets often column/beam, not plate/brace |
| p24 S-321 | 0 | 11 | 1 | 1/11 | 0 | Small L clips still missing |

No hard region gate. Title-seeded frames are not treated as ground truth.

Schedule cells (`token_p18_1143`–`1151`): failure class **NOT_A_MEMBER**. Retrieval may still return table borders; that is not a member association.

## 10. Remaining failures

Explicit classes ([`v2_summary.json`](v2_summary.json) `failure_classes`):

| Class | N | Meaning |
|-------|--:|---------|
| RETRIEVED | 8 | Gold id in v2 (Population A) |
| PROXY_RECOVERED | 30 | Population B proxy only |
| RETRIEVAL_FAILURE | 28 | Population B, no local/leader-target candidate |
| AMBIGUITY | 2 | Human gold abstention (`token_p8_367`, `token_p8_424`) |
| NOT_A_MEMBER | 7 | Splice schedule |
| RANKING_FAILURE | 0 | Gold present but below top-1 (none after the local-vs-leader sort fix) |

Of the 28 remaining proxy misses, typical mechanisms:

1. **Extraction gap** — no stroke under the label in `geometry.json` (`token_p8_355` W10X15: v2 candidates = 0; the joist is visible on the PDF).
2. **Giant local window ≠ member** — `token_p8_348` W30X90.
3. **Parallel joist / neighbor wall** — `token_p8_381` / `430` / `431`.
4. **Leader tip missing or hopping to hatch/web** — 10/11 p24 L-clips; `token_p18_1186`.

This is still a **retrieval / extraction** problem. Ranking cannot recover an unextracted stroke.

## 11. Visual QA

Legend (also [`v2_renders/LEGEND.txt`](v2_renders/LEGEND.txt)): **blue = label**, **gray/dashed orange = baseline**, **green = v2**, **magenta = human gold** (associated only), **purple = leader / target point**. Crops are label-centered; giant boxes do not expand the clip. Source PDF not modified.

| Case | File |
|------|------|
| Giant-polyline failure | [`v2_renders/giant_polyline_failure_token_p8_348.png`](v2_renders/giant_polyline_failure_token_p8_348.png) — W30X90; green still bay-scale, not the girder |
| Recovered p8 (new vs baseline) | [`v2_renders/recovered_p8_member_token_p8_359.png`](v2_renders/recovered_p8_member_token_p8_359.png) — smaller boxes than baseline giant; not confirmed as the W18X40 joist |
| Leader p18 | [`v2_renders/leader_p18_token_p18_1162.png`](v2_renders/leader_p18_token_p18_1162.png) — purple leader; green is the column, not the splice plate |
| Leader p24 | [`v2_renders/leader_p24_token_p24_1361.png`](v2_renders/leader_p24_token_p24_1361.png) — hop to joist web/hatch, not the L4 hanger |
| Remaining retrieval failure | [`v2_renders/remaining_retrieval_failure_token_p8_355.png`](v2_renders/remaining_retrieval_failure_token_p8_355.png) — visible W10X15, **zero** candidate overlays |
| Ambiguous | [`v2_renders/ambiguous_token_p8_367.png`](v2_renders/ambiguous_token_p8_367.png) — gold abstention preserved |

## 12. Safety

| Constraint | Status |
|------------|--------|
| Production association / `orchestrator.py` | untouched |
| GHX | untouched |
| Semantic Review | untouched |
| Takeoff | untouched |
| `retrieval.py` / G1 harness | not replaced |
| `graph_builder` production behavior | untouched |
| Semantic extraction/correction | untouched |
| ML / training | none |
| VLM | none |
| Section-size completion | none (`L4X4` stays `L4X4`) |
| Leader as member | **0** |
| Human gold rewritten | **no** |

Tests: `python -m pytest tests/test_rd_geometry_phase.py tests/test_rd_geometry_retrieval_v2.py -q` → **18 passed**.

## 13. Decision gate

Factual observations only:

- Population A coverage was already 8/8 and stays 8/8. Ranking is not the limiter there.
- Population B: **28/58** still have no local/leader-target candidate. Of the 30 proxy hits, visual QA does not support treating them as the human member. Only **9/58** introduced a primitive that was absent from baseline, and those 9 are not gold-id confirmed.
- p18 leader hop fires (5/7) but often on the wrong object. p24 leader recovery is **1/11**.
- Giant bbox winners can be suppressed; that does not create the missing joist/clip stroke.
- The missing geometry is frequently **not in `geometry.json`** (dense-page cap, leader/dimension misclassification, collinear merge).

**Conclusion: A. Retrieval still insufficient → continue deterministic retrieval work.**

Do **not** move to ML ranking. Candidate generation is not demonstrably strong on the 58. Ranking cannot recover unextracted members. Ambiguity abstention on `token_p8_367` / `token_p8_424` should stay.

Next deterministic work, still R&D/shadow:

1. Extraction: stop dropping joist-scale strokes (dense cap / leader-vs-line / dimension-vs-member using numeric section text).
2. Segmentation: split merged bay polylines **before** candidate generation, without project-specific ids.
3. Leader tips: follow the arrow to **small** geometry (clip/plate), not the first large hatch/web.
4. Keep this harness unwired.

Do **not** productionize `retrieval_v2`, replace `nearest_geometry`, or attach this sidecar to Semantic Review.
