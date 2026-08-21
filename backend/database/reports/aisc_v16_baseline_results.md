# AISC v16 baseline results (honest, no Optuna)
Test rows: 6512. Candidate generator: `generate_candidates_v3` (limit=25). ML baseline: one default-hyperparameter XGBRanker (`rank:pairwise`, same params as `train_label_ranker_v3.py`'s `BASE_PARAMS`), trained fresh on this dataset's train split -- no Optuna, no promotion.

**Candidate-generation recall ceiling on this test set: 0.7204** (this is `top1`-of-a-1-item-check, i.e. true-label-in-candidate-set rate -- no re-ranking baseline below can exceed it)

## Overall
| Method | Top-1 | Top-3 | MRR | n |
|---|---|---|---|---|
| deterministic | 0.1405 | 0.1405 | 0.1405 | 6512 |
| string_similarity | 0.7055 | 0.7993 | 0.7555 | 6512 |
| ml_ranker_v3_default | 0.7394 | 0.8151 | 0.7787 | 6512 |

## By catalog scope (modern is the primary benchmark)

### modern
| Method | Top-1 | Top-3 | MRR | n |
|---|---|---|---|---|
| deterministic | 0.1433 | 0.1433 | 0.1433 | 5786 |
| string_similarity | 0.7058 | 0.8000 | 0.7561 | 5786 |
| ml_ranker_v3_default | 0.7383 | 0.8156 | 0.7783 | 5786 |

### historical
| Method | Top-1 | Top-3 | MRR | n |
|---|---|---|---|---|
| deterministic | 0.1185 | 0.1185 | 0.1185 | 726 |
| string_similarity | 0.7025 | 0.7934 | 0.7511 | 726 |
| ml_ranker_v3_default | 0.7479 | 0.8113 | 0.7818 | 726 |

## By designation holdout (unseen-designation generalization)

### seen_designation
| Method | Top-1 | Top-3 | MRR | n |
|---|---|---|---|---|
| deterministic | 0.1345 | 0.1345 | 0.1345 | 4341 |
| string_similarity | 0.6975 | 0.7971 | 0.7509 | 4341 |
| ml_ranker_v3_default | 0.7346 | 0.8150 | 0.7763 | 4341 |

### holdout
| Method | Top-1 | Top-3 | MRR | n |
|---|---|---|---|---|
| deterministic | 0.1525 | 0.1525 | 0.1525 | 2171 |
| string_similarity | 0.7213 | 0.8038 | 0.7648 | 2171 |
| ml_ranker_v3_default | 0.7490 | 0.8153 | 0.7835 | 2171 |

## By corruption type (ml_ranker_v3_default)
| Corruption | Top-1 | Top-3 | MRR | n |
|---|---|---|---|---|
| 0_to_O | 1.0000 | 1.0000 | 1.0000 | 109 |
| 1_to_I | 1.0000 | 1.0000 | 1.0000 | 154 |
| 2_to_Z | 1.0000 | 1.0000 | 1.0000 | 128 |
| 5_to_S | 1.0000 | 1.0000 | 1.0000 | 159 |
| 6_to_G | 1.0000 | 1.0000 | 1.0000 | 59 |
| 8_to_B | 1.0000 | 1.0000 | 1.0000 | 59 |
| B_to_8 | 1.0000 | 1.0000 | 1.0000 | 20 |
| G_to_6 | 1.0000 | 1.0000 | 1.0000 | 1 |
| I_to_1 | 1.0000 | 1.0000 | 1.0000 | 7 |
| L_to_1 | 0.8788 | 0.8788 | 0.8788 | 33 |
| S_to_5 | 1.0000 | 1.0000 | 1.0000 | 123 |
| added_parens | 1.0000 | 1.0000 | 1.0000 | 281 |
| added_prefix_letter | 0.3925 | 0.3925 | 0.3925 | 265 |
| added_suffix_letter | 0.9925 | 1.0000 | 0.9962 | 265 |
| char_deletion_interior | 0.7562 | 0.8607 | 0.8058 | 402 |
| char_deletion_trailing | 0.7989 | 0.9732 | 0.8847 | 373 |
| family_only_partial | 0.2500 | 1.0000 | 0.5833 | 4 |
| missing_family_prefix | 0.4667 | 0.5179 | 0.4918 | 390 |
| multi_corruption_severity_2 | 0.6085 | 0.7210 | 0.6706 | 871 |
| multi_corruption_severity_3 | 0.4776 | 0.6012 | 0.5423 | 1003 |
| multi_corruption_severity_4 | 0.4185 | 0.5109 | 0.4676 | 184 |
| separator_dash | 1.0000 | 1.0000 | 1.0000 | 190 |
| separator_multiply_sign | 1.0000 | 1.0000 | 1.0000 | 194 |
| separator_space | 0.9861 | 0.9861 | 0.9861 | 216 |
| separator_space_after | 1.0000 | 1.0000 | 1.0000 | 210 |
| unknown_char_multi | 0.6861 | 0.8962 | 0.7983 | 395 |
| unknown_char_single | 0.8873 | 0.9808 | 0.9344 | 417 |

## By family (ml_ranker_v3_default, modern families only)
| Family | Top-1 | Top-3 | MRR | n |
|---|---|---|---|---|
| HSS | 0.7464 | 0.8125 | 0.7800 | 2027 |
| 2L | 0.8326 | 0.9104 | 0.8717 | 926 |
| W | 0.6996 | 0.8153 | 0.7613 | 839 |
| WT | 0.6759 | 0.7496 | 0.7145 | 651 |
| L | 0.7748 | 0.8438 | 0.8094 | 493 |
| S | 0.6381 | 0.7335 | 0.6872 | 409 |
| MC | 0.6703 | 0.7582 | 0.7160 | 91 |
| ST | 0.7831 | 0.8072 | 0.7976 | 83 |
| PIPE | 0.6452 | 0.7581 | 0.7105 | 62 |
| C | 0.7705 | 0.8197 | 0.7923 | 61 |
| M | 0.7018 | 0.7018 | 0.7079 | 57 |
| HP | 0.7308 | 0.7500 | 0.7491 | 52 |
| MT | 0.7714 | 0.8286 | 0.8000 | 35 |
