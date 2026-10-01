# Geometry Representation Repair (G8)

R&D-only candidate population experiment. No association, no production extraction/CAP/retrieval changes, gold untouched.

**Document:** `doc_0d910a43b4a021e3`  
**Gold SHA:** `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`  
**Cases:** 75  
**G8_GATE = `REPRESENTATION_READY_FOR_ASSOCIATION`**

## 1. Question

Can we recover member-level geometry *candidates* from raw PyMuPDF drawings without changing production extraction or association?

## 2. Global metrics

| Metric | Value |
|---|---:|
| Raw visible-member cases | 58 |
| Raw geometry present | 56 |
| CAP retained (on-label) | 36 |
| Current member-kind retained | 5 |
| Cases with ≥1 R&D member candidate | 75 |
| Visible-miss recovered (R&D) | 43 |
| Short-stroke recovered | 22 |
| Compound segmentation candidates | 269 |
| Associated gold preserved | 8 |
| Giant nearby (A) | 16 |
| Giant among B member cands | 0 |

## 3. Per-page breakdown

### p8

| Metric | Value |
|---|---:|
| n | 50 |
| visible | 40 |
| raw_present | 40 |
| member_retained | 4 |
| b_candidates_cases | 50 |
| improved | 28 |
| leader_required | 0 |
| leader_recoverable | 0 |

### p18

| Metric | Value |
|---|---:|
| n | 14 |
| visible | 7 |
| raw_present | 7 |
| member_retained | 1 |
| b_candidates_cases | 14 |
| improved | 3 |
| leader_required | 7 |
| leader_recoverable | 4 |

### p24

| Metric | Value |
|---|---:|
| n | 11 |
| visible | 11 |
| raw_present | 9 |
| member_retained | 0 |
| b_candidates_cases | 11 |
| improved | 8 |
| leader_required | 11 |
| leader_recoverable | 8 |

## 4. Loss-class histogram

- `RECLASSIFIED_DIMENSION`: 21
- `RECLASSIFIED_LEADER`: 7
- `CAP_DROPPED`: 17
- `RETAINED_MEMBER`: 9
- `RAW_MISSING`: 9
- `RAW_AMBIGUOUS`: 12

## 5. Short-stroke findings

| Class | n | CAP_DROPPED | RECLASS_* | RETAINED_MEMBER | B recovered |
|---|---:|---:|---:|---:|---:|
| joist_scale_W | 30 | 3 | 20 | 6 | 25 |
| girder_W | 6 | 1 | 5 | 0 | 4 |
| short_W | 21 | 12 | 1 | 2 | 13 |
| plate | 4 | 0 | 1 | 1 | 4 |
| L_clip_angle | 13 | 1 | 1 | 0 | 13 |
| WT | 1 | 0 | 0 | 0 | 1 |

## 6. Compound / segmentation

- Compound paths considered: **625**
- Derived segments: **732**
- Segments near gold labels: **280**
- Useful member-scale segments (extent≤400.0): **710**
- Obvious false/large segments: **22**

Segmentation is vertex-split only, preserves `raw_id#segN` provenance, and never assigns beam/member identity.

## 7. Leader-target findings

| Status | Count |
|---|---:|
| TARGET_PRESENT_NON_MEMBER | 6 |
| TARGET_PRESENT_MEMBERLIKE | 5 |
| TARGET_MISSING_AFTER_CLASSIFICATION | 2 |
| TARGET_MISSING_AFTER_CAP | 5 |

Leader-required: 18. Memberlike or recoverable: 12.

## 8. Top before/after examples

| token | label | gold | A | B | B_n | change |
|---|---|---|---|---|---:|---|
| `token_p8_332` | W14X22 | no_valid_member | A_RECLASSIFIED | B_RECOVERED | 28 | improved |
| `token_p8_336` | W21X50 | no_valid_member | A_RECLASSIFIED | B_RECOVERED | 12 | improved |
| `token_p8_338` | W21X44 | no_valid_member | A_RECLASSIFIED | B_RECOVERED | 10 | improved |
| `token_p8_341` | W16X26 | no_valid_member | A_RECLASSIFIED | B_RECOVERED | 9 | improved |
| `token_p8_340` | W21X44 | associated | A_GOLD_PRESENT | B_GOLD_PRESERVED | 9 | preserved |
| `token_p8_395` | W16X31 | associated | A_GOLD_PRESENT | B_GOLD_PRESERVED | 10 | preserved |
| `token_p8_396` | W16X31 | associated | A_GOLD_PRESENT | B_GOLD_PRESERVED | 11 | preserved |

## 9. False / ambiguous candidate examples

- (none flagged beyond large vertex-split segments)

- `token_p18_1169`: loss=RAW_AMBIGUOUS; members=35; leader=TARGET_PRESENT_MEMBERLIKE; change=improved
- `token_p18_1173`: loss=RAW_AMBIGUOUS; members=25; leader=TARGET_MISSING_AFTER_CLASSIFICATION; change=improved
- `token_p18_1178`: loss=RAW_AMBIGUOUS; members=12; leader=TARGET_PRESENT_NON_MEMBER; change=improved_neighborhood_only
- `token_p18_1180`: loss=RAW_AMBIGUOUS; members=11; leader=TARGET_PRESENT_NON_MEMBER; change=improved_neighborhood_only
- `token_p18_1186`: loss=RAW_AMBIGUOUS; members=17; leader=TARGET_MISSING_AFTER_CAP; change=improved
- `token_p24_1359`: loss=RAW_AMBIGUOUS; members=24; leader=TARGET_PRESENT_MEMBERLIKE; change=improved
- `token_p24_1360`: loss=RAW_AMBIGUOUS; members=23; leader=TARGET_MISSING_AFTER_CLASSIFICATION; change=improved
- `token_p24_1362`: loss=RAW_AMBIGUOUS; members=39; leader=TARGET_PRESENT_MEMBERLIKE; change=improved

## 10. Verdict

**G8_GATE = `REPRESENTATION_READY_FOR_ASSOCIATION`**

R&D candidate population is sufficient to begin an isolated association experiment. Production extraction remains unchanged; association is not implemented here.

## 11. Next phase recommendation

Next: isolated association experiment over R&D candidates only (shadow ranking, no production wiring), stratified by loss class and leader.

## 12. Safety

- Gold SHA unchanged: `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`
- Production extractor / retrieval / CAP untouched by this script
- Associated gold 8/8 preserved: True

