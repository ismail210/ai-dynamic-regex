"""Build the BROADENED deletion/insertion fallback training slice
(companion to ``generate_label_reconstruction_production_aligned.py``).

Why a separate script/dataset version rather than editing the original in
place: the original ``label_reconstruction_production_aligned_20260828``
dataset is what the currently-PROMOTED model was trained and frozen
against (Section 6/13 of the broadened-ranker brief -- "the old model must
remain available for A/B comparison"). Regenerating it in place would
silently change the files on disk out from under that comparison. This
script writes to its own directory/version instead, additive to (never
replacing) the original.

Only rows where ``candidates.is_broadened_fallback_query`` actually agrees
the standard generator would abstain with zero candidates are kept -- most
single corruptions do NOT trigger this (the standard generator already
handles most of them), so this dataset is deliberately small and precise,
not "every deletion/insertion of every catalog label."

Ground truth is exclusively synthetic AISC-catalog corruption (same
provenance model as the original script) -- the held-out PDF-attack
benchmark (``estima3d_pdf_attack_benchmark_v1``) is NEVER read here and
contributes zero rows (Section 6: it is external evaluation data only).

Run from ``backend/``:
  python scripts/generate_label_reconstruction_broadened.py
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
from typing import Iterable

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import database_loader  # noqa: E402
from services.label_reconstruction.candidates import (  # noqa: E402
    CandidateSet,
    _fuzzy_candidates,
    conservative_normalize,
    is_broadened_fallback_query,
)
from services.label_reconstruction.catalog_reload import (  # noqa: E402
    refresh_all_dependent_caches,
)
from services.label_reconstruction.corruption import (  # noqa: E402
    CORRUPTION_FAMILIES,
    generate_multi_corruption,
    generate_single_corruption,
)

OUT_DIR = BACKEND_DIR / "training" / "datasets" / "label_reconstruction_broadened"
DATASET_VERSION = "label_reconstruction_broadened_20260914"
DEFAULT_SEED = 20260914
CANDIDATE_LIMIT = 10
# Only the two corruption families that actually change string LENGTH can
# ever trigger the broadened path (a same-length corruption's target is
# always reachable, if at all, through the standard generator's
# structural-field/OCR-flex strategies) -- restricting generation to these
# keeps this script fast and its output 100% on-topic, per the brief's
# "do not turn this into a giant feature-engineering sprint" instruction.
LENGTH_CHANGING_FAMILIES = ("char_deletion", "char_insertion")


def _variants_for_label(label: str, rng: random.Random) -> list[tuple[str, list[str], int]]:
    variants: list[tuple[str, list[str], int]] = []
    for name, _fn in CORRUPTION_FAMILIES:
        if name not in LENGTH_CHANGING_FAMILIES:
            continue
        result = generate_single_corruption(label, rng, family_name=name)
        if result is not None and result.text != label:
            variants.append((result.text, result.corruption_types, 1))
    # A couple of chained deletion+insertion combinations too (severity 2),
    # restricted to just these two families so the result is still a pure
    # length-changing corruption, never accidentally also an OCR/separator
    # corruption that the standard generator would have handled anyway.
    for _ in range(2):
        result = generate_multi_corruption(label, rng, 2)
        if (
            result is not None
            and result.text != label
            and set(result.corruption_types) & {"char_deletion_trailing", "char_deletion_interior"}
        ):
            variants.append((result.text, result.corruption_types, 2))
    return variants


def _split_for(raw_text: str, seed: int) -> str:
    """Identical formula to generate_label_reconstruction_production_aligned's
    ``_split_for`` (no force_test reservation here -- this slice is too small
    to carve out a combo-holdout the way the much larger original dataset
    does; string-level dedup is still the anti-leakage mechanism)."""

    digest = hashlib.sha256(f"{seed}|{raw_text}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def build_rows(entries: list[tuple[str, str]], seed: int) -> tuple[list[dict], list[dict], dict]:
    labels = sorted({label for label, _family in entries})
    family_by_label = {label: family for label, family in entries}

    raw_variants: dict[str, dict] = {}
    for label in labels:
        rng = random.Random(f"{seed}:broadened:{label}")
        for raw_text, tags, severity in _variants_for_label(label, rng):
            if raw_text in raw_variants:
                continue
            raw_variants[raw_text] = {
                "clean_designation": label,
                "family": family_by_label[label],
                "corruption_type": tags,
                "corruption_severity": severity,
            }

    pointwise_rows: list[dict] = []
    pairwise_rows: list[dict] = []
    decision_counts: Counter[str] = Counter()
    total = len(raw_variants)
    for index, (raw_text, meta) in enumerate(raw_variants.items(), start=1):
        target_label = meta["clean_designation"]
        normalized = conservative_normalize(raw_text)
        triggers_broadening = is_broadened_fallback_query(raw_text, normalized)
        decision = "not_broadened"  # this corruption didn't actually need the fallback -- not useful for this slice
        candidate_labels: list[str] = []
        if triggers_broadening:
            candidate_labels = _fuzzy_candidates(normalized, limit=CANDIDATE_LIMIT)
            decision = "rank_broadened" if target_label in candidate_labels else "abstain_broadened_no_valid_candidate"
        decision_counts[decision] += 1
        if decision == "not_broadened":
            continue  # not a member of this dataset's population at all

        split = _split_for(raw_text, seed)
        row = {
            "row_kind": "pointwise",
            "query": raw_text,
            "normalized_query": normalized,
            "clean_designation": target_label,
            "family": meta["family"],
            "source_kind": "synthetic_catalog_corruption_broadened",
            "corruption_type": meta["corruption_type"],
            "corruption_severity": meta["corruption_severity"],
            "split": split,
            "expected_decision": decision,
            "candidate_labels": candidate_labels,
            "candidate_count": len(candidate_labels),
            "target_in_candidates": target_label in candidate_labels,
            "is_fallback_broadened": True,
            "dataset_version": DATASET_VERSION,
            "seed": seed,
        }
        pointwise_rows.append(row)

        if decision == "rank_broadened":
            for rank, candidate in enumerate(candidate_labels):
                pairwise_rows.append({
                    "row_kind": "pairwise",
                    "query": raw_text,
                    "normalized_query": normalized,
                    "candidate": candidate,
                    "target": int(candidate == target_label),
                    "split": split,
                    "family": meta["family"],
                    "corruption_type": meta["corruption_type"],
                    "corruption_severity": meta["corruption_severity"],
                    "deterministic_rank": None,
                    "fuzzy_rank": rank,
                    "generation_reasons": ["fuzzy_fallback_broadened"],
                    "is_fallback_broadened": True,
                })

        if index % 500 == 0 or index == total:
            print(f"broadened generation: {index}/{total}", flush=True)

    return pointwise_rows, pairwise_rows, dict(decision_counts)


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

    pointwise_rows, pairwise_rows, decision_counts = build_rows(entries, args.seed)

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
        "candidate_generator": "services.label_reconstruction.candidates._fuzzy_candidates",
        "candidate_limit": CANDIDATE_LIMIT,
        "serving_entry_point": "services.label_reconstruction.shadow.reconstruct (broadened branch)",
        "feature_generator": "services.label_reconstruction.features.pair_features",
        "length_changing_families": list(LENGTH_CHANGING_FAMILIES),
        "pointwise_rows": len(pointwise_rows),
        "pairwise_rows": len(pairwise_rows),
        "pointwise_split_counts": dict(sorted(Counter(r["split"] for r in pointwise_rows).items())),
        "pairwise_split_counts": dict(sorted(Counter(r["split"] for r in pairwise_rows).items())),
        "decision_counts": decision_counts,
        "no_pdf_attack_benchmark_data": True,
        "files": {
            "pointwise.jsonl": _sha256(pointwise_path),
            "pairwise.jsonl": _sha256(pairwise_path),
        },
        "notes": (
            "Additive companion to label_reconstruction_production_aligned_20260828 -- "
            "rows here are ONLY the deletion/insertion corruptions for which "
            "candidates.is_broadened_fallback_query is True (i.e. the standard "
            "generator would abstain with zero candidates). 'rank_broadened' "
            "pointwise rows have their target reachable via the broadened "
            "fuzzy-similarity search and produce pairwise ranking groups; "
            "'abstain_broadened_no_valid_candidate' rows are retrieval "
            "failures kept for honest recall@k reporting, never ranking rows."
        ),
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(manifest, indent=2), flush=True)
    print(f"runtime_seconds: {time.time() - started:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
