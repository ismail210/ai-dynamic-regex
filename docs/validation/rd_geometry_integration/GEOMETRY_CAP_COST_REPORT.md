# E1 — Dense-Page Geometry Cap Cost Experiment

**Status: measurement only.** No production code was modified. No Retrieval V3. No gold
changes. No association-accuracy claim.

- Document: `doc_0d910a43b4a021e3` (Burrville ES - ST)
- Pages: p8, p18, p24
- Script: `backend/scripts/rd_geometry_integration/cap_cost_experiment.py`
- Data: `cap_cost_results.jsonl`, `cap_cost_summary.json`

---

## 1. Executive Summary

**CAP_450 destroys 9 of 21 audited visible-member targets (42.9%).** Those 9 are present
in raw PDF geometry and survive only under `CAP_NO_LIMIT`. Raising the cap to 900 or 1800
recovers **zero** of them.

| Cap | Audited-21 identifiable targets surviving | Survival % |
| --- | ---: | ---: |
| CAP_450 | 12 / 21 | 57.1% |
| CAP_900 | 12 / 21 | 57.1% |
| CAP_1800 | 12 / 21 | 57.1% |
| CAP_NO_LIMIT | 21 / 21 | 100.0% |

**Incremental benefit (audited 21):**

| Change | Additional targets surviving |
| --- | ---: |
| 450 → 900 | **0** |
| 900 → 1800 | **0** |
| 1800 → No Limit | **9** |

Why 900/1800 help so little: production `structural_first` keeps **long strokes first**
(`max(width,height) >= 80pt`), then fills with short strokes. On these pages there are only
172–350 long strokes. The nine audited targets lost at CAP_450 are **short-stroke** paths
with retention ranks **2405–2946** — far below even an 1800-slot budget once long strokes
take the first slots.

Cap vs classification on the same 21 (under CAP_450):

| Stage outcome under CAP_450 | Count |
| --- | ---: |
| Lost at the cap | **9** |
| Survives cap, but classified as leader/dimension | **7** |
| Survives all extraction stages (member-eligible kind) | **5** |

So the cap is demonstrably destructive, but it is **not** the only extraction loss: even
among targets that survive CAP_450, 7/12 are immediately reclassified as callouts. Cap
raising alone does not make those usable as member candidates.

**Associated regression control: 8/8 survive under every cap. Zero regressions.**

This experiment does **not** measure retrieval or association accuracy.

---

## 2. Experimental Controls

| Control | Status |
| --- | --- |
| Same PDF | `uploads/Burrville ES - ST.pdf` |
| Same pages | 8, 18, 24 |
| Same production helpers | `_select_under_dense_cap`, `_structural_keep_score`, `_classify_path`, `_looks_like_leader`, `_looks_like_dimension`, `_gid`, `merge_collinear_fragments` |
| Only variable | dense-page path cap: 450 / 900 / 1800 / no numeric limit |
| Tiny / page-frame prefilter | Unchanged (applied before ranking, as in production) |
| Classification / leader / dimension rules | Unchanged |
| Retrieval / `nearest_geometry` | Not run |
| Human gold | Read-only; SHA-256 verified before and after |

**Cap selection mechanism (inspected in production code):**

1. Exclude tiny noise (`max_span < 3pt`) and page-frame boxes.
2. Score remaining paths with `_structural_keep_score` (thin long strokes preferred).
3. Split into long (`max_span >= 80pt`) and short.
4. Keep `long_strokes[:cap]`, then fill remaining slots from `short_strokes`.

`CAP_NO_LIMIT` keeps the entire ranked pool after the same tiny/page-frame exclusions
(isolating the numeric cap, not removing the prefilter).

**Replay fidelity (CAP_450 vs shipped `geometry.json`):**

| Page | Faithful? | Notes |
| --- | --- | --- |
| p8 | Partial (431/435 id match; 439 vs 435 merged) | Within-run survival comparisons remain valid; minor ordinal/tie drift vs artifact |
| p18 | Exact (433/433) | |
| p24 | Exact (392/392) | |

---

## 3. Page-Level Results

| Page | Raw | Ranked pool | Long (≥80pt) | Short | 450 | 900 | 1800 | No Limit |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 3586 | 3151 | 172 | 2979 | 450 (12.6%) | 900 (25.1%) | 1800 (50.2%) | 3151 (87.9%) |
| 18 | 5300 | 2815 | 209 | 2606 | 450 (8.5%) | 900 (17.0%) | 1800 (34.0%) | 2815 (53.1%) |
| 24 | 4749 | 2784 | 350 | 2434 | 450 (9.5%) | 900 (19.0%) | 1800 (37.9%) | 2784 (58.6%) |

