# AISC v16 candidate-generation diagnostic recall (full catalog, single corruptions)
`generate_candidates_v3` (limit=25), catalog = `aisc_v16_label_catalog.csv` (3842 entries, 37 families), one corrupted query per (label × single-corruption-family), seed=20260813.

**Not the held-out ranking-benchmark ceiling.** This number evaluates the
candidate generator alone, against every catalog label, using only single,
unchained corruptions, with no train/val/test split and no designation
holdout. It is a candidate-generator stress test, not a bound on ranker
performance. For the actual held-out test-set ceiling (real corruption
distribution: chained severity-2/3/4 corruptions, designation holdout,
real train/test partition) — the number that upper-bounds
`ml_ranker_v3_default`'s achievable top-1 — see
`aisc_v16_baseline_results.md`'s "Candidate-generation recall ceiling on
this test set" (0.7204). The two are not comparable and should not be used
interchangeably.

**Overall candidate-generator diagnostic recall: 0.8383 (19171/22870)**

## Recall by catalog scope
| Scope | Recall | Checks |
|---|---|---|
| historical | 0.8514 | 2450 |
| modern | 0.8367 | 20420 |

## Recall by corruption type
| Corruption | Recall | Checks |
|---|---|---|
| added_noise | 0.7915 | 3842 |
| char_deletion | 0.9501 | 3831 |
| missing_prefix | 0.3117 | 3840 |
| ocr_substitution | 0.9958 | 3820 |
| separator | 0.9978 | 3696 |
| unknown_char | 0.9896 | 3841 |

## Recall by family
| Family | Recall | Checks |
|---|---|---|
| HSS | 0.8406 | 6732 |
| 2L | 0.8726 | 3453 |
| W | 0.8320 | 2946 |
| WT | 0.7797 | 2320 |
| L | 0.8662 | 1914 |
| S | 0.7941 | 1559 |
| ST R | 0.8637 | 1152 |
| ST S | 0.7793 | 426 |
| MC | 0.8293 | 287 |
| ST | 0.8333 | 252 |
| M | 0.8165 | 218 |
| PIPE | 0.8761 | 218 |
| C | 0.8431 | 204 |
| MT | 0.8261 | 161 |
| HP | 0.8654 | 156 |
| B | 0.9615 | 130 |
| XP | 0.8208 | 106 |
| XXP | 0.8171 | 82 |
| P | 0.9877 | 81 |
| JR | 0.9077 | 65 |
| CB | 0.9600 | 50 |
| T FS | 0.7917 | 48 |
| BJ | 0.7692 | 39 |
| WF | 0.8333 | 36 |
| ST JR | 0.7143 | 35 |
| J | 0.9091 | 33 |
| H | 0.9333 | 30 |
| U | 0.8214 | 28 |
| WFCB | 0.7200 | 25 |
| JRC | 0.7778 | 18 |
| JRU | 0.9444 | 18 |
| G | 1.0000 | 15 |
| WFB | 0.7000 | 10 |
| BLB | 0.6667 | 6 |
| BP | 0.6667 | 6 |
| LWF | 0.8333 | 6 |
| BCB | 1.0000 | 5 |

## Sample misses (true label never appeared in candidates)
- `2L` / `2L` --[unknown_char]--> `**`
- `2L` / `2L` --[added_noise]--> `W2L`
- `2L` / `2L1.25X1.25X0.125` --[missing_prefix]--> `2L`
- `2L` / `2L1.25X1.25X0.1875` --[missing_prefix]--> `2L`
- `2L` / `2L1.5X1.5X0.1875` --[added_noise]--> `B2L1.5X1.5X0.1875`
- `2L` / `2L1.5X1.5X0.1875` --[missing_prefix]--> `2L`
- `2L` / `2L1.5X1.5X0.25` --[missing_prefix]--> `2L`
- `2L` / `2L1.75X1.25X0.1875` --[added_noise]--> `W2L1.75X1.25X0.1875`
- `2L` / `2L1.75X1.25X0.25` --[added_noise]--> `B2L1.75X1.25X0.25`
- `2L` / `2L1.75X1.75X0.125` --[missing_prefix]--> `2L`
- `2L` / `2L1.75X1.75X0.1875` --[added_noise]--> `W2L1.75X1.75X0.1875`
- `2L` / `2L10X10X1` --[missing_prefix]--> `2L`
- `2L` / `2L10X10X1-1/4X1-1/2` --[missing_prefix]--> `2L`
- `2L` / `2L10X10X1-1/8` --[missing_prefix]--> `2L`
- `2L` / `2L10X10X1-3/8` --[missing_prefix]--> `2L`
- `2L` / `2L10X10X1-3/8X3/4` --[missing_prefix]--> `2L`
- `2L` / `2L10X10X1X1-1/2` --[added_noise]--> `B2L10X10X1X1-1/2`
- `2L` / `2L10X10X3/4` --[missing_prefix]--> `2L`
- `2L` / `2L10X10X3/4X1-1/2` --[added_noise]--> `B2L10X10X3/4X1-1/2`
- `2L` / `2L10X10X3/4X1-1/2` --[missing_prefix]--> `2L`
- `2L` / `2L10X10X7/8` --[added_noise]--> `W2L10X10X7/8`
- `2L` / `2L10X10X7/8` --[missing_prefix]--> `2L`
- `2L` / `2L11X11X0.5` --[missing_prefix]--> `2L`
- `2L` / `2L12X12X0.4375` --[missing_prefix]--> `2L`
- `2L` / `2L12X12X1` --[added_noise]--> `W2L12X12X1`
- `2L` / `2L12X12X1-1/4` --[missing_prefix]--> `2L`
- `2L` / `2L12X12X1-1/4X3/4` --[added_noise]--> `W2L12X12X1-1/4X3/4`
- `2L` / `2L12X12X1-1/8X1-1/2` --[added_noise]--> `B2L12X12X1-1/8X1-1/2`
- `2L` / `2L12X12X1-1/8X1-1/2` --[missing_prefix]--> `2L`
- `2L` / `2L12X12X1-1/8X3/4` --[added_noise]--> `B2L12X12X1-1/8X3/4`
- `2L` / `2L12X12X1-1/8X3/4` --[missing_prefix]--> `2L`
- `2L` / `2L12X12X1-3/8` --[added_noise]--> `W2L12X12X1-3/8`
- `2L` / `2L12X12X1-3/8X1-1/2` --[missing_prefix]--> `2L`
- `2L` / `2L12X12X1-3/8X3/4` --[added_noise]--> `B2L12X12X1-3/8X3/4`
- `2L` / `2L12X12X1-3/8X3/4` --[missing_prefix]--> `2L`
- `2L` / `2L12X12X1X3/4` --[added_noise]--> `B2L12X12X1X3/4`
- `2L` / `2L13X13X0.375` --[added_noise]--> `W2L13X13X0.375`
- `2L` / `2L14X14X0.3125` --[missing_prefix]--> `2L`
- `2L` / `2L1X1X0.125` --[missing_prefix]--> `2L`
- `2L` / `2L1X1X0.1875` --[missing_prefix]--> `2L`
