# Executive Verdict

**NEED_MORE_EVIDENCE**

Holdout is promising (false_flips=0, recovered=43, genuine_preservation_rate=1.0, docs=3) but does not yet clear the conservative IMPLEMENT bar (need: docs>=3, own_label>=6 with recovery>=6 @rate>=0.8, genuine>=10 with preservation_rate=1.0, mixed>=3, ownership_unestablished <= max(3, own/2)). Current: own=46, mixed=6, unestablished=33, own_rate=0.9348.

## 1. What E5 tested

Multi-document shadow holdout of the narrowly scoped E3/E4 V1 rule: ignore numeric content only when it deterministically belongs to the member's **own label**, before `_looks_like_dimension`. Not general nearby-digit stripping. Production classifiers untouched.

## 2. Holdout documents/pages

| project | doc_id | pages | independent | why |
| --- | --- | --- | --- | --- |
| Springhill Lake | `doc_f6ddc4a7e233ffb0` | [7, 8] | True | Independent school structural set; dense framing pages with many WxxXxx [nn] designations and load callouts. |
| Structure - Copy | `doc_9414716bffc67596` | [6, 8] | True | Independent structural package; framing/detail pages with member labels and fraction/length annotations. |
| Struct | `doc_683e6eef0a945c9a` | [7, 9] | True | Independent structural drawings; high density of W-shape labels with trailing numeric annotation content. |

## 3. Dataset composition

- Total cases: **113**
- Documents: **3**
- Pages: **6**
- Own-label contamination: **46**
- Genuine-dimension controls: **12**
- Mixed member+dimension: **6**
- Unrelated-number controls: **16**
- Ownership unestablished: **33**

## 4. V0 vs V1 results

- Member recovery (own-label): **43**
- Genuine dimension preserved: **18** / 12
- False flips: **0**
- Unchanged: **70**
- Own-label recovery rate: **0.9348**
- Genuine preservation rate: **1.0**
- False-flip observed rate: **0.0** (holdout fraction only — not a production-safety estimate)
- Net recovered members: **43**

## 5. Own-label contamination cases

