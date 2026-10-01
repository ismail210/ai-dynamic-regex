# D-Case Forensics: `token_p24_1359`

**Gate: `D_CASE_ISOLATED`**

**Scope:** Read-only forensic diagnosis of the single G9 false-association audit Class D case.  
**No G10. No gold/G8/G9/production changes.**

---

## Executive Diagnosis

G9 ranks a **405 pt vertical wall/hatch line** above a **27 pt vertex-split segment** of the tip `plate_or_symbol` that corresponds to the L6 relieving angle.

The wrong decision occurs at **G9 ranking after eligibility** — both candidates are present and eligible; the feature composition favors the long LINE.

---

## FACTUAL EVIDENCE vs INFERENCE

### FACTS
- Label `L6x3-1/2x3/8` on p24; human gold `no_valid_member` (reason: leader → small L6 angle; old overlay = long wall).
- G8 `leader_tip` = G9 `leader_tip` = `[664.32, 517.92]`.
- Selected: `rnd_raw_p24_480_d0c0ca5e54d7` len=405, kind=LINE_MEMBER_CANDIDATE, der=on_label_retained, rank=1, score=**0.6002**.
- Correct (audit): `raw_p24_10_9d8fbf0dfe5b#seg1` len=27, kind=SEGMENT_MEMBER_CANDIDATE, der=vertex_split, rank=2, score=**0.4797**.
- Tip distances: wall **21.0** pt · correct seg **23.28** pt · parent plate_or_symbol **23.28** pt.
- Tip role labels exist in G8 `leader_audit` but are not inputs to G9 `score_components`.
- Frozen-set search: **1** ASSOCIATED long-over-short-segment case (`token_p24_1359` only).
- Leader ASSOCIATED count in frozen 75: **2** (`p18_1188` short tip = B; `p24_1359` = D).

### INFERENCES
- Ownership should follow the tip toward the short angle/plate, not the long wall.
- Ranking priors (LINE kind, retained provenance, segment penalty) + near-tied tip distance explain the inversion.
- This is not yet evidence of a broad G9 failure class in the frozen Burrville set.

---

## 1. Pipeline Trace

| Stage | Value |
|---|---|
| Label | `L6x3-1/2x3/8` bbox `[681.0, 505.58, 740.78, 518.18]` |
| Gold | `no_valid_member` / missing_retrieval / leader_required |
| G8 loss | `RAW_AMBIGUOUS` · A=`A_RAW_AMBIGUOUS` · B=`B_RECOVERED` |
| Leader status | `TARGET_PRESENT_MEMBERLIKE` |
| G9 mode | `leader` |
| G9 decision | `ASSOCIATED` → `rnd_raw_p24_480_d0c0ca5e54d7` |
| Wrong locus | **G9_RANKING_AFTER_ELIGIBILITY** |

Gold SHA (unchanged): `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`

---

## 2. Selected Candidate — `rnd_raw_p24_480_d0c0ca5e54d7`

| Field | Value |
|---|---|
| source_raw_id | `raw_p24_480_d0c0ca5e54d7` |
| source_geometry_id | `geom_3b848d5ef250` |
| candidate_kind | LINE_MEMBER_CANDIDATE |
| derivation | on_label_retained |
| current_kind (G8) | line |
| bbox | `[643.32, 138.96, 643.32, 543.96]` |
| length | 405.0 |
| orientation | -90° |
| distance_pt (label) | 37.68 |
| centroid_distance_pt | 183.327 |
| tip distance | 21.0 |
| G9 rank / score | 1 / 0.6002 |
| leader_score | 0.58 |
| kind_score | 1.0 |
| provenance_score | 1.0 |
| penalty | 0.0 |

**Why attractive (facts):** full LINE prior, retained provenance, length still ≤520 so length_score=1.0, tip beside the long vertical stroke, no segment penalty. This geometry is also in the historical gold `candidate_geometry_ids` list as the wrong wall overlay.

---

## 3. Correct Candidate — `raw_p24_10_9d8fbf0dfe5b#seg1`

| Field | Value |
|---|---|
| source_raw_id | `raw_p24_10_9d8fbf0dfe5b` |
| parent tip role | plate_or_symbol @ tip_distance=23.28 |
| candidate_kind | SEGMENT_MEMBER_CANDIDATE |
| derivation | vertex_split (segment_index=1) |
| bbox | `[641.04, 516.96, 641.04, 543.96]` |
| parent bbox | `[625.32, 516.96, 641.04, 543.96]` |
| length | 27.0 |
| orientation | 90° |
| distance_pt (label) | 39.96 |
| tip distance | 23.28 |
| G9 rank / score | 2 / 0.4797 |
| leader_score | 0.5344 |
| kind_score | 0.72 |
| provenance_score | 0.55 |
| penalty | 0.05 |

