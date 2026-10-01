# E2 — Classification Cost Experiment

**Status: measurement only.** Production classifiers, filters, and caps were not modified.
No E3. No Retrieval V3. Human gold immutable.

- Document: `doc_0d910a43b4a021e3` (Burrville ES - ST)
- Pages: p8, p18, p24
- Script: `backend/scripts/rd_geometry_integration/classification_cost_experiment.py`
- Data: `classification_cost_results.jsonl`, `classification_cost_summary.json`
- Target identities: reused exactly from E1 fingerprints / extraction audit (no invented gold IDs)

---

## 1. Executive Summary

**Among geometry that survives the cap, classification is a major secondary bottleneck.**

At production **CAP_450**, of the 21 audited visible-member targets:

| Stage | Count |
| --- | ---: |
| Raw present | 21 |
| Survive cap | 12 |
| Lost at cap | 9 |
| Survive cap → remain member-eligible | **5** |
| Survive cap → lost to `_looks_like_dimension` | **6** |
| Survive cap → lost to `_looks_like_leader` | **0** |
| Survive cap → other filter | 0 |
| Eligible but audit says retrieval-stage miss | 2 |

**Classification survival (CAP_450):**

\[
\frac{5\ \text{eligible}}{12\ \text{cap survivors}} = 41.7\%
\]

So **7 of 12 cap survivors (58.3%)** are made ineligible by classification — all via
dimension classification in the primary attribution (6 explicit + 1 ambiguous case that is
also dimension-classified).

**Under diagnostic CAP_NO_LIMIT** (not a production proposal):

| Stage | Count |
| --- | ---: |
| Survive cap | 21 |
| Remain member-eligible | **6** |
| Lost to dimension | **7** |
| Lost to leader | **7** |
| Other filter | 0 |

The 9 targets recovered from the cap do **not** become usable members in general: **7 become
`leader`**, 1 becomes `dimension`, and only 1 (`token_p24_1385`) becomes an eligible `line`.
Classification survival falls to **28.6%** (6/21) because the restored short strokes are
exactly the length band `_looks_like_leader` targets (8–72pt).

**CAP_SURVIVAL ≠ MEMBER_ELIGIBILITY** is confirmed by measurement, including W30X90.

---

## 2. Experimental Controls

| Control | Status |
| --- | --- |
| Same PDF / pages / gold | Yes |
| Same raw geometry / E1 target fingerprints | Yes |
| Production helpers called unchanged | `_classify_path`, `_looks_like_leader`, `_looks_like_dimension`, `_nearby_text`, `_select_under_dense_cap` |
| Cap conditions | CAP_450 (production) and CAP_NO_LIMIT (diagnostic population only) |
| Classifier predicates | **Not modified** — only instrumented in the R&D wrapper |
| Retrieval / GHX / Semantic Review / takeoff / ML | Untouched |

**Production predicates (inspected, not changed):**

| Helper | Exact condition |
| --- | --- |
| `_looks_like_leader` | `kind ∈ {LINE, POLYLINE}` AND `8 ≤ length ≤ 72` AND `min(w,h) < 24` |
| `_looks_like_dimension` | `kind ∈ {LINE, POLYLINE, PATH}` AND `length ≥ 12` AND nearby text matches `\d+(\.\d+)?` |
| Application order | leader **first**, else dimension; then small rectangle/circle → symbol |
| Nearby text | nearest `document.lines` center within page `nearby_radius` of geometry center |

Predicate reconstructions matched the production helpers on every audited call
(`dimension_predicate_matches_helper` / `leader_predicate_matches_helper` = true).

---

## 3. 21-Case Results

### CAP_450

