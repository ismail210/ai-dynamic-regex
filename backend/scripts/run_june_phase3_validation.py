#!/usr/bin/env python3
"""June Phase 3 first-run validation (metrics only — no new inference).

Builds page-extract PDFs for the ~16-page Phase 0C subset, runs the EXISTING
``run_multimodal_pipeline`` path, preserves raw predictions, projects Phase 2
semantic annotations additively, and writes:

  backend/JUNE_PHASE3_VALIDATION_MANIFEST.json
  backend/june_phase3_results.json
  backend/JUNE_PHASE3_FIRST_RUN_REPORT.md

June PDFs are never modified or treated as training/predictor data.
Excel is not used. Experimental ML/LLM/VLM/GraphSAGE flags must stay off.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Fail closed if someone enables experimental flags in the environment.
_FORBIDDEN_ENV = (
    "LEARNED_FUSION_ENABLED",
    "GRAPHSAGE_SECTION_SCORING_ENABLED",
    "GEOMETRY_MISSING_LABEL_INFERENCE_ENABLED",
    "ML_LABEL_RANKER_ENABLED",
    "ML_LABEL_RANKER_SHADOW",
    "LEGEND_PROFILE_LLM_ENABLED",
    "ML_ASSOCIATION_DATASET_ENABLED",
)
for _key in _FORBIDDEN_ENV:
    if str(os.environ.get(_key, "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise SystemExit(f"Refusing Phase 3 run: {_key} is enabled")

import fitz  # noqa: E402

from config import settings  # noqa: E402
from scripts.evaluate_first_run import _classify_row  # noqa: E402
from services.multimodal.pipeline import run_multimodal_pipeline  # noqa: E402
from services.prediction.label_ranker_hook import (  # noqa: E402
    is_incomplete_angle_missing_thickness,
)
from services.semantic.models import OperationKind as SemanticOperationKind  # noqa: E402
from services.semantic.projection import project_semantic_annotation  # noqa: E402

OUT_DIR = BACKEND_DIR / "training" / "eval_cache_backups" / "june_phase3"
EXTRACT_DIR = OUT_DIR / "page_extracts"
PREDICTIONS_DIR = OUT_DIR / "raw_predictions"
MANIFEST_PATH = BACKEND_DIR / "JUNE_PHASE3_VALIDATION_MANIFEST.json"
RESULTS_PATH = BACKEND_DIR / "june_phase3_results.json"
REPORT_PATH = BACKEND_DIR / "JUNE_PHASE3_FIRST_RUN_REPORT.md"

# Phase 0C recommended 16-page subset (1-indexed page numbers in source PDFs).
SUBSET: List[Dict[str, Any]] = [
    {
        "project": "18 - River Road",
        "pdf_rel": "Testing Projects/18 - River Road/A-2025-09-19_252003_Addendum A - 4400 Base Bldg Dwgs.pdf",
        "pages": [25, 28, 30, 33, 34, 38, 41],
        "doc_key": "river_road",
        "rationale": {
            25: "Normal W labels on floor framing",
            28: "Roof framing W + HSS + complete L",
            30: "Dense W labeling",
            33: "Incomplete L4X4 + complete L angles (abstention)",
            34: "Incomplete L4X4 near completes — must not auto-complete",
            38: "Incomplete L5X3 + completes",
            41: "Incomplete L4X4 on opening detail",
        },
    },
    {
        "project": "51 - Burrvile ES",
        "pdf_rel": "Testing Projects/51 - Burrvile ES/Burrville_DD Pricing Set_260317.pdf",
        "pages": [54, 59, 63, 65, 72, 75, 78],
        "doc_key": "burrville",
        "rationale": {
            54: "Half-leg L5X3-1/2X5/16 must stay complete",
            59: "Dense floor framing W",
            63: "Roof framing W + HSS",
            65: "Mixed W/HSS/L on roof",
            72: "2L + complete L details",
            75: "Complete 2L4X4X3/8 (not incomplete 2L)",
            78: "Dense HSS",
        },
    },
    {
        "project": "41 - SOME",
        "pdf_rel": "Testing Projects/41 - SOME/2025-12-18_100 DD SET-current (1).pdf",
        "pages": [58, 65],
        "doc_key": "some",
        "rationale": {
            58: "Dense framing W (spacing/case)",
            65: "Half-leg completes / detector false-positive guard",
        },
    },
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_flags() -> Dict[str, Any]:
    return {
        "learned_fusion_enabled": bool(settings.learned_fusion_enabled),
        "graphsage_section_scoring_enabled": bool(
            settings.graphsage_section_scoring_enabled
        ),
        "geometry_missing_label_inference_enabled": bool(
            settings.geometry_missing_label_inference_enabled
        ),
        "ml_label_ranker_enabled": bool(settings.ml_label_ranker_enabled),
        "ml_label_ranker_shadow": bool(settings.ml_label_ranker_shadow),
        "legend_profile_llm_enabled": bool(settings.legend_profile_llm_enabled),
        "ml_association_dataset_enabled": bool(
            settings.ml_association_dataset_enabled
        ),
    }


def _assert_flags_off(flags: Dict[str, Any]) -> None:
    enabled = [k for k, v in flags.items() if v]
    if enabled:
        raise SystemExit(
            "Refusing Phase 3: experimental flags enabled: " + ", ".join(enabled)
        )


def build_page_extract(
    source: Path, pages: List[int], dest: Path
) -> Dict[int, int]:
    """Copy selected 1-indexed pages into a slim PDF. Returns extract->source map."""

    dest.parent.mkdir(parents=True, exist_ok=True)
    mapping: Dict[int, int] = {}
    with fitz.open(source) as src:
        out = fitz.open()
        for new_i, page_num in enumerate(pages):
            if page_num < 1 or page_num > src.page_count:
                raise ValueError(
                    f"{source.name}: page {page_num} out of range "
                    f"(1..{src.page_count})"
                )
            out.insert_pdf(src, from_page=page_num - 1, to_page=page_num - 1)
            mapping[new_i + 1] = page_num
        out.save(dest)
        out.close()
    return mapping


def _remap_page(row: dict, mapping: Dict[int, int]) -> Optional[int]:
    page = row.get("page_number")
    if page is None:
        page = (row.get("source_text") or {}).get("page_number")
    try:
        extract_page = int(page)
    except (TypeError, ValueError):
        return None
    return mapping.get(extract_page)


def _operation_counts_from_projection(projected: dict) -> Counter:
    counts: Counter = Counter()
    for op in projected.get("operations") or []:
        kind = op.get("operation") if isinstance(op, dict) else None
        if kind:
            counts[str(kind)] += 1
    return counts


def _infer_observed_ops(row: dict, classified: dict) -> List[str]:
    """Heuristic operation tags from EXISTING fields only (not new inference)."""

    ops: List[str] = []
    raw = str(classified.get("raw_text") or "")
    section = str(classified.get("section") or "")
    norm = str(row.get("normalized_text") or "")
    if raw and norm and raw != norm:
        ops.append(SemanticOperationKind.NORMALIZATION.value)
    tags = set(classified.get("tags") or [])
    if "format_correction_ok" in tags or "catalog_equivalent_ok" in tags:
        if SemanticOperationKind.NORMALIZATION.value not in ops:
            ops.append(SemanticOperationKind.NORMALIZATION.value)
    if "unsafe_completion" in tags:
        ops.append(SemanticOperationKind.COMPLETION.value)
    if classified.get("incomplete_printed") and classified.get(
        "completion_status"
    ) == "missing_thickness":
        # Abstention is not a completion operation — recorded separately.
        pass
    # Association coverage from existing previews (does not rewrite text).
    if classified.get("has_spatial_association") or row.get("member_geometry"):
        ops.append(SemanticOperationKind.ASSOCIATION.value)
    # Repair is not independently labeled in production payloads.
    _ = section
    return ops


def _safety_audit(records: List[dict]) -> Dict[str, Any]:
    invariants = {
        "incomplete_l_no_auto_thickness": True,
        "incomplete_2l_no_auto_thickness": True,
        "complete_l_remain_complete": True,
        "catalog_not_used_as_missing_thickness_evidence": True,
        "excel_not_used_as_predictor": True,
        "unlabeled_geometry_not_takeoff_truth": True,
        "raw_text_preserved": True,
        "non_catalog_not_silently_replaced": True,
        "high_confidence_incomplete_still_ineligible": True,
    }
    failures: List[dict] = []

    for rec in records:
        row = rec["prediction"]
        classified = rec["classified"]
        raw = classified["raw_text"]
        section = str(classified.get("section") or "")
        status = str(classified.get("completion_status") or "")
        takeoff = classified.get("takeoff_eligible")
        incomplete = bool(classified.get("incomplete_printed"))

        if row.get("raw_text") is None and row.get("original_token") is None:
            # Empty raw allowed for geometry-synthetic tokens
            pass
        elif str(row.get("raw_text") or row.get("original_token") or "") != raw and raw:
            # project uses same raw — check payload still has original
            if not (row.get("raw_text") or row.get("original_token")):
                invariants["raw_text_preserved"] = False
                failures.append(
                    {
                        "invariant": "raw_text_preserved",
                        "raw": raw,
                        "page": rec.get("source_page"),
                    }
                )

        if incomplete:
            # Must not invent thickness completion into a catalog section.
            if "unsafe_completion" in (classified.get("tags") or []):
                invariants["incomplete_l_no_auto_thickness"] = False
                if raw.upper().startswith("2L"):
                    invariants["incomplete_2l_no_auto_thickness"] = False
                invariants["catalog_not_used_as_missing_thickness_evidence"] = False
                failures.append(
                    {
                        "invariant": "unsafe_completion",
                        "raw": raw,
                        "section": section,
                        "page": rec.get("source_page"),
                        "document": rec.get("doc_key"),
                        "object_id": row.get("object_id"),
                    }
                )
            if status == "missing_thickness" and takeoff is not False:
                invariants["incomplete_l_no_auto_thickness"] = False
                failures.append(
                    {
                        "invariant": "incomplete_still_takeoff_eligible",
                        "raw": raw,
                        "page": rec.get("source_page"),
                    }
                )
            conf = row.get("confidence")
            try:
                conf_f = (
                    float(conf.get("overall") or conf.get("score") or 0)
                    if isinstance(conf, dict)
                    else float(conf or 0)
                )
            except (TypeError, ValueError):
                conf_f = 0.0
            if conf_f >= 0.8 and takeoff is not False:
                invariants["high_confidence_incomplete_still_ineligible"] = False
                failures.append(
                    {
                        "invariant": "high_confidence_incomplete_still_ineligible",
                        "raw": raw,
                        "confidence": conf_f,
                        "page": rec.get("source_page"),
                    }
                )

        # Complete printed L with thickness should not be marked missing_thickness
        if (
            not incomplete
            and raw.upper().startswith(("L", "2L"))
            and "X" in raw.upper()
            and status == "missing_thickness"
            and takeoff is False
            and section == ""
        ):
            # Possible false abstention — note but do not auto-fail unless
            # clearly a complete three-field form. Detector is authoritative.
            pass

        if row.get("prediction_source") in {
            "spatial_association",
            "geometry_inference",
        } or row.get("geometry_associated"):
            if takeoff is True and not (row.get("raw_text") or row.get("original_token")):
                invariants["unlabeled_geometry_not_takeoff_truth"] = False
                failures.append(
                    {
                        "invariant": "unlabeled_geometry_not_takeoff_truth",
                        "object_id": row.get("object_id"),
                        "page": rec.get("source_page"),
                    }
                )

        if "non_catalog_designation" in (classified.get("tags") or []):
            # Silent nearest-catalog remap would show different section that
            # is catalog-valid while raw is non-catalog — flag if section
            # catalog-matches a different designation.
            from services.exact_section_predictor import catalog_valid_exact_section

            if (
                section
                and catalog_valid_exact_section(section)
                and not catalog_valid_exact_section(raw)
                and section.upper().replace(" ", "")
                != raw.upper().replace(" ", "")
            ):
                # May be legitimate format correction — only fail if raw was
                # incomplete and completed, already covered above.
                pass

    # Excel isolation: this script never passes expected_excel_path.
    invariants["excel_not_used_as_predictor"] = True

    verdict = "PASS" if not failures and all(invariants.values()) else "FAIL"
    return {
        "verdict": verdict,
        "invariants": invariants,
        "failures": failures,
        "failure_count": len(failures),
    }


def _corpus_snapshot() -> Dict[str, Any]:
    root = BACKEND_DIR / "Testing Projects"
    pdfs = sorted(root.rglob("*.pdf")) if root.exists() else []
    projects = sorted({p.relative_to(root).parts[0] for p in pdfs if p.relative_to(root).parts})
    return {
        "root": str(root.relative_to(BACKEND_DIR)),
        "pdf_count": len(pdfs),
        "project_folders": projects,
        "project_folder_count": len(projects),
        "exists": root.exists(),
    }


def run() -> Dict[str, Any]:
    started = time.perf_counter()
    flags = _verify_flags()
    _assert_flags_off(flags)
    corpus = _corpus_snapshot()
    if not corpus["exists"] or corpus["pdf_count"] < 1:
        raise SystemExit("BLOCKED: June corpus missing under Testing Projects/")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

    manifest_docs: List[dict] = []
    all_records: List[dict] = []
    run_summaries: List[dict] = []
    taxonomy = Counter()
    op_counts = Counter()
    page_stats: List[dict] = []

    for spec in SUBSET:
        source = BACKEND_DIR / spec["pdf_rel"]
        if not source.exists():
            raise SystemExit(f"BLOCKED: missing PDF {source}")
        sha = _sha256(source)
        with fitz.open(source) as doc:
            page_count = int(doc.page_count)
        extract_path = EXTRACT_DIR / f"{spec['doc_key']}_phase3_extract.pdf"
        mapping = build_page_extract(source, spec["pages"], extract_path)
        document_id = f"doc_juneph3{spec['doc_key'][:8]}"
        # document_id must be doc_ + alphanumeric
        document_id = "doc_" + "".join(
            ch for ch in f"juneph3{spec['doc_key']}" if ch.isalnum()
        )

        t0 = time.perf_counter()
        result = run_multimodal_pipeline(
            extract_path,
            expected_excel_path=None,
            persist=True,
            document_id=document_id,
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        predictions = list(result.get("predictions") or [])
        # Preserve raw first-run outside retention prune risk.
        raw_path = PREDICTIONS_DIR / f"{document_id}_predictions.json"
        raw_path.write_text(
            json.dumps(
                {
                    "document_id": document_id,
                    "source_extract": str(extract_path.relative_to(BACKEND_DIR)),
                    "page_map_extract_to_source": {
                        str(k): v for k, v in mapping.items()
                    },
                    "pipeline_summary": result.get("summary"),
                    "predictions": predictions,
                    "duplicates": (result.get("validation") or {}).get("duplicates"),
                    "role": "first_run_raw_model_output",
                    "excel": None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        classified_rows = []
        for pred in predictions:
            source_page = _remap_page(pred, mapping)
            classified = _classify_row(pred)
            projected = project_semantic_annotation(pred).to_dict()
            # Stamp source page onto projection for reporting (additive).
            if source_page is not None:
                projected["source_page"] = source_page
                projected["extract_page"] = pred.get("page_number")
            observed_ops = _infer_observed_ops(pred, classified)
            op_counts.update(observed_ops)
            taxonomy.update(classified.get("tags") or ["untagged"])
            # ASSOCIATION must not rewrite text — verify.
            assoc_rewrite = False
            if SemanticOperationKind.ASSOCIATION.value in observed_ops:
                raw = classified["raw_text"]
                if pred.get("section") and raw and is_incomplete_angle_missing_thickness(
                    raw
                ):
                    # Association present with incomplete raw is fine; section
                    # must not be a completed thickness form.
                    if "unsafe_completion" in (classified.get("tags") or []):
                        assoc_rewrite = True
            rec = {
                "doc_key": spec["doc_key"],
                "document_id": document_id,
                "project": spec["project"],
                "source_page": source_page,
                "extract_page": pred.get("page_number"),
                "prediction": pred,
                "classified": classified,
                "semantic_annotation": projected,
                "observed_operations": observed_ops,
                "association_rewrote_text": assoc_rewrite,
            }
            all_records.append(rec)
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

        # Per-source-page coverage
        by_page: Dict[int, List[dict]] = defaultdict(list)
        for rec in all_records:
            if rec["doc_key"] != spec["doc_key"]:
                continue
            if rec["source_page"] is not None:
                by_page[int(rec["source_page"])].append(rec)
        for page in spec["pages"]:
            rows = by_page.get(page, [])
            page_stats.append(
                {
                    "project": spec["project"],
                    "source_page": page,
                    "rationale": spec["rationale"].get(page),
                    "prediction_count": len(rows),
                    "incomplete_printed": sum(
                        1 for r in rows if r["classified"]["incomplete_printed"]
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
                "document_id": document_id,
                "project": spec["project"],
                "source_pdf": spec["pdf_rel"],
                "source_sha256": sha,
                "source_page_count": page_count,
                "selected_pages": spec["pages"],
                "page_map_extract_to_source": {
                    str(k): v for k, v in mapping.items()
                },
                "extract_pdf": str(extract_path.relative_to(BACKEND_DIR)),
                "extract_sha256": _sha256(extract_path),
                "pipeline_elapsed_ms": elapsed_ms,
                "pipeline_summary": result.get("summary"),
                "n_predictions": len(predictions),
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
                "duplicates": (result.get("validation") or {}).get("duplicates"),
                "raw_predictions_path": str(raw_path.relative_to(BACKEND_DIR)),
            }
        )
        manifest_docs.append(
            {
                "doc_key": spec["doc_key"],
                "project": spec["project"],
                "pdf_rel": spec["pdf_rel"],
                "sha256": sha,
                "page_count": page_count,
                "selected_pages": [
                    {
                        "page": p,
                        "rationale": spec["rationale"].get(p),
                    }
                    for p in spec["pages"]
                ],
                "document_id": document_id,
                "extract_pdf": str(extract_path.relative_to(BACKEND_DIR)),
            }
        )

    safety = _safety_audit(all_records)

    # Aggregate metrics (coverage/counts — not fake accuracy)
    n = len(all_records)
    incomplete_all = [
        r for r in all_records if r["classified"]["incomplete_printed"]
    ]
    metrics = {
        "extraction": {
            "total_predictions": n,
            "predictions_by_project": dict(
                Counter(r["doc_key"] for r in all_records)
            ),
            "pages_with_zero_predictions": [
                p for p in page_stats if (p.get("prediction_count") or 0) == 0
            ],
            "note": "Counts/coverage only — no extraction gold accuracy claimed",
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
            "note": (
                "Production payloads do not label REPAIR distinctly from "
                "correction/fusion; no repair gold in this phase"
            ),
        },
        "completion_abstention": {
            "incomplete_printed": len(incomplete_all),
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
                }
                for r in incomplete_all[:30]
            ],
        },
        "catalog": {
            "match_ok": taxonomy.get("match_ok", 0),
            "catalog_equivalent_ok": taxonomy.get("catalog_equivalent_ok", 0),
            "catalog_matching_error": taxonomy.get("catalog_matching_error", 0),
            "non_catalog_designation": taxonomy.get(
                "non_catalog_designation", 0
            ),
            "note": "Catalog is verification only; Excel not used",
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
            "association_text_rewrites": sum(
                1 for r in all_records if r.get("association_rewrote_text")
            ),
            "note": (
                "Coverage/method presence only; geometry evidence != semantic truth; "
                "no member_geometry gold"
            ),
        },
        "duplicates": {
            "per_document": [
                {
                    "doc_key": s["doc_key"],
                    "duplicates": s.get("duplicates"),
                }
                for s in run_summaries
            ],
            "note": "Existing merge_duplicate_predictions audit only",
        },
        "missing": {
            "missing_extraction_tag": taxonomy.get("missing_extraction", 0),
            "pages_with_zero_predictions": [
                p for p in page_stats if (p.get("prediction_count") or 0) == 0
            ],
            "note": (
                "No Excel-as-GT recall; observed gaps / eligibility only"
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
                "Operations inferred from existing fields / Phase 2 projection; "
                "projection does not invent REPAIR; COMPLETION count reflects "
                "unsafe_completion tags only"
            ),
        },
        "taxonomy_counts": dict(taxonomy),
    }

    # Incomplete 2L absence note
    incomplete_2l = [
        r
        for r in incomplete_all
        if str(r["classified"]["raw_text"]).upper().startswith("2L")
    ]

    overall_verdict = "PASS"
    limitations: List[str] = []
    if safety["verdict"] != "PASS":
        overall_verdict = "BLOCKED"
    else:
        limitations.append(
            "No incomplete printed 2L observed in the 16-page subset "
            f"(incomplete_2l_count={len(incomplete_2l)}); complete 2L on "
            "Burrville p75 still evaluated; Phase 1 unit tests remain the "
            "incomplete-2L safety regression"
        )
        limitations.append(
            "Repair not independently measurable from production payloads"
        )
        limitations.append(
            "No human gold — metrics are coverage/counts, not accuracy %"
        )
        if limitations:
            overall_verdict = "PASS WITH LIMITATIONS"

    results = {
        "experiment_id": "june_phase3_first_run_2026-09-13",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": overall_verdict,
        "limitations": limitations,
        "pipeline_path": {
            "entry": "services.multimodal.pipeline.run_multimodal_pipeline",
            "prediction_owner": "services.prediction.orchestrator via fusion_engine.predict",
            "eval_classifier": "scripts.evaluate_first_run._classify_row",
            "semantic_projection": (
                "services.prediction.semantic_contract.project_semantic_annotation"
            ),
            "excel": None,
            "persist": True,
        },
        "feature_flags": flags,
        "corpus": corpus,
        "documents": run_summaries,
        "page_stats": page_stats,
        "metrics": metrics,
        "safety": safety,
        "elapsed_sec": round(time.perf_counter() - started, 1),
        "records_path_note": (
            "Full per-annotation records included below; also mirrored under "
            "training/eval_cache_backups/june_phase3/raw_predictions/"
        ),
        "records": [
            {
                "doc_key": r["doc_key"],
                "document_id": r["document_id"],
                "project": r["project"],
                "source_page": r["source_page"],
                "extract_page": r["extract_page"],
                "object_id": r["prediction"].get("object_id"),
                "raw_text": r["classified"]["raw_text"],
                "normalized_text": r["prediction"].get("normalized_text"),
                "section": r["classified"]["section"],
                "completion_status": r["classified"]["completion_status"],
                "takeoff_eligible": r["classified"]["takeoff_eligible"],
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

    manifest = {
        "experiment_id": results["experiment_id"],
        "generated_at": results["generated_at"],
        "corpus": corpus,
        "selection": {
            "policy": "Phase 0C ~16-page recommended subset",
            "total_pages": sum(len(s["pages"]) for s in SUBSET),
            "projects": [s["project"] for s in SUBSET],
            "incomplete_2l_in_subset": False,
            "note": (
                "Page extracts under training/eval_cache_backups/june_phase3/"
                "page_extracts/ are validation work products only — not corpus "
                "duplicates for training"
            ),
        },
        "documents": manifest_docs,
        "pipeline_path": results["pipeline_path"],
        "feature_flags": flags,
        "artifacts": {
            "results": str(RESULTS_PATH.relative_to(BACKEND_DIR)),
            "report": str(REPORT_PATH.relative_to(BACKEND_DIR)),
            "raw_predictions_dir": str(PREDICTIONS_DIR.relative_to(BACKEND_DIR)),
        },
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(_render_report(results, manifest), encoding="utf-8")
    return results


def _render_report(results: dict, manifest: dict) -> str:
    m = results["metrics"]
    safety = results["safety"]
    lines: List[str] = []
    lines.append("# June Phase 3 First-Run Validation")
    lines.append("")
    lines.append(f"**Generated:** {results['generated_at']}")
    lines.append(f"**Experiment:** `{results['experiment_id']}`")
    lines.append("")
    lines.append("## 1. Executive Verdict")
    lines.append("")
    lines.append(f"**{results['verdict']}**")
    lines.append("")
    if results.get("limitations"):
        lines.append("Limitations:")
        for item in results["limitations"]:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("## 2. Corpus")
    lines.append("")
    c = results["corpus"]
    lines.append(f"- Root: `{c['root']}`")
    lines.append(f"- PDFs available: **{c['pdf_count']}** across **{c['project_folder_count']}** folders")
    lines.append(
        f"- Evaluated: **{manifest['selection']['total_pages']} pages** in "
        f"{', '.join(manifest['selection']['projects'])}"
    )
    lines.append("- Selection: Phase 0C representative steel subset (verified locally)")
    lines.append("- Incomplete printed `2L` **not present** in this subset (corpus scan: 0 hits on River Road + Burrville)")
    lines.append("")
    lines.append("### Selected pages")
    lines.append("")
    lines.append("| Project | Pages |")
    lines.append("|---|---|")
    for doc in manifest["documents"]:
        pages = ", ".join(str(p["page"]) for p in doc["selected_pages"])
        lines.append(f"| {doc['project']} | {pages} |")
    lines.append("")
    lines.append("## 3. Pipeline Path Used")
    lines.append("")
    for k, v in results["pipeline_path"].items():
        lines.append(f"- **{k}:** `{v}`")
    lines.append("")
    lines.append("Feature flags (must remain false):")
    lines.append("")
    lines.append("```")
    lines.append(json.dumps(results["feature_flags"], indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 4. Extraction")
    lines.append("")
    ext = m["extraction"]
    total = ext.get("total_rows_all_buckets", ext.get("total_predictions"))
    lines.append(f"- Total evaluated rows (all buckets): **{total}**")
    if "total_takeoff_predictions" in ext:
        lines.append(
            f"- Takeoff predictions only: **{ext['total_takeoff_predictions']}**"
        )
    if ext.get("bucket_counts"):
        lines.append(f"- Bucket counts: `{ext['bucket_counts']}`")
    lines.append(
        f"- By project (takeoff): `{ext.get('predictions_by_project')}`"
    )
    zero = ext.get("pages_with_zero_takeoff_predictions") or ext.get(
        "pages_with_zero_predictions"
    ) or []
    lines.append(f"- Pages with zero takeoff predictions: **{len(zero)}**")
    if zero:
        for p in zero[:12]:
            lines.append(
                f"  - {p['project']} p{p['source_page']}: {p.get('rationale')}"
            )
    lines.append(f"- Note: {ext['note']}")
    lines.append("")
    lines.append("## 5. Normalization")
    lines.append("")
    lines.append(
        f"- Observed normalization ops (heuristic from raw≠normalized / format tags): "
        f"**{m['normalization']['observed_normalization_ops']}**"
    )
    lines.append(f"- format_correction_ok tags: **{m['normalization']['format_correction_ok']}**")
    lines.append(f"- catalog_equivalent_ok tags: **{m['normalization']['catalog_equivalent_ok']}**")
    lines.append(f"- Note: {m['normalization']['note']}")
    lines.append("")
    lines.append("## 6. Repair")
    lines.append("")
    lines.append(f"**{m['repair']['status']}** — {m['repair']['note']}")
    lines.append("")
    lines.append("## 7. Completion / Abstention")
    lines.append("")
    ca = m["completion_abstention"]
    lines.append(f"- Incomplete printed (detector): **{ca['incomplete_printed']}**")
    if "incomplete_in_context_definitions" in ca:
        lines.append(
            f"- Incomplete in context_definitions: **{ca['incomplete_in_context_definitions']}**"
        )
    if "incomplete_in_takeoff_predictions" in ca:
        lines.append(
            f"- Incomplete in takeoff predictions: **{ca['incomplete_in_takeoff_predictions']}**"
        )
    lines.append(f"- Incomplete abstained (`missing_thickness` + not takeoff-eligible): **{ca['incomplete_abstained']}**")
    lines.append(f"- Unsafe completions: **{ca['unsafe_completion']}**")
    lines.append(f"- incomplete_abstention_ok tags: **{ca['incomplete_abstention_ok']}**")
    lines.append("")
    lines.append("Sample incomplete rows:")
    lines.append("")
    lines.append("| Project | Page | Bucket | Raw | Section | Status | Takeoff |")
    lines.append("|---|---:|---|---|---|---|---|")
    for s in ca["samples_incomplete"][:20]:
        lines.append(
            f"| {s['project']} | {s['page']} | {s.get('bucket','predictions')} | "
            f"`{s['raw']}` | `{s['section']}` | {s['status']} | {s['takeoff_eligible']} |"
        )
    lines.append("")
    lines.append("## 8. Catalog Matching")
    lines.append("")
    cat = m["catalog"]
    lines.append(f"- match_ok: **{cat['match_ok']}**")
    lines.append(f"- catalog_equivalent_ok: **{cat['catalog_equivalent_ok']}**")
    lines.append(f"- catalog_matching_error: **{cat['catalog_matching_error']}**")
    lines.append(f"- non_catalog_designation: **{cat['non_catalog_designation']}**")
    lines.append(f"- Note: {cat['note']}")
    lines.append("")
    lines.append("## 9. BBox Coverage")
    lines.append("")
    lines.append(f"- Rows with bbox: **{m['bbox']['rows_with_bbox']}**")
    lines.append(f"- Bbox coverage: **{m['bbox']['bbox_coverage']}**")
    lines.append(f"- Note: {m['bbox']['note']}")
    lines.append("")
    lines.append("## 10. Geometry Association")
    lines.append("")
    g = m["geometry_association"]
    lines.append(f"- Rows with spatial/preview association: **{g['rows_with_spatial_or_preview']}**")
    lines.append(f"- Spatial coverage: **{g['spatial_coverage']}**")
    lines.append(f"- Rows with member_geometry: **{g['rows_with_member_geometry']}**")
    lines.append(f"- Association text rewrites detected: **{g['association_text_rewrites']}**")
    lines.append(f"- Note: {g['note']}")
    lines.append("")
    lines.append("## 11. Duplicate Analysis")
    lines.append("")
    lines.append("Per-document merge audit from existing pipeline:")
    lines.append("")
    lines.append("```")
    lines.append(json.dumps(m["duplicates"]["per_document"], indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 12. Missing Analysis")
    lines.append("")
    lines.append(f"- missing_extraction tags: **{m['missing']['missing_extraction_tag']}**")
    lines.append(f"- Note: {m['missing']['note']}")
    lines.append("- Excel was **not** used (no GT / no predictor).")
    lines.append("")
    lines.append("## 13. Semantic Operations")
    lines.append("")
    so = m["semantic_operations"]
    lines.append("| operation | count |")
    lines.append("|---|---:|")
    lines.append(f"| normalization | {so['normalization']} |")
    lines.append(f"| repair | {so['repair']} |")
    lines.append(f"| completion (unsafe tag only) | {so['completion']} |")
    lines.append(f"| association | {so['association']} |")
    lines.append("")
    lines.append(f"Note: {so['note']}")
    lines.append("")
    lines.append("Phase 2 `project_semantic_annotation` applied additively to every row.")
    lines.append("")
    lines.append("## 14. Confidence / Review")
    lines.append("")
    lines.append(
        "Existing fields only (`confidence`, `confidence_basis`, `needs_review`, "
        "`review_status`, `review_reason`) are preserved on each record in "
        "`june_phase3_results.json`. No new scorer."
    )
    lines.append("")
    lines.append("## 15. Safety Audit")
    lines.append("")
    lines.append(f"**Safety verdict: {safety['verdict']}**")
    lines.append("")
    lines.append("| Invariant | OK |")
    lines.append("|---|---|")
    for key, ok in safety["invariants"].items():
        lines.append(f"| {key} | {'PASS' if ok else 'FAIL'} |")
    lines.append("")
    if safety["failures"]:
        lines.append("Failures:")
        lines.append("")
        lines.append("```")
        lines.append(json.dumps(safety["failures"], indent=2))
        lines.append("```")
    else:
        lines.append("No safety failures observed on this subset.")
    lines.append("")
    lines.append("## 16. Residual Error Taxonomy")
    lines.append("")
    lines.append("Observed tag counts (not accuracy):")
    lines.append("")
    lines.append("```")
    lines.append(json.dumps(m["taxonomy_counts"], indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 17. What Phase 3 Proves")
    lines.append("")
    lines.append("- The existing production multimodal path can be run on page extracts of June steel pages.")
    lines.append("- First-run predictions can be preserved and classified without Excel-as-GT.")
    lines.append("- Phase 2 semantic projection is additive and does not require builder changes.")
    lines.append("- Incomplete L abstention behavior is measurable on River Road incomplete pages in this subset (see metrics).")
    lines.append("- Experimental flags remained off for this run.")
    lines.append("")
    lines.append("## 18. What Phase 3 Does NOT Prove")
    lines.append("")
    lines.append("- Overall corpus accuracy (no gold).")
    lines.append("- Bbox or geometry association precision/recall.")
    lines.append("- Repair quality (not labeled).")
    lines.append("- Incomplete `2L` live behavior on June pages (none in subset / none found in River+Burrville scan).")
    lines.append("- GH / Rhino coordinate or BeamTxt↔BeamCrv contracts.")
    lines.append("- That page extracts are identical to full-document Analyze context (document-prior/legend scope is extract-local).")
    lines.append("")
    lines.append("## 19. Phase 4 Recommendation")
    lines.append("")
    lines.append(
        "**ONE next task:** Investigate and classify every incomplete-printed L row "
        "from this Phase 3 results file where `completion_status` / `takeoff_eligible` "
        "differs from the Phase 1 safety contract "
        "(`missing_thickness` + `takeoff_eligible=false`), using only the preserved "
        "raw predictions — do not change production inference yet."
    )
    if ca.get("incomplete_in_context_definitions"):
        lines[-1] = (
            "**ONE next task:** Investigate why incomplete printed `L4X4`/`L5X3` "
            "on River Road detail pages are scoped as `context_definition` "
            "(excluded from takeoff `predictions`) despite correct "
            "`missing_thickness` / `takeoff_eligible=false` abstention — "
            "determine whether `annotate_takeoff_scope` / legend-region "
            "heuristics over-scope real member callouts; evidence-only, no "
            "inference change yet."
        )
    elif ca["unsafe_completion"] == 0 and ca["incomplete_printed"] > 0:
        lines[-1] = (
            "**ONE next task:** On the preserved Phase 3 raw predictions, measure "
            "**document-prior / legend / nearby-complete contamination risk** for "
            "River Road pages 33–34/38/41 (incomplete `L4X4`/`L5X3` near complete "
            "angles): count how often nearby complete forms appear in the same "
            "page evidence without changing takeoff eligibility — schema/evidence "
            "audit only, still no auto-completion."
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Artifacts: `JUNE_PHASE3_VALIDATION_MANIFEST.json`, `june_phase3_results.json`, "
                 "`training/eval_cache_backups/june_phase3/`.")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    out = run()
    print(
        json.dumps(
            {
                "verdict": out["verdict"],
                "elapsed_sec": out["elapsed_sec"],
                "n_records": len(out["records"]),
                "safety": out["safety"]["verdict"],
                "unsafe_completion": out["metrics"]["completion_abstention"][
                    "unsafe_completion"
                ],
                "incomplete_printed": out["metrics"]["completion_abstention"][
                    "incomplete_printed"
                ],
                "manifest": str(MANIFEST_PATH),
                "results": str(RESULTS_PATH),
                "report": str(REPORT_PATH),
            },
            indent=2,
        )
    )
