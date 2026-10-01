# G8-Era Human Validation — Preparation Plan

**Status:** `G8_ERA_HUMAN_VALIDATION_PREPARATION = COMPLETE`

**Purpose:** Prepare a separate human ownership review against the **frozen G8**
candidate universe. This is **not** a gold rewrite, not G10, not G9 tuning.

---

## 1. Two validation universes (do not conflate)

| Layer | Candidate universe | Role |
|---|---|---|
| Historical gold (`review_kit/gold_outcomes.jsonl`) | Pre-G8 association candidates | **Immutable** historical evidence |
| G8-era human validation (this folder) | Frozen G8 `B_candidates` | **Future** ownership review layer |

Historical `NO_VALID_MEMBER` often means “no listed candidate was the member,” not
“no steel exists.” The false-association audit (B=21) showed many of those decisions
are **stale relative to G8**, but audit class B is evidence — not automatic new gold.

---

## 2. Existing architecture discovered

### Human gold
- Path: `docs/validation/rd_geometry_integration/review_kit/gold_outcomes.jsonl`
- SHA (frozen): `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`
- Fields include: `token_id`, `decision`, `review_label`, `selected_geometry_id`,
  `reviewed_target_geometry_ids`, `candidate_geometry_ids`, `reason`, `error_bucket`,
  `reviewer_id`, `review_source`
- Metrics: `review_kit/gold_metrics.json` (do not modify)

### Review kit tooling
- Generator: `backend/scripts/rd_geometry_integration/review_kit.py`
- UI: `review_kit/index.html` + per-token HTML; decisions in `review_kit/decisions/`
- Historical `review_label` values: `direct_target`, `no_valid_target`,
  `ambiguous_requires_adjudication`, `unavailable`, …
- **Limitation:** kit pages list **pre-G8 `geom_*` candidates**, not frozen G8
  `rnd_raw_*` / `#segN` IDs. Reuse the *decision pattern* and crops; do **not** use
  the old candidate checkboxes as G8 ownership truth.

### G8 / G9 / audit (frozen inputs)
- G8 results SHA: `1931707165664d9e8e6ea198171624b9f9d8bb25dda2edd40d86619126ed3c44`
- G9 results SHA: `b459522eb097c285a359bd01a2be61c389daeded6415f236b6a0c47323cb4814`
- Audit: `g9_false_association_audit/` (21B + 5C + 1D)
- D-case forensics: `g9_false_association_audit/d_case_forensics/` (`D_CASE_ISOLATED`)

### What can be reused
- Evidence hierarchy / review discipline from `review_kit/README.md`
- Per-token decision JSON file pattern
- Existing visual crops (audit / G8 / G9 / historical assoc renders)
- Audit classifications B/C/D and competing-candidate lists

### What must not be reused as write target
- `gold_outcomes.jsonl` / `gold_metrics.json` (immutable)
- Production UI / Semantic Review / takeoff

---

## 3. Proposed G8-era decision vocabulary

| Decision | Meaning | Owned G8 IDs |
|---|---|---|
| `VALID_MEMBER` | One G8 candidate owned by the annotation | exactly 1 |
| `NO_VALID_MEMBER` | No G8 candidate is the owned member | 0 |
| `AMBIGUOUS` | Multiple plausible owners; not deterministic | ≥2 listed |
| `NEEDS_REVIEW` | Insufficient crop/PDF evidence | 0 |

Maps from historical labels: see `g8_era_human_validation_schema.json`.

Ownership question (mandatory):

> Which frozen G8 candidate, if any, is actually owned by this annotation?

Evidence hierarchy (distance last): explicit relationship → leader tip → overlap/contact
→ orientation → topology → repeated context → distance.

---

## 4. Manifest scope (exactly 27)

| Audit class | Count | Priority | Review intent |
|---|---:|---|---|
| B PREVIOUSLY_MISSING_CANDIDATE | 21 | MEDIUM if audit conf=MEDIUM else NORMAL | Confirm ownership independently |
| C AMBIGUOUS_UNDER_NEW_REPRESENTATION | 5 | HIGH | Allow AMBIGUOUS; show competitors |
| D G9_CLEARLY_WRONG | 1 | HIGH | Reference G9 fail; independent verify |
| **Total** | **27** | | |

Priority is workflow only, not correctness.

Tokens:
- B: token_p8_347, token_p8_419, token_p8_336, token_p8_337, token_p8_341, token_p8_343, token_p8_345, token_p8_346, token_p8_352, token_p8_354, token_p8_356, token_p8_361, token_p8_363, token_p8_369, token_p8_371, token_p8_372, token_p8_399, token_p8_410, token_p8_411, token_p8_412, token_p18_1188
- C: token_p8_381, token_p8_382, token_p8_383, token_p8_384, token_p8_430
- D: token_p24_1359

---

## 5. How to review B cases

1. Open crop (prefer audit false-assoc render).
2. Enumerate frozen `g8_candidates` (IDs, kind, derivation, length, bbox).
3. Apply evidence hierarchy — do not accept “G8 recovered it” as ownership.
4. Decide VALID_MEMBER (one id) / NO_VALID_MEMBER / AMBIGUOUS / NEEDS_REVIEW.
5. Record notes. Leave `reviewer_decision` null until the future collection step.

**Do not** auto-convert audit B → VALID_MEMBER.

---

## 6. How to review C cases

Tokens: `token_p8_381`, `token_p8_382`, `token_p8_383`, `token_p8_384`, `token_p8_430`.

1. Show all competing same-scale / parallel candidates from the manifest.
2. If PDF does not establish deterministic ownership → **AMBIGUOUS** (list competitors).
3. Do not force a winner for dataset convenience.

---

## 7. How to review D case (`token_p24_1359`)

Reference (not auto-answer):
- G9 selected: `rnd_raw_p24_480_d0c0ca5e54d7` (405pt wall)
- Audit better: `raw_p24_10_9d8fbf0dfe5b#seg1` (short segment)

Reviewer independently verifies ownership via leader tip + short angle geometry.
See `../g9_false_association_audit/d_case_forensics/`.

---

## 8. Artifacts in this folder

| File | Role |
|---|---|
| `G8_ERA_HUMAN_VALIDATION_PLAN.md` | This plan |
| `g8_era_human_validation_schema.json` | Proposed decision schema |
| `g8_era_human_validation_manifest.jsonl` | Exact 27-case review queue |
| `g8_era_human_validation_summary.json` | Counts, SHAs, gate |
| `review.html` | Lightweight isolated review index (G8 IDs) |
| `decisions_pending/` | Empty placeholder for **future** human decisions |

---

## 9. Explicit non-goals

- No G10 / G9 weight or threshold changes
- No G8 regeneration / candidate rewrites
- No historical gold edits
- No production extraction / association / Semantic Review / takeoff changes
- No ML / VLM
- No claiming accuracy improvement from this preparation

---

## 10. Next step (not this task)

A **separate** human collection pass writes JSON into `decisions_pending/` and eventually
a **separate** outcomes file (e.g. `g8_era_review_outcomes.jsonl`) — never into
`review_kit/gold_outcomes.jsonl`.

---

## Safety / SHA verification

- Gold: `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`
- G8: `1931707165664d9e8e6ea198171624b9f9d8bb25dda2edd40d86619126ed3c44`
- G9: `b459522eb097c285a359bd01a2be61c389daeded6415f236b6a0c47323cb4814`
- Audit: `4d6b3164b60f60a083246192136f7eacbb649753fae4a8b5fc0a212a76866410`
- Gold metrics path present and **not modified** by this prep