| Token | Label | Raw | Cap | Dim | Leader | Classification | Eligible | Primary stage | Nearby text → digit |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |
| token_p8_332 | W14X22 | ✓ | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | `W14X22  [25]` → 14 |
| token_p8_337 | W21X44 | ✓ | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | `W21X44  [30]` → 21 |
| token_p8_340 | W21X44 | ✓ | ✓ | | | line | ✓ | OTHER (control OK) | *(empty)* |
| token_p8_346 | W10X15 | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |
| token_p8_348 | W30X90 | ✓ | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | `17K` → 17 |
| token_p8_351 | W18X35 | ✓ | ✓ | | | line | ✓ | OTHER | *(empty)* |
| token_p8_355 | W10X15 | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |
| token_p8_359 | W18X40 | ✓ | ✓ | | | line | ✓ | RETRIEVAL_STAGE_ONLY | *(empty)* |
| token_p8_367 | W14X22 | ✓ | ✓ | ✓ | | dimension | | AMBIGUOUS | `21KW14X22  [14]` → 21 |
| token_p8_381 | W18X35 | ✓ | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | `W18X35  [35]` → 18 |
| token_p8_430 | W18X35 | ✓ | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | `W18X35  [28]` → 18 |
| token_p18_1143 | W10X33 | ✓ | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | `7/8` → 7 |
| token_p18_1162 | PL 3/8" | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |
| token_p18_1169 | PL 1 1/2" | ✓ | ✓ | | | rectangle | ✓ | RETRIEVAL_STAGE_ONLY | `(Fy = 50 ksi)` *(rect; dim N/A)* |
| token_p18_1178 | L4X4X1/4 | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |
| token_p18_1186 | WT7X19 | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |
| token_p24_1359 | L6x3-1/2x3/8 | ✓ | ✓ | | | line | ✓ | OTHER | `DWGS` |
| token_p24_1360 | L4x4x3/8 | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |
| token_p24_1361 | L4X4X3/8 | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |
| token_p24_1377 | L4x4x3/8 | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |
| token_p24_1385 | L4x4x3/8 | ✓ | | | | NOT_REACHED | | CAP_LOSS | — |

### CAP_NO_LIMIT

| Token | Cap | Dim | Leader | Class | Eligible | Primary stage | Notes |
| --- | ---: | ---: | ---: | --- | ---: | --- | --- |
| token_p8_332 | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | same as 450 |
| token_p8_337 | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | same |
| token_p8_340 | ✓ | | | line | ✓ | OTHER | control |
| token_p8_346 | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | was CAP_LOSS; now dim via `W10X15  [9]` |
| token_p8_348 | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | same (`17K`) |
| token_p8_351 | ✓ | | | line | ✓ | OTHER | |
| token_p8_355 | ✓ | ✓ | ✓ | **leader** | | LEADER_CLASSIFICATION | both true; leader precedence; len 67.71 |
| token_p8_359 | ✓ | | | line | ✓ | RETRIEVAL_STAGE_ONLY | |
| token_p8_367 | ✓ | ✓ | | dimension | | AMBIGUOUS | |
| token_p8_381 | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | |
| token_p8_430 | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | |
| token_p18_1143 | ✓ | ✓ | | dimension | | DIMENSION_CLASSIFICATION | |
| token_p18_1162 | ✓ | | ✓ | leader | | LEADER_CLASSIFICATION | |
| token_p18_1169 | ✓ | | | rectangle | ✓ | RETRIEVAL_STAGE_ONLY | |
| token_p18_1178 | ✓ | ✓ | ✓ | leader | | LEADER_CLASSIFICATION | both; leader wins |
| token_p18_1186 | ✓ | ✓ | ✓ | leader | | LEADER_CLASSIFICATION | both; leader wins |
| token_p24_1359 | ✓ | | | line | ✓ | OTHER | |
| token_p24_1360 | ✓ | ✓ | ✓ | leader | | LEADER_CLASSIFICATION | both; leader wins |
| token_p24_1361 | ✓ | | ✓ | leader | | LEADER_CLASSIFICATION | |
| token_p24_1377 | ✓ | ✓ | ✓ | leader | | LEADER_CLASSIFICATION | both; leader wins |
| token_p24_1385 | ✓ | | | **line** | ✓ | OTHER | only recovered short stroke that stays eligible |

---

## 4. Stage Funnel

### CAP_450

```
21 raw
 ↓
12 survive cap          (−9 CAP_LOSS)
 ↓
 5 remain eligible      (−6 DIMENSION primary; −1 AMBIGUOUS also dimension-classified)
 ↓
 3 extraction-OK without audit retrieval-miss tag
 2 eligible but RETRIEVAL_STAGE_ONLY (p8_359, p18_1169)
```

Classification survival among cap survivors: **5/12 = 41.7%**.

### CAP_NO_LIMIT

```
21 raw
 ↓
21 survive cap          (−0 CAP_LOSS)
 ↓
 6 remain eligible      (−7 DIMENSION; −7 LEADER; −1 AMBIGUOUS)
```

Classification survival: **6/21 = 28.6%**.

Associated-8 control: **8/8 eligible under both caps** (100% classification survival; 0 regressions).

---

## 5. Classification Attribution

Primary stage only (no double-counting):

