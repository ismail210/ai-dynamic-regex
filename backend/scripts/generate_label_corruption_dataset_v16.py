"""
Synthetic OCR-corruption dataset for the AISC v16 all-editions catalog
(3,842 designations, 37 families) -- the training-prep counterpart of
``generate_label_corruption_dataset.py`` (which targets the old 2,299-label
catalog and writes into the versioned production dataset registry).

This script is deliberately NOT registered through
``services.training_pipeline.dataset_registry`` -- it is exploratory/prep
data for an honest first baseline against the larger catalog, not a
promoted training artifact. Output is plain JSONL + a manifest, written to
``training/datasets/label_reconstruction_v16/``.

Reuses the exact same corruption machinery
(``services.label_reconstruction.corruption``) and candidate generator
(``generate_candidates_v3``) as production, just pointed at the new catalog
via ``services.database_loader.reload_from_aisc_v16_catalog`` (restored to
the production catalog before exit).

Row schema (pointwise): clean_designation, family, catalog_scope,
corruption_type, corrupted_text, corruption_severity, source_designation_id
(source_row_id from the v16 catalog CSV), source_edition, split,
designation_holdout, unseen_combo, dataset_version, seed.

Splitting (Phase 8 -- leakage-free):
  1. Every corrupted string is deduplicated globally before splitting (no
     corrupted instance appears in more than one split).
  2. A fraction of DISTINCT CANONICAL DESIGNATIONS is reserved as a
     designation-level holdout: every row for those designations is forced
     into "test" (`designation_holdout=True`) regardless of string hash --
     this measures generalization to designations never seen in training at
     all, not just unseen corrupted spellings of a seen designation.
  3. A fraction of multi-corruption tag COMBINATIONS is separately reserved
     test-only, to measure generalization to unseen corruption patterns.
  4. Everything else is assigned by a seeded hash of the corrupted string
     (70/15/15 train/validation/test).
These are independent, layered holdouts -- a row can be a "seen-designation,
unseen-corruption" test case (the common case) or additionally an
"unseen-designation" test case (holdout designations only).

Hard negatives (Phase 7) come from the same two sources as the production
v2 generator: same-family catalog entries at small edit distance from the
true label, plus whatever `generate_candidates_v3` itself proposes for the
corrupted string -- the negatives a ranker most needs to learn to
de-prioritize are exactly the ones the deterministic system already
considers plausible. Negative difficulty (mean/median edit distance vs a
random-negative baseline) is reported in the manifest, not per-row.

Run from `backend/`: python scripts/generate_label_corruption_dataset_v16.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Dict, FrozenSet, List, Set, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import database_loader  # noqa: E402
from services.label_reconstruction.candidates import generate_candidates_v3  # noqa: E402
from services.label_reconstruction.catalog_reload import refresh_all_dependent_caches  # noqa: E402
from services.label_reconstruction.corruption import (  # noqa: E402
    CORRUPTION_FAMILIES,
    generate_multi_corruption,
    generate_single_corruption,
)

DATABASE_DIR = BACKEND_DIR / "database"
CATALOG_PATH = DATABASE_DIR / "aisc_v16_label_catalog.csv"
OUT_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_v16"

DEFAULT_SEED = 20260813
DATASET_VERSION = "label_reconstruction_v16_20260813"
RESERVED_COMBO_FRACTION = 1 / 7
DESIGNATION_HOLDOUT_FRACTION = 0.08  # ~8% of distinct canonical designations
NEGATIVES_PER_ROW = 4


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def _variants_for_label(label: str, rng: random.Random) -> List[Tuple[str, List[str], int]]:
    out: List[Tuple[str, List[str], int]] = []
    for name, _fn in CORRUPTION_FAMILIES:
        result = generate_single_corruption(label, rng, family_name=name)
        if result is not None and result.text != label:
            out.append((result.text, result.corruption_types, 1))
    for severity in (2, 3):
        result = generate_multi_corruption(label, rng, severity)
        if result is not None and result.text != label:
            out.append((result.text, result.corruption_types, len(result.corruption_types)))
    return out


def _split_for(raw_corrupted: str, seed: int, *, force_test: bool) -> str:
    if force_test:
        return "test"
    digest = hashlib.sha256(f"{seed}|{raw_corrupted}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def build_pointwise_rows(entries, seed: int):
    rng_holdout = random.Random(f"{seed}:designation_holdout")
    designations = sorted(e.designation for e in entries)
    n_holdout = max(1, round(len(designations) * DESIGNATION_HOLDOUT_FRACTION))
    holdout_designations: Set[str] = set(rng_holdout.sample(designations, n_holdout))

    by_designation = {e.designation: e for e in entries}
    raw_variants: List[Tuple[str, List[str], int]] = []
    seen_raw: Set[str] = set()
    combo_counts: Dict[FrozenSet[str], int] = {}

    for entry in entries:
        label = entry.designation
        rng = random.Random(f"{seed}:{label}")
        for raw, tags, severity in _variants_for_label(label, rng):
            if raw in seen_raw or raw == label:
                continue
            seen_raw.add(raw)
            raw_variants.append((label, raw, tags, severity))
            if severity >= 2:
                key = frozenset(tags)
                combo_counts[key] = combo_counts.get(key, 0) + 1

    combo_keys = sorted(combo_counts.keys(), key=lambda combo: sorted(combo))
    reserved_combos: Set[FrozenSet[str]] = set()
    if combo_keys:
        rng_reserve = random.Random(f"{seed}:reserved_combos")
        n_reserved = max(1, round(len(combo_keys) * RESERVED_COMBO_FRACTION))
        reserved_combos = set(rng_reserve.sample(combo_keys, min(n_reserved, len(combo_keys))))

    rows: List[dict] = []
    for label, raw, tags, severity in raw_variants:
        entry = by_designation[label]
        is_holdout = label in holdout_designations
        unseen_combo = severity >= 2 and frozenset(tags) in reserved_combos
        force_test = is_holdout or unseen_combo
        split = _split_for(raw, seed, force_test=force_test)
        rows.append(
            {
                "row_kind": "pointwise",
                "clean_designation": label,
                "family": entry.family,
                "catalog_scope": entry.catalog_scope,
                "corrupted_text": raw,
                "corruption_type": tags,
                "corruption_severity": severity,
                "source_designation_id": entry.source_row_id,
                "source_edition": entry.source_edition,
                "split": split,
                "designation_holdout": is_holdout,
                "unseen_combo": unseen_combo,
                "dataset_version": DATASET_VERSION,
                "seed": seed,
            }
        )
    return rows, holdout_designations, reserved_combos


def build_pairwise_rows(pointwise_rows: List[dict], entries, *, k_negatives: int):
    by_family: Dict[str, List[str]] = {}
    for entry in entries:
        by_family.setdefault(entry.family, []).append(entry.designation)

    negative_cache: Dict[str, List[str]] = {}
    negative_edit_distances: List[int] = []
    random_edit_distances: List[int] = []
    rng_random_baseline = random.Random(f"{DEFAULT_SEED}:random_negative_baseline")
    all_labels = sorted(by_designation_labels(entries))

    pairwise: List[dict] = []
    for row in pointwise_rows:
        target = row["clean_designation"]
        candidate_set = generate_candidates_v3(row["corrupted_text"], limit=10)

        pairwise.append(
            {
                "row_kind": "pairwise",
                "query": row["corrupted_text"],
                "candidate": target,
                "target": 1,
                "split": row["split"],
                "family": row["family"],
                "catalog_scope": row["catalog_scope"],
                "designation_holdout": row["designation_holdout"],
                "deterministic_rank": (
                    candidate_set.candidates.index(target)
                    if target in candidate_set.candidates
                    else None
                ),
            }
        )

        if target not in negative_cache:
            pool = by_family.get(row["family"], [])
            scored = sorted(
                (label for label in pool if label != target),
                key=lambda label: (_edit_distance(target, label), label),
            )
            negative_cache[target] = scored[: k_negatives + 2]
        negatives = list(negative_cache[target])
        for candidate in candidate_set.candidates:
            if candidate != target and candidate not in negatives:
                negatives.append(candidate)

        seen_neg: Set[str] = set()
        added = 0
        for negative in negatives:
            if negative in seen_neg or negative == target:
                continue
            seen_neg.add(negative)
            negative_edit_distances.append(_edit_distance(target, negative))
            random_label = rng_random_baseline.choice(all_labels)
            random_edit_distances.append(_edit_distance(target, random_label))
            pairwise.append(
                {
                    "row_kind": "pairwise",
                    "query": row["corrupted_text"],
                    "candidate": negative,
                    "target": 0,
                    "split": row["split"],
                    "family": row["family"],
                    "catalog_scope": row["catalog_scope"],
                    "designation_holdout": row["designation_holdout"],
                    "deterministic_rank": (
                        candidate_set.candidates.index(negative)
                        if negative in candidate_set.candidates
                        else None
                    ),
                }
            )
            added += 1
            if added >= k_negatives:
                break

    return pairwise, negative_edit_distances, random_edit_distances


def by_designation_labels(entries) -> List[str]:
    return [e.designation for e in entries]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--negatives-per-row", type=int, default=NEGATIVES_PER_ROW)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    catalog = database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    try:
        entries = catalog.entries()
        pointwise_rows, holdout_designations, reserved_combos = build_pointwise_rows(
            entries, args.seed
        )
        pairwise_rows, negative_dists, random_dists = build_pairwise_rows(
            pointwise_rows, entries, k_negatives=args.negatives_per_row
        )

        pointwise_path = OUT_DIR / "pointwise.jsonl"
        pairwise_path = OUT_DIR / "pairwise.jsonl"
        with pointwise_path.open("w", encoding="utf-8") as handle:
            for row in pointwise_rows:
                handle.write(json.dumps(row) + "\n")
        with pairwise_path.open("w", encoding="utf-8") as handle:
            for row in pairwise_rows:
                handle.write(json.dumps(row) + "\n")

        split_counts: Dict[str, int] = {}
        for row in pointwise_rows:
            split_counts[row["split"]] = split_counts.get(row["split"], 0) + 1

        mean_neg_dist = sum(negative_dists) / len(negative_dists) if negative_dists else 0.0
        mean_rand_dist = sum(random_dists) / len(random_dists) if random_dists else 0.0

        manifest = {
            "dataset_version": DATASET_VERSION,
            "seed": args.seed,
            "catalog_path": str(CATALOG_PATH.relative_to(BACKEND_DIR)),
            "catalog_entries": len(entries),
            "catalog_families": len(catalog.families()),
            "pointwise_rows": len(pointwise_rows),
            "pairwise_rows": len(pairwise_rows),
            "split_counts_pointwise": split_counts,
            "designation_holdout_count": len(holdout_designations),
            "designation_holdout_fraction_target": DESIGNATION_HOLDOUT_FRACTION,
            "reserved_unseen_combos": sorted(sorted(c) for c in reserved_combos),
            "negatives_per_row": args.negatives_per_row,
            "negative_difficulty": {
                "mean_hard_negative_edit_distance": round(mean_neg_dist, 3),
                "mean_random_negative_edit_distance": round(mean_rand_dist, 3),
                "note": (
                    "Hard negatives should be meaningfully CLOSER (lower edit "
                    "distance) to the true label than a random same-family "
                    "negative -- otherwise the ranker isn't being trained "
                    "against realistic confusions."
                ),
            },
            "corruption_families": [name for name, _ in CORRUPTION_FAMILIES],
        }
        (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        print(f"pointwise rows: {len(pointwise_rows)}")
        print(f"pairwise rows: {len(pairwise_rows)}")
        print(f"split counts (pointwise): {split_counts}")
        print(f"designation holdout: {len(holdout_designations)} designations")
        print(f"reserved unseen combos: {len(reserved_combos)}")
        print(f"mean hard-negative edit distance: {mean_neg_dist:.2f} vs random {mean_rand_dist:.2f}")
        print(f"written to: {OUT_DIR}")
        return 0
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()


if __name__ == "__main__":
    raise SystemExit(main())
