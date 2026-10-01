# Geometry Association Shadow (G9)

Isolated deterministic text→geometry association over **G8 R&D candidates**. No production association, extraction, retrieval, CAP, gold, takeoff, or ML changes.

**G9_GATE = `ASSOCIATION_STILL_NOT_READY`**  
**Cases:** 75  
**Gold SHA:** `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`

## 1. Executive Summary

- Associated gold Recall@1/3/5: **0.625 / 1.0 / 1.0**
- Exact gold match: **2 / 8**
- False assoc on no-valid-member: **27**
- Ambiguous forced association: **1**
- Leader success / false: **2 / 0**
- Schedule false assoc: **0**
- Giant / NON_MEMBER selected: **0 / 0**
- Abstain / Ambiguous / Associated / NoValid: **6 / 25 / 31 / 13**

## 2. Scope and Safety

R&D shadow only. `geometry_extractor.py`, `retrieval.py`, `retrieval_v2.py`, Semantic Review, takeoff, GHX, and Human Gold are untouched.

## 3–5. Inputs / Gold / G8 population

Inputs: Human Gold (75) + G8 `B_candidates` + leader_audit. G8 gate was `REPRESENTATION_READY_FOR_ASSOCIATION`.

## 6–11. Association model

Hard eligibility → direct/leader mode → weighted evidence (distance=0.34, bbox=0.18, orient=0.12, length=0.12, kind=0.12, leader=0.08, provenance=0.04) → penalties → margin gate (min_score=0.58, min_margin=0.08).

Hard exclusions: NON_MEMBER, UNKNOWN, giant extent≥600, large segments, leader-line-as-member. Leader tip NON_MEMBER → NO_VALID_MEMBER.

## 12. Baselines

- **A** production nearest geom among associated: 6 / 8 match gold
- **B** nearest eligible G8 candidate among associated: 8 / 8
- **C** G9 multi-signal: 2 / 8

Among G9 ASSOCIATED decisions that match gold, 0 beat nearest-only (ranking value); 2 required G8 population availability.

## 13. Overall metrics

| Metric | Value |
|---|---:|
| recall_at_1 | 0.625 |
| recall_at_3 | 1.0 |
| recall_at_5 | 1.0 |
| associated_gold_exact_match | 2 |
| false_association_no_valid_member | 27 |
| ambiguous_forced_association | 1 |
| leader_success | 2 |
| leader_false_association | 0 |
| schedule_false_association | 0 |
| giant_selected | 0 |
| non_member_selected | 0 |
| large_segment_selected | 0 |
| abstention_rate | 0.4133 |

## 14. Stratified metrics

- **associated_gold:** {'n': 8, 'ASSOCIATED': 3, 'AMBIGUOUS': 5, 'ABSTAIN': 0, 'NO_VALID_MEMBER': 0, 'gold_exact': 2}
- **human_ambiguous:** {'n': 2, 'ASSOCIATED': 1, 'AMBIGUOUS': 1, 'ABSTAIN': 0, 'NO_VALID_MEMBER': 0, 'gold_exact': 0}
- **human_no_valid_member:** {'n': 65, 'ASSOCIATED': 27, 'AMBIGUOUS': 19, 'ABSTAIN': 6, 'NO_VALID_MEMBER': 13, 'gold_exact': 0}
- **visible_member:** {'n': 58, 'ASSOCIATED': 27, 'AMBIGUOUS': 19, 'ABSTAIN': 6, 'NO_VALID_MEMBER': 6, 'gold_exact': 0}
- **leader_required:** {'n': 18, 'ASSOCIATED': 2, 'AMBIGUOUS': 6, 'ABSTAIN': 4, 'NO_VALID_MEMBER': 6, 'gold_exact': 0}
- **schedule_table:** {'n': 7, 'ASSOCIATED': 0, 'AMBIGUOUS': 0, 'ABSTAIN': 0, 'NO_VALID_MEMBER': 7, 'gold_exact': 0}
- **g8_recovered:** {'n': 45, 'ASSOCIATED': 24, 'AMBIGUOUS': 15, 'ABSTAIN': 6, 'NO_VALID_MEMBER': 0, 'gold_exact': 0}
- **g8_neighborhood_only:** {'n': 15, 'ASSOCIATED': 4, 'AMBIGUOUS': 5, 'ABSTAIN': 0, 'NO_VALID_MEMBER': 6, 'gold_exact': 0}
- **short_stroke_loss:** {'n': 21, 'ASSOCIATED': 12, 'AMBIGUOUS': 9, 'ABSTAIN': 0, 'NO_VALID_MEMBER': 0, 'gold_exact': 0}

## 15–17. Per-page

- **p8:** {'n': 50, 'ASSOCIATED': 29, 'AMBIGUOUS': 19, 'ABSTAIN': 2, 'NO_VALID_MEMBER': 0, 'gold_exact': 2}
- **p18:** {'n': 14, 'ASSOCIATED': 1, 'AMBIGUOUS': 2, 'ABSTAIN': 1, 'NO_VALID_MEMBER': 10, 'gold_exact': 0}
- **p24:** {'n': 11, 'ASSOCIATED': 1, 'AMBIGUOUS': 4, 'ABSTAIN': 3, 'NO_VALID_MEMBER': 3, 'gold_exact': 0}

