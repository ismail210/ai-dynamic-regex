"""Read-only validator for the production-aligned reconstruction dataset.

Run from ``backend/``:
  python scripts/validate_label_reconstruction_production_aligned.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.generate_label_reconstruction_production_aligned import (  # noqa: E402
    CANDIDATE_LIMIT,
    DATASET_VERSION,
    OUT_DIR,
    SAFETY_FIXTURES,
    _decision_for,
)
from services import database_loader  # noqa: E402
from services.label_reconstruction.candidates import (  # noqa: E402
    conservative_normalize,
    has_reliable_numeric_constraints,
    ineligible_for_section_reconstruction,
    is_missing_thickness_hss,
)
from services.label_reconstruction.catalog_reload import (  # noqa: E402
    refresh_all_dependent_caches,
)
from services.label_reconstruction.features import FEATURE_NAMES, pair_features  # noqa: E402
from services.label_reconstruction.structural_parser import (  # noqa: E402
    generation_fields_compatible,
    parse_fields,
)


def _load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    errors: list[dict] = []

    def fail(invariant: str, row: dict | None, detail: str) -> None:
        if len(errors) < 100:
            errors.append(
                {
                    "invariant": invariant,
                    "query": row.get("query") if row else None,
                    "detail": detail,
                }
            )

    manifest = json.loads((OUT_DIR / "manifest.json").read_text(encoding="utf-8"))
    pointwise = _load_jsonl(OUT_DIR / "pointwise.jsonl")
    pairwise = _load_jsonl(OUT_DIR / "pairwise.jsonl")
    points_by_query = {row["query"]: row for row in pointwise}
    pairs_by_query: dict[str, list[dict]] = defaultdict(list)
    for row in pairwise:
        pairs_by_query[row["query"]].append(row)

    if len(points_by_query) != len(pointwise):
        fail("split_unique_query", None, "duplicate pointwise query")
    if manifest.get("dataset_version") != DATASET_VERSION:
        fail("dataset_version", None, str(manifest.get("dataset_version")))
    if manifest.get("candidate_limit") != CANDIDATE_LIMIT:
        fail("candidate_limit", None, str(manifest.get("candidate_limit")))
    if manifest.get("candidate_generator") != (
        "services.label_reconstruction.candidates.generate_candidates"
    ):
        fail("train_serve_candidate_generator", None, str(manifest))
    if manifest.get("feature_generator") != (
        "services.label_reconstruction.features.pair_features"
    ):
        fail("train_serve_feature_generator", None, str(manifest))

    database_loader.reset_to_default()
    refresh_all_dependent_caches()

    numeric_violations: list[dict] = []
    for index, row in enumerate(pointwise, start=1):
        target = row.get("clean_designation")
        decision, candidate_set = _decision_for(row["query"], target)
        if decision != row["expected_decision"]:
            fail(
                "recomputed_decision",
                row,
                f"stored={row['expected_decision']} recomputed={decision}",
            )
        if candidate_set.candidates != row["candidate_labels"]:
            fail(
                "recomputed_candidate_set",
                row,
                "stored candidates differ from production generator",
            )
        if candidate_set.generation_reasons != row["generation_reasons"]:
            fail(
                "recomputed_generation_reasons",
                row,
                "stored reasons differ from production generator",
            )

        pair_rows = pairs_by_query.get(row["query"], [])
        if decision == "rank":
            if not target or target not in candidate_set.candidates:
                fail("rank_target_present", row, f"target={target!r}")
            positives = [pair for pair in pair_rows if pair["target"] == 1]
            if len(positives) != 1 or positives[0]["candidate"] != target:
                fail("one_valid_positive", row, f"positives={positives!r}")
            if [pair["candidate"] for pair in pair_rows] != candidate_set.candidates:
                fail(
                    "pairwise_equals_production_candidates",
                    row,
                    "pairwise candidate order differs",
                )
        elif pair_rows:
            fail(
                "abstention_has_no_pairwise_rows",
                row,
                f"{len(pair_rows)} pairwise rows",
            )

        normalized = conservative_normalize(row["query"])
        if has_reliable_numeric_constraints(normalized):
            query_parse = parse_fields(normalized)
            for candidate in candidate_set.candidates:
                candidate_parse = parse_fields(candidate)
                compatible = (
                    query_parse.ok
                    and candidate_parse.ok
                    and query_parse.family == candidate_parse.family
                    and query_parse.grammar == candidate_parse.grammar
                    and generation_fields_compatible(
                        query_parse.fields, candidate_parse.fields
                    )
                )
                if not compatible:
                    violation = {
                        "query": row["query"],
                        "candidate": candidate,
                        "query_fields": query_parse.fields,
                        "candidate_fields": candidate_parse.fields,
                    }
                    numeric_violations.append(violation)
                    fail(
                        "reliable_numeric_candidate_compatibility",
                        row,
                        json.dumps(violation),
                    )
        if index % 500 == 0 or index == len(pointwise):
            print(f"validation: {index}/{len(pointwise)}", flush=True)

    for pair in pairwise:
        point = points_by_query.get(pair["query"])
        if point is None:
            fail("orphan_pairwise_row", pair, "query missing from pointwise")
            continue
        if pair["candidate"] not in point["candidate_labels"]:
            fail(
                "pairwise_candidate_allowed",
                pair,
                f"candidate={pair['candidate']}",
            )
        if pair["target"] == 1 and pair["candidate"] != point.get(
            "clean_designation"
        ):
            fail("positive_matches_clean_target", pair, str(pair))

    fixture_results = {}
    for query, _target, expected_decision in SAFETY_FIXTURES:
        row = points_by_query.get(query)
        if row is None:
            fail("safety_fixture_present", {"query": query}, "missing")
            continue
        fixture_results[query] = {
            "decision": row["expected_decision"],
            "candidate_count": row["candidate_count"],
            "candidates": row["candidate_labels"],
        }
        if row["expected_decision"] != expected_decision:
            fail(
                "safety_fixture_decision",
                row,
                f"expected={expected_decision}",
            )
        if pairs_by_query.get(query):
            fail("safety_fixture_not_ranked", row, "pairwise rows exist")

    for query in ("HSS8X8", "HSS8x8", "HSS 8X8 8X8"):
        row = points_by_query.get(query)
        if row and any(
            not candidate.startswith("HSS8X8X")
            for candidate in row["candidate_labels"]
        ):
            fail("hss8x8_dimensions", row, str(row["candidate_labels"]))
    for query in ("HSS8X8", "HSS8x8", "HSS 8X8 8X8"):
        if any(
            pair["target"] == 1
            and pair["candidate"] in {"HSS18X18X1", "HSS18X18X3/8"}
            for pair in pairs_by_query.get(query, [])
        ):
            fail("hss8x8_unsafe_positive", points_by_query[query], "")

    hss6 = points_by_query.get("HSS6X8X1/2")
    if hss6 and (
        hss6["candidate_labels"]
        or hss6["expected_decision"] != "abstain_no_valid_candidate"
    ):
        fail("hss6x8_abstains", hss6, str(hss6))
    if any(
        pair["target"] == 1 and pair["candidate"] == "HSS16X8X1/2"
        for pair in pairs_by_query.get("HSS6X8X1/2", [])
    ):
        fail("hss6x8_no_hss16_positive", hss6, "")

    for row in pointwise:
        normalized = conservative_normalize(row["query"])
        if ineligible_for_section_reconstruction(row["query"], normalized):
            if row["expected_decision"] != "abstain_ineligible":
                fail("ineligible_abstains", row, row["expected_decision"])
            if pairs_by_query.get(row["query"]):
                fail("ineligible_not_ranked", row, "")
        if is_missing_thickness_hss(normalized):
            if row["expected_decision"] != "abstain_missing_thickness":
                fail("missing_thickness_abstains", row, row["expected_decision"])
            if pairs_by_query.get(row["query"]):
                fail("missing_thickness_not_ranked", row, "")

    split_by_query: dict[str, set[str]] = defaultdict(set)
    ids_by_split: dict[str, set[str]] = defaultdict(set)
    holdout_ids: set[str] = set()
    for row in pointwise:
        split_by_query[row["query"]].add(row["split"])
        source_id = row.get("source_designation_id")
        if source_id:
            ids_by_split[row["split"]].add(source_id)
            if row["designation_holdout"]:
                holdout_ids.add(source_id)
                if row["split"] != "test":
                    fail("holdout_test_only", row, row["split"])
    for query, splits in split_by_query.items():
        if len(splits) > 1:
            fail(
                "query_cross_split",
                {"query": query},
                ",".join(sorted(splits)),
            )
    for split in ("train", "validation"):
        overlap = holdout_ids & ids_by_split[split]
        if overlap:
            fail("holdout_designation_leakage", None, f"{split}={len(overlap)}")

    # Execute one shared feature call as a schema guard.
    sample_pair = pairwise[0] if pairwise else None
    if sample_pair:
        sample_features = pair_features(
            sample_pair["query"],
            sample_pair["candidate"],
            rank=sample_pair["deterministic_rank"],
            reasons=sample_pair["generation_reasons"],
            fuzzy_rank=sample_pair.get("fuzzy_rank"),
        )
        if list(sample_features) != FEATURE_NAMES:
            fail("feature_schema", sample_pair, "pair_features != FEATURE_NAMES")

    report = {
        "status": "PASS" if not errors else "FAIL",
        "dataset_version": manifest.get("dataset_version"),
        "catalog_source": manifest.get("catalog_source"),
        "pointwise_rows": len(pointwise),
        "pairwise_rows": len(pairwise),
        "pointwise_split_counts": dict(
            sorted(Counter(row["split"] for row in pointwise).items())
        ),
        "pairwise_split_counts": dict(
            sorted(Counter(row["split"] for row in pairwise).items())
        ),
        "decision_counts": dict(
            sorted(
                Counter(row["expected_decision"] for row in pointwise).items()
            )
        ),
        "duplicate_queries": len(pointwise) - len(points_by_query),
        "designation_overlap": {
            "train_validation": len(
                ids_by_split["train"] & ids_by_split["validation"]
            ),
            "train_test": len(ids_by_split["train"] & ids_by_split["test"]),
            "validation_test": len(
                ids_by_split["validation"] & ids_by_split["test"]
            ),
        },
        "designation_holdout_count": len(holdout_ids),
        "holdout_in_train": len(holdout_ids & ids_by_split["train"]),
        "holdout_in_validation": len(
            holdout_ids & ids_by_split["validation"]
        ),
        "numeric_candidate_violations": len(numeric_violations),
        "candidate_generator": manifest.get("candidate_generator"),
        "feature_generator": manifest.get("feature_generator"),
        "safety_fixtures": fixture_results,
        "errors": errors,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
