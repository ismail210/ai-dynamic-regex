"""Generate the versioned AISC damaged-label-reconstruction dataset.

Canonical AISC label -> synthetic corruption -> (corrupted text, canonical
label) pairs, for training/evaluating a candidate RANKER (never a generator
-- see ``services.label_reconstruction`` package docstring). This is the
dataset behind docs' Part F/G/H/I: it is the one ML task in this repo that
currently has trustworthy ground truth without waiting on human-reviewed
association data, because the AISC v16 catalog itself defines the correct
answer for every corruption we synthesize.

Two row kinds are produced, both under one dataset version:

* Pointwise rows (``row_kind: "pointwise"``): one row per corrupted string,
  carrying the corruption metadata needed to break accuracy down by
  corruption family/severity later (Part H).
* Pairwise/ranking rows (``row_kind: "pairwise"``): one positive
  (query=corrupted text, candidate=true label, target=1) plus several hard
  negatives (target=0) per pointwise row, for training a ranker. Hard
  negatives come from two sources: same-family catalog entries at small
  edit distance from the TRUE label (the "off-by-one-dimension" confusions
  called out in the spec, e.g. W18X35 vs W18X30/W18X40/W16X35/W21X35), and
  whatever the existing deterministic candidate generator
  (``services.label_reconstruction.candidates.generate_candidates``) itself
  proposes for that corrupted string -- i.e. the negatives a trained ranker
  most needs to learn to de-prioritize are exactly the ones the current
  system already considers plausible.

Splitting (Part I) is deliberately NOT about hiding catalog labels from any
split -- the catalog is fixed and fully known at inference time, so a model
"memorizing" that W18X35 is a valid label is not leakage. What must never
happen is evaluating on the exact corrupted STRING seen during training.
So:

1. Every generated ``raw_corrupted`` string is deduplicated globally before
   splitting -- each distinct string appears in exactly one split.
2. A held-out set of specific multi-corruption TAG COMBINATIONS (e.g. the
   frozenset {"8_to_B", "5_to_S"}) is reserved so those exact combinations
   only ever appear in the test split, even though the individual
   corruption families that compose them appear throughout train/val too.
   This is the "unseen corruption combinations" slice from Part I.3.
3. Remaining strings are assigned by a seeded hash of the string itself
   (70/15/15 train/validation/test), so the split is reproducible for a
   given ``--seed`` without needing to persist a lookup table.

Run from the ``backend/`` directory: ``python scripts/generate_label_corruption_dataset.py``
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from pathlib import Path
from typing import Dict, FrozenSet, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.database_loader import catalog_entries  # noqa: E402
from services.label_reconstruction.candidates import (  # noqa: E402
    conservative_normalize,
    generate_candidates,
)
from services.label_reconstruction.corruption import (  # noqa: E402
    CORRUPTION_FAMILIES,
    family_of,
    generate_multi_corruption,
    generate_single_corruption,
)
from services.training_pipeline import dataset_registry  # noqa: E402

DEFAULT_SEED = 20260807
DATASET_MODALITY = "label_reconstruction"
RESERVED_COMBO_FRACTION = 1 / 7  # ~15% of distinct multi-corruption tag combos
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


def _catalog_labels() -> List[str]:
    return sorted({label for label, _type in catalog_entries()})


def _by_family(labels: List[str]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for label in labels:
        grouped.setdefault(family_of(label), []).append(label)
    return grouped


def _variants_for_label(label: str, rng: random.Random) -> List[Tuple[str, List[str], int]]:
    """One corrupted string per single-corruption family, plus a couple of
    severity-2/3 chained corruptions. Skips families that can't apply."""

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


def build_pointwise_rows(seed: int) -> Tuple[List[dict], Set[FrozenSet[str]]]:
    labels = _catalog_labels()
    raw_variants: List[Tuple[str, str, List[str], int]] = []
    seen_raw: Set[str] = set()
    combo_counts: Dict[FrozenSet[str], int] = {}

    for label in labels:
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
    reserved: Set[FrozenSet[str]] = set()
    if combo_keys:
        rng_reserve = random.Random(f"{seed}:reserved_combos")
        n_reserved = max(1, round(len(combo_keys) * RESERVED_COMBO_FRACTION))
        reserved = set(rng_reserve.sample(combo_keys, min(n_reserved, len(combo_keys))))

    rows: List[dict] = []
    for label, raw, tags, severity in raw_variants:
        force_test = severity >= 2 and frozenset(tags) in reserved
        split = _split_for(raw, seed, force_test=force_test)
        rows.append(
            {
                "row_kind": "pointwise",
                "raw_corrupted": raw,
                "normalized": conservative_normalize(raw),
                "target_label": label,
                "family": family_of(label),
                "corruption_types": tags,
                "severity": severity,
                "split": split,
                "unseen_combo": force_test,
                "supervised": True,
            }
        )
    return rows, reserved


