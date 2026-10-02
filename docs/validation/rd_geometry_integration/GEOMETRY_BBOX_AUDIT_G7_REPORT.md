# Geometry / BBox Representation Audit (G7)

Read-only audit of Burrville human-gold pages (p8 / p18 / p24) before any new text↔geometry association work.

**Document:** `doc_0d910a43b4a021e3`  
**Gold SHA:** `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`  
**Cases:** 75  
**G7_GATE = `REPRESENTATION_NOT_READY`**

## 1. Question

Before touching text↔geometry association, do we have reliable member-level geometry primitives and usable bounding boxes?

## 2. Population census (current artifact)

- **p8:** 433 objects; kinds={'line': 121, 'polyline': 14, 'rectangle': 8, 'symbol': 5, 'dimension': 12, 'leader': 270, 'arc': 3}; LOCAL=421, GIANT=11, COMPOUND=1, DEGENERATE=0; usable_local_member_kind=140; short_member_kind_retained=7
- **p18:** 433 objects; kinds={'line': 79, 'dimension': 101, 'polyline': 17, 'symbol': 9, 'rectangle': 39, 'leader': 188}; LOCAL=430, GIANT=3, COMPOUND=0, DEGENERATE=0; usable_local_member_kind=141; short_member_kind_retained=5
- **p24:** 384 objects; kinds={'line': 136, 'dimension': 45, 'polyline': 56, 'rectangle': 64, 'symbol': 15, 'leader': 68}; LOCAL=379, GIANT=2, COMPOUND=2, DEGENERATE=0; usable_local_member_kind=266; short_member_kind_retained=11

## 3. Key metrics

| Metric | Value |
|---|---:|
| Raw present (relevant visible-member cases) | 44 / 58 (0.76) |
| Current retention among raw-present | 6 / 44 (0.14) |
| Usable LOCAL bbox among retained primary | 17 / 17 (1.00) |
| Giant/compound flag rate (all cases) | 18 / 75 (0.24) |
| Short-stroke nearest retained | 0 / 21 |
| Leader-required with target present | 6 / 18 |
| Gold geometry coverage (8 associated) | 8 / 8 (1.00) |
| Visible-miss cases with usable local geometry now | 56 / 58 |

> **Interpretation note:** `usable local geometry` counts any retained member-kind LOCAL bbox near the label. It does **not** prove that the correct labeled member survived. The on-label stroke retention rate (0.14) is the stricter representation signal.

## 4. Dominant blockers

- **GEOMETRY_POPULATION_GAP:** 39
- **NO_MAJOR_REPRESENTATION_GAP:** 15
- **SEGMENTATION_GAP:** 3
- **RETRIEVAL_GAP:** 6
- **LEADER_TARGET_GAP:** 12

Failure-stage histogram (per gold case):
- `geometry_population_gap`: 36
- `representation_sufficient_for_case`: 8
- `segmentation_gap`: 3
- `retrieval_gap_not_representation`: 6
- `not_a_member_schedule`: 7
- `leader_target_gap`: 12
- `raw_geometry_gap`: 3

## 5. Giant polyline audit

Giant/compound primitives remain in the retained population on framing pages. Simple long lines (2 points, length ≈ bbox diagonal) are distinguishable from multi-point compound polylines via point_count + length/diagonal, but the current primitive is still one bbox for the whole path — **segmentation would be required** before treating giant bay polylines as member-level candidates.

### p8 giant examples

| geometry_id | kind | point_count | path_length | bbox |
|---|---|---:|---:|---|
| `geom_1885f3670e4e` | rectangle | 4 | 2524.68 | `[2735.88, 51.72, 2970.0, 2108.16]` |
| `geom_391188c4798e` | line | 2 | 988.051 | `[205.2, 1114.8, 1058.64, 1612.68]` |
| `geom_b2e19d2fbdfd` | line | 2 | 977.616 | `[636.6, 390.24, 1481.04, 882.84]` |
| `geom_79b4c492e763` | rectangle | 4 | 1614.72 | `[192.84, 379.56, 627.6, 1124.76]` |
| `geom_f6bf2271b085` | line | 2 | 856.384 | `[192.84, 379.56, 621.12, 1121.16]` |
| `geom_59a6f49b264f` | polyline | 6 | 1194.001 | `[1059.24, 882.84, 1481.04, 1612.56]` |

### p18 giant examples

| geometry_id | kind | point_count | path_length | bbox |
|---|---|---:|---:|---|
| `geom_8b1669b94681` | rectangle | 4 | 2524.68 | `[2735.88, 51.72, 2970.0, 2108.16]` |
| `geom_fd3ce72cb8da` | line | 2 | 2056.439 | `[2699.88, 51.72, 2699.88, 2108.16]` |
| `geom_c54124a64788` | line | 2 | 788.4 | `[1573.44, 1722.84, 2361.84, 1722.84]` |

### p24 giant examples

