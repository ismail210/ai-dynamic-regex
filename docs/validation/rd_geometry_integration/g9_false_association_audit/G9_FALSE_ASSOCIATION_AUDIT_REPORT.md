# G9 False Association Forensic Audit

**G9_FALSE_ASSOCIATION_AUDIT_GATE = `AUDIT_COMPLETE_G10_NOT_YET_JUSTIFIED`**

**Cases audited:** 27  
**Project:** Burrville ES - ST (`doc_0d910a43b4a021e3`)  
**Gold SHA (unchanged):** `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`

## Executive Conclusion

The 27 G9 “false associations” against human `NO_VALID_MEMBER` are **not** primarily
scorer errors. Under the frozen G8 candidate universe:

- **21** cases are **previously missing candidates**
  (old gold was made against an incomplete association candidate set).
- **5** cases remain **ambiguous** with multiple
  plausible parallel members.
- **0** cases are **genuinely** no-valid-member
  with a wrong G9 pick.
- **1** cases are **clear G9 ranking/decision errors**
  where a better G8 candidate exists.

Primary implication: treating all 27 as true false associations overstates G9 failure.
Most are **stale-candidate-universe** effects from G8 recovery. Human gold is **not** rewritten.

## Scope

Read-only forensic audit of G9 ASSOCIATED ∩ human `no_valid_member`. No G10 implementation.
No production extraction/association changes. No G8/G9 scoring changes. No gold edits.
No ML/VLM/threshold tuning.

## Frozen Inputs

| Artifact | Path | Role |
|---|---|---|
| Human gold | `review_kit/gold_outcomes.jsonl` | Historical decisions (immutable) |
| G8 results | `representation_repair_g8_results.jsonl` | Frozen candidate universe |
| G9 results | `association_shadow_g9_results.jsonl` | Decisions / rankings under audit |
| G9 summary | `association_shadow_g9_summary.json` | Reported false_nvm=27 |
| G9 report | `GEOMETRY_ASSOCIATION_G9_REPORT.md` | Prior gate ASSOCIATION_STILL_NOT_READY |

Gold SHA verified: `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`  
G8 results SHA: `1931707165664d9e8e6ea198171624b9f9d8bb25dda2edd40d86619126ed3c44`  
G9 results SHA: `b459522eb097c285a359bd01a2be61c389daeded6415f236b6a0c47323cb4814`

## Classification Definitions

- **A — GENUINELY_NO_VALID_MEMBER:** Even with G8, no valid member should associate; G9 pick is false.
- **B — PREVIOUSLY_MISSING_CANDIDATE:** Valid/plausible member now visible via G8; old gold NVM is stale for this universe (gold file unchanged).
- **C — AMBIGUOUS_UNDER_NEW_REPRESENTATION:** Multiple plausible members; ownership not deterministic.
- **D — G9_CLEARLY_WRONG:** Valid G8 candidate exists; G9 selected a different, clearly wrong one.

## Results

| Class | Count | Meaning |
|---|---:|---|
| A | 0 | Genuine false association / still no valid member |
| B | 21 | Stale candidate-universe (OLD_GOLD_STALE_CANDIDATE_UNIVERSE) |
| C | 5 | Ambiguous under G8 |
| D | 1 | Clear G9 ranking/decision error |

Confidence: {"HIGH": 20, "MEDIUM": 7}

Derived:
- candidate_universe_stale_count (B) = **21**
- genuine_false_association_count (A+D) = **1**
- ambiguous_count (C) = **5**
- cases_requiring_future_g10 (D) = **1**

## Category A — Genuine No Valid Member

_None._


## Category B — Previously Missing Candidate

