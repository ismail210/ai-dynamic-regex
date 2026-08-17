# AISC v16 training scale estimate

Measured from the actual controlled run (`generate_label_corruption_dataset_v16.py`,
seed=20260813), not a projection -- these are the real produced counts.

| Quantity | Value |
|---|---|
| Canonical labels (catalog) | 3,842 |
| Corruption variants attempted per label | 6 single-family + 2 chained (severity 2, 3) = 8 |
| Pointwise rows actually produced (after global string dedup) | 26,851 (~7.0/label -- some corruption families don't apply to every label, e.g. `missing_prefix` on a 1-token family-only string) |
| Positives (= pointwise rows, one true-label row each) | 26,851 |
| Negatives per positive (target) | 4 (`NEGATIVES_PER_ROW`) |
| Pairwise rows produced | 134,033 (~4.0 negatives/positive realized) |
| Split (pointwise) | train 16,789 / validation 3,550 / test 6,512 |
| Designation holdout | 307 designations (~8%) forced test-only |
| Reserved unseen multi-corruption combos | 185 |

## Size on disk / memory

- `pointwise.jsonl`: 11.3 MB
- `pairwise.jsonl`: 27.9 MB
- Both load fully into memory as plain Python lists/numpy arrays without
  issue (low hundreds of MB peak during feature-matrix construction) -- no
  chunking/streaming needed at this scale.

## Runtime (this machine, single process, no GPU)

- Dataset generation (corruption + a `generate_candidates_v3` call per
  pointwise row for negative mining): several minutes, dominated by
  candidate generation (~27k calls), not corruption synthesis itself.
- Baseline evaluation (candidate generation for 6,512 test rows + training
  one default-hyperparameter XGBRanker on ~107k pairwise train rows): a
  few minutes.
- Feature ablation (7 XGBRanker training runs -- 1 full + 6 masked -- on
  the same ~107k-row train matrix, reused rather than regenerated):
  proportionally longer but each run itself is fast once the feature
  matrix is built once.

None of this required a scale-down; it comfortably fits a single
un-accelerated process in single-digit minutes end to end.

## Scaling relationship

Row count scales roughly linearly in three independent knobs:
`pointwise_rows ≈ labels × variants_applied_per_label` and
`pairwise_rows ≈ pointwise_rows × (1 + negatives_per_positive)`. Concretely:

- Doubling `negatives_per_row` (4 -> 8) -> ~241k pairwise rows.
- Adding severity-4/5 chained corruptions or multiple random draws per
  corruption family per label (e.g. 3 samples of `ocr_substitution`
  instead of 1) -> pointwise rows grow proportionally with the multiplier.
- Extending to the full historical-family grammar (once `structural_parser`
  gains grammars for the 24 historical families, see the parser-fix report)
  would not by itself change label count (already included -- this dataset
  already spans all 37 families) but would improve candidate-generation
  quality for those families, which indirectly changes how many negatives
  the generator proposes.

## Recommendation: measure before scaling up

This run (134k pairwise rows) is a deliberately controlled first pass, not
a ceiling. Before generating a larger corpus, the honest next experiment is
a data-scaling curve: train the same default-hyperparameter ranker on
25%/50%/100% of the current train split (subsample by canonical label, not
by row, to keep groups intact) and compare validation group top-1 accuracy.
If 100% notably outperforms 50%, more data is likely worth generating next;
if the curve is already flat, the bottleneck is elsewhere (see the
baseline-results and feature-ablation reports) and generating more rows of
the same kind would not help. This curve was NOT run in this phase per
scope (no large-corpus generation, no Optuna) -- it is the natural
next-phase action.