| Failure | CAP_450 | NO_LIMIT |
| --- | ---: | ---: |
| Cap loss | 9 | 0 |
| Dimension classification | **6** | **7** |
| Leader classification | **0** | **7** |
| Other filter | 0 | 0 |
| Retrieval-stage only | 2 | 2 |
| Ambiguous | 1 | 1 |
| Other (survives / control OK) | 3 | 4 |

Secondary flags among CAP_450 survivors: `looks_like_dimension=true` on **7/12**
(includes the ambiguous case). `looks_like_leader=true` on **0/12**.

Under NO_LIMIT, both predicates are true on 5 targets; production order always awards
**leader** in those ties (`leader_took_precedence=true`).

---

## 6. `_looks_like_dimension` Analysis

### Measured trigger

Every dimension loss matched:

`kind_ok AND length≥12 AND nearby_text_contains_digit`

No `TRIGGER_NOT_EXPOSED` cases among audited dimension classifications.

### What the nearby text actually is

Two mechanisms appear:

1. **Own structural label digits** (dominant on p8 parallel members):
   - `W21X44  [30]` → digit `21` (`token_p8_337`)
   - `W18X35  [35]` → `18` (`token_p8_381`)
   - `W14X22  [25]` → `14` (`token_p8_332`)
2. **Unrelated numeric annotation near the stroke** (W30X90):
   - `token_p8_348`: nearby text is **`17K`** (reaction), distance 20.92pt — **not** the
     `W30X90` label. The girder is reclassified because *any* digit within the nearby-text
     radius fires the predicate.

So the audit hypothesis (“digits in `W21X44 [30]`”) is **confirmed for several p8 cases**,
but is **incomplete**: the predicate does not require the digit to come from the member’s
own designation — a nearby load callout is enough.

### Why some members survive as `line`

Eligible survivors (`token_p8_340`, `p8_351`, `p8_359`, `p24_1359`) had empty nearby text
or non-digit text (`DWGS`) inside the radius, so the digit conjunct failed.

### Rectangles are outside the dimension predicate

`token_p18_1169` has nearby `(Fy = 50 ksi)` with digit `50`, but base kind is `rectangle`,
so `_looks_like_dimension` never applies. It stays member-eligible.

### p8 population scan (all 50 gold labels)

Nearest on-segment stroke ≥25pt under each p8 label, under CAP_450:

| Outcome | Count |
| --- | ---: |
| Retained as `dimension` | **27** |
| Cap-dropped | 14 |
| Retained eligible (`line`/member) | **9** |

Matches the extraction-audit convention scan. Of the 27 dimension cases, all that reached
classification had a digit match in nearby text (same predicate).

---

## 7. `_looks_like_leader` Analysis

At **CAP_450**, leader classification causes **0** audited primary losses among cap
survivors. The production leader band (`8 ≤ length ≤ 72` and thin bbox) does not hit the
long girder/joist strokes that survive the long-stroke-first cap.

At **CAP_NO_LIMIT**, leader classification becomes the dominant fate of the 9 formerly
cap-dropped short strokes:

| Token | Length | Both predicates? | Final class |
| --- | ---: | ---: | --- |
| token_p8_355 | 67.71 | yes | leader (precedence) |
| token_p18_1162 | 21.72 | no | leader |
| token_p18_1178 | 18.24 | yes | leader |
| token_p18_1186 | 51.1 | yes | leader |
| token_p24_1360 | 18.24 | yes | leader |
| token_p24_1361 | 17.99 | no | leader |
| token_p24_1377 | 18.16 | yes | leader |

These are tip-local / short member fragments from the audit — **not** proven weld-symbol
reference lines in this measurement (those were often different retained objects under
CAP_450). Here the measured fact is: short restored strokes fall into the leader length
band and are labeled `leader`, which makes them ineligible as members.

Only `token_p24_1385` (93.43pt) escapes the 72pt leader ceiling and stays `line`.

---

## 8. CAP vs CLASSIFICATION Matrix