- `token_p8_336` p8 `W21X50` → selected=`rnd_raw_p8_1260_a31b1adb0cdb` best=`rnd_raw_p8_1260_a31b1adb0cdb` conf=HIGH: Label sits on the W21X50 girder; G8 reclass_restore recovers the under-label stroke previously classified as dimension. Old gold overlays were distant infill/stair, not this girder.
- `token_p8_337` p8 `W21X44` → selected=`rnd_raw_p8_1274_e21a18219b27` best=`rnd_raw_p8_1274_e21a18219b27` conf=HIGH: Label sits on the upper W21X44 girder. Under-label raw was a leader stub; G8 neighborhood reclass recovers the girder segment G9 selected.
- `token_p8_341` p8 `W16X26` → selected=`rnd_raw_p8_1284_2ab7f6b159ec` best=`rnd_raw_p8_1284_2ab7f6b159ec` conf=HIGH: Label sits on W16X26 joist; G8 reclass_restore recovers the on-label joist previously treated as dimension. Old overlays were EJ wall / wall beam.
- `token_p8_343` p8 `W16X26` → selected=`rnd_raw_p8_1285_cba42058a285` best=`rnd_raw_p8_1285_cba42058a285` conf=HIGH: Label sits on W16X26 joist; G8 recovers that joist via reclass_restore. Old overlays were distant infill / W21X44 wall.
- `token_p8_345` p8 `W10X15` → selected=`rnd_raw_p8_1286_88fce0a03302` best=`rnd_raw_p8_1286_88fce0a03302` conf=HIGH: Short W10X15 joist under the label was CAP-dropped; G8 cap_restore returns the ~75pt stroke G9 associates. Old gold had no short-joist candidate.
- `token_p8_346` p8 `W10X15` → selected=`rnd_raw_p8_1287_18ba2761eddd` best=`rnd_raw_p8_1287_18ba2761eddd` conf=HIGH: Mirror of p8_345: CAP-dropped short W10X15 under label recovered by G8 cap_restore; previously absent from association candidates.
- `token_p8_347` p8 `W16X26` → selected=`rnd_raw_p8_1288_c0f7320ead19` best=`rnd_raw_p8_1288_c0f7320ead19` conf=MEDIUM: Label sits on W16X26 joist. Under-label raw was CAP-dropped leader stub; G8 neighborhood reclass recovers a member-scale joist stroke G9 selects. Crowded bay has other long strokes, but selected matches the labeled joist scale.
- `token_p8_352` p8 `W16X26` → selected=`rnd_raw_p8_1292_be2a2c871ca2` best=`rnd_raw_p8_1292_be2a2c871ca2` conf=HIGH: Label sits on W16X26 girder; G8 recovers a ~109pt member-scale stroke under the label (neighborhood after CAP drop). Old candidates were callout/giant polyline.
- `token_p8_354` p8 `W18X35` → selected=`rnd_raw_p8_1294_4e2b694a2be6` best=`rnd_raw_p8_1294_4e2b694a2be6` conf=HIGH: Label sits on W18X35 joist; G8 reclass_restore recovers that joist after leader misclass. Old overlays were distant infill / wall.
- `token_p8_356` p8 `W16X26` → selected=`rnd_raw_p8_1296_4f4b33f9373b` best=`rnd_raw_p8_1296_4f4b33f9373b` conf=HIGH: Label sits on W16X26 girder; G8 reclass recovers the girder previously classified as dimension. Old overlays were W14/W12 infills.
- `token_p8_361` p8 `W16X26` → selected=`rnd_raw_p8_1301_5bbc33a526a9` best=`rnd_raw_p8_1301_5bbc33a526a9` conf=HIGH: Label sits on W16X26 joist; G8 recovers on-label joist (was dimension). Old green/orange were EJ wall / tall wall box.
- `token_p8_363` p8 `W16X26` → selected=`rnd_raw_p8_1302_189e6c134034` best=`rnd_raw_p8_1302_189e6c134034` conf=HIGH: Label sits on W16X26 joist; only old candidate was a giant bay polyline. G8 reclass_restore exposes the joist stroke G9 selects.
- `token_p8_369` p8 `W16X26` → selected=`rnd_raw_p8_1326_cea5e757337b` best=`rnd_raw_p8_1326_cea5e757337b` conf=HIGH: Label sits on W16X26 joist; G8 recovers it from dimension class. Old overlay was the W21X44 wall beam.
- `token_p8_371` p8 `W10X15` → selected=`rnd_raw_p8_1327_7e831bb3d961` best=`rnd_raw_p8_1327_7e831bb3d961` conf=HIGH: Short W10X15 under label was CAP-dropped; G8 cap_restore recovers ~75pt stroke. Old overlay was W14X22 infill.
- `token_p8_372` p8 `W10X15` → selected=`rnd_raw_p8_1328_27999919be3c` best=`rnd_raw_p8_1328_27999919be3c` conf=HIGH: Short W10X15 CAP-dropped; G8 recovers joist. Old green/orange were W14X22 infill and stair, not the joist.
- `token_p8_399` p8 `W10X15` → selected=`rnd_raw_p8_1367_4908eae79b6f` best=`rnd_raw_p8_1367_4908eae79b6f` conf=HIGH: Short W10X15 CAP-dropped under label; G8 cap_restore recovers it. Old overlays were W14X22 infill / stair.
- `token_p8_410` p8 `W10X15` → selected=`rnd_raw_p8_1397_51483cb885bd` best=`rnd_raw_p8_1397_51483cb885bd` conf=HIGH: W10X15 at wall CAP-dropped; G8 recovers short stroke. Old overlays were W16X31 / W21X44 wall members.
- `token_p8_411` p8 `W10X15` → selected=`rnd_raw_p8_1398_5786610a6f08` best=`rnd_raw_p8_1398_5786610a6f08` conf=HIGH: W10X15 CAP-dropped; G8 recovers short joist. Old overlay was W16X31 at EJ.
- `token_p8_412` p8 `W10X15` → selected=`rnd_raw_p8_1399_a867be18d612` best=`rnd_raw_p8_1399_a867be18d612` conf=HIGH: W10X15 CAP-dropped; G8 recovers short joist. Old overlay was W16X31 at EJ.
- `token_p8_419` p8 `W16X26` → selected=`rnd_raw_p8_1484_19ed80f9fdf5` best=`rnd_raw_p8_1484_19ed80f9fdf5` conf=MEDIUM: Label sits on W16X26 joist; G8 reclass recovers that stroke (was dimension). Nearby longer wall/infill strokes compete but selected matches under-label raw_trace reclass of the joist.
- `token_p18_1188` p18 `PL 3 3/4"` → selected=`rnd_raw_p18_5045_9d434832f314` best=`rnd_raw_p18_5045_9d434832f314` conf=HIGH: Leader points to the embed plate. G9 selects the CAP-restored tip stroke (tip_distance=0) that coincides with the plate edge; that stroke was absent from the retained CAP set. Old gold overlays were studs/rebar, not the plate.


