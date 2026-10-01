# GEOMETRY OWNERSHIP E5.1

## Executive Verdict

**OWNERSHIP_GATE = READY_FOR_IMPLEMENTATION**

None of the 33 cases are missed own-label ownership. 30 are clearly unrelated annotations; 3 bare-digit cases remain unprovable and correctly require abstention. Deterministic ownership contract is the existing E3 identify_own_label_lines rule — no proximity-only expansion needed. Counterexamples (17K, 7/8, 23'-10") remain safe.

## 1. Why E5.1 was required

E5 closed Phase E with `IMPLEMENTATION_GATE = NEED_MORE_EVIDENCE` because `OWNERSHIP_UNESTABLISHED = 33`. V1 recovery/preservation looked strong, but ownership proof quality was the remaining blocker. E5.1 audits those 33 cases only — investigation, not implementation.

## 2. The 33 ownership-unestablished cases

Loaded from frozen E5 results (`sha=66d4d96f59014a7f0fd5e5f8483a504123203d76b2fc0d9d098bfae2d4fe7c15`). Count verified: **33**.

| token | project | page | member | nearby | pattern |
| --- | --- | ---: | --- | --- | --- |
| `springhill_lake_p7_733d0f9286_0008` | Springhill Lake | 7 | 'W18X40' | '5' | bare_digit |
| `springhill_lake_p7_733d0f9286_0009` | Springhill Lake | 7 | 'W18X40' | '5' | bare_digit |
| `springhill_lake_p7_82cf7a26a6_0358` | Springhill Lake | 7 | 'W18X71' | 'H24' | grid_or_axis_mark |
| `springhill_lake_p7_926145b0c8_0446` | Springhill Lake | 7 | 'W12' | 'H12' | grid_or_axis_mark |
| `springhill_lake_p7_98c2265533_0007` | Springhill Lake | 7 | 'W18X46' | 'H50' | grid_or_axis_mark |
| `springhill_lake_p7_b9b23d4717_0432` | Springhill Lake | 7 | 'W16X36' | '-0\'-2 1/2"' | dimension_or_note |
| `springhill_lake_p7_d5aec1a6c9_0434` | Springhill Lake | 7 | 'W16X36' | '-0\'-2 1/2"' | dimension_or_note |
| `springhill_lake_p7_fa5b05cdbe_0439` | Springhill Lake | 7 | 'W16X36' | '-0\'-2 1/2"' | dimension_or_note |
| `springhill_lake_p8_194a0f8a64_0005` | Springhill Lake | 8 | 'W18X35' | '1' | bare_digit |
| `springhill_lake_p8_1a2d40723d_0119` | Springhill Lake | 8 | 'W8X18' | 'S-311' | sheet_or_plate_mark |
| `springhill_lake_p8_1ea4c3889e_0109` | Springhill Lake | 8 | 'W18X46' | 'H14' | grid_or_axis_mark |
| `springhill_lake_p8_342940385c_0039` | Springhill Lake | 8 | 'W18X60' | 'H30' | grid_or_axis_mark |
| `springhill_lake_p8_360da977ba_0040` | Springhill Lake | 8 | 'W12' | 'H25' | grid_or_axis_mark |
| `springhill_lake_p8_cb5b9583ee_0110` | Springhill Lake | 8 | 'W16X26' | 'H15' | grid_or_axis_mark |
| `springhill_lake_p8_cdc426c010_0058` | Springhill Lake | 8 | 'W18X40' | 'H10' | grid_or_axis_mark |
| `springhill_lake_p8_d9d68d8333_0114` | Springhill Lake | 8 | 'HSS6X6X3/8' | 'L4X3-1/2X3/8' | other_member_designation |
| `struct_p7_00568632c9_0109` | Struct | 7 | 'W18X35' | 'R=16K' | reaction_or_load |
| `struct_p7_1fad790069_0098` | Struct | 7 | 'W18X35' | 'CL2' | grid_or_axis_mark |
| `struct_p7_90de8a857b_0070` | Struct | 7 | 'W27X84' | 'R=22K' | reaction_or_load |
| `struct_p7_acac241532_0110` | Struct | 7 | 'W14X22' | 'S505' | sheet_or_plate_mark |
| `struct_p7_bf22be207c_0071` | Struct | 7 | 'W27X84' | 'R=22K' | reaction_or_load |
| `struct_p7_df208bdb1d_0068` | Struct | 7 | 'W27X84' | 'R=22K' | reaction_or_load |
| `struct_p7_e1da060299_0057` | Struct | 7 | 'W21X44' | '(1*)' | quantity_mark |
| `struct_p7_f15bdfceac_0067` | Struct | 7 | 'W27X84' | 'R=22K' | reaction_or_load |
| `struct_p9_0705ea4d54_0233` | Struct | 9 | 'W12X19' | 'L3' | grid_or_axis_mark |
| `struct_p9_0c8b18d502_0387` | Struct | 9 | 'W18X35' | '(1*)' | quantity_mark |
| `struct_p9_3471d1443c_0039` | Struct | 9 | 'W14X22' | '(4*)' | quantity_mark |
| `struct_p9_42f37906f1_0018` | Struct | 9 | 'W14X22' | '(4*)' | quantity_mark |
| `struct_p9_5a11805e8f_0017` | Struct | 9 | 'W14X22' | '(4*)' | quantity_mark |
| `struct_p9_cfb876d49c_0237` | Struct | 9 | 'W12X19' | 'BP3' | sheet_or_plate_mark |
| `struct_p9_d0afc06cf4_0384` | Struct | 9 | 'W12X19' | 'BP4' | sheet_or_plate_mark |
| `struct_p9_f5d15208c0_0215` | Struct | 9 | 'W12X19' | 'BP3' | sheet_or_plate_mark |
| `structure_copy_p8_608256f151_0073` | Structure - Copy | 8 | 'C6X8' | 'WIDTH \'W\' > 2\'-0"' | dimension_or_note |

## 3. Ownership evidence inventory

| Evidence | Available | Positive | Negative | N/A |
| --- | ---: | ---: | ---: | ---: |
| same_source_word_ids | 0 | 0 | 33 | 0 |
| same_text_span | 33 | 0 | 33 | 0 |
| same_pdf_block_line | 33 | 0 | 33 | 0 |
| word_adjacency | 33 | 0 | 33 | 0 |
| bbox_overlap | 33 | 0 | 33 | 0 |
| bbox_containment | 33 | 0 | 33 | 0 |
| baseline_alignment | 0 | 0 | 0 | 33 |
| rotation_alignment | 0 | 0 | 0 | 33 |
| split_label_metadata | 0 | 0 | 33 | 0 |
| merged_label_metadata | 0 | 0 | 0 | 33 |

Availability ≠ proof. Nearest-text proximity is explicitly **not** treated as ownership.

## 4. Visual vs machine ownership

- Visual ownership yes: **0**
- Machine ownership provable yes: **0**
- Visual yes / machine no (representation gap): **0**
- Machine evidence sufficient: **0**

## 5. Deterministic ownership categories

- DETERMINISTIC_OWNERSHIP_PROVABLE: **0**
- DETERMINISTIC_OWNERSHIP_NOT_PROVABLE: **3**
- CLEARLY_UNRELATED_NUMERIC: **30**
- MEMBER_LABEL_SPLIT: **0**
- EXTRACTION_REPRESENTATION_GAP: **0**
- OTHER: **0**

## 6. Candidate ownership signals

Tested against the 33:
1. **Same text span / designation containment in nearby line text** — 0 positives (by E5 bucket construction).
2. **Same PDF block+line + word adjacency** — 0 true member↔numeric pairs.
3. **BBox overlap / containment with member label bbox** — 0 containments; 0 meaningful overlaps.
4. **source_word_ids / merge metadata** — not available on holdout live PDF path.
5. **E3 identify_own_label_lines** — already negative for all 33; remains the only proposed production ownership predicate.

## 7. Counterexample testing

- W30X90 + 17K not stripped: **True**
- Genuine 7/8 preserved: **True**
- Mixed 23'-10" preserved: **True**
- Own-label W21X44 [30] stripped: **True**

## 8. Genuine-dimension safety

No proposed expansion of ownership beyond E3 same-line designation ownership. Dimension-like nearby strings in the 33 (`-0'-2 1/2"`, `WIDTH 'W' > 2'-0"`) are classified **CLEARLY_UNRELATED** to the member designation (they are other annotations). V1 must not strip them; E5 already left them unchanged.

## 9. Unrelated-number safety

30 / 33 are clearly unrelated (grid/axis marks, reactions, sheet/plate marks, quantity marks, other member designations, dimension/note text). Proximity-only ownership would be dangerous here — and is rejected.

## 10. Split-label / extraction gaps

- MEMBER_LABEL_SPLIT: **0**
- EXTRACTION_REPRESENTATION_GAP: **0**
No case required split-label reconstruction to prove ownership. When Burrville own-label *is* proven (E3), digits already live inside the same extracted line/span (e.g. `W21X44  [30]`).

## 11. Quantitative results

- Total audited: **33**
- Deterministic ownership provable: **0**
- Deterministic ownership not provable: **3**
- Clearly unrelated: **30**
- Split-label: **0**
- Representation gap: **0**
- Other: **0**
- Resolved without fuzzy/proximity-only logic: **33 / 33**

## 12. Minimal ownership contract

**e3_own_label_line_ownership_v1**

OWNERSHIP_PROVEN only if:

1. A document line L is selected as production nearby text for the stroke.
2. L is identified as the member's own annotation by identify_own_label_lines: (a) L.text contains the member designation token, or (b) the member label center lies in L.bbox and L frames the label bbox; bare load callouts matching ^\d+(\.\d+)?\s*K$ are excluded.
3. Only then may digits be stripped from L.text before _looks_like_dimension.

Otherwise: **OWNERSHIP_UNESTABLISHED** → do not strip.

Explicit non-signals:

- Nearest geometry alone
- Nearest digit text alone / proximity-only
- Fuzzy string match
- Catalog / AISC existence
- Document prior
- ML / VLM

E5.1 found 0/33 unestablished cases where richer PDF word evidence deterministically proved ownership that E3 missed. Most are clearly unrelated annotations; remaining bare digits stay unproven → abstain.

## 13. Regression against E3/E4

- Gold SHA ok: **True** (`0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`)
- Extractor SHA ok: **True**
- E3 SHA ok: **True**
- E5 results SHA ok: **True**
- E3 own-label recoveries intact: **True**
- E4 genuine preserved: **True**
- Counterexamples pass: **True**

## 14. Limitations

- Holdout documents lack multimodal `document.json` / token `source_word_ids`; audit uses live PDF words.
- Visual judgments are recorded conservatively from crops + text pattern classes.
- Dimension-like strings in the 33 were not re-bucketed into E4 genuine controls; they are assessed only for *member-label ownership*.
- E5.1 does not expand Phase E with new projects.

## 15. FINAL OWNERSHIP GATE

**OWNERSHIP_GATE = READY_FOR_IMPLEMENTATION**

None of the 33 cases are missed own-label ownership. 30 are clearly unrelated annotations; 3 bare-digit cases remain unprovable and correctly require abstention. Deterministic ownership contract is the existing E3 identify_own_label_lines rule — no proximity-only expansion needed. Counterexamples (17K, 7/8, 23'-10") remain safe.

## 16. If READY: next implementation specification

### Next task only (do **not** execute in E5.1)

- **File:** `backend/services/engineering/geometry_extractor.py`
- **Site:** where `_nearby_text(...)` result is passed to `_looks_like_dimension(...)` during path classification.
- **Minimal change:** if the chosen nearby line is an own-label line under the E3 `identify_own_label_lines` contract (designation-token containment / label framed by annotation line; exclude bare `nK` loads), pass digit-stripped text into `_looks_like_dimension` only. Leader predicate and CAP_450 unchanged.
- **Guards:** no strip without ownership; never strip on proximity alone; never strip `17K`-class loads; never strip genuine fraction/length lines that are not own-label.
- **Expected:** `W21X44 [30]`-class own-label contamination → member-eligible; `7/8`, `23'-10"`, `17K`, grid marks, BP/S marks unchanged as dimension triggers when they are the nearby text.
- **Tests/fixtures:** E3 tokens p8_332/337/381/430; p8_348; p18_1143; E4 genuine controls; at least one E5 own-label recovery + one E5.1 unrelated mark (`H24` / `R=22K`).
- **Rollback:** revert the single digit-strip branch.

_NOT_READY / REPRESENTATION_GAP sections: not applicable._

## 17. Files changed

- `backend/scripts/rd_geometry_integration/ownership_evidence_audit_e5_1.py`
- `backend/tests/test_rd_geometry_ownership_e5_1.py`
- `docs/validation/rd_geometry_integration/ownership_evidence_e5_1_results.jsonl`
- `docs/validation/rd_geometry_integration/ownership_evidence_e5_1_summary.json`
- `docs/validation/rd_geometry_integration/GEOMETRY_OWNERSHIP_E5_1_REPORT.md`
- `docs/validation/rd_geometry_integration/ownership_e5_1_renders/`
- `docs/validation/rd_geometry_integration/ownership_e5_1_review.html`
- `backend/scripts/rd_geometry_integration/README.md`

## 18. Tests

See pytest invocation in the agent final response (phase + retrieval_v2 + E3 + E4 + E5 + E5.1).