| Token | Raw | CAP_450 | Class@450 | NO_LIMIT | Class@NL |
| --- | ---: | ---: | --- | ---: | --- |
| p8_332 | ✓ | ✓ | dimension | ✓ | dimension |
| p8_337 | ✓ | ✓ | dimension | ✓ | dimension |
| p8_340 | ✓ | ✓ | line ✓ | ✓ | line ✓ |
| p8_346 | ✓ | ✗ cap | — | ✓ | dimension |
| p8_348 | ✓ | ✓ | dimension | ✓ | dimension |
| p8_351 | ✓ | ✓ | line ✓ | ✓ | line ✓ |
| p8_355 | ✓ | ✗ cap | — | ✓ | leader |
| p8_359 | ✓ | ✓ | line ✓ | ✓ | line ✓ |
| p8_367 | ✓ | ✓ | dimension | ✓ | dimension |
| p8_381 | ✓ | ✓ | dimension | ✓ | dimension |
| p8_430 | ✓ | ✓ | dimension | ✓ | dimension |
| p18_1143 | ✓ | ✓ | dimension | ✓ | dimension |
| p18_1162 | ✓ | ✗ cap | — | ✓ | leader |
| p18_1169 | ✓ | ✓ | rectangle ✓ | ✓ | rectangle ✓ |
| p18_1178 | ✓ | ✗ cap | — | ✓ | leader |
| p18_1186 | ✓ | ✗ cap | — | ✓ | leader |
| p24_1359 | ✓ | ✓ | line ✓ | ✓ | line ✓ |
| p24_1360 | ✓ | ✗ cap | — | ✓ | leader |
| p24_1361 | ✓ | ✗ cap | — | ✓ | leader |
| p24_1377 | ✓ | ✗ cap | — | ✓ | leader |
| p24_1385 | ✓ | ✗ cap | — | ✓ | line ✓ |

Death stage summary for the 21:

- **Dies at cap (450):** 9
- **Dies at dimension (while surviving 450):** 6 (+1 ambiguous)
- **Dies at leader (only after NO_LIMIT restores them):** 7
- **Survives extraction/classification @450:** 5 (of which 2 are retrieval-stage per audit)

---

## 9. Interpretation

What E2 **proves**:

1. **Classification is a major secondary bottleneck** after the cap: only 41.7% of
   CAP_450 survivors remain member-eligible.
2. **`_looks_like_dimension` is the production-cap classification killer** for this set
   (6 primary losses; 0 leader losses among survivors).
3. The dimension predicate fires on **any nearby digit**, including reaction text (`17K`)
   and the member’s own designation (`W21X44 [30]`).
4. **NO_LIMIT restores raw presence but classification still prevents eligibility** for
   8/9 recovered targets — mostly via `_looks_like_leader` on short strokes.
5. Associated gold geometries are **not** harmed by these classifiers in the measured set
   (8/8 stay `line` / eligible).
6. Other post-classification filters (symbol reclass, etc.) caused **0** audited primary
   losses here.

What E2 does **not** prove:

- That changing the dimension predicate would improve association accuracy.
- That NO_LIMIT is a viable production setting.
- That every dimension-classified stroke is “wrong” in all drawing contexts — only that
  these audited visible members are made ineligible by it.

---

## 10. Smallest Next Experiment

**Recommend: E3 — Member-vs-callout dimension-shadow diagnostic (measurement only).**

Hold CAP_450 fixed. For cap-surviving strokes that `_looks_like_dimension` currently flips,
shadow-evaluate a **read-only** alternative nearby-text rule (e.g. ignore digits that come
from the associated engineering token’s own bbox, or require dimension-arrow morphology)
and report only:

- how many of the 6 audited dimension losses would remain eligible
- false-flip risk on true dimension lines (associated-8 must stay clean; plus a sample of
  known dimension strokes)

Do **not** implement the rule in production. Do **not** change `_looks_like_dimension` yet.
Do **not** start Retrieval V3 — ranking is still downstream of eligibility.

A leader/weld-symbol experiment is secondary: leader cost appears mainly on the
NO_LIMIT-recovered short-stroke population, which still requires a cap-selection strategy
before those strokes exist under CAP_450.

---

## Artifacts and safety

**Created**

- `backend/scripts/rd_geometry_integration/classification_cost_experiment.py`
- `docs/validation/rd_geometry_integration/GEOMETRY_CLASSIFICATION_COST_REPORT.md`
- `docs/validation/rd_geometry_integration/classification_cost_results.jsonl`
- `docs/validation/rd_geometry_integration/classification_cost_summary.json`

**Modified**

- `backend/scripts/rd_geometry_integration/README.md` (index only)

**Verified untouched**

- `review_kit/gold_outcomes.jsonl` (SHA-256 `0fad4291…b976b155`)
- `retrieval.py`, `retrieval_v2.py`
- Production extraction / `_looks_like_dimension` / `_looks_like_leader` / filters
- GHX, Semantic Review, takeoff, ML/VLM
- Prior E1 / audit artifacts (read-only)