Parent plate is **not** kept as a whole `PLATE_MEMBER_CANDIDATE` in G8 B — only split segments.

---

## 4. Leader Trace

```
label L6x3-1/2x3/8
  └─ leader → tip (664.32, 517.92)
        ├─ tip_d=0.00  leader_like   raw_p24_4088        (pointer; not in B)
        ├─ tip_d=21.0  member_like   raw_p24_480 wall    ← G9 selected
        └─ tip_d=23.28 plate_or_symbol raw_p24_10 angle  ← correct family (#seg1 rank 2)
```

- Endpoint **is** preserved in G8/G9.
- Endpoint geometry **is** used (`leader_score`).
- Tip **role** (`plate_or_symbol` vs `member_like`) is **not** used by the scorer.

---

## 5. G9 Decision Reconstruction

Fixed weights: distance=0.34, bbox=0.18, orient=0.12, length=0.12, kind=0.12, leader=0.08, provenance=0.04.

| Contribution | Selected wall | Correct seg | Δ (sel−cor) |
|---|---:|---:|---:|
| distance | 0.1799 | 0.1702 | 0.0097 |
| bbox | 0.028 | 0.0224 | 0.0056 |
| orient | 0.066 | 0.066 | 0.0 |
| length | 0.12 | 0.12 | 0.0 |
| kind | 0.12 | 0.0864 | 0.0336 |
| leader | 0.0464 | 0.0428 | 0.0036 |
| provenance | 0.04 | 0.022 | 0.018 |
| −penalty | -0.0 | -0.05 | 0.05 |
| **total** | **0.6002** | **0.4797** | **0.1205** |

Dominant factual drivers of the wall win: **segment penalty**, **LINE vs SEGMENT kind prior**, **retained vs vertex_split provenance**. Tip/label distances are nearly tied and do not decide the case alone.

---

## 6. Failure Mechanisms (evidence-backed)

| Code | Mechanism | Applies? |
|---|---|---|
| D | LONG_WALL_GEOMETRY_DOMINATES_DISTANCE | **Yes** |
| C | SHORT_TARGET_DISTANCE_DISADVANTAGED | **Yes** |
| G | RANKING_FEATURE ISSUE | **Yes** |
| B | LEADER_ENDPOINT_REPRESENTED_BUT_NOT_USED (roles unused) | **Yes** (nuance) |
| F | CANDIDATE_GENERATION/SEGMENTATION ISSUE | **Yes** (secondary) |
| A | LEADER_ENDPOINT_NOT_REPRESENTED | No |
| E | CANDIDATE_CLASSIFICATION_ERROR | No |

---

## 7. Broader Pattern Search (frozen artifacts only)

- Leader-required labels: 18
- Leader ASSOCIATED: 2 (`token_p18_1188`, `token_p24_1359`)
- ASSOCIATED long≥200 over short SEGMENT/plate/small: **1** → only `token_p24_1359`
- Tip `plate_or_symbol` + ASSOCIATED selected length>150: **1** → only `token_p24_1359`

Contrast: `token_p18_1188` selected a short CAP tip stroke (audited **B**), not a long wall.

**Do not classify other tokens as D** — the false-association audit did not.

---

## 8. Decision Gate

# `D_CASE_ISOLATED`

Recommend **no G10** at this time.

If a future holdout shows the same long-wall-vs-short-tip inversion repeatedly, a **narrowly scoped READ-ONLY decision-policy experiment specification** (not an implementation) would be the next step — e.g. document how tip-role or length-vs-tip features would change ordering under frozen G8 candidates. That experiment is **not** started here.

---

## Safety

- Gold SHA: `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155` (matches expected)
- G8 results SHA: `1931707165664d9e8e6ea198171624b9f9d8bb25dda2edd40d86619126ed3c44`
- G9 results SHA: `b459522eb097c285a359bd01a2be61c389daeded6415f236b6a0c47323cb4814`
- G8/G9 scripts and `geometry_extractor.py` not modified by this forensics emit
- No weights/thresholds/gold/G10 changes

See also: `token_p24_1359_forensics.json`, `review.html`
