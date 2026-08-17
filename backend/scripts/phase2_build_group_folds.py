"""
Phase 2: build leakage-safe grouped 5-fold CV over the development pool
(train + validation, legacy_external_test excluded entirely).

Grouping key: source_designation_id (see phase0_reproducibility.json --
1:1 with clean_designation; matches the catalog row identity the existing
designation_holdout mechanism already uses). Every pairwise row derived
from corruptions of the same underlying clean designation goes to the same
fold, so no fold's validation half can see a designation its training half
also saw -- the exact leakage class GroupKFold exists to prevent.

Uses sklearn's StratifiedGroupKFold (family as the stratification label)
if plain GroupKFold produces meaningfully imbalanced per-fold family
distribution; falls back to reporting why if not needed.

Persists:
  fold_assignment.json   -- group_id -> fold index (0-4), single source of truth
  fold_audit.json        -- per-fold counts/distributions + leakage check

Run from `backend/`: python scripts/phase2_build_group_folds.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_v16"
EXPERIMENT_DIR = BACKEND_DIR / "training" / "experiments" / "v16_ranker_groupcv_20260816"
N_SPLITS = 5
SEED = 20260813


def _load_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def family_imbalance_score(fold_family_counts: list[Counter]) -> float:
    """Max relative deviation of any family's per-fold share from its
    overall share, across all folds and families -- 0.0 is perfectly even."""
    total = Counter()
    for c in fold_family_counts:
        total.update(c)
    overall_total = sum(total.values())
    worst = 0.0
    for fam, overall_count in total.items():
        overall_share = overall_count / overall_total
        for c in fold_family_counts:
            fold_total = sum(c.values()) or 1
            fold_share = c.get(fam, 0) / fold_total
            worst = max(worst, abs(fold_share - overall_share))
    return worst


def main() -> int:
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)

    pointwise_rows = _load_jsonl(DATA_DIR / "pointwise.jsonl")
    corrupted_to_group = {r["corrupted_text"]: r["source_designation_id"] for r in pointwise_rows}
    corrupted_to_family = {r["corrupted_text"]: r["family"] for r in pointwise_rows}
    corrupted_to_severity = {r["corrupted_text"]: r["corruption_severity"] for r in pointwise_rows}
    corrupted_to_corrtype = {
        r["corrupted_text"]: ((r["corruption_type"] or ["none"])[0] if r["corruption_severity"] == 1
                               else f"multi_corruption_severity_{r['corruption_severity']}")
        for r in pointwise_rows
    }

    pairwise_rows = _load_jsonl(DATA_DIR / "pairwise.jsonl")
    dev_rows = [r for r in pairwise_rows if r["split"] in ("train", "validation")]
    print(f"development pool (train+validation) pairwise rows: {len(dev_rows)}")

    # Group by query (== a ranking group of 1 positive + N negatives), then
    # tag every query-group with its designation-level group id and family.
    query_to_rows = defaultdict(list)
    for r in dev_rows:
        query_to_rows[r["query"]].append(r)
    queries = sorted(query_to_rows.keys())  # stable order
    query_group_id = np.array([corrupted_to_group[q] for q in queries])
    query_family = np.array([corrupted_to_family[q] for q in queries])

    unique_groups = sorted(set(query_group_id))
    print(f"unique query-groups (ranking groups): {len(queries)}")
    print(f"unique designation-level groups (source_designation_id): {len(unique_groups)}")

    # --- Try plain GroupKFold first ---
    gkf = GroupKFold(n_splits=N_SPLITS)
    plain_fold_of_query = np.full(len(queries), -1, dtype=int)
    plain_family_counts = [Counter() for _ in range(N_SPLITS)]
    for fold_idx, (_, val_idx) in enumerate(gkf.split(queries, groups=query_group_id)):
        plain_fold_of_query[val_idx] = fold_idx
        for i in val_idx:
            plain_family_counts[fold_idx][query_family[i]] += 1
    plain_imbalance = family_imbalance_score(plain_family_counts)
    print(f"plain GroupKFold max family-share deviation across folds: {plain_imbalance:.4f}")

    # --- Try StratifiedGroupKFold (family as stratification label) ---
    sgkf = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    strat_fold_of_query = np.full(len(queries), -1, dtype=int)
    strat_family_counts = [Counter() for _ in range(N_SPLITS)]
    for fold_idx, (_, val_idx) in enumerate(sgkf.split(queries, y=query_family, groups=query_group_id)):
        strat_fold_of_query[val_idx] = fold_idx
        for i in val_idx:
            strat_family_counts[fold_idx][query_family[i]] += 1
    strat_imbalance = family_imbalance_score(strat_family_counts)
    print(f"StratifiedGroupKFold max family-share deviation across folds: {strat_imbalance:.4f}")

    use_stratified = strat_imbalance < plain_imbalance
    fold_of_query = strat_fold_of_query if use_stratified else plain_fold_of_query
    method = "StratifiedGroupKFold" if use_stratified else "GroupKFold"
    print(f"\nusing {method} (lower max family-share deviation)")

    # --- Leakage assertion: group ids must never cross fold boundary ---
    group_to_fold = {}
    for q, f in zip(queries, fold_of_query):
        gid = corrupted_to_group[q]
        f = int(f)
        if gid in group_to_fold:
            assert group_to_fold[gid] == f, f"LEAKAGE: group {gid} split across folds"
        group_to_fold[gid] = f
    print(f"leakage assertion passed: all {len(group_to_fold)} designation groups map to exactly one fold each")

    for fold_idx in range(N_SPLITS):
        train_groups = {g for g, f in group_to_fold.items() if f != fold_idx}
        val_groups = {g for g, f in group_to_fold.items() if f == fold_idx}
        overlap = train_groups & val_groups
        assert not overlap, f"LEAKAGE in fold {fold_idx}: {overlap}"
    print("cross-checked intersection(train_group_ids, val_group_ids) == empty for all 5 folds")

    # --- Persist fold assignment (group_id -> fold) ---
    (EXPERIMENT_DIR / "fold_assignment.json").write_text(
        json.dumps({"method": method, "n_splits": N_SPLITS, "seed": SEED, "group_to_fold": group_to_fold}, indent=2),
        encoding="utf-8",
    )

    # --- Fold audit ---
    audit = {"method": method, "n_splits": N_SPLITS}
    for fold_idx in range(N_SPLITS):
        val_mask = fold_of_query == fold_idx
        val_queries = [q for q, m in zip(queries, val_mask) if m]
        train_queries = [q for q, m in zip(queries, val_mask) if not m]
        val_rows_n = sum(len(query_to_rows[q]) for q in val_queries)
        train_rows_n = sum(len(query_to_rows[q]) for q in train_queries)
        val_designations = {corrupted_to_group[q] for q in val_queries}
        train_designations = {corrupted_to_group[q] for q in train_queries}
        fam_counts = Counter(corrupted_to_family[q] for q in val_queries)
        corr_counts = Counter(corrupted_to_corrtype[q] for q in val_queries)
        sev_counts = Counter(corrupted_to_severity[q] for q in val_queries)
        audit[f"fold_{fold_idx}"] = {
            "train_query_groups": len(train_queries),
            "val_query_groups": len(val_queries),
            "train_rows": train_rows_n,
            "val_rows": val_rows_n,
            "train_unique_designations": len(train_designations),
            "val_unique_designations": len(val_designations),
            "val_family_distribution": dict(fam_counts.most_common()),
            "val_corruption_distribution": dict(corr_counts.most_common()),
            "val_severity_distribution": {str(k): v for k, v in sev_counts.most_common()},
        }
    (EXPERIMENT_DIR / "fold_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    for fold_idx in range(N_SPLITS):
        a = audit[f"fold_{fold_idx}"]
        print(f"fold {fold_idx}: train_groups={a['train_query_groups']} val_groups={a['val_query_groups']} "
              f"train_rows={a['train_rows']} val_rows={a['val_rows']} val_designations={a['val_unique_designations']}")

    print(f"\nsaved fold_assignment.json and fold_audit.json to {EXPERIMENT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
