#!/usr/bin/env python3
"""First-run validation report (Excel = reference/diff only).

Does NOT replace the 8-doc proxy-gold regression cache under
``training/eval_cache_backups/doc_*/``.

Uses already-persisted Analyze artifacts:

  engineering_artifacts/<doc_id>/multimodal/predictions.json
  engineering_artifacts/<doc_id>/multimodal/predictions_view.json

Optional ``--excel`` is comparison/reference only — never a predictor and
never treated as unquestioned ground truth.

Usage (from backend/):

  python scripts/evaluate_first_run.py --document-id doc_0d910a43b4a021e3
  python scripts/evaluate_first_run.py --document-id doc_... --excel path.xlsx
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.artifact_store import read_artifact  # noqa: E402
from services.database_loader import catalog_form  # noqa: E402
from services.exact_section_predictor import (  # noqa: E402
    catalog_valid_exact_section,
)
from services.prediction.label_ranker_hook import (  # noqa: E402
    is_incomplete_angle_missing_thickness,
)
from services.token_extractor import (  # noqa: E402
    core_section_token,
    normalize_engineering_token,
)

# Error taxonomy (format correction ≠ semantic inference)
TAXONOMY = (
    "ocr_error",
    "extraction_error",
    "normalization_error",
    "fraction_parsing_error",
    "abbreviation_error",
    "punctuation_trailing_noise_error",
    "catalog_matching_error",
    "incomplete_label_inference",  # semantic — must not auto-resolve
    "unsafe_completion",
    "bbox_error",
    "geometry_association_error",
    "duplicate_repeated_element_error",
    "missing_extraction",
    "non_catalog_designation",
    "format_correction_ok",
    "catalog_equivalent_ok",
    "incomplete_abstention_ok",
    "match_ok",
)


def _load_predictions(document_id: str) -> List[dict]:
    view = read_artifact(document_id, "predictions_view.json") or {}
    preds = view.get("predictions") if isinstance(view, dict) else None
    if preds:
        return list(preds)
    raw = read_artifact(document_id, "predictions.json") or {}
    if isinstance(raw, dict):
        return list(raw.get("predictions") or [])
    return []


def _raw_text(row: dict) -> str:
    return str(
        row.get("raw_text")
        or row.get("original_token")
        or row.get("normalized_text")
        or ""
    )


def _classify_row(row: dict) -> Dict[str, Any]:
    raw = _raw_text(row)
    section = str(row.get("section") or "")
    status = str(row.get("completion_status") or "")
    takeoff = row.get("takeoff_eligible")
    incomplete = is_incomplete_angle_missing_thickness(raw)
    catalog = catalog_valid_exact_section(raw)
    form = catalog_form(raw) or catalog_form(normalize_engineering_token(raw))
    bbox = row.get("bounding_box") or row.get("bbox")
    # Association is stored as geometry_preview / graph_preview on first-run
    # predictions_view rows (not a top-level spatial_association field).
    geom_preview = row.get("geometry_preview")
    graph_preview = row.get("graph_preview")
    spatial = (
        row.get("spatial_association")
        or (
            isinstance(geom_preview, dict)
            and bool(geom_preview.get("object_id") or geom_preview.get("bbox"))
        )
        or (
            isinstance(graph_preview, dict)
            and bool(graph_preview.get("object_id") or graph_preview.get("edges"))
        )
        or row.get("geometry_associated")
    )

    tags: List[str] = []
    if incomplete:
        if status == "missing_thickness" and takeoff is False:
            tags.append("incomplete_abstention_ok")
        elif section and catalog_valid_exact_section(section):
            tags.append("unsafe_completion")
            tags.append("incomplete_label_inference")
        else:
            tags.append("incomplete_abstention_ok")
    elif catalog and section:
        if normalize_engineering_token(section) == normalize_engineering_token(
            str(catalog)
        ):
            tags.append("match_ok")
            if normalize_engineering_token(raw) != normalize_engineering_token(
                str(catalog)
            ):
                tags.append("format_correction_ok")
        elif form and normalize_engineering_token(section) == normalize_engineering_token(
            form
        ):
            tags.append("catalog_equivalent_ok")
        else:
            tags.append("catalog_matching_error")
    elif section and not catalog_form(section):
        tags.append("non_catalog_designation")
    elif not section:
        tags.append("missing_extraction")

    if raw and any(raw.endswith(ch) for ch in ",;\""):
        if incomplete and "incomplete_abstention_ok" in tags:
            pass
        elif "match_ok" in tags or "catalog_equivalent_ok" in tags:
            tags.append("format_correction_ok")
        elif "unsafe_completion" not in tags:
            tags.append("punctuation_trailing_noise_error")

    return {
        "raw_text": raw,
        "section": section,
        "completion_status": status,
        "takeoff_eligible": takeoff,
        "incomplete_printed": incomplete,
        "catalog_valid_from_raw": catalog,
        "has_bbox": bool(bbox),
        "has_spatial_association": bool(spatial),
        "tags": tags,
    }


def summarize(document_id: str, excel_path: Optional[str] = None) -> Dict[str, Any]:
    rows = _load_predictions(document_id)
    classified = [_classify_row(r) for r in rows]
    tag_counts: Counter = Counter()
    for item in classified:
        tag_counts.update(item["tags"] or ["untagged"])

    incomplete = [c for c in classified if c["incomplete_printed"]]
    unsafe = [c for c in classified if "unsafe_completion" in c["tags"]]
    abstained = [
        c
        for c in incomplete
        if c.get("completion_status") == "missing_thickness"
        and c.get("takeoff_eligible") is False
    ]
    with_bbox = sum(1 for c in classified if c["has_bbox"])
    with_spatial = sum(1 for c in classified if c["has_spatial_association"])

    excel_note = None
    if excel_path:
        excel_note = {
            "path": excel_path,
            "role": "reference_diff_only",
            "warning": (
                "User-edited Excel is NOT official ground truth and must not "
                "be used as a predictor. Diff against first-run predictions "
                "for error classification only."
            ),
        }
        try:
            from services.takeoff.canonical_takeoff_eval import (
                evaluate as canonical_evaluate,
                parse_workbook_ground_truth,
            )

            preds = _load_predictions(document_id)
            gt = parse_workbook_ground_truth(excel_path)
            excel_note["diff_summary"] = {
                k: canonical_evaluate(preds, gt).get(k)
                for k in (
                    "overall_success_pct",
                    "precision_pct",
                    "matching_quantity",
                    "ground_truth_total",
                )
            }
        except Exception as exc:  # noqa: BLE001
            excel_note["diff_error"] = str(exc)

    return {
        "document_id": document_id,
        "source": "engineering_artifacts multimodal predictions_view/predictions",
        "role": "first_run_raw_model_output",
        "n_predictions": len(classified),
        "metrics": {
            "incomplete_printed": len(incomplete),
            "incomplete_abstained": len(abstained),
            "unsafe_completion": len(unsafe),
            "unsafe_completion_rate": (
                round(len(unsafe) / len(incomplete), 4) if incomplete else 0.0
            ),
            "rows_with_bbox": with_bbox,
            "rows_with_spatial_association": with_spatial,
            "bbox_coverage": (
                round(with_bbox / len(classified), 4) if classified else 0.0
            ),
        },
        "taxonomy_counts": dict(tag_counts),
        "taxonomy_labels": list(TAXONOMY),
        "excel_reference": excel_note,
        "regression_suite_note": (
            "Internal proxy-gold regression remains at "
            "training/eval_cache_backups/doc_*/predictions_view.json — "
            "do not overwrite with this report."
        ),
        "sample_unsafe": unsafe[:10],
        "sample_incomplete_abstained": abstained[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", required=True)
    parser.add_argument(
        "--excel",
        default=None,
        help="Optional Excel reference/diff only (not ground truth)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON output path",
    )
    args = parser.parse_args()
    report = summarize(args.document_id, excel_path=args.excel)
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