Dropped from raw at CAP_450: p8 **3136**, p18 **4850**, p24 **4299**.

Because long strokes number only 172–350, CAP_450 already keeps **all** long strokes on
every audited page, then fills the rest with the highest-scoring short strokes. Further
raises mostly add more short strokes — but the missed member fragments sit very deep in
that short queue.

---

## 4. Target Survival

Target identity rules (no invented gold geometry IDs):

- **Associated:** raw path that produces `selected_geometry_id` under CAP_450.
- **Audited 21:** re-matched from `extraction_audit.jsonl` (`near_label` longest ≥25pt, or
  tip-local non-leader target).
- **Other visible-member misses:** nearest on-segment stroke under the label if
  `leader_required=false`; otherwise `TARGET_IDENTITY_UNCERTAIN`.

### 4.1 Audited 21 (primary)

| Cap | Identifiable | Survive cap | Survival % | Survive cap but callout-classified | Member-eligible after classify |
| --- | ---: | ---: | ---: | ---: | ---: |
| CAP_450 | 21 | 12 | 57.1% | 7 | 5 |
| CAP_900 | 21 | 12 | 57.1% | 7 | 5 |
| CAP_1800 | 21 | 12 | 57.1% | 7 | 5 |
| CAP_NO_LIMIT | 21 | 21 | 100.0% | 15 | 6 |

Uncertain identities in this set: **0**.

### 4.2 Associated 8 (regression control)

| Cap | Identifiable | Survive cap | Survival % |
| --- | ---: | ---: | ---: |
| CAP_450 | 8 | 8 | 100% |
| CAP_900 | 8 | 8 | 100% |
| CAP_1800 | 8 | 8 | 100% |
| CAP_NO_LIMIT | 8 | 8 | 100% |

**Regressions: 0.** All eight known gold geometries remain present under every larger cap.

### 4.3 Visible-member misses (58)

| Cap | Identifiable | Uncertain | Survive cap | Survival % (of identifiable) |
| --- | ---: | ---: | ---: | ---: |
| CAP_450 | 48 | 10 | 27 | 56.2% |
| CAP_900 | 48 | 10 | 28 | 58.3% |
| CAP_1800 | 48 | 10 | 29 | 60.4% |
| CAP_NO_LIMIT | 48 | 10 | 48 | 100.0% |

The 10 uncertain cases are almost all `leader_required` labels not in the extraction audit
(refusing to invent tip targets), plus one p8 label with no on-segment stroke within the
conservative window.

These are **extraction target survival** rates only — not retrieval correctness.

### 4.4 Ambiguous 2

Reported separately in `cap_cost_summary.json` / JSONL (`population=ambiguous`). Not folded
into the 58.

---

## 5. Incremental Benefit

### Audited 21

| Change | Additional targets surviving | Regressions |
| --- | ---: | ---: |
| CAP_450 → CAP_900 | 0 | 0 |
| CAP_900 → CAP_1800 | 0 | 0 |
| CAP_1800 → CAP_NO_LIMIT | **9** | 0 |

### Visible-member misses (48 identifiable)

| Change | Additional targets surviving | Regressions |
| --- | ---: | ---: |
| CAP_450 → CAP_900 | 1 | 0 |
| CAP_900 → CAP_1800 | 1 | 0 |
| CAP_1800 → CAP_NO_LIMIT | **19** | 0 |

**Conclusion on incremental caps:** doubling or quadrupling 450 does not move the audited
failure set. The losses sit at ranks ≫ 1800. Only removing the numeric cap (keeping the
full ranked pool) recovers them.

---

## 6. Failure Examples

### `token_p8_355` (W10X15 infill joist)

| Stage | Result |
| --- | --- |
| RAW_PRESENT | yes (67.71pt stroke under label) |
| Cap rank | **2946** (short-stroke queue; bbox max span 65.4 < 80) |
| CAP_450 / 900 / 1800 | **dropped** |
| CAP_NO_LIMIT | survives, then classified **leader** |

Neighborhood within 22pt: raw 3 → CAP_450 keeps 2 → NO_LIMIT keeps 3.

### `token_p8_348` (W30X90) — **not a cap failure**

| Stage | Result |
| --- | --- |
| RAW_PRESENT | yes (323.97pt diagonal girder) |
| Cap rank | 155 (long stroke) |
| CAP_450 | **survives** |
| CLASSIFICATION | **dimension** |
| Member-eligible | no |

This is a classification-cost case. Counting it as a cap recovery would be wrong.

### `token_p18_1186` (WT7X19)

| Stage | Result |
| --- | --- |
| RAW_PRESENT | yes (51.1pt tip/leader fragment from audit tip evidence) |
| Cap rank | **2653** |
| CAP_450 / 900 / 1800 | **dropped** |
| CAP_NO_LIMIT | survives, classified **leader** |