| token | project | page | nearby | V0 | V1 | outcome |
| --- | --- | ---: | --- | --- | --- | --- |
| `springhill_lake_p7_0265b90c3e_0437` | Springhill Lake | 7 | 'W16X36' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p7_1085570e39_0440` | Springhill Lake | 7 | 'W16X36' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p7_30386b6e9c_0436` | Springhill Lake | 7 | 'W16X50' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p7_3a5e6f470f_0002` | Springhill Lake | 7 | 'W21X44  (36)' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p7_71cee0689a_0433` | Springhill Lake | 7 | 'C6 FRAMES' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p7_8f96a33db5_0435` | Springhill Lake | 7 | 'W16X36' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p7_b92f37d408_0003` | Springhill Lake | 7 | 'W21X44  (36)' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p7_f7f730f7da_0010` | Springhill Lake | 7 | 'W14X22' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p8_0377431114_0012` | Springhill Lake | 8 | 'W21X55  (60)' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p8_1d2f170323_0004` | Springhill Lake | 8 | 'W21X62  (22)' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p8_1fa2271a0a_0251` | Springhill Lake | 8 | 'W18X50  (50)  c = 1"' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p8_1fcb9de517_0016` | Springhill Lake | 8 | 'W21X55  (60)' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p8_6edca2c49c_0013` | Springhill Lake | 8 | 'W18X35  (32)  c = 3/4"' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p8_afea06021a_0015` | Springhill Lake | 8 | 'W21X55  (60)' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p8_bc9ec11230_0010` | Springhill Lake | 8 | 'W24X94  (52)' | dimension | line | MEMBER_RECOVERED |
| `springhill_lake_p8_dcdae1eb2a_0011` | Springhill Lake | 8 | 'W24X94  (52)' | dimension | line | MEMBER_RECOVERED |
| `struct_p7_066ced5606_0044` | Struct | 7 | 'W21x44' | dimension | line | MEMBER_RECOVERED |
| `struct_p7_0737262739_0051` | Struct | 7 | 'W21x44' | dimension | line | MEMBER_RECOVERED |
| `struct_p7_2e08dc823d_0053` | Struct | 7 | 'W21x44' | dimension | line | MEMBER_RECOVERED |
| `struct_p7_35e6f5ca83_0048` | Struct | 7 | 'W21x44' | dimension | line | MEMBER_RECOVERED |
| `struct_p7_47fce0ed3e_0052` | Struct | 7 | 'W21x44' | dimension | line | MEMBER_RECOVERED |
| `struct_p7_72a21a8131_0045` | Struct | 7 | 'W21x44' | dimension | line | MEMBER_RECOVERED |
| `struct_p7_7a3d5b1969_0054` | Struct | 7 | 'W21x44' | dimension | line | MEMBER_RECOVERED |
| `struct_p7_7d6ef3de6e_0043` | Struct | 7 | 'W21x44' | dimension | line | MEMBER_RECOVERED |
| `struct_p9_0eafae0daf_0050` | Struct | 9 | 'W18x40 [34]' | dimension | line | MEMBER_RECOVERED |
| `struct_p9_1148e17029_0051` | Struct | 9 | 'W18x35 [34] C=3/4"' | dimension | line | MEMBER_RECOVERED |
| `struct_p9_24424c2836_0059` | Struct | 9 | 'W18x40 [34] C=3/4"' | dimension | line | MEMBER_RECOVERED |
| `struct_p9_260d7fb24f_0053` | Struct | 9 | 'W18x35 [34] C=3/4"' | dimension | line | MEMBER_RECOVERED |
| `struct_p9_2d6b6f3056_0060` | Struct | 9 | 'W18x40 [34] C=3/4"' | dimension | line | MEMBER_RECOVERED |
| `struct_p9_7d39d3da9b_0046` | Struct | 9 | 'W30x108 [46]' | dimension | line | MEMBER_RECOVERED |
| `struct_p9_aa4eadd5dc_0037` | Struct | 9 | 'W24x55 [20]' | dimension | line | MEMBER_RECOVERED |
| `struct_p9_e4c909db01_0038` | Struct | 9 | 'W24x55 [20]' | dimension | line | MEMBER_RECOVERED |
| `structure_copy_p6_0c0417fa3e_0072` | Structure - Copy | 6 | 'L3x3x3/16' | dimension | line | MEMBER_RECOVERED |
| `structure_copy_p6_3d152ff6bb_0445` | Structure - Copy | 6 | 'L2x2x3/16  BRIDGING' | leader | leader | NO_CHANGE |
| `structure_copy_p6_5c904fcb81_0082` | Structure - Copy | 6 | 'L3x3x3/16' | dimension | line | MEMBER_RECOVERED |
| `structure_copy_p6_ac1fb257bb_0435` | Structure - Copy | 6 | 'L3x3x3/16' | leader | leader | NO_CHANGE |
| `structure_copy_p6_e1bb65cacf_0326` | Structure - Copy | 6 | 'L2x2x3/16  BRIDGING' | leader | leader | NO_CHANGE |
| `structure_copy_p6_e45d9b7959_0077` | Structure - Copy | 6 | 'L3x3x3/16' | dimension | line | MEMBER_RECOVERED |
| `structure_copy_p8_26aafbfbaa_0165` | Structure - Copy | 8 | 'C6x8.2, U.N.O.' | dimension | line | MEMBER_RECOVERED |
| `structure_copy_p8_26aafbfbaa_0166` | Structure - Copy | 8 | 'C6x8.2, U.N.O.' | dimension | line | MEMBER_RECOVERED |

## 6. Genuine-dimension controls