## Category C — Ambiguous Under New Representation

- `token_p8_381` p8 `W18X35` → selected=`rnd_raw_p8_1338_4cd2ddf31320` best=`None` conf=MEDIUM: G8 recovers multiple parallel W18-scale joist strokes that all touch the label neighborhood (same-scale competitors at ~0 distance). PDF shows a dense parallel bay; ownership of a single stroke is not deterministic from geometry alone even though a member is visible.
- `token_p8_382` p8 `W18X35` → selected=`rnd_raw_p8_1339_91f1ee05f373` best=`None` conf=MEDIUM: Parallel W18X35 bay: top-3 G8 candidates are same-scale joist strokes with near-zero label distance and thin G9 margin (~0.08). Deterministic ownership not established.
- `token_p8_383` p8 `W18X35` → selected=`rnd_raw_p8_1340_15043854c468` best=`None` conf=MEDIUM: Same parallel-bay pattern as neighboring W18 labels: multiple recovered member-scale strokes compete at the label. Ambiguous under G8 universe.
- `token_p8_384` p8 `W18X40` → selected=`rnd_raw_p8_1341_16dcbc2956c0` best=`None` conf=MEDIUM: W18X40 among parallel W18X40s. Selected stroke was already a retained member line, but several similar-length retained/recovered strokes also touch the label. Gold overlays showed SOG/wall; under G8 the bay remains multi-candidate ambiguous.
- `token_p8_430` p8 `W18X35` → selected=`rnd_raw_p8_1496_77117ad76f03` best=`None` conf=MEDIUM: Parallel W18 bay with ≥4 same-scale recovered strokes at near-zero label distance and thin margin. Member geometry is present, but ownership of one specific joist is not deterministic.