Neighborhood within 22pt of that tip stroke: raw 9 → CAP_450 **0** → CAP_900 **4** →
CAP_1800 **5** → NO_LIMIT **9**. Local density does improve at 900 even though this
particular tip stroke remains below the cut — secondary evidence that moderate raises
help *some* nearby paths, but not the audited tip primitive itself.

### `token_p18_1162` (PL 3/8")

| Stage | Result |
| --- | --- |
| RAW_PRESENT | yes (21.72pt tip-local fragment) |
| Cap rank | **2759** |
| CAP_450 / 900 / 1800 | **dropped** |
| CAP_NO_LIMIT | survives, classified **leader** |

### `token_p24_1385` (L4x4x3/8)

| Stage | Result |
| --- | --- |
| RAW_PRESENT | yes (93.43pt tip-local path) |
| Cap rank | **2405** |
| CAP_450 / 900 / 1800 | **dropped** |
| CAP_NO_LIMIT | survives as **line** (member-eligible) |

This is one of the few cases where removing the cap yields a member-eligible kind, not
just a callout.

### Ranks of all 9 audited targets lost at CAP_450

`2405, 2653, 2759, 2762, 2768, 2776, 2782, 2921, 2946`

All exceed 1800. All are in the short-stroke portion of the ranked pool.

---

## 7. Cap vs Classification

Explicit separation for audited 21 under CAP_450:

| Bucket | Count | Meaning |
| --- | ---: | --- |
| Lost at cap | 9 | RAW yes → CAP_450 no |
| Survives cap, classified callout | 7 | CAP yes → kind ∈ {leader, dimension, symbol} |
| Survives all extraction stages | 5 | CAP yes → member-eligible kind |

Under CAP_NO_LIMIT the 9 return, but **8 of those 9 become callout-classified** (only
`token_p24_1385` becomes a member-eligible `line`). So:

> Removing the cap restores raw presence; it does **not** by itself restore
> member-eligible geometry for most audited tip/joist fragments.

W30X90 (`token_p8_348`) remains the clearest example of “survives every cap, dies at
classification.”

---

## 8. Interpretation

What this experiment **proves**:

1. **CAP_450 is demonstrably destructive** for identifiable visible-member targets:
   9/21 audited (42.9%) and 21/48 identifiable misses (43.8%) are absent after the cap.
2. **Those losses are deep in the short-stroke ranking** (ranks ~2400–2950), not near the
   450 boundary — so CAP_900 and CAP_1800 provide essentially no audited-target recovery.
3. **A large share of remaining losses are classification**, not cap: 7/12 audited targets
   that survive CAP_450 are labeled leader/dimension.
4. **Associated gold geometries do not regress** when the cap is raised or removed.
5. **Raising/removing the cap alone is insufficient** as a path to member-eligible
   candidates for most tip-local fragments (they reappear as leaders).

What this experiment **does not** prove:

- That a larger cap improves retrieval Recall@K or association accuracy.
- That NO_LIMIT is a viable production setting (object counts rise to ~2800–3150/page).
- That short-stroke rank position is “wrong” — only that the current scoring+cap pair
  drops these particular visible members.

---

## 9. Next Experiment

Based strictly on these measurements:

**Recommended next: E2 — Classification Cost Experiment.**

Measure, with the cap held fixed at production 450 (and optionally re-run under NO_LIMIT
as a shadow), how many identifiable targets that **already survive the cap** are removed
from member eligibility by `_looks_like_dimension` / `_looks_like_leader`. Primary metric:
classification flip rate on the 12 audited survivors and the associated-8 control.

A secondary follow-on (not E2) would be a **cap-selection strategy** experiment — e.g.
label-aware retention or different short-stroke scoring — because numeric raises to 900/1800
do not reach ranks 2400+. That is a different variable from E2.

**Do not implement E2 here. Do not implement Retrieval V3. Do not change production.**

---

## Artifacts and safety

**Created**

- `backend/scripts/rd_geometry_integration/cap_cost_experiment.py`
- `docs/validation/rd_geometry_integration/GEOMETRY_CAP_COST_REPORT.md`
- `docs/validation/rd_geometry_integration/cap_cost_results.jsonl`
- `docs/validation/rd_geometry_integration/cap_cost_summary.json`

**Modified**

- `backend/scripts/rd_geometry_integration/README.md` (index entry only)

**Verified untouched**

- `review_kit/gold_outcomes.jsonl` (SHA-256 `0fad4291…b976b155`)
- `retrieval.py`, `retrieval_v2.py`
- Production extraction / filtering / GHX / Semantic Review / takeoff / ML / VLM
