# E4 — Genuine-Dimension Control Expansion + V1 False-Flip Diagnostic
## 1. Executive conclusion
- Defensible genuine-dimension controls identified: **25**
- Remained dimension under V1: **25**
- False dimension→member flips: **0**
- E3 own-label recovery regression: **4/4**
- V1 production-ready? **No.** E4 provides additional evidence but does not establish production safety. Zero dangerous false flips on the Burrville control set (genuine n=25, Category C n=8) supports considering a narrowly scoped production-change experiment later — not implemented in E4. Multi-document holdout still required.

## 2. Scope
- Burrville pages **p8, p18, p24** (`doc_0d910a43b4a021e3`)
- Sources: `geometry.json` dimension objects + `document.json` nearby text; E3 regression tokens via CAP_450 fingerprints
- Control set expanded because E3 had only **n=1** genuine-dimension control
- Acceptance rule: production `kind=dimension`, length≥12, nearby text matches fraction / length / inch / plate-thickness patterns, not member designations, loads, dates, or scales. Insufficient cases recorded but not counted as genuine.
- V1 reused from E3 (`classify_shadow_ignore_own_numbers`) without modification

## 3. Control-set composition
| category | inspected | accepted | ambiguous | insufficient |
| --- | ---: | ---: | ---: | ---: |
| A | 17 | 11 | 0 | 0 |
| B | 18 | 6 | 0 | 0 |
| C | 13 | 8 | 0 | 0 |
| D | 4 | 4 | 0 | 0 |
| E | 1 | 1 | 0 | 0 |

Categories: A=fraction, B=length/inch, C=near member, D=own-label contamination, E=unrelated numeric.

## 4. V0 vs V1 results
| control category | V0 dimension | V1 dimension | changes | false flips |
| --- | ---: | ---: | ---: | ---: |
| A | 11 | 11 | 0 | 0 |
| B | 6 | 6 | 0 | 0 |
| C | 8 | 8 | 0 | 0 |
| D | 4 | 0 | 4 | 0 |
| E | 1 | 1 | 0 | 0 |

## 5. Genuine-dimension safety
No genuine-dimension control flipped dimension→member under V1 in this Burrville control set.

## 6. Difficult member + dimension cases
| control_id | page | member | trigger | V0 | V1 | change | safety |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| gdim_p8_geom_593de4cf85ad | 8 | 'W12X16  [15]' | '23\' - 10"' | dim | dim | DIMENSION_PRESERVED | SAFE_OWN_LABEL_REMOVAL |
| gdim_p8_geom_b17916eb7117 | 8 | 'W14X22  [23]' | '23\' - 10"' | dim | dim | DIMENSION_PRESERVED | SAFE_OWN_LABEL_REMOVAL |
| gdim_p8_geom_d692ed561875 | 8 | 'W16X26  [28]' | '31\' - 10"' | dim | dim | DIMENSION_PRESERVED | SAFE_OWN_LABEL_REMOVAL |
| gdim_p18_geom_65f49b170a85 | 18 | 'L4X4X1/4 TYP' | '1" MAX' | dim | dim | DIMENSION_PRESERVED | SAFE_OWN_LABEL_REMOVAL |
| gdim_p18_geom_6bcfc13d3067 | 18 | 'W14X43 TO' | '2"' | dim | dim | DIMENSION_PRESERVED | SAFE_OWN_LABEL_REMOVAL |
| gdim_p24_geom_0b01d943fbd9 | 24 | 'L4X4X3/8 HGR, TYP' | '1/2"' | dim | dim | DIMENSION_PRESERVED | SAFE_OWN_LABEL_REMOVAL |
| gdim_p24_geom_679b8ab0e077 | 24 | 'L4x4x3/8 ' | '3/16' | dim | dim | DIMENSION_PRESERVED | SAFE_OWN_LABEL_REMOVAL |
| gdim_p24_geom_7bdc3406efaa | 24 | 'L4x4x3/8 DSA' | '3/16' | dim | dim | DIMENSION_PRESERVED | SAFE_OWN_LABEL_REMOVAL |