| token | project | page | nearby | V0 | V1 | outcome |
| --- | --- | ---: | --- | --- | --- | --- |
| `structure_copy_p6_64b55a2b26_0120` | Structure - Copy | 6 | '3"' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p6_73f6748a7c_0256` | Structure - Copy | 6 | '1/4' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p6_e5bcfb1a91_0254` | Structure - Copy | 6 | '1/4' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p6_e908fa0dc5_0250` | Structure - Copy | 6 | '1/4' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p8_0deffebd49_0029` | Structure - Copy | 8 | '3"' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p8_1ddfb908b8_0037` | Structure - Copy | 8 | '1/8' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p8_6af0dbd3f7_0044` | Structure - Copy | 8 | '1/8' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p8_72f09dea22_0043` | Structure - Copy | 8 | '1/8' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p8_74877832aa_0030` | Structure - Copy | 8 | '3"' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p8_a7585b821e_0042` | Structure - Copy | 8 | '1/8' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p8_d6a5f24ca1_0036` | Structure - Copy | 8 | '1/8' | dimension | dimension | DIMENSION_PRESERVED |
| `structure_copy_p8_f3a50916bd_0035` | Structure - Copy | 8 | '1/8' | dimension | dimension | DIMENSION_PRESERVED |

## 7. Mixed/negative controls

Mixed member+dimension: **6**; unrelated numeric: **16**.

| token | bucket | nearby | label | outcome |
| --- | --- | --- | --- | --- |
| `springhill_lake_p7_a46d2ea6f8_0019` | MIXED_MEMBER_DIMENSION | '6"' | 'W8X18' | DIMENSION_PRESERVED |
| `springhill_lake_p7_ce4c5d14fd_0241` | MIXED_MEMBER_DIMENSION | '10\' - 2"' | 'W12' | DIMENSION_PRESERVED |
| `springhill_lake_p7_cfb1926ab0_0244` | MIXED_MEMBER_DIMENSION | '9\' - 1"' | 'W12' | DIMENSION_PRESERVED |
| `springhill_lake_p8_924e86f46f_0127` | MIXED_MEMBER_DIMENSION | '5"' | 'W8X18' | DIMENSION_PRESERVED |
| `struct_p7_8f17a172e8_0235` | MIXED_MEMBER_DIMENSION | '11\'-3"' | 'W14X22' | DIMENSION_PRESERVED |
| `struct_p9_0176019ec0_0065` | MIXED_MEMBER_DIMENSION | '6"' | 'W18X40' | DIMENSION_PRESERVED |
| `springhill_lake_p7_0354157316_0053` | UNRELATED_NUMERIC | '17K' | 'HSS14X10X3/8' | UNCHANGED_DIMENSION |
| `springhill_lake_p7_1d5bd2c092_0016` | UNRELATED_NUMERIC | '22K' | 'W12' | UNCHANGED_DIMENSION |
| `springhill_lake_p7_a2de29b779_0005` | UNRELATED_NUMERIC | '22K' | 'W16X40' | UNCHANGED_DIMENSION |
| `springhill_lake_p7_b314cff513_0006` | UNRELATED_NUMERIC | '18K' | 'W18X40' | UNCHANGED_DIMENSION |
| `springhill_lake_p7_b8a23ee411_0011` | UNRELATED_NUMERIC | '28K' | 'W12' | UNCHANGED_DIMENSION |
| `springhill_lake_p7_dedc7c9da5_0316` | UNRELATED_NUMERIC | '26K' | 'W8X24' | UNCHANGED_DIMENSION |
| `springhill_lake_p7_e7f0f6bdba_0013` | UNRELATED_NUMERIC | '18K' | 'W12' | UNCHANGED_DIMENSION |
| `springhill_lake_p7_fe99975169_0317` | UNRELATED_NUMERIC | '26K' | 'W8X24' | UNCHANGED_DIMENSION |
| `springhill_lake_p8_09b06c4bdc_0047` | UNRELATED_NUMERIC | '42K' | 'W27X84' | UNCHANGED_DIMENSION |
| `springhill_lake_p8_495fbdedd2_0044` | UNRELATED_NUMERIC | '42K' | 'W27X84' | UNCHANGED_DIMENSION |
| `springhill_lake_p8_7b577babb9_0244` | UNRELATED_NUMERIC | '64K' | 'W8X24' | UNCHANGED_DIMENSION |
| `springhill_lake_p8_8c190dbb8e_0245` | UNRELATED_NUMERIC | '64K' | 'W8X24' | UNCHANGED_DIMENSION |
| `springhill_lake_p8_9d863e1485_0008` | UNRELATED_NUMERIC | '21K' | 'W12' | UNCHANGED_DIMENSION |
| `springhill_lake_p8_c34dcf796d_0003` | UNRELATED_NUMERIC | '32K' | 'W21X50' | UNCHANGED_DIMENSION |
| `springhill_lake_p8_ecd95ce384_0006` | UNRELATED_NUMERIC | '23K' | 'W12' | UNCHANGED_DIMENSION |
| `springhill_lake_p8_ffbf96f216_0048` | UNRELATED_NUMERIC | '44K' | 'W27X94' | UNCHANGED_DIMENSION |

