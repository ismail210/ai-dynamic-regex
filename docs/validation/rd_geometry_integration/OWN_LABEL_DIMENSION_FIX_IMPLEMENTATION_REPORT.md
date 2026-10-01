# Own-Label Dimension Fix

## 1. Approved hypothesis

Proven own-label numeric content (e.g. `W21X44 [30]`) must not trigger
`_looks_like_dimension`. Ownership is established only by the E3
`identify_own_label_lines` contract. If ownership is not proven, production
behavior is unchanged.

## 2. Exact production change

**File:** `backend/services/engineering/geometry_extractor.py` only.

| Addition | Role |
| --- | --- |
| `identify_own_label_lines` | Production port of E3 ownership |
| `_member_designation_token` | Extract designation from nearby annotation text |
| `_strip_digits` | Digit removal for proven own-label text only |
| `_nearby_text_and_line` | Return winning nearby line object (for ownership) |
| `_nearby_text_for_dimension` | Strip digits iff ownership proven |
| Call-site in `extract_geometry` | Use filtered text for dimension predicate only |

Leader detection, CAP_450, path ordering, and stored `nearby_text` on geometry
objects are unchanged (raw nearby text is still recorded).

## 3. Ownership rule used

**OWNERSHIP_PROVEN** only if:

1. Production nearby line `L` is selected.
2. `L.text` yields a member designation token
   (`W|WT|HSS|C|MC…` or complete `L#X#X…` with thickness).
3. `identify_own_label_lines` marks `L` as own-label for that token
   (token contained in line text / label framed by annotation line).
4. Bare loads matching `^\d+(\.\d+)?\s*K$` are never own-label.

Otherwise: **do not strip**.

Explicit non-signals: proximity-only, fuzzy match, catalog, document prior, ML.

## 4. Positive cases

| Case | Nearby | V0 dim | V1 dim |
| --- | --- | --- | --- |
| E3 p8_337 style | `W21X44  [30]` | yes | no (member-eligible) |
| E3 p8_332 style | `W14X22  [25]` | yes | no |
| E3 p8_381 style | `W18X35  [35]` | yes | no |
| E3 p8_430 style | `W18X35  [28]` | yes | no |

`extract_geometry` integration: long stroke + own-label nearby → kind ≠ `dimension`.

## 5. Genuine-dimension controls

| Nearby | Remains dimension |
| --- | --- |
| `7/8` | yes |
| `23' - 10"` | yes |

Digits are not stripped because these lines are not member designations under
the ownership contract.

## 6. Unrelated numeric controls

| Nearby | Stripped? | Dimension |
| --- | --- | --- |
| `17K` (near W30X90) | no | yes |
| `H24` / `H12` | no | yes |
| `R=22K` | no | yes |
| `BP3` / `S-311` / `(4*)` | no | yes |
| `L4X3-1/2X3/8` | no | yes |
| `-0'-2 1/2"` / `WIDTH 'W' > 2'-0"` | no | yes |

## 7. Mixed cases

Member designation present in the document structure while nearby text is a
genuine dimension (`7/8`, `23'-10"`): ownership does not transfer; dimension
signal preserved.

## 8. Incomplete-label safety

| Text | `_member_designation_token` |
| --- | --- |
| `L4X4` | `""` (no strip path) |
| `2L4X4` | `""` |
| `L4X4X1/4` | token (complete angle — not incompleteness completion) |

This change does not invent thickness or complete incomplete angles.

## 9. Before vs after metrics

From `OwnLabelBeforeAfterComparisonTests` matrix:

| Metric | Value |
| --- | ---: |
| Own-label recoveries | ≥4 |
| Genuine/unrelated dims preserved | ≥4 |
| False flips (non-own → non-dimension) | **0** |

## 10. False-flip audit

No false flips in the required positive/negative/genuine/mixed matrix.
Unrelated marks and genuine dimensions keep digit evidence.

## 11. Regression results

```text
python -m pytest \
  tests/test_own_label_dimension_fix.py \
  tests/test_rd_geometry_phase.py \
  tests/test_rd_geometry_retrieval_v2.py \
  tests/test_rd_geometry_dimension_shadow.py \
  tests/test_rd_geometry_dimension_control_e4.py \
  tests/test_rd_geometry_dimension_holdout_e5.py \
  tests/test_rd_geometry_ownership_e5_1.py \
  tests/test_dense_page_geometry_cap.py \
  -q
```

**77 passed**, 25 subtests passed.

Gold SHA unchanged:
`0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`

E3/E4/E5 result artifacts unchanged. CAP dense-page tests still pass.

## 12. Files changed

Production:

- `backend/services/engineering/geometry_extractor.py`

Tests / docs / R&D test relaxations for intentional extractor drift:

- `backend/tests/test_own_label_dimension_fix.py` (new)
- `backend/tests/test_rd_geometry_dimension_control_e4.py`
- `backend/tests/test_rd_geometry_dimension_holdout_e5.py`
- `backend/tests/test_rd_geometry_ownership_e5_1.py`
- `backend/scripts/rd_geometry_integration/multi_document_dimension_holdout.py`
- `backend/scripts/rd_geometry_integration/ownership_evidence_audit_e5_1.py`
- `docs/validation/rd_geometry_integration/OWN_LABEL_DIMENSION_FIX_IMPLEMENTATION_REPORT.md`

## 13. Git status

See agent final `git status --short` for the working tree. **Not committed.**

Expected production delta: `geometry_extractor.py` only among production services.

## 14. Final implementation verdict

**IMPLEMENTATION_VALIDATED**

Own-label digit contamination is gated by deterministic E3 ownership; genuine
dimensions and unrelated numeric marks remain unchanged; false flips = 0 in the
required matrix; CAP/leader/retrieval/gold untouched.