def _hard_negatives_for_label(
    target_label: str, family_pool: List[str], *, k: int
) -> List[str]:
    scored = sorted(
        (label for label in family_pool if label != target_label),
        key=lambda label: (_edit_distance(target_label, label), label),
    )
    return scored[:k]


def build_pairwise_rows(
    pointwise_rows: List[dict], *, k_negatives: int = NEGATIVES_PER_ROW
) -> List[dict]:
    labels = _catalog_labels()
    grouped = _by_family(labels)
    negative_cache: Dict[str, List[str]] = {}

    pairwise: List[dict] = []
    for row in pointwise_rows:
        target = row["target_label"]
        split = row["split"]
        candidate_set = generate_candidates(row["raw_corrupted"], limit=10)

        def _rank_and_reasons(label: str):
            if label in candidate_set.candidates:
                return candidate_set.candidates.index(label), candidate_set.generation_reasons.get(label)
            return None, None

        target_rank, target_reasons = _rank_and_reasons(target)
        pairwise.append(
            {
                "row_kind": "pairwise",
                "query": row["raw_corrupted"],
                "candidate": target,
                "target": 1,
                "split": split,
                "family": row["family"],
                "deterministic_rank": target_rank,
                "generation_reasons": target_reasons,
                "supervised": True,
            }
        )

        if target not in negative_cache:
            pool = grouped.get(row["family"], [])
            negative_cache[target] = _hard_negatives_for_label(
                target, pool, k=k_negatives + 2
            )
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
            negative_rank, negative_reasons = _rank_and_reasons(negative)
            pairwise.append(
                {
                    "row_kind": "pairwise",
                    "query": row["raw_corrupted"],
                    "candidate": negative,
                    "target": 0,
                    "split": split,
                    "family": row["family"],
                    "deterministic_rank": negative_rank,
                    "generation_reasons": negative_reasons,
                    "supervised": True,
                }
            )
            added += 1
            if added >= k_negatives:
                break

    return pairwise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--negatives-per-row", type=int, default=NEGATIVES_PER_ROW)
    args = parser.parse_args()

    pointwise_rows, reserved_combos = build_pointwise_rows(args.seed)
    pairwise_rows = build_pairwise_rows(pointwise_rows, k_negatives=args.negatives_per_row)
    all_rows = pointwise_rows + pairwise_rows

    split_counts: Dict[str, int] = {}
    class_distribution: Dict[str, int] = {}
    source_counts: Dict[str, int] = {"pointwise": 0, "pairwise": 0}
    for row in all_rows:
        split_counts[row["split"]] = split_counts.get(row["split"], 0) + 1
        source_counts[row["row_kind"]] = source_counts.get(row["row_kind"], 0) + 1
        if row["row_kind"] == "pointwise":
            class_distribution[row["family"]] = class_distribution.get(row["family"], 0) + 1

    manifest = dataset_registry.write_dataset_version(
        modality=DATASET_MODALITY,
        samples=all_rows,
        source_counts=source_counts,
        class_distribution=class_distribution,
        split_counts=split_counts,
        feature_schema=[
            "raw_corrupted",
            "normalized",
            "target_label",
            "family",
            "corruption_types",
            "severity",
            "query",
            "candidate",
            "target",
        ],
        config={
            "seed": args.seed,
            "negatives_per_row": args.negatives_per_row,
            "reserved_unseen_combos": sorted(sorted(c) for c in reserved_combos),
            "catalog_version": "aisc-shapes-database-v160-2.xlsx#Database v16.0",
            "corruption_families": [name for name, _ in CORRUPTION_FAMILIES],
        },
        notes=(
            "Synthetic AISC label-corruption dataset for damaged-steel-label "
            "reconstruction (Part F/G/H/I). Pointwise + pairwise-ranking rows "
            "in one version; string-level dedup guarantees no corrupted "
            "instance appears in more than one split; a reserved set of "
            "multi-corruption tag combinations is test-only."
        ),
    )

    print(f"Dataset version: {manifest.version_id}")
    print(f"Pointwise rows: {source_counts['pointwise']}")
    print(f"Pairwise rows: {source_counts['pairwise']}")
    print(f"Split counts (all rows): {split_counts}")
    print(f"Reserved unseen combos: {len(reserved_combos)}")
    print(f"Family distribution (pointwise): {class_distribution}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