## 18. Associated gold analysis

- `token_p8_340` gold=`geom_095898d74240` decision=AMBIGUOUS match=False rank=1 margin=0.0005 B_nearest_match=True
- `token_p8_395` gold=`geom_cf1c1b4a4515` decision=AMBIGUOUS match=False rank=2 margin=0.0391 B_nearest_match=True
- `token_p8_396` gold=`geom_0b5ef1f9c497` decision=AMBIGUOUS match=False rank=2 margin=0.0392 B_nearest_match=True
- `token_p8_397` gold=`geom_90463060295d` decision=AMBIGUOUS match=False rank=1 margin=0.05 B_nearest_match=True
- `token_p8_398` gold=`geom_485e0c733148` decision=ASSOCIATED match=True rank=1 margin=0.1147 B_nearest_match=True
- `token_p8_421` gold=`geom_5f6b0423ca08` decision=ASSOCIATED match=True rank=1 margin=0.1023 B_nearest_match=True
- `token_p8_427` gold=`geom_edbfa26d671d` decision=AMBIGUOUS match=False rank=1 margin=0.0086 B_nearest_match=True
- `token_p8_432` gold=`geom_edbfa26d671d` decision=ASSOCIATED match=False rank=3 margin=0.1112 B_nearest_match=True

## 19–24. Failure / safety slices

False associations on no-valid-member: **27**
- `token_p8_336` W21X50 → rnd_raw_p8_1260_a31b1adb0cdb score≈0.8696 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_337` W21X44 → rnd_raw_p8_1274_e21a18219b27 score≈0.8711 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_341` W16X26 → rnd_raw_p8_1284_2ab7f6b159ec score≈0.8387 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_343` W16X26 → rnd_raw_p8_1285_cba42058a285 score≈0.8414 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_345` W10X15 → rnd_raw_p8_1286_88fce0a03302 score≈0.8675 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_346` W10X15 → rnd_raw_p8_1287_18ba2761eddd score≈0.8671 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_347` W16X26 → rnd_raw_p8_1288_c0f7320ead19 score≈0.8176 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_352` W16X26 → rnd_raw_p8_1292_be2a2c871ca2 score≈0.814 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_354` W18X35 → rnd_raw_p8_1294_4e2b694a2be6 score≈0.8665 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_356` W16X26 → rnd_raw_p8_1296_4f4b33f9373b score≈0.8654 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_361` W16X26 → rnd_raw_p8_1301_5bbc33a526a9 score≈0.8371 reasons=['near_label', 'member_scale', 'valid_candidate_kind']
- `token_p8_363` W16X26 → rnd_raw_p8_1302_189e6c134034 score≈0.8455 reasons=['near_label', 'member_scale', 'valid_candidate_kind']

Leader NON_MEMBER tip cases forced to NO_VALID_MEMBER when status=`TARGET_PRESENT_NON_MEMBER`.

## 25. Candidate population vs ranking improvement

- G8 made gold geom available for all 8 associated cases (gold mirrors / retained strokes).
- Baseline B (nearest G8) matches gold on **8/8**.
- G9 multi-signal exact-associates gold on **2/8** (others mostly AMBIGUOUS from near-ties with parallel strokes).
- Ranking-only wins (G9 correct, B wrong): **0**.
- Primary improvement source: **primarily_G8_candidate_population**.

**Fairness conclusion:** Once G8 restores member-scale candidates, simple nearest-eligible already recovers the 8 associated gold geometries. G9’s multi-signal margin gate does **not** improve exact association on that set; it mainly trades false-positives vs abstention on dense framing pages. High “false association” on human `no_valid_member` is expected under the gold contract whenever visible members were missing from the *old* candidate set but are now present in G8 — the scorer is gold-blind and sees strong on-label geometry.

## 26–28. Visual QA / failures / safety

Renders under `association_shadow_g9_renders/` (optional). Safety counters: giant=0, non_member=0, large_seg=0.

Remaining failure modes:
1. Parallel-member near-ties → AMBIGUOUS on true associated gold.
2. Dense p8 neighborhoods → ASSOCIATED on human no_valid_member when G8 recovered an on-label stroke.
3. One human ambiguous case forced to ASSOCIATED.
4. Leader tip memberlike association still low volume (success count small).

## 29. Test Results

See pytest output for `test_rd_geometry_association_g9.py` + geometry R&D suite (**84 passed**, 1 skipped).

## 30. G9 Gate

**G9_GATE = `ASSOCIATION_STILL_NOT_READY`**

Evidence is **not** strong enough for the next validation phase as a ranking breakthrough. G8 population is necessary; G9 scoring is not yet a reliable association policy under the Human Gold decision contract.

## 31. Recommendation for G10

Do **not** implement production association. Optional G10 should be a **decision-policy** experiment (when to abstain vs associate on dense parallel bays) with frozen G8 candidates — still shadow-only — or expand holdout pages before any wiring. Stop here for review.