Interpretation: V1 only strips digits when the production nearby line is identified as the member's own annotation. Genuine dimension text that is merely nearby is not treated as own-label evidence.

## 7. E3 regression check
| token | expected | V0 dim | V1 dim | V1 member | change | pass |
| --- | --- | --- | --- | --- | --- | --- |
| token_p8_332 | V0=dim, V1=member recovered | True | False | True | DIMENSION_TO_MEMBER | YES |
| token_p8_337 | V0=dim, V1=member recovered | True | False | True | DIMENSION_TO_MEMBER | YES |
| token_p8_381 | V0=dim, V1=member recovered | True | False | True | DIMENSION_TO_MEMBER | YES |
| token_p8_430 | V0=dim, V1=member recovered | True | False | True | DIMENSION_TO_MEMBER | YES |
| token_p8_348 | V0=dim, V1=dim (17K unrelated) | True | True | False | DIMENSION_PRESERVED | YES |
| token_p18_1143 | V0=dim, V1=dim (7/8 genuine) | True | True | False | DIMENSION_PRESERVED | YES |

## 8. Visual QA
Renders written under `backend/scripts/rd_geometry_integration/dimension_control_renders/` (15 files). Overlays: geometry (green), label (blue), own-label (orange dashed), trigger text (red).
- `e3reg_token_p18_1143_p18.png`
- `e3reg_token_p8_332_p8.png`
- `e3reg_token_p8_337_p8.png`
- `e3reg_token_p8_348_p8.png`
- `e3reg_token_p8_381_p8.png`
- `e3reg_token_p8_430_p8.png`
- `gdim_p18_geom_1232c9e584e5_p18.png`
- `gdim_p18_geom_3edfd36115a7_p18.png`
- `gdim_p18_geom_63f918a23a5b_p18.png`
- `gdim_p18_geom_65f49b170a85_p18.png`
- `gdim_p18_geom_6bfac3628a2d_p18.png`
- `gdim_p8_geom_593de4cf85ad_p8.png`
- `gdim_p8_geom_a07e7d6f70fc_p8.png`
- `gdim_p8_geom_b17916eb7117_p8.png`
- `gdim_p8_geom_d692ed561875_p8.png`

## 9. Metrics
- genuine_dimension_n: **25**
- preserved_n: **25**
- false_flip_n: **0**
- false_flip_rate: **0.0** (observed Burrville fraction only — not a production-safety estimate)
- ambiguous_n: **0**
- insufficient_n: **0**
- own_label_regression_n: **4**
- unrelated_numeric_n: **1**
- category_C_genuine_n: **8**
- own_label_context_genuine_n: **9**
- E3 known own-label recovery (separate): **4/4** (regression pass=True)

False-flip rate is an observed fraction on this Burrville control set only; it is **not** a reliable production-safety estimate.

## 10. Evidence limitations
- Sample limited to Burrville p8/p18/p24 R&D pages only
- Many schedule-table fractions on p18 share similar geometry; dedupe reduces effective diversity
- Category C population is sparse at ≤100 pt member↔dimension pairing
- Plate-thickness callouts (`3/8" PL TYP`) accepted as dimension-like with medium confidence — not traditional length dimensions
- Visual QA is diagnostic, not a substitute for multi-project sampling
- E4 does **not** establish production safety for V1

## 11. Recommendation
**A** — E4 provides additional evidence but does not establish production safety. Zero dangerous false flips on the Burrville control set (genuine n=25, Category C n=8) supports considering a narrowly scoped production-change experiment later — not implemented in E4. Multi-document holdout still required.

If pursued later (not in E4): smallest next step would be a narrowly scoped shadow flag gated to member-designation own-label digit stripping only, with a multi-document false-flip holdout — **not implemented here**.
