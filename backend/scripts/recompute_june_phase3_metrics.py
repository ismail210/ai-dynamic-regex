#!/usr/bin/env python3
"""Recompute June Phase 3 metrics from preserved first-run artifacts.

Includes takeoff ``predictions`` plus ``context_definitions`` /
``non_member_annotations`` / ``repeated_detail_members`` so incomplete-L
abstention rows scoped out of takeoff are not missed.

Does not re-run the multimodal pipeline or change production inference.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.evaluate_first_run import _classify_row  # noqa: E402
from scripts.run_june_phase3_validation import (  # noqa: E402
    BACKEND_DIR,
    MANIFEST_PATH,
    PREDICTIONS_DIR,
    REPORT_PATH,
    RESULTS_PATH,
    SUBSET,
    _infer_observed_ops,
    _remap_page,
    _render_report,
    _safety_audit,
    _verify_flags,
)
from services.artifact_store import read_artifact  # noqa: E402
from services.prediction.semantic_contract import (  # noqa: E402
    SemanticOperationKind,
    project_semantic_annotation,
)


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text())
    flags = _verify_flags()

    all_records = []
    taxonomy: Counter = Counter()
    op_counts: Counter = Counter()
    run_summaries = []
    page_stats = []

    for spec, mdoc in zip(SUBSET, manifest["documents"]):
        did = mdoc["document_id"]
        raw_path = PREDICTIONS_DIR / f"{did}_predictions.json"
        raw = json.loads(raw_path.read_text())
        mapping = {int(k): int(v) for k, v in raw["page_map_extract_to_source"].items()}
        art = read_artifact(did, "predictions.json") or {}
        buckets = {
            "predictions": list(raw.get("predictions") or []),
            "context_definitions": list(art.get("context_definitions") or []),
            "non_member_annotations": list(art.get("non_member_annotations") or []),
            "repeated_detail_members": list(art.get("repeated_detail_members") or []),
        }
        # Persist sidecar buckets next to takeoff predictions (additive).
        raw["context_definitions"] = buckets["context_definitions"]
        raw["non_member_annotations"] = buckets["non_member_annotations"]
        raw["repeated_detail_members"] = buckets["repeated_detail_members"]
        raw_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        seen = set()
        combined = []
        for bucket, rows in buckets.items():
            for pred in rows:
                key = (
                    bucket,
                    pred.get("object_id"),
                    pred.get("raw_text"),
                    pred.get("page_number"),
                    str(pred.get("bounding_box")),
                )
                if key in seen:
                    continue
                seen.add(key)
                combined.append((bucket, pred))

        classified_rows = []
        for bucket, pred in combined:
            source_page = _remap_page(pred, mapping)
            classified = _classify_row(pred)
            projected = project_semantic_annotation(pred).to_dict()
            if source_page is not None:
                projected["source_page"] = source_page
                projected["extract_page"] = pred.get("page_number")
            observed_ops = _infer_observed_ops(pred, classified)
            op_counts.update(observed_ops)
            taxonomy.update(classified.get("tags") or ["untagged"])
            all_records.append(
                {
                    "doc_key": spec["doc_key"],
                    "document_id": did,
                    "project": spec["project"],
                    "source_page": source_page,
                    "extract_page": pred.get("page_number"),
                    "bucket": bucket,
                    "prediction": pred,
                    "classified": classified,
                    "semantic_annotation": projected,
                    "observed_operations": observed_ops,
                    "association_rewrote_text": False,
                }
            )
            classified_rows.append(classified)

        incomplete = [c for c in classified_rows if c["incomplete_printed"]]
        unsafe = [c for c in classified_rows if "unsafe_completion" in c["tags"]]
        abstained = [
            c
            for c in incomplete
            if c.get("completion_status") == "missing_thickness"
            and c.get("takeoff_eligible") is False
        ]
        with_bbox = sum(1 for c in classified_rows if c["has_bbox"])
        with_spatial = sum(1 for c in classified_rows if c["has_spatial_association"])

        by_page: dict = defaultdict(list)
        for rec in all_records:
            if rec["doc_key"] != spec["doc_key"] or rec["source_page"] is None:
                continue
            by_page[int(rec["source_page"])].append(rec)
        for page in spec["pages"]:
            rows = by_page.get(page, [])
            page_stats.append(
                {
                    "project": spec["project"],
                    "source_page": page,
                    "rationale": spec["rationale"].get(page),
                    "prediction_count": sum(
                        1 for r in rows if r["bucket"] == "predictions"
                    ),
                    "all_bucket_count": len(rows),
                    "incomplete_printed": sum(
                        1 for r in rows if r["classified"]["incomplete_printed"]
                    ),
                    "incomplete_in_context_definitions": sum(
                        1
                        for r in rows
                        if r["classified"]["incomplete_printed"]
                        and r["bucket"] == "context_definitions"
                    ),
                    "bbox_coverage": (
                        round(
                            sum(1 for r in rows if r["classified"]["has_bbox"])
                            / len(rows),
                            4,
                        )
                        if rows
                        else None
                    ),
                    "spatial_coverage": (
                        round(
                            sum(
                                1
                                for r in rows
                                if r["classified"]["has_spatial_association"]
                            )
                            / len(rows),
                            4,
                        )
                        if rows
                        else None
                    ),
                }
            )

        run_summaries.append(
            {
                "doc_key": spec["doc_key"],
                "document_id": did,
                "project": spec["project"],
                "source_pdf": spec["pdf_rel"],
                "selected_pages": spec["pages"],
                "page_map_extract_to_source": raw["page_map_extract_to_source"],
                "n_predictions_takeoff": len(buckets["predictions"]),
                "n_context_definitions": len(buckets["context_definitions"]),
                "n_non_member_annotations": len(buckets["non_member_annotations"]),
                "n_combined_rows": len(combined),
                "incomplete_printed": len(incomplete),
                "incomplete_abstained": len(abstained),
                "unsafe_completion": len(unsafe),
                "rows_with_bbox": with_bbox,
                "rows_with_spatial_association": with_spatial,
                "bbox_coverage": (
                    round(with_bbox / len(classified_rows), 4)
                    if classified_rows
                    else 0.0
                ),
                "spatial_coverage": (
                    round(with_spatial / len(classified_rows), 4)
                    if classified_rows
                    else 0.0
                ),
                "duplicates": raw.get("duplicates"),
                "raw_predictions_path": str(raw_path.relative_to(BACKEND_DIR)),
                "pipeline_summary": raw.get("pipeline_summary"),
            }
        )

    safety = _safety_audit(all_records)
    n = len(all_records)
    incomplete_all = [
        r for r in all_records if r["classified"]["incomplete_printed"]
    ]
    takeoff_n = sum(1 for r in all_records if r["bucket"] == "predictions")

    metrics = {
        "extraction": {
            "total_takeoff_predictions": takeoff_n,
            "total_rows_all_buckets": n,
            "bucket_counts": dict(Counter(r["bucket"] for r in all_records)),
            "predictions_by_project": dict(
                Counter(
                    r["doc_key"]
                    for r in all_records
                    if r["bucket"] == "predictions"
                )
            ),
            "pages_with_zero_takeoff_predictions": [
                p for p in page_stats if (p.get("prediction_count") or 0) == 0
            ],
            "note": (
                "Takeoff predictions vs context_definitions/non_member retained "
                "separately; no extraction gold accuracy"
            ),
        },
        "normalization": {
            "observed_normalization_ops": op_counts.get(
                SemanticOperationKind.NORMALIZATION.value, 0
            ),
            "format_correction_ok": taxonomy.get("format_correction_ok", 0),
            "catalog_equivalent_ok": taxonomy.get("catalog_equivalent_ok", 0),
            "note": "Format/catalog-form only; not semantic inference",
        },
        "repair": {
            "status": "not_independently_measurable",
            "note": "Production payloads do not label REPAIR distinctly",
        },
        "completion_abstention": {
            "incomplete_printed": len(incomplete_all),
            "incomplete_in_takeoff_predictions": sum(
                1 for r in incomplete_all if r["bucket"] == "predictions"
            ),
            "incomplete_in_context_definitions": sum(
                1
                for r in incomplete_all
                if r["bucket"] == "context_definitions"
            ),
            "incomplete_abstained": sum(
                1
                for r in incomplete_all
                if r["classified"].get("completion_status")
                == "missing_thickness"
                and r["classified"].get("takeoff_eligible") is False
            ),
            "unsafe_completion": taxonomy.get("unsafe_completion", 0),
            "incomplete_abstention_ok": taxonomy.get(
                "incomplete_abstention_ok", 0
            ),
            "samples_incomplete": [
                {
                    "raw": r["classified"]["raw_text"],
                    "section": r["classified"]["section"],
                    "status": r["classified"]["completion_status"],
                    "takeoff_eligible": r["classified"]["takeoff_eligible"],
                    "page": r["source_page"],
                    "project": r["project"],
                    "bucket": r["bucket"],
                    "object_scope": r["prediction"].get("object_scope"),
                }
                for r in incomplete_all[:40]
            ],
        },
        "catalog": {
            "match_ok": taxonomy.get("match_ok", 0),
            "catalog_equivalent_ok": taxonomy.get("catalog_equivalent_ok", 0),
            "catalog_matching_error": taxonomy.get("catalog_matching_error", 0),
            "non_catalog_designation": taxonomy.get(
                "non_catalog_designation", 0
            ),
            "note": "Catalog verification only; Excel not used",
        },
        "bbox": {
            "rows_with_bbox": sum(
                1 for r in all_records if r["classified"]["has_bbox"]
            ),
            "bbox_coverage": (
                round(
                    sum(1 for r in all_records if r["classified"]["has_bbox"])
                    / n,
                    4,
                )
                if n
                else 0.0
            ),
            "takeoff_bbox_coverage": (
                round(
                    sum(
                        1
                        for r in all_records
                        if r["bucket"] == "predictions"
                        and r["classified"]["has_bbox"]
                    )
                    / takeoff_n,
                    4,
                )
                if takeoff_n
                else 0.0
            ),
            "note": "Coverage only — no bbox gold accuracy",
        },
        "geometry_association": {
            "rows_with_spatial_or_preview": sum(
                1
                for r in all_records
                if r["classified"]["has_spatial_association"]
            ),
            "spatial_coverage": (
                round(
                    sum(
                        1
                        for r in all_records
                        if r["classified"]["has_spatial_association"]
                    )
                    / n,
                    4,
                )
                if n
                else 0.0
            ),
            "rows_with_member_geometry": sum(
                1 for r in all_records if r["prediction"].get("member_geometry")
            ),
            "association_text_rewrites": 0,
            "note": "Coverage only; geometry evidence != semantic truth",
        },
        "duplicates": {
            "per_document": [
                {"doc_key": s["doc_key"], "duplicates": s.get("duplicates")}
                for s in run_summaries
            ],
            "note": "Existing merge audit on takeoff predictions",
        },
        "missing": {
            "missing_extraction_tag": taxonomy.get("missing_extraction", 0),
            "pages_with_zero_takeoff_predictions": [
                p for p in page_stats if (p.get("prediction_count") or 0) == 0
            ],
            "note": (
                "No Excel-as-GT; includes pages where steel text exists only "
                "as context_definition"
            ),
        },
        "semantic_operations": {
            "normalization": op_counts.get(
                SemanticOperationKind.NORMALIZATION.value, 0
            ),
            "repair": op_counts.get(SemanticOperationKind.REPAIR.value, 0),
            "completion": op_counts.get(
                SemanticOperationKind.COMPLETION.value, 0
            ),
            "association": op_counts.get(
                SemanticOperationKind.ASSOCIATION.value, 0
            ),
            "note": (
                "Heuristic from existing fields; COMPLETION = unsafe_completion "
                "tags only"
            ),
        },
        "taxonomy_counts": dict(taxonomy),
    }

    limitations = [
        "Repair not independently measurable from production payloads",
        "No human gold — metrics are coverage/counts, not accuracy %",
        "Page extracts are extract-local for document-prior/legend scope "
        "(not full-PDF Analyze context)",
        "Incomplete printed 2L not observed in River Road + Burrville corpus "
        "scan / this subset",
        "Incomplete L rows observed primarily as context_definition "
        "(excluded from takeoff predictions) — residual scope finding",
    ]
    overall = (
        "BLOCKED" if safety["verdict"] != "PASS" else "PASS WITH LIMITATIONS"
    )

    results = {
        "experiment_id": "june_phase3_first_run_2026-09-13",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": overall,
        "limitations": limitations,
        "pipeline_path": {
            "entry": "services.multimodal.pipeline.run_multimodal_pipeline",
            "prediction_owner": (
                "services.prediction.orchestrator via fusion_engine.predict"
            ),
            "eval_classifier": "scripts.evaluate_first_run._classify_row",
            "semantic_projection": (
                "services.prediction.semantic_contract.project_semantic_annotation"
            ),
            "buckets_evaluated": [
                "predictions",
                "context_definitions",
                "non_member_annotations",
                "repeated_detail_members",
            ],
            "excel": None,
            "persist": True,
            "metrics_pass": "recompute_from_preserved_artifacts",
        },
        "feature_flags": flags,
        "corpus": manifest["corpus"],
        "documents": run_summaries,
        "page_stats": page_stats,
        "metrics": metrics,
        "safety": safety,
        "records": [
            {
                "doc_key": r["doc_key"],
                "document_id": r["document_id"],
                "project": r["project"],
                "source_page": r["source_page"],
                "extract_page": r["extract_page"],
                "bucket": r["bucket"],
                "object_id": r["prediction"].get("object_id"),
                "raw_text": r["classified"]["raw_text"],
                "normalized_text": r["prediction"].get("normalized_text"),
                "section": r["classified"]["section"],
                "completion_status": r["classified"]["completion_status"],
                "takeoff_eligible": r["classified"]["takeoff_eligible"],
                "object_scope": r["prediction"].get("object_scope"),
                "needs_review": r["prediction"].get("needs_review"),
                "review_status": r["prediction"].get("review_status"),
                "review_reason": r["prediction"].get("review_reason"),
                "confidence": r["prediction"].get("confidence"),
                "confidence_basis": r["prediction"].get("confidence_basis"),
                "has_bbox": r["classified"]["has_bbox"],
                "has_spatial_association": r["classified"][
                    "has_spatial_association"
                ],
                "has_member_geometry": bool(
                    r["prediction"].get("member_geometry")
                ),
                "tags": r["classified"]["tags"],
                "observed_operations": r["observed_operations"],
                "semantic_annotation": r["semantic_annotation"],
            }
            for r in all_records
        ],
    }

    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    manifest["selection"]["buckets_evaluated"] = results["pipeline_path"][
        "buckets_evaluated"
    ]
    manifest["generated_at"] = results["generated_at"]
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report = _render_report(results, manifest)
    next_task = (
        "**ONE next task:** Investigate why incomplete printed `L4X4`/`L5X3` on "
        "River Road detail pages are scoped as `context_definition` (excluded "
        "from takeoff `predictions`) despite correct `missing_thickness` / "
        "`takeoff_eligible=false` abstention — determine whether "
        "`annotate_takeoff_scope` / legend-region heuristics are over-scoping "
        "real member callouts; evidence-only, no inference change yet."
    )
    marker = "**ONE next task:**"
    idx = report.rfind(marker)
    if idx >= 0:
        end = report.find("\n\n", idx)
        if end < 0:
            end = len(report)
        report = report[:idx] + next_task + report[end:]
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(
        json.dumps(
            {
                "verdict": overall,
                "safety": safety["verdict"],
                "n_records": n,
                "takeoff": takeoff_n,
                "incomplete_printed": len(incomplete_all),
                "incomplete_abstained": metrics["completion_abstention"][
                    "incomplete_abstained"
                ],
                "unsafe": metrics["completion_abstention"]["unsafe_completion"],
                "incomplete_in_context_definitions": metrics[
                    "completion_abstention"
                ]["incomplete_in_context_definitions"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
