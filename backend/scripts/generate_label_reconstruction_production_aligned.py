"""Build production-aligned Structural Reconstruction ranking data.

The dataset uses the production catalog and the exact candidate generator
called by ``services.label_reconstruction.shadow.reconstruct``. A ranking
positive is emitted only when the clean catalog designation is present in
that candidate set. Exact, ineligible, missing-thickness, and no-valid-target
queries remain pointwise-only decision records.

Run from ``backend/``:
  python scripts/generate_label_reconstruction_production_aligned.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import FrozenSet, Iterable

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import database_loader  # noqa: E402
from services.label_reconstruction.candidates import (  # noqa: E402
    CandidateSet,
    conservative_normalize,
    generate_candidates,
    ineligible_for_section_reconstruction,
    is_missing_thickness_hss,
)
from services.label_reconstruction.catalog_reload import (  # noqa: E402
    refresh_all_dependent_caches,
)
from services.label_reconstruction.corruption import (  # noqa: E402
    CORRUPTION_FAMILIES,
    generate_multi_corruption,
    generate_single_corruption,
)

OUT_DIR = (
    BACKEND_DIR
    / "training"
    / "datasets"
    / "label_reconstruction_production_aligned"
)
DATASET_VERSION = "label_reconstruction_production_aligned_20260828"
DEFAULT_SEED = 20260827
RESERVED_COMBO_FRACTION = 1 / 7
DESIGNATION_HOLDOUT_FRACTION = 0.08
CANDIDATE_LIMIT = 25

SAFETY_FIXTURES = (
    ("HSS8X8", None, "abstain_missing_thickness"),
    ("HSS8x8", None, "abstain_missing_thickness"),
    ("HSS 8X8 8X8", None, "abstain_missing_thickness"),
    ("HSS10X10", None, "abstain_missing_thickness"),
    ("HSS3X3", None, "abstain_missing_thickness"),
    ("HSS6X8X1/2", None, "abstain_no_valid_candidate"),
    ('PL 3 3/4"', None, "abstain_ineligible"),
    ('PLATE 3 3/8"', None, "abstain_ineligible"),
    ('CAP PL 3/8"', None, "abstain_ineligible"),
    ('CONN PL 1/2"', None, "abstain_ineligible"),
    ('BP 3/8"', None, "abstain_ineligible"),
    ('BENT PLATE 1/2"', None, "abstain_ineligible"),
    ('3/16"', None, "abstain_ineligible"),
    ('5/16".', None, "abstain_ineligible"),
    ('2"x4"x1/4"', None, "abstain_ineligible"),
    ('2"x2"x1/4"', None, "abstain_ineligible"),
    ('1/2"x1/4"', None, "abstain_ineligible"),
    ('1/4"x2"', None, "abstain_ineligible"),
    ('1/2"⌀x6"', None, "abstain_ineligible"),
    ('1/8"x1"', None, "abstain_ineligible"),
    ("4x4", None, "abstain_ineligible"),
    ("3/4X4X6", None, "abstain_ineligible"),
    ("W16X26", "W16X26", "exact_match"),
    ("HSS8X8X1/2", "HSS8X8X1/2", "exact_match"),
)


def _variants_for_label(
    label: str, rng: random.Random
) -> list[tuple[str, list[str], int]]:
    variants: list[tuple[str, list[str], int]] = []
    for name, _fn in CORRUPTION_FAMILIES:
        result = generate_single_corruption(label, rng, family_name=name)
        if result is not None and result.text != label:
            variants.append((result.text, result.corruption_types, 1))
    for severity in (2, 3):
        result = generate_multi_corruption(label, rng, severity)
        if result is not None and result.text != label:
            variants.append(
                (result.text, result.corruption_types, len(result.corruption_types))
            )
    return variants


def _split_for(raw_text: str, seed: int, *, force_test: bool) -> str:
    if force_test:
        return "test"
    digest = hashlib.sha256(f"{seed}|{raw_text}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def _decision_for(
    raw_text: str, target_label: str | None
) -> tuple[str, CandidateSet]:
    normalized = conservative_normalize(raw_text)
    if ineligible_for_section_reconstruction(raw_text, normalized):
        return (
            "abstain_ineligible",
            CandidateSet(normalized, "", [], {}),
        )
    if database_loader.is_catalog_label(normalized):
        return (
            "exact_match",
            CandidateSet(
                normalized,
                "",
                [normalized],
                {normalized: ["exact_match"]},
            ),
        )

    candidate_set = generate_candidates(raw_text, limit=CANDIDATE_LIMIT)
    if is_missing_thickness_hss(normalized):
        return "abstain_missing_thickness", candidate_set
    if target_label and target_label in candidate_set.candidates:
        return "rank", candidate_set
    return "abstain_no_valid_candidate", candidate_set


def build_pointwise_rows(
    entries: list[tuple[str, str]], seed: int
) -> tuple[list[dict], set[str], set[FrozenSet[str]]]:
    labels = sorted({label for label, _family in entries})
    family_by_label = {label: family for label, family in entries}
    holdout_rng = random.Random(f"{seed}:designation_holdout")
    holdout_count = max(1, round(len(labels) * DESIGNATION_HOLDOUT_FRACTION))
    holdout_labels = set(holdout_rng.sample(labels, holdout_count))

    raw_variants: dict[str, dict] = {}
    combo_counts: Counter[FrozenSet[str]] = Counter()
    for label in labels:
        rng = random.Random(f"{seed}:{label}")
        for raw_text, tags, severity in _variants_for_label(label, rng):
            if raw_text in raw_variants:
                continue
            raw_variants[raw_text] = {
                "clean_designation": label,
                "family": family_by_label[label],
                "corruption_type": tags,
                "corruption_severity": severity,
                "source_designation_id": label,
                "source_kind": "synthetic_catalog_corruption",
                "safety_fixture": False,
            }
            if severity >= 2:
                combo_counts[frozenset(tags)] += 1

    combo_keys = sorted(combo_counts, key=lambda combo: sorted(combo))
    reserve_rng = random.Random(f"{seed}:reserved_combos")
    reserve_count = max(1, round(len(combo_keys) * RESERVED_COMBO_FRACTION))
    reserved_combos = set(
        reserve_rng.sample(combo_keys, min(reserve_count, len(combo_keys)))
    )

    for raw_text, target_label, expected_decision in SAFETY_FIXTURES:
        existing = raw_variants.get(raw_text)
        if existing is None:
            raw_variants[raw_text] = {
                "clean_designation": target_label,
                "family": (
                    family_by_label.get(target_label, "") if target_label else ""
                ),
                "corruption_type": ["production_safety_fixture"],
                "corruption_severity": 0,
                "source_designation_id": target_label,
                "source_kind": "production_safety_fixture",
                "safety_fixture": True,
                "fixture_expected_decision": expected_decision,
            }
        else:
            existing["safety_fixture"] = True
            existing["fixture_expected_decision"] = expected_decision

    rows: list[dict] = []
    total = len(raw_variants)
    for index, (raw_text, metadata) in enumerate(raw_variants.items(), start=1):
        target_label = metadata["clean_designation"]
        decision, candidate_set = _decision_for(raw_text, target_label)
        tags = metadata["corruption_type"]
        severity = metadata["corruption_severity"]
        designation_holdout = bool(
            target_label and target_label in holdout_labels
        )
        unseen_combo = (
            severity >= 2 and frozenset(tags) in reserved_combos
        )
        force_test = (
            metadata["safety_fixture"]
            or designation_holdout
            or unseen_combo
        )
        row = {
            "row_kind": "pointwise",
            "query": raw_text,
            "normalized_query": candidate_set.normalized,
            "clean_designation": target_label,
            "family": metadata["family"],
            "source_kind": metadata["source_kind"],
            "source_designation_id": metadata["source_designation_id"],
            "corruption_type": tags,
            "corruption_severity": severity,
            "split": _split_for(raw_text, seed, force_test=force_test),
            "designation_holdout": designation_holdout,
            "unseen_combo": unseen_combo,
            "safety_fixture": metadata["safety_fixture"],
            "fixture_expected_decision": metadata.get(
                "fixture_expected_decision"
            ),
            "expected_decision": decision,
            "candidate_labels": candidate_set.candidates,
            "generation_reasons": candidate_set.generation_reasons,
            "fuzzy_ranks": candidate_set.fuzzy_ranks,
            "candidate_count": len(candidate_set.candidates),
            "target_in_candidates": bool(
                target_label and target_label in candidate_set.candidates
            ),
            "dataset_version": DATASET_VERSION,
            "seed": seed,
        }
        rows.append(row)
        if index % 500 == 0 or index == total:
            print(f"candidate generation: {index}/{total}", flush=True)
    return rows, holdout_labels, reserved_combos


def build_pairwise_rows(pointwise_rows: Iterable[dict]) -> list[dict]:
    rows: list[dict] = []
    for pointwise in pointwise_rows:
        if pointwise["expected_decision"] != "rank":
            continue
        target_label = pointwise["clean_designation"]
        for rank, candidate in enumerate(pointwise["candidate_labels"]):
            rows.append(
                {
                    "row_kind": "pairwise",
                    "query": pointwise["query"],
                    "normalized_query": pointwise["normalized_query"],
                    "candidate": candidate,
                    "target": int(candidate == target_label),
                    "split": pointwise["split"],
                    "family": pointwise["family"],
                    "source_designation_id": pointwise[
                        "source_designation_id"
                    ],
                    "designation_holdout": pointwise[
                        "designation_holdout"
                    ],
                    "corruption_type": pointwise["corruption_type"],
                    "corruption_severity": pointwise[
                        "corruption_severity"
                    ],
                    "deterministic_rank": rank,
                    "generation_reasons": pointwise[
                        "generation_reasons"
                    ].get(candidate, []),
                    "fuzzy_rank": pointwise["fuzzy_ranks"].get(candidate),
                }
            )
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    started = time.time()

    database_loader.reset_to_default()
    refresh_all_dependent_caches()
    entries = database_loader.catalog_entries()
    pointwise_rows, holdout_labels, reserved_combos = build_pointwise_rows(
        entries, args.seed
    )
    pairwise_rows = build_pairwise_rows(pointwise_rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pointwise_path = OUT_DIR / "pointwise.jsonl"
    pairwise_path = OUT_DIR / "pairwise.jsonl"
    _write_jsonl(pointwise_path, pointwise_rows)
    _write_jsonl(pairwise_path, pairwise_rows)

    manifest = {
        "dataset_version": DATASET_VERSION,
        "seed": args.seed,
        "catalog_source": database_loader.catalog_version(),
        "catalog_entries": len(entries),
        "candidate_generator": (
            "services.label_reconstruction.candidates.generate_candidates"
        ),
        "candidate_limit": CANDIDATE_LIMIT,
        "serving_entry_point": (
            "services.label_reconstruction.shadow.reconstruct"
        ),
        "feature_generator": (
            "services.label_reconstruction.features.pair_features"
        ),
        "pointwise_rows": len(pointwise_rows),
        "pairwise_rows": len(pairwise_rows),
        "pointwise_split_counts": dict(
            sorted(Counter(r["split"] for r in pointwise_rows).items())
        ),
        "pairwise_split_counts": dict(
            sorted(Counter(r["split"] for r in pairwise_rows).items())
        ),
        "decision_counts": dict(
            sorted(
                Counter(
                    r["expected_decision"] for r in pointwise_rows
                ).items()
            )
        ),
        "designation_holdout_count": len(holdout_labels),
        "reserved_unseen_combos": sorted(
            sorted(combo) for combo in reserved_combos
        ),
        "safety_fixture_count": sum(
            bool(r["safety_fixture"]) for r in pointwise_rows
        ),
        "files": {
            "pointwise.jsonl": _sha256(pointwise_path),
            "pairwise.jsonl": _sha256(pairwise_path),
        },
        "notes": (
            "Production-aligned ranking data. Pairwise rows contain only "
            "candidates returned by production generate_candidates; exact, "
            "ineligible, missing-thickness, and target-absent queries are "
            "pointwise-only abstention/decision records."
        ),
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(json.dumps(manifest, indent=2), flush=True)
    print(f"runtime_seconds: {time.time() - started:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
