# AISC v16 ranker feature-group ablation
Train groups: 16781, validation groups: 3547. Metric: group top-1 accuracy (highest-scored candidate in each (query, candidate-set) group is the true label). Each `without_X` row zeroes group X's columns in both train and validation matrices and retrains from scratch -- same architecture/hyperparameters as the `all_features` row, only the information changes.

| Condition | Group top-1 accuracy | Delta vs all_features |
|---|---|---|
| all_features | 0.9439 | -- |
| without_length | 0.9402 | -0.0037 |
| without_edit_distance | 0.9281 | -0.0158 |
| without_char_position | 0.9478 | +0.0039 |
| without_family | 0.9436 | -0.0003 |
| without_structural_dims | 0.9436 | -0.0003 |
| without_generation_provenance | 0.9611 | +0.0172 |

## Geometry/graph features
Not included above: an architecture audit of `services/label_reconstruction/features.py` and `ranker.py` found **zero** geometry/graph/fusion features wired into the label ranker at all (`services.multimodal`'s geometry/graph/fusion machinery feeds a separate scoring path, not this one). There is nothing to ablate here -- the honest answer to "are geometry/graph features helping label ranking" is that they cannot be, because none currently exist in this model.