## Category D — G9 Clearly Wrong

- `token_p24_1359` p24 `L6x3-1/2x3/8` → selected=`rnd_raw_p24_480_d0c0ca5e54d7` best=`raw_p24_10_9d8fbf0dfe5b#seg1` conf=HIGH: Leader targets the small L6 relieving angle. G9 ASSOCIATED a 405pt vertical wall/hatch line (on_label_retained). Short plate/angle segments exist in G8 (rank-2 vertex_split seg from tip plate_or_symbol; additional CAP short strokes). Selected geometry is clearly the long brick/wall line, not the angle.


## Per-Page Findings

- **p8:** n=25 A=0 B=20 C=5 D=0
- **p18:** n=1 A=0 B=1 C=0 D=0
- **p24:** n=1 A=0 B=0 C=0 D=1

## Candidate-Universe Effect

G8 restored member-scale strokes previously lost to CAP drop or dimension/leader reclass.
For most p8 framing labels, human gold `NO_VALID_MEMBER` reflected **missing retrieval /
wrong overlays**, not “no steel exists.” Once G8 exposes on-label strokes, gold-blind G9
naturally ASSOCIATES them. That is a **universe change**, not proof that G9 invented members.

Category B cases document OLD vs NEW:

- OLD: CAP_DROPPED / RECLASSIFIED_DIMENSION / RECLASSIFIED_LEADER (or wrong association overlays)
- NEW: `cap_restore` / `reclass_restore` / tip short-stroke recovery present in `B_candidates`
- VISUAL: selected geometry matches the member the gold *reason text* already described as under the label

## Implications for Human Gold

- Gold file SHA unchanged: `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`
- Gold decisions remain historical evidence from the **pre-G8** candidate universe
- Category B must **not** auto-promote to ASSOCIATED in gold
- Any future gold refresh must be an explicit, separate human review against G8 candidates

## G10 Readiness Assessment

Gate = **`AUDIT_COMPLETE_G10_NOT_YET_JUSTIFIED`**.

Rationale: D population is small (1); the dominant
story is stale-candidate-universe (B) plus parallel-bay ambiguity (C). A dedicated G10
association-policy experiment is **not yet justified** as the next step solely from these
27 cases. Optional later work could still characterize the single D leader/short-target
failure, but that is not a broad ranking-policy program.

## Safety / Non-Production Status

- Production `geometry_extractor.py`: untouched by this audit
- G8 script/results: consumed read-only
- G9 script/results: consumed read-only
- Human gold: SHA pinned, not rewritten
- Artifacts isolated under `docs/validation/rd_geometry_integration/g9_false_association_audit/`
- No Semantic Review / takeoff / GHX / ML wiring

## Artifact Index

- `validation/rd_geometry_integration/g9_false_association_audit/g9_false_association_audit.jsonl`
- `validation/rd_geometry_integration/g9_false_association_audit/g9_false_association_audit_summary.json`
- `validation/rd_geometry_integration/g9_false_association_audit/G9_FALSE_ASSOCIATION_AUDIT_REPORT.md`
- `validation/rd_geometry_integration/g9_false_association_audit/review.html`
- `validation/rd_geometry_integration/g9_false_association_audit/renders/`
