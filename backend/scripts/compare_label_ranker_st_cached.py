"""Offline candidate-ranker comparison against cached ST.pdf predictions.

Loads a registered candidate directly by version. Both ranker flags remain
false; production labels and cache files are never modified.

Run from ``backend/``:
  python scripts/compare_label_ranker_st_cached.py --version-id ID
"""

from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402
from services import database_loader  # noqa: E402
from services.label_reconstruction.candidates import (  # noqa: E402
    conservative_normalize,
    generate_candidates,
    has_reliable_numeric_constraints,
    ineligible_for_section_reconstruction,
    is_missing_thickness_hss,
)
from services.label_reconstruction.catalog_reload import (  # noqa: E402
    refresh_all_dependent_caches,
)
from services.label_reconstruction.ranker import load_ranker_version  # noqa: E402
from services.structural_parser import (  # noqa: E402
    generation_fields_compatible,
    parse_fields,
)

CACHE_PATH = (
    BACKEND_DIR
    / "training"
    / "engineering_artifacts"
    / "doc_0bfc2d61245dbce2"
    / "multimodal"
    / "predictions_view.json"
)
OUTPUT_DIR = (
    BACKEND_DIR
    / "training"
    / "datasets"
    / "label_reconstruction_production_aligned"
)
UNSAFE_LABELS = {
    "HSS18X18X1",
    "HSS18X18X3/8",
    "HSS16X8X1/2",
}


def _text(row: dict) -> str:
    return str(
        row.get("raw_text")
        or row.get("original_token")
        or row.get("corrected_text")
        or ""
    )


def _live_section(row: dict) -> str:
    return str(row.get("section") or row.get("section_prediction") or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-id", required=True)
    args = parser.parse_args()

    if settings.ml_label_ranker_enabled or settings.ml_label_ranker_shadow:
        print("Refusing comparison: both label-ranker flags must be false.")
        return 1
    ranker = load_ranker_version(args.version_id)
    if ranker is None:
        print(f"Candidate model {args.version_id!r} not found.")
        return 1

    database_loader.reset_to_default()
    refresh_all_dependent_caches()
    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    predictions = (
        payload if isinstance(payload, list) else payload.get("predictions", [])
    )

    applications = 0
    disagreements: list[dict] = []
    potential_repairs: list[dict] = []
    unsafe_disagreements: list[dict] = []
    hss18x18x1 = 0
    hss16x8x12 = 0
    plate_contamination = 0
    missing_thickness_forced = 0
    exact_label_changes = 0
    abstentions = {
        "ineligible": 0,
        "missing_thickness": 0,
        "no_candidates": 0,
        "exact_match": 0,
    }

    for row in predictions:
        raw_text = _text(row)
        live_section = _live_section(row)
        normalized = conservative_normalize(raw_text)

        if ineligible_for_section_reconstruction(raw_text, normalized):
            abstentions["ineligible"] += 1
            continue
        if database_loader.is_catalog_label(normalized):
            abstentions["exact_match"] += 1
            if normalized != live_section and raw_text:
                # The ranker is deliberately not applied; this remains zero.
                exact_label_changes += 0
            continue

        candidate_set = generate_candidates(raw_text)
        if is_missing_thickness_hss(normalized):
            abstentions["missing_thickness"] += 1
            continue
        if not candidate_set.candidates:
            abstentions["no_candidates"] += 1
            continue

        applications += 1
        ranked = ranker.rank(
            raw_text,
            candidate_set.candidates,
            generation_reasons=candidate_set.generation_reasons,
            fuzzy_ranks=candidate_set.fuzzy_ranks,
        )
        candidate_pick = ranked[0]
        if candidate_pick == "HSS18X18X1":
            hss18x18x1 += 1
        if candidate_pick == "HSS16X8X1/2":
            hss16x8x12 += 1

        unsafe_reason = None
        if candidate_pick in UNSAFE_LABELS:
            unsafe_reason = "known_unsafe_label"
        if has_reliable_numeric_constraints(normalized):
            query_parse = parse_fields(normalized)
            candidate_parse = parse_fields(candidate_pick)
            if not (
                query_parse.ok
                and candidate_parse.ok
                and query_parse.family == candidate_parse.family
                and query_parse.grammar == candidate_parse.grammar
                and generation_fields_compatible(
                    query_parse.fields, candidate_parse.fields
                )
            ):
                unsafe_reason = "reliable_numeric_constraint_violation"

        if candidate_pick != live_section:
            detail = {
                "raw_text": raw_text,
                "production_section": live_section,
                "candidate_ranker": candidate_pick,
                "deterministic_top": candidate_set.candidates[0],
                "candidate_count": len(candidate_set.candidates),
                "unsafe_reason": unsafe_reason,
            }
            disagreements.append(detail)
            normalized_similarity = SequenceMatcher(
                None, normalized, candidate_pick
            ).ratio()
            live_similarity = SequenceMatcher(
                None, normalized, live_section
            ).ratio()
            if (
                not unsafe_reason
                and normalized_similarity > live_similarity
                and database_loader.is_catalog_label(candidate_pick)
            ):
                potential_repairs.append(
                    {
                        **detail,
                        "ranker_similarity": normalized_similarity,
                        "production_similarity": live_similarity,
                    }
                )
        if unsafe_reason:
            unsafe_disagreements.append(
                {
                    "raw_text": raw_text,
                    "production_section": live_section,
                    "candidate_ranker": candidate_pick,
                    "reason": unsafe_reason,
                }
            )

    result = {
        "comparison_kind": (
            "offline_candidate_vs_cached_production_no_ground_truth"
        ),
        "model_version": ranker.version_id,
        "cache_path": str(CACHE_PATH),
        "prediction_count": len(predictions),
        "flags": {
            "ML_LABEL_RANKER_ENABLED": settings.ml_label_ranker_enabled,
            "ML_LABEL_RANKER_SHADOW": settings.ml_label_ranker_shadow,
        },
        "ranker_applications": applications,
        "disagreements_with_production": len(disagreements),
        "potential_ocr_repairs": len(potential_repairs),
        "unsafe_disagreements": len(unsafe_disagreements),
        "unsafe_counts": {
            "HSS8X8_to_HSS18X18X1": hss18x18x1,
            "HSS6X8X1/2_to_HSS16X8X1/2": hss16x8x12,
            "plate_or_anonymous_to_rolled": plate_contamination,
            "missing_thickness_forced_wall": missing_thickness_forced,
            "exact_label_changes": exact_label_changes,
        },
        "abstention_behavior": abstentions,
        "potential_repair_examples": potential_repairs[:50],
        "disagreement_examples": disagreements[:100],
        "unsafe_examples": unsafe_disagreements[:50],
        "notes": (
            "Potential repairs are not ground-truth accuracy: they are safe "
            "catalog candidates with greater string similarity to raw OCR "
            "than the cached production section."
        ),
    }
    output_path = OUTPUT_DIR / f"st_comparison_{ranker.version_id}.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    print(f"comparison_path: {output_path}", flush=True)
    return 1 if unsafe_disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