## 8. False-flip audit

No dangerous false flips observed in this holdout sample.


## 9. Visual QA findings

QA crops under `dimension_holdout_e5_renders/` (80 files). Review page: `dimension_holdout_e5_review.html`.
Every changed case was rendered. Overlay: geometry (green), label (blue), own-label (orange dashed), trigger (red).

## 10. Regression against E3/E4

- Gold SHA ok: **True** (`0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`)
- Extractor SHA ok: **True**
- E3 results SHA ok: **True**
- E3 own-label 4/4: **True**
- E3 W30X90/17K preserved: **True**
- E3 7/8 genuine preserved: **True**
- E4 genuine preserved 25/25, false flips 0: **True**
- Regression pass: **True**

## 11. Limitations

- Holdout uses live PDF text/drawing extraction (no prebuilt multimodal geometry.json for these docs).
- Nearby radius fixed at 48 pt (production default) without per-page scale artifacts.
- Case association is stroke↔nearest digit text under CAP_450 — not human gold.
- Sample is still a small slice of the full testing corpus.
- Zero false flips ≠ production safety.
- Burrville remains the only project with frozen human geometry gold.

## 12. Final implementation gate

**IMPLEMENTATION_GATE = NEED_MORE_EVIDENCE**

Holdout is promising (false_flips=0, recovered=43, genuine_preservation_rate=1.0, docs=3) but does not yet clear the conservative IMPLEMENT bar (need: docs>=3, own_label>=6 with recovery>=6 @rate>=0.8, genuine>=10 with preservation_rate=1.0, mixed>=3, ownership_unestablished <= max(3, own/2)). Current: own=46, mixed=6, unestablished=33, own_rate=0.9348.

## 13. If IMPLEMENT: next-task implementation specification

_Not applicable — gate is not IMPLEMENT._

## 14. If DO_NOT_IMPLEMENT: failure analysis

_Not applicable._

## 15. If NEED_MORE_EVIDENCE: exact missing evidence

Holdout is promising (false_flips=0, recovered=43, genuine_preservation_rate=1.0, docs=3) but does not yet clear the conservative IMPLEMENT bar (need: docs>=3, own_label>=6 with recovery>=6 @rate>=0.8, genuine>=10 with preservation_rate=1.0, mixed>=3, ownership_unestablished <= max(3, own/2)). Current: own=46, mixed=6, unestablished=33, own_rate=0.9348.

Minimum additional evidence before re-opening IMPLEMENT:
- ≥1 additional independent project with prebuilt or audited geometry association (not only live nearest-text pairing)
- ≥10 additional own-label contamination recoveries across ≥2 new pages types (plan + detail)
- ≥10 additional genuine-dimension controls including more Category-C shared-digit cases
- Explicit audit of OWNERSHIP_UNESTABLISHED residual rate

## 16. Files changed

- `backend/scripts/rd_geometry_integration/multi_document_dimension_holdout.py`
- `backend/tests/test_rd_geometry_dimension_holdout_e5.py`
- `docs/validation/rd_geometry_integration/dimension_holdout_e5_results.jsonl`
- `docs/validation/rd_geometry_integration/dimension_holdout_e5_summary.json`
- `docs/validation/rd_geometry_integration/GEOMETRY_DIMENSION_HOLDOUT_E5_REPORT.md`
- `docs/validation/rd_geometry_integration/dimension_holdout_e5_renders/`
- `docs/validation/rd_geometry_integration/dimension_holdout_e5_review.html`
- `backend/scripts/rd_geometry_integration/README.md`

## 17. Test results

See E5 run log / pytest invocation in the agent final response. Required suite: phase + retrieval_v2 + E3 + E4 + E5.
