"""
Pipeline evaluation report (Phase 11).

Read-only: never retrains a model, never mutates approved/unknown/history
datasets. Reports four DELIBERATELY SEPARATE sections rather than one
headline number, because extraction fidelity, prediction accuracy, review
behavior, and confidence calibration measure different things and mixing
them hides which stage of the pipeline is actually weak:

  A. Extraction fidelity   — how well raw text/provenance was captured
  B. Prediction performance — how well the AI pipeline chose a label
  C. Review behavior        — how much human review the pipeline requires
  D. Confidence             — whether displayed scores are trustworthy

Where ground truth is scoped to a document/project, metrics are grouped by
that document rather than pooled across every token, which is what would
leak — repeating the same easy label hundreds of times on one drawing must
not drown out a handful of hard labels on another.

Usage:
    cd backend
    python scripts/evaluate_pipeline.py [--output report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from services.artifact_store import read_artifact  # noqa: E402
from services.dataset_manager import dataset_manager  # noqa: E402
from services.prediction.calibration import fit_calibration  # noqa: E402
from services.prediction.orchestrator import predict_token  # noqa: E402
from services.wildcard_matcher import has_wildcards  # noqa: E402


def _corruption_type(token: str) -> str:
    if has_wildcards(token):
        return "wildcard"
    if any(not char.isalnum() for char in token if char not in "X./-"):
        return "ocr_noise"
    return "clean"


def section_extraction_fidelity() -> Dict[str, Any]:
    """A. Extraction fidelity — from every analyzed document's persisted
    predictions (each one already carries the canonical source_text/
    comparison contract; no re-prediction needed here)."""

    registry_dir = settings.document_registry_dir
    if not registry_dir.exists():
        return {"status": "no_documents", "documents": 0}

    total = 0
    exact = 0
    normalized = 0
    text_available = 0
    page_available = 0
    bbox_available = 0
    documents_seen = 0

    for manifest_path in registry_dir.glob("*.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("stage") != "analyzed":
            continue
        document_id = manifest.get("document_id")
        predictions = read_artifact(document_id, "predictions.json")
        if not predictions:
            continue
        documents_seen += 1
        for prediction in predictions.get("predictions") or []:
            source_text = prediction.get("source_text") or {}
            comparison = prediction.get("comparison") or {}
            total += 1
            if source_text.get("available"):
                text_available += 1
            if source_text.get("page_number") is not None:
                page_available += 1
            if source_text.get("bounding_box") is not None:
                bbox_available += 1
            if comparison.get("exact_match"):
                exact += 1
            if comparison.get("normalized_match"):
                normalized += 1

    if total == 0:
        return {
            "status": "no_analyzed_predictions",
            "documents": documents_seen,
            "note": "Run at least one document through /analyze to populate this section.",
        }
    return {
        "status": "ok",
        "documents": documents_seen,
        "tokens": total,
        "raw_text_exact_match_rate": round(exact / total, 4),
        "normalized_match_rate": round(normalized / total, 4),
        "source_text_coverage": round(text_available / total, 4),
        "page_number_coverage": round(page_available / total, 4),
        "bounding_box_coverage": round(bbox_available / total, 4),
    }


def _predict_holdout(rows: List[dict]) -> List[dict]:
    results = []
    for row in rows:
        token = str(row.get("token") or "").strip()
        true_label = str(row.get("class") or "").strip()
        if not token or not true_label:
            continue
        prediction = predict_token(token, queue_unknown=False, persist_learning=False)
        results.append({"token": token, "true_label": true_label, "prediction": prediction})
    return results


def section_prediction_performance() -> Dict[str, Any]:
    """B. Prediction performance — approved (human-confirmed) rows are the
    only labeled ground truth this repository has; each is re-predicted
    fresh (queue_unknown=False, persist_learning=False so this is read-only)
    and scored against the human-confirmed label.

    Uses a hash holdout split and a shadow exact-section index that excludes
    test tokens so metrics are not inflated by memorization.
    """

    from services.exact_section_predictor import (
        reload_exact_section_artifact,
        train_exact_section_model,
    )
    from services.training_pipeline.preprocessing import assign_split

    approved = dataset_manager.load_approved_dataset()
    if approved is None or approved.empty:
        return {"status": "no_labeled_data", "rows": 0}

    rows = approved.to_dict("records")
    holdout: List[dict] = []
    for row in rows:
        split = str(row.get("eval_split") or "").strip()
        if not split:
            split = assign_split(str(row.get("unknown_id") or row.get("token") or ""))
            row["eval_split"] = split
        if split == "test":
            holdout.append(row)

    if not holdout:
        # Fall back to hashing every row when legacy CSVs lack eval_split.
        holdout = [
            row
            for row in rows
            if assign_split(str(row.get("unknown_id") or row.get("token") or ""))
            == "test"
        ]

    if not holdout:
        return {"status": "no_holdout_rows", "rows": len(rows)}

    exclude_tokens = {
        str(row.get("token") or "").strip()
        for row in holdout
        if str(row.get("token") or "").strip()
    }
    # Shadow index: train without test tokens so retrieval cannot memorize them.
    train_exact_section_model(
        persist=False,
        exclude_tokens=exclude_tokens,
        exclude_split="test",
    )
    reload_exact_section_artifact()

    evaluated = _predict_holdout(holdout)
    if not evaluated:
        return {"status": "no_usable_rows", "rows": len(holdout)}

    top1 = top3 = top5 = candidate_recall = 0
    auto_accepted = 0
    auto_accepted_correct = 0
    abstained = 0
    by_family: Dict[str, List[int]] = defaultdict(list)
    by_corruption: Dict[str, List[int]] = defaultdict(list)
    wildcard_correct = wildcard_total = 0

    for item in evaluated:
        true_label = item["true_label"].upper().replace(" ", "")
        prediction = item["prediction"]
        predicted = str(prediction.get("section") or "").upper().replace(" ", "")
        if not predicted:
            abstained += 1
        candidates = [
            str(c.get("label") or "").upper().replace(" ", "")
            for c in prediction.get("canonical_candidates") or []
        ]
        ranked = ([predicted] if predicted else []) + [
            c for c in candidates if c != predicted
        ]

        is_top1 = bool(predicted) and predicted == true_label
        is_top3 = true_label in ranked[:3]
        is_top5 = true_label in ranked[:5]
        in_candidates = true_label in candidates or is_top1

        top1 += is_top1
        top3 += is_top3
        top5 += is_top5
        candidate_recall += in_candidates

        review_status = str(prediction.get("review_status") or "")
        if review_status == "auto_accepted":
            auto_accepted += 1
            auto_accepted_correct += int(is_top1)

        family = str(prediction.get("family") or "UNKNOWN")
        by_family[family].append(int(is_top1))

        corruption = _corruption_type(item["token"])
        by_corruption[corruption].append(int(is_top1))
        if corruption == "wildcard":
            wildcard_total += 1
            wildcard_correct += int(is_top1)

    n = len(evaluated)
    return {
        "status": "ok",
        "rows": n,
        "holdout_rows": n,
        "approved_rows_total": len(rows),
        "top_1_accuracy": round(top1 / n, 4),
        "top_3_accuracy": round(top3 / n, 4),
        "top_5_accuracy": round(top5 / n, 4),
        "candidate_generation_recall": round(candidate_recall / n, 4),
        "abstention_rate": round(abstained / n, 4),
        "auto_accepted_rate": round(auto_accepted / n, 4),
        "auto_accepted_accuracy": (
            round(auto_accepted_correct / auto_accepted, 4) if auto_accepted else None
        ),
        "accuracy_by_family": {
            family: round(sum(values) / len(values), 4)
            for family, values in by_family.items()
        },
        "accuracy_by_corruption_type": {
            kind: round(sum(values) / len(values), 4)
            for kind, values in by_corruption.items()
        },
        "wildcard_resolution_accuracy": (
            round(wildcard_correct / wildcard_total, 4) if wildcard_total else None
        ),
        "wildcard_sample_count": wildcard_total,
        "note": (
            "Metrics use hash holdout (eval_split=test) and a shadow "
            "exact-section index that excludes those tokens."
        ),
    }, evaluated


def section_review_behavior(evaluated: Optional[List[dict]]) -> Dict[str, Any]:
    """C. Review behavior — queue composition and correction outcomes."""

    counts = dataset_manager.unknown_counts()
    pending = counts.get("pending")
    approved_count = counts.get("approved")
    rejected_count = counts.get("rejected")

    result: Dict[str, Any] = {
        "pending_review_count": pending,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
    }
    if approved_count is not None and rejected_count is not None and (approved_count + rejected_count):
        result["correction_acceptance_rate"] = round(
            approved_count / (approved_count + rejected_count), 4
        )

    if evaluated:
        unresolved = sum(
            1
            for item in evaluated
            if (item["prediction"].get("comparison") or {}).get("match_status")
            in {"unresolved", "source_text_not_found"}
        )
        needs_review = sum(
            1 for item in evaluated if item["prediction"].get("needs_review")
        )
        n = len(evaluated)
        result["manual_review_rate_on_holdout"] = round(needs_review / n, 4)
        result["unresolved_rate_on_holdout"] = round(unresolved / n, 4)
    return result


def section_confidence(evaluated: Optional[List[dict]]) -> Dict[str, Any]:
    """D. Confidence — calibration fit status plus an empirical reliability
    breakdown (accuracy observed within each ranking-score band)."""

    calibration_model = fit_calibration()
    result: Dict[str, Any] = {
        "calibration_fitted": calibration_model is not None,
        "calibration_sample_count": (
            calibration_model.sample_count if calibration_model else 0
        ),
    }
    if not evaluated:
        result["reliability_by_score_band"] = {}
        return result

    bands = {"low (<0.55)": [], "medium (0.55-0.80)": [], "high (>=0.80)": []}
    for item in evaluated:
        score = float(
            item["prediction"].get("ranking_score")
            or (item["prediction"].get("confidence") or {}).get("overall")
            or 0.0
        )
        correct = int(
            str(item["prediction"].get("section") or "").upper().replace(" ", "")
            == item["true_label"].upper().replace(" ", "")
        )
        if score >= 0.80:
            bands["high (>=0.80)"].append(correct)
        elif score >= 0.55:
            bands["medium (0.55-0.80)"].append(correct)
        else:
            bands["low (<0.55)"].append(correct)

    result["reliability_by_score_band"] = {
        band: {
            "count": len(values),
            "empirical_accuracy": round(sum(values) / len(values), 4) if values else None,
        }
        for band, values in bands.items()
    }
    return result


def build_report() -> Dict[str, Any]:
    extraction = section_extraction_fidelity()
    performance_result = section_prediction_performance()
    if isinstance(performance_result, tuple):
        performance, evaluated = performance_result
    else:
        performance, evaluated = performance_result, None

    return {
        "schema_version": "1.0",
        "note": (
            "Extraction fidelity, prediction performance, review behavior, and "
            "confidence are reported separately and must not be averaged into "
            "one headline number."
        ),
        "extraction_fidelity": extraction,
        "prediction_performance": performance,
        "review_behavior": section_review_behavior(evaluated),
        "confidence": section_confidence(evaluated),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=str, default=None, help="Optional JSON output path")
    args = parser.parse_args()

    report = build_report()
    text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote evaluation report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
