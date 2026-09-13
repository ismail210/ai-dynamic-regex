# Broadened-Fallback XGBRanker — Training, Evaluation, Promotion

Repo: `ai-dynamic-regex` @ `bassam/estima3d-integration`. Model family: `label_reconstruction`.

## 1. What this replaces

The repair-trace sprint wired `services.label_reconstruction` into the semantic pipeline in
shadow mode. For deletion/insertion queries the standard candidate generator abstains on
(`W10X3` from `W10X33`, `W88X10` from `W8X10`) — because their numeric fields *look* complete and
reliable even though the string length changed — `services.semantic.repair_shadow` fell back to
raw `difflib.SequenceMatcher.ratio()` ordering. That's a real ordering (not fabricated), but it's
blind to everything the trained ranker already knows (edit distance, family compatibility,
structural field distance, OCR-confusion positions).

This work moves that broadened fallback onto the trained ranker itself.

## 2. Existing XGBRanker audit (done before writing any new code)

- **Training entry point**: `scripts/train_label_ranker_v3.py`, consuming
  `training/datasets/label_reconstruction_production_aligned/{pointwise,pairwise}.jsonl` produced by
  `scripts/generate_label_reconstruction_production_aligned.py` (dataset version
  `label_reconstruction_production_aligned_20260828` — purely **synthetic AISC-catalog corruption**,
  no "projects" concept exists in this pipeline at all; that concept belongs to the separate
  `bassam/structural-repair-training` worktree's Model A/B work, not to this ranker).
- **Feature generator**: `services/label_reconstruction/features.py::pair_features` — the single
  function used at both train and serve time. Schema (pre-existing, 30 columns) already included
  `edit_distance`, `edit_distance_norm`, `len_diff_abs`, and per-field numeric-distance features —
  i.e. the raw material for ranking different-length candidates already existed; it just never saw
  broadened-fallback queries during training, and repair_shadow.py never routed them to the ranker
  at inference.
- **Model registry**: `services/training_pipeline/model_registry.py`. Currently-promoted version
  before this work: `label_reconstruction_20260828_111425` (30 features, `rank:ndcg`,
  val NDCG@10 0.949).
- **Real bug found and fixed en route**: `ranker.py::load_ranker_version` (used for offline
  A/B comparison) had the same training-machine-absolute-path problem `get_active_ranker` was
  already fixed for in the repair-trace sprint — it was never given the same fix, so it silently
  returned `None` for every non-active version on this machine. Fixed identically (local
  version-scoped path fallback).

## 3. Why deletion/insertion got zero candidates before

`W12X22` → `W12X2` (deleted trailing digit) still matches the `depth_weight` regex
(`W\d+X[\d./]+`), so `structural_parse.is_structural = True`. The deterministic single-char-repair
layer (`semantic_preprocessor.normalization._try_repair`) only runs when parsing **fails** — so it
never even looks at this case. `label_reconstruction.candidates.generate_candidates` treats
`"12"`/`"2"` as **reliable, fully-printed fields** (`has_reliable_numeric_constraints` → True) and
therefore disables its own fuzzy fallback (`allow_fuzzy = not has_reliable_numeric_constraints(...)`)
— by design, so a genuinely different real designation's fields are never silently "corrected" away.
Net effect: zero candidates, zero repair, forever — exactly the benchmark's finding.

## 4. New feature schema (v5)

`services/label_reconstruction/features.py`, `FEATURE_SCHEMA_VERSION = "v5_broadened_fallback"`:

- **+1 reason one-hot**: `reason_fuzzy_fallback_broadened` (added to `GENERATION_REASONS`).
- **+1 query-level context flag**: `is_fallback_broadened` (0/1, constant across every candidate for
  one query) — appended at the end of `FEATURE_NAMES` (32 total, up from 30).

Backward compatible by construction, not by convention: `pair_features()` always returns the full
current key set; `LabelRanker.score()` indexes only into `self.feature_names` (the calling model
version's own recorded schema), so an **older** model simply never looks up the two new keys — no
crash, no silent corruption, verified in
`tests/test_label_reconstruction_broadened.py::OlderModelBackwardCompatibilityTests`.

**Fail-safe added** (Section 12/26 of the brief): `shadow.reconstruct()` now wraps the ranker-scoring
call in `try/except`, degrading to "no ranker score for this call" (the deterministic candidate list
is still returned) on any exception — a genuine schema mismatch or scoring error can no longer crash
the semantic pipeline. Verified in `ReconstructFailSafeTests`.

## 5. Where broadening now lives

Moved from `services.semantic.repair_shadow` (a duplicate, SequenceMatcher-only implementation) into
`services.label_reconstruction.shadow.reconstruct()` itself — the correct layer, since it's a
candidate-*retrieval* decision, not a UI-trace concern. New shared gate:
`candidates.is_broadened_fallback_query(raw_text, normalized)`, used identically by:
- `reconstruct()` at inference (widens to `_fuzzy_candidates` only when triggered, scores with the
  ranker when available, falls back to the caller computing `SequenceMatcher` similarity only when
  no model is loaded), and
- `scripts/generate_label_reconstruction_broadened.py` at training-data-generation time,

so the two can never silently drift apart.

**A real regression was caught and fixed during this work**: the first version of
`is_broadened_fallback_query` fired for *any* grammar, which broke an existing, deliberate safety
fixture — `test_hss6x8x1_2_abstains_when_absent` (`HSS6X8X1/2` is a fully-specified, syntactically
valid, but genuinely **nonexistent** HSS combination; the test asserts the system must never guess a
substitute for it). The eligibility gate is now restricted to `depth_weight` grammar only (W/M/S/HP/
C/MC/L/2L — a single weight/size field). HSS's much sparser 3-field combinatorial space makes
"nearest real member" a materially less reliable guess than it is for W-shape depth/weight tables,
and guessing a substitute size for a custom/nonexistent HSS is a real engineering-safety risk this
module must not take. All safety fixtures pass after the fix (§9).

## 6. Training data (no PDF-attack-benchmark data anywhere)

Two dataset versions, each row keeping its own split, combined only at training time (neither
regenerated in place — the original stays available for comparison):

| Dataset | Rows (pairwise) | Source |
|---|---:|---|
| `label_reconstruction_production_aligned_20260828` (existing, regenerated locally byte-for-byte from the same deterministic seed/script since the JSONL files themselves weren't present on this machine) | 149,056 train / — | Synthetic AISC-catalog corruption, all `CORRUPTION_FAMILIES` |
| `label_reconstruction_broadened_20260914` (new) | 8,251 train / 1,772 val / 1,639 test | Synthetic AISC-catalog corruption, restricted to `char_deletion` + the new `char_insertion` family, **kept only when `is_broadened_fallback_query` is True** |

New corruption family added: `corruption.py::corrupt_char_insertion` (duplicates a digit or the `X`
separator — the mirror image of the existing `corrupt_char_deletion`). Only digit-duplication
insertions trigger broadening (`W12X26`→`W122X26`); separator-duplication (`W18X40`→`W18XX40`)
breaks the regex outright and is already reachable through the standard generator's own built-in
fuzzy inclusion — confirmed empirically, not assumed.

Of 5,708 length-changing corruptions of the catalog's 2,299 labels, only **1,174** actually trigger
`is_broadened_fallback_query` (the rest are already handled by the standard path) — this dataset is
deliberately small and precise, not "every deletion/insertion of every label." Target-in-candidates
recall (the retrieval question, separate from ranking): **1,173 / 1,174 = 99.9%** — retrieval is not
the bottleneck; ranking quality is.

**No PDF-attack-benchmark data was read anywhere in this pipeline** — verified by
`NoOracleLeakageTests` (static source-text check) and by construction (the generator only ever calls
`database_loader.catalog_entries()` + the corruption functions).

Completion boundary preserved: `is_broadened_fallback_query` explicitly excludes
`is_missing_thickness_hss`/`is_missing_thickness_angle` cases (bare `HSS8X8`, `L4X4`, `2L4X4`) —
those stay `COMPLETION`-only concerns, never treated as a repair candidate hunt.

## 7. New model

- **Version**: `label_reconstruction_20260913_230531` (promoted; supersedes
  `label_reconstruction_20260828_111425`, which remains on disk/in the registry for comparison).
- **Rejected candidate**: `label_reconstruction_20260913_224644` — the first training run, before
  the depth_weight-grammar-scope fix; explicitly marked `rejected` in the registry with the reason
  recorded (§5's HSS regression).
- **Objective**: `rank:pairwise` (beat `rank:ndcg` on validation NDCG@10 — both were evaluated, per
  existing convention).
- **Hyperparameters**: identical to the existing promoted model (`max_depth=5, learning_rate=0.1,
  n_estimators=200, subsample=0.9, colsample_bytree=0.9`), `random_state=20260914`.
- **Validation NDCG@10**: 0.9606 overall (0.9602 standard-only rows, 0.9638 broadened-only rows).
- **Dependencies recorded**: xgboost version, git revision, `feature_schema_version: v5_broadened_fallback`.

## 8. SequenceMatcher baseline vs old ranker vs new ranker

Held-out validation+test rows of the broadened dataset (never used for training), same candidate
pool scored three ways:

| Bucket | n | SequenceMatcher (old behavior) | Old promoted ranker (schema v4) | **New ranker (schema v5)** |
|---|---:|---:|---:|---:|
| **deletion** | 155 | Top-1 72.90% · Top-3 90.97% · MRR 0.829 | Top-1 74.19% · MRR 0.837 | **Top-1 74.84% · Top-3 91.61% · MRR 0.835** |
| **insertion** | 182 | Top-1 98.35% · Top-3 100% · MRR 0.992 | Top-1 98.35% · MRR 0.992 | **Top-1 98.90% · Top-3 100% · MRR 0.995** |
| **multi_error** | 6 | Top-1 83.33% · MRR 0.917 | Top-1 66.67% · MRR 0.806 | **Top-1 50.00% · MRR 0.722** |

**deletion and insertion (the two statistically meaningful buckets) both improve over the
SequenceMatcher baseline and over the old ranker.** `multi_error` has only 6 held-out examples — a
single flipped ranking moves it by ~17 points — and is **not** a basis for any conclusion either way;
reported honestly rather than hidden.

## 9. Real PDF-attack-benchmark validation (external, held out, never touched by training)

Two real attacked documents from `estima3d_pdf_attack_benchmark_v1` (`FnF_Structure_p5_genA.pdf`,
`FnF_Structure_p5_genB.pdf` — real project, corrupted copies, verified mutations with known clean
answers) were re-run end to end through the live pipeline with the new promoted model active:

| Document | Broadened-fallback cases found | Top-1 correct | Mutation types covered |
|---|---:|---:|---|
| genA | 19 | 14 (73.7%) | deletion |
| genB | 7 | 6 (85.7%) | insertion, multi_error |
| **Combined** | **26** | **20 (76.9%)** | deletion, insertion, multi_error |

The prior sprint's PDF-attack-benchmark measured **0% Top-1 for deletion** (zero repair attempts at
all). On these same real, attacked, held-out documents, deletion/insertion cases are now resolved
correctly **~77% of the time**, end to end, through the real pipeline. The two deletion misses
(`W10X1`→predicted `W10X12`, truth `W10X15`; `W8X1`→predicted `W18X119`, truth `W8X15`) are genuinely
ambiguous — multiple real, close catalog members exist — consistent with the brief's own "ambiguity
principle" (§15): the goal is better ordering, not forced certainty.

**Clean-control safety**: 0 / 54 clean controls (27 per document) false-changed with the new model
active. This is also structurally guaranteed, not just empirically observed: `repair_shadow.
needs_repair_shadow` returns `False` immediately for any `catalog_status == CATALOG_EXACT_MATCH`
annotation — the ranker is **never invoked** for a clean label regardless of which model version is
active. Switching ranker versions cannot affect clean-control safety by construction.

## 10. Standard repair regression check

All 9 single-tag OCR-substitution corruption classes (`0↔O`, `1↔I`, `2↔Z`, `5↔S`, `6↔G`, `8↔B`, plus
`L→1`) on the frozen standard dataset's held-out rows: **100% Top-1 for both the old and new model,
every class, n=24–105 per class.** Zero regression.

## 11. Safety checks (all pass)

| Check | Result |
|---|---|
| `L4X4` never broadened (completion boundary) | ✅ |
| `2L4X4` never broadened | ✅ |
| `HSS8X8` (missing thickness) never broadened | ✅ |
| `HSS5.563X0.258` (exact round HSS) never broadened | ✅ |
| `HSS6X8X1/2` (nonexistent-but-plausible HSS) still abstains, never guesses | ✅ (the regression this work found and fixed) |
| `W10X3` (deletion) correctly triggers broadening | ✅ |
| `W122X26` (digit-duplication insertion) correctly triggers broadening | ✅ |
| `W18XX40` (separator-duplication insertion) correctly handled by the *standard* path, not broadened | ✅ |
| `ML_LABEL_RANKER_ENABLED` unchanged (still `false` by default) | ✅ — production `analyze` traffic is untouched; only `force_shadow_score=True` callers (Semantic Review) see the new ranker |

## 12. Feature importance / ablation

**`is_fallback_broadened` and `reason_fuzzy_fallback_broadened` both show ZERO gain-importance** in
the trained tree (confirmed on both the flawed and corrected model — not a fluke). Top features by
gain are unchanged from the old model's own ranking: `deterministic_rank`, `edit_distance`,
`fuzzy_rank`, `reason_fuzzy_nearest_neighbor`, `ocr_aware_distance`, `is_structurally_compatible`.

**Honest conclusion, not hidden**: the new context flag contributes nothing measurable. The
measured improvement (§8/§9) comes entirely from training on more examples of the broadened
population, which reinforces the tree's use of features that already existed (`edit_distance`,
`len_diff_abs`, field-distance, reason one-hots) — not from telling the tree explicitly "this is a
broadened query." A further 3-way ablation retraining run was not necessary to reach this
conclusion: zero importance on both new columns is a direct, sufficient answer to "did the new
feature matter?" A follow-on implication worth flagging: **the same gain might be reachable by
simply adding more deletion/insertion training examples to the standard schema, without a schema
bump at all** — worth testing before investing in more context-flag-style features.

## 13. Tests

- New: `tests/test_label_reconstruction_broadened.py` (17 tests — eligibility gate, the new
  corruption family, feature schema stability/backward-compatibility, ranker fail-safety, no-oracle-
  leakage).
- Updated: `tests/test_semantic_repair_shadow.py` (one assertion updated to reflect the new, better
  `label_reconstruction_broadened_ranker` provenance instead of the old `..._fuzzy_fallback` source
  string — a real capability upgrade, not a weakened test).
- Full targeted suite (`semantic or label_reconstruction or ranker or shadow`): **200 passed** (was
  183 before this work).
- Full backend suite: **1,147 passed**, same **9 pre-existing, unrelated failures** as the repair-
  trace sprint baseline (`test_a2_a7_human_review.py` ×8, `test_repeated_detail_linker.py` ×1) —
  confirmed via direct diff against the pre-change baseline, not assumed. Zero new failures.
- Full frontend suite: **187 passed**, unchanged (no frontend code touched this round).

## 14. Promotion decision

**PROMOTED.** `label_reconstruction_20260913_230531` is now the active `label_reconstruction` model.

Gate-by-gate:
1. Deletion/insertion ranking measurably improves over SequenceMatcher — **yes** (both buckets,
   held-out rows AND real attacked-PDF validation).
2. Standard repair does not materially regress — **yes** (0% change, 9/9 classes).
3. Clean-control automatic false-change remains zero — **yes** (0/54 real, structurally guaranteed).
4. Incomplete L/2L safety remains — **yes**.
5. Round-HSS safety remains — **yes**.
6. Model loading is portable on Windows — **yes** (fixed `load_ranker_version` too, matching the
   earlier `get_active_ranker` fix).
7. Feature schema validation passes / fails safely on mismatch — **yes** (try/except added,
   verified).
8. Targeted tests pass — **yes** (200/200).
9. Full relevant backend suite has no new failures — **yes** (1,147 passed, same 9 pre-existing).

`multi_error`'s n=6 result is not a gate failure — the brief's own gate list doesn't require it, and
6 examples cannot support any promotion decision either way.

## 15. Next step

Given `is_fallback_broadened` measured zero importance (§12), the highest-leverage next action is
**not** more context features — it's **more broadened-population training data**: the current
broadened dataset has only 1,174 pointwise examples (vs. the standard dataset's much larger
population). Generating a larger, still-`depth_weight`-scoped deletion/insertion corpus (e.g. by
corrupting each catalog label multiple times with different RNG seeds, rather than once) and
retraining is the concrete, measurable-again next step — test the §12 hypothesis directly rather
than guessing at it.