| geometry_id | kind | point_count | path_length | bbox |
|---|---|---:|---:|---|
| `geom_da9a403d42eb` | rectangle | 4 | 2524.68 | `[2735.88, 51.72, 2970.0, 2108.16]` |
| `geom_f9db71ef4e43` | line | 2 | 2056.439 | `[2699.88, 51.72, 2699.88, 2108.16]` |

## 6. Small / short-stroke classes

| Class | n_gold | raw_present | retained | usable_local |
|---|---:|---:|---:|---:|
| joist_scale_W | 30 | 29 | 7 | 30 |
| girder_W | 6 | 6 | 0 | 6 |
| short_W | 21 | 15 | 2 | 21 |
| plate | 4 | 2 | 3 | 4 |
| L_clip_angle | 13 | 2 | 0 | 12 |
| WT | 1 | 0 | 0 | 0 |

## 7. Leader target geometry

Leader-required gold cases: **18**. Target present: **6**. Leader present / target missing: **12**. Leader missing: **0**.

A leader stroke is not the member. Many detail/section callouts lose either the leader or the tip-neighborhood target under CAP_450 / classification.

## 8. Feature readiness for future association

| Feature | Exists? | Reliable? | Useful for association? | Notes |
|---|---|---|---|---|
| geometry bbox | YES | PARTIAL | YES | Present on all objects; giant/compound bboxes are common on framing pages. |
| centroid | YES | YES | YES | Derived from bbox; reliable when bbox is LOCAL. |
| path length | YES | YES | YES | Always populated for retained strokes. |
| orientation | YES | YES | YES | Present for lines; useful with label alignment later. |
| start/end | PARTIAL | PARTIAL | YES | Available via points[0]/points[-1] when points exist. |
| point count | YES | YES | PARTIAL | Useful for compound detection; not a member signal alone. |
| closed/open | NO | NO | PARTIAL | Not an explicit field; only inferable from kind/points. |
| geometry kind | YES | PARTIAL | YES | Reliable as extractor output; dimension/leader reclass still filters members. |
| label bbox | YES | YES | YES | Present in gold and document tokens. |
| label orientation | NO | NO | YES | Not stored on gold rows; would need derivation from text span. |
| text→geometry distance | PARTIAL | YES | YES | Computable from bboxes/centroids; not pre-stored. |
| leader endpoint | PARTIAL | PARTIAL | YES | Inferable from raw endpoints; often cap-dropped before retention. |
| source/path ID | PARTIAL | YES | PARTIAL | geometry_id stable in artifact; raw drawing id not persisted. |

## 9. Associated gold coverage

| token_id | gold_geometry_id | present | kind | bbox_quality |
|---|---|---|---|---|
| `token_p8_340` | `geom_095898d74240` | True | line | LOCAL_BBOX |
| `token_p8_395` | `geom_cf1c1b4a4515` | True | line | LOCAL_BBOX |
| `token_p8_396` | `geom_0b5ef1f9c497` | True | line | LOCAL_BBOX |
| `token_p8_397` | `geom_90463060295d` | True | line | LOCAL_BBOX |
| `token_p8_398` | `geom_485e0c733148` | True | line | LOCAL_BBOX |
| `token_p8_421` | `geom_5f6b0423ca08` | True | line | LOCAL_BBOX |
| `token_p8_427` | `geom_edbfa26d671d` | True | line | LOCAL_BBOX |
| `token_p8_432` | `geom_edbfa26d671d` | True | line | LOCAL_BBOX |

## 10. What this does **not** conclude

This audit does not score association accuracy. Retrieval may still rank the wrong LOCAL candidate even when representation is adequate for that neighborhood.

## 11. Verdict

**G7_GATE = `REPRESENTATION_NOT_READY`**

Member-level geometry population and/or bbox localization are still materially insufficient for a clean association experiment. Fix population retention (short strokes / detail targets), reduce giant-compound candidate dominance, and/or restore leader-target primitives before association work.

### What must be fixed before association

1. **GEOMETRY_POPULATION_GAP** — On-label strokes are raw-present for most visible members but only ~14% remain as usable member-kind geometry (CAP drop + dimension/leader reclass).
2. **LEADER_TARGET_GAP** — 12/18 leader-required cases lack retained tip-target geometry (leader ≠ member).
3. **SEGMENTATION_GAP** — Giant/compound primitives remain selectable; member-level association needs segmentation or hard exclusion of giant bboxes.
4. **Do not confuse** nearby LOCAL candidates (56/58 visible-miss neighborhoods) with correct-member survival — that is candidate availability noise, not representation readiness.

## 12. Safety

- Gold SHA unchanged: `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`
- Production files not modified by this audit script (`geometry_extractor.py` pre-existing own-label fix only)
- E3 / E5 / E5.1 frozen result artifacts not overwritten by G7
- Own-label dimension fix left untouched
- Note: E4's `test_repeated_execution_identical_results` can rewrite E4 control/results in-place; marked `@pytest.mark.slow` and excluded from the default G7 suite run

