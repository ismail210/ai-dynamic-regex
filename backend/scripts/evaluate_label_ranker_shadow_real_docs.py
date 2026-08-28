"""Controlled shadow evaluation on cached real-document Analyze predictions.

Requires:
  ML_LABEL_RANKER_ENABLED=false
  ML_LABEL_RANKER_SHADOW=true

Uses existing predictions_view.json caches so OCR / fusion / MobileNet /
GraphSAGE are not re-run. Live ``section`` values are read-only; the ranker
hook is invoked as Analyze would after fusion. Does not write the cache,
registry, or model artifacts.

Run from ``backend/``:
  ML_LABEL_RANKER_ENABLED=false ML_LABEL_RANKER_SHADOW=true \\
    python scripts/evaluate_label_ranker_shadow_real_docs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402
from services.database_loader import is_catalog_label  # noqa: E402
from services.label_reconstruction.candidates import (  # noqa: E402
    candidate_respects_reliable_query_fields,
    conservative_normalize,
    generate_candidates,
    ineligible_for_section_reconstruction,
    is_missing_thickness_hss,
    reliable_acceptance_parse,
)
from services.label_reconstruction.structural_parser import (  # noqa: E402
    field_generation_compatible,
    parse_fields,
)
from services.label_reconstruction.ranker import get_active_ranker  # noqa: E402
from services.prediction.label_ranker_hook import (  # noqa: E402
    apply_label_ranker_for_analyze,
)
from services.training_pipeline.model_registry import get_active_model  # noqa: E402

CACHES = [
    {
        "document": "Struct.pdf",
        "document_id": "doc_683e6eef0a945c9a",
        "path": BACKEND_DIR
        / "training"
        / "engineering_artifacts"
        / "doc_683e6eef0a945c9a"
        / "multimodal"
        / "predictions_view.json",
    },
    {
        "document": "Burrville ES - ST.pdf",
        "document_id": "doc_0d910a43b4a021e3",
        "path": BACKEND_DIR
        / "training"
        / "engineering_artifacts"
        / "doc_0d910a43b4a021e3"
        / "multimodal"
        / "predictions_view.json",
    },
    {
        "document": "ST.pdf",
        "document_id": "doc_0bfc2d61245dbce2",
        "path": BACKEND_DIR
        / "training"
        / "engineering_artifacts"
        / "doc_0bfc2d61245dbce2"
        / "multimodal"
        / "predictions_view.json",
    },
]

OUTPUT_DIR = (
    BACKEND_DIR
    / "training"
    / "engineering_artifacts"
    / "label_ranker_shadow_eval"
)

SAFETY_FIXTURES = [
    "HSS8X8",
    "HSS8x8",
    "HSS10X10",
    "HSS6X8X1/2",
    "PL",
    "PLATE",
    "CAP PL",
    "CONN PL",
    '5/16"',
    "W??X?7",
]


def _text(row: dict) -> str:
    return str(
        row.get("original_token")
        or row.get("raw_text")
        or row.get("corrected_text")
        or ""
    ).strip()


def _live_section(row: dict) -> str:
    return str(row.get("section") or row.get("section_prediction") or "").strip()


def _page(row: dict):
    return row.get("page_number", row.get("page"))


def _unsafe_reasons(query: str, live: str, xgb: str, candidates: list[str], reason: str) -> list[str]:
    flags: list[str] = []
    qn = conservative_normalize(query)
    xn = conservative_normalize(xgb) if xgb else ""
    if xgb and candidates and xgb not in candidates:
        flags.append("candidate_outside_generated_set")
    if reason == "exact_match" and xgb and xgb != qn and live and live != xgb:
        flags.append("protected_exact_overridden")
    if is_missing_thickness_hss(qn) and xgb:
        flags.append("missing_thickness_hss_invented_wall")
    if ineligible_for_section_reconstruction(query, qn) and xgb:
        flags.append("plate_or_ineligible_to_rolled")
    if qn.startswith("HSS8X8") and "HSS18" in xn:
        flags.append("hss8_to_hss18")
    if "HSS6X8X1/2" in qn.replace(" ", "") and "HSS16X8" in xn:
        flags.append("hss6x8x12_to_hss16")
    if qn.startswith("W") and not qn.startswith("WT") and xn.startswith("WT"):
        flags.append("w_to_wt")
    flags.extend(_field_regression_flags(qn, xn))
    return flags


def _field_regression_flags(normalized_query: str, xgb_label: str) -> list[str]:
    if not xgb_label:
        return []
    if candidate_respects_reliable_query_fields(normalized_query, xgb_label):
        return []
    constraints = reliable_acceptance_parse(normalized_query)
    candidate = parse_fields(xgb_label)
    if constraints is None or not candidate.ok:
        return ["reliable_field_regression"]
    flags: list[str] = []
    if candidate.family != constraints.family:
        flags.append("family_regression")
    n = min(len(constraints.fields), len(candidate.fields))
    thickness_idx = None
    if constraints.grammar in ("leg_leg_thickness", "hss_rect"):
        thickness_idx = n - 1 if n >= 3 else None
    elif constraints.grammar == "hss_round":
        thickness_idx = 1 if n >= 2 else None
    size_changed = False
    thickness_changed = False
    for i in range(n):
        qf, cf = constraints.fields[i], candidate.fields[i]
        if field_generation_compatible(qf, cf):
            continue
        if thickness_idx is not None and i == thickness_idx:
            thickness_changed = True
        else:
            size_changed = True
    if thickness_changed:
        flags.append("thickness_regression")
    if size_changed:
        flags.append("size_dimension_regression")
    return flags or ["reliable_field_regression"]


def main() -> int:
    print("ENABLED", settings.ml_label_ranker_enabled)
    print("SHADOW", settings.ml_label_ranker_shadow)
    if settings.ml_label_ranker_enabled:
        print("Refusing: ML_LABEL_RANKER_ENABLED must be false.")
        return 1
    if not settings.ml_label_ranker_shadow:
        print("Refusing: ML_LABEL_RANKER_SHADOW must be true for this eval.")
        return 1

    entry = get_active_model("label_reconstruction")
    ranker = get_active_ranker()
    active = (entry or {}).get("version_id")
    print("active_version", active)
    print("ranker_loaded", ranker is not None, getattr(ranker, "version_id", None))
    if not ranker or not active or ranker.version_id != active:
        print("Refusing: active promoted ranker must load.")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    object.__setattr__(
        settings,
        "ml_label_ranker_shadow_log_path",
        OUTPUT_DIR / "shadow_log.jsonl",
    )

    records: list[dict] = []
    counts = {
        "documents_with_cache": 0,
        "extracted_labels": 0,
        "ranker_eligible": 0,
        "shadow_applications": 0,
        "agreements": 0,
        "disagreements": 0,
        "exact_label": 0,
        "missing_thickness": 0,
        "plate_ineligible": 0,
        "no_candidates": 0,
        "hook_applied": 0,
        "live_mutated": 0,
        "thickness_regressions": 0,
        "size_dimension_regressions": 0,
        "hss_safety_violations": 0,
        "w_to_wt_violations": 0,
        "anonymous_dimension_xgb": 0,
        "exact_label_mutations": 0,
        "xgb_vs_deterministic_disagreements": 0,
        "field_gate_rejected": 0,
    }

    for spec in CACHES:
        path = spec["path"]
        if not path.exists():
            print("skip missing cache", spec["document"], path)
            continue
        counts["documents_with_cache"] += 1
        payload = json.loads(path.read_text(encoding="utf-8"))
        predictions = (
            payload if isinstance(payload, list) else payload.get("predictions", [])
        )
        for row in predictions:
            raw = _text(row)
            if not raw:
                continue
            counts["extracted_labels"] += 1
            live = _live_section(row)
            live_before = live
            normalized = conservative_normalize(raw)
            bucket = "rankable"
            if ineligible_for_section_reconstruction(raw, normalized):
                bucket = "plate_ineligible"
                counts["plate_ineligible"] += 1
            elif is_catalog_label(normalized):
                bucket = "exact_label"
                counts["exact_label"] += 1
            elif is_missing_thickness_hss(normalized):
                bucket = "missing_thickness"
                counts["missing_thickness"] += 1
            else:
                cs = generate_candidates(raw)
                if not cs.candidates:
                    bucket = "no_candidates"
                    counts["no_candidates"] += 1
                else:
                    counts["ranker_eligible"] += 1

            meta = apply_label_ranker_for_analyze(raw_text=raw, live_section=live)
            if meta.get("applied"):
                counts["hook_applied"] += 1
            if meta.get("live_section") != live_before:
                counts["live_mutated"] += 1

            shadow = meta.get("shadow") or {}
            xgb = shadow.get("ml_prediction")
            if xgb:
                counts["shadow_applications"] += 1
            candidates = list(shadow.get("top_k_candidates") or [])
            if not candidates and bucket == "rankable":
                candidates = generate_candidates(raw).candidates

            live_disagree = bool(xgb) and xgb != live
            if xgb:
                if live_disagree:
                    counts["disagreements"] += 1
                else:
                    counts["agreements"] += 1
            if shadow.get("disagreement"):
                counts["xgb_vs_deterministic_disagreements"] += 1
            if shadow.get("field_gate_rejected"):
                counts["field_gate_rejected"] += 1

            unsafe = _unsafe_reasons(
                raw, live, xgb or "", candidates, meta.get("reason") or ""
            )
            if "thickness_regression" in unsafe:
                counts["thickness_regressions"] += 1
            if "size_dimension_regression" in unsafe:
                counts["size_dimension_regressions"] += 1
            if any(
                flag in unsafe
                for flag in (
                    "missing_thickness_hss_invented_wall",
                    "hss8_to_hss18",
                    "hss6x8x12_to_hss16",
                )
            ):
                counts["hss_safety_violations"] += 1
            if "w_to_wt" in unsafe:
                counts["w_to_wt_violations"] += 1
            if bucket == "plate_ineligible" and xgb:
                counts["anonymous_dimension_xgb"] += 1
            if bucket == "exact_label" and xgb and xgb != normalized:
                counts["exact_label_mutations"] += 1
            records.append(
                {
                    "document": spec["document"],
                    "document_id": spec["document_id"],
                    "page": _page(row),
                    "query": raw,
                    "normalized": normalized,
                    "bucket": bucket,
                    "live_section": live,
                    "shadow_xgb": xgb,
                    "deterministic_pick": shadow.get("current_prediction")
                    or meta.get("selected_prediction"),
                    "selected_prediction": meta.get("selected_prediction"),
                    "reason": meta.get("reason"),
                    "candidate_set": candidates[:20],
                    "candidate_count": len(candidates),
                    "exact_protected": bucket == "exact_label",
                    "abstention": bucket
                    in ("plate_ineligible", "missing_thickness", "no_candidates")
                    or meta.get("reason") == "no_candidates",
                    "ranker_applied": bool(meta.get("applied")),
                    "ranker_invoked": bool(meta.get("invoked")),
                    "model_version": meta.get("model_version"),
                    "margin": shadow.get("margin"),
                    "ranking_scores": (shadow.get("ranking_scores") or [])[:8],
                    "disagreement_vs_live": live_disagree,
                    "disagreement_vs_deterministic": bool(shadow.get("disagreement")),
                    "unsafe_flags": unsafe,
                    "hook_live_section": meta.get("live_section"),
                }
            )

    disagreements = [r for r in records if r["disagreement_vs_live"]]
    safety_rows = []
    live_before_after = []
    for fixture in SAFETY_FIXTURES:
        live = ""
        meta1 = apply_label_ranker_for_analyze(raw_text=fixture, live_section=live)
        meta2 = apply_label_ranker_for_analyze(raw_text=fixture, live_section=live)
        live_before_after.append(
            {
                "query": fixture,
                "live_before": live,
                "hook_live_1": meta1.get("live_section"),
                "hook_live_2": meta2.get("live_section"),
                "applied_1": meta1.get("applied"),
                "applied_2": meta2.get("applied"),
                "selected_1": meta1.get("selected_prediction"),
                "selected_2": meta2.get("selected_prediction"),
                "equal_selected": meta1.get("selected_prediction")
                == meta2.get("selected_prediction"),
            }
        )
        shadow = meta1.get("shadow") or {}
        safety_rows.append(
            {
                "query": fixture,
                "reason": meta1.get("reason"),
                "selected": meta1.get("selected_prediction"),
                "shadow_xgb": shadow.get("ml_prediction"),
                "applied": meta1.get("applied"),
                "candidates": (shadow.get("top_k_candidates") or [])[:12],
                "unsafe_flags": _unsafe_reasons(
                    fixture,
                    live,
                    shadow.get("ml_prediction") or "",
                    shadow.get("top_k_candidates") or [],
                    meta1.get("reason") or "",
                ),
            }
        )

    summary = {
        "flags": {
            "ML_LABEL_RANKER_ENABLED": settings.ml_label_ranker_enabled,
            "ML_LABEL_RANKER_SHADOW": settings.ml_label_ranker_shadow,
        },
        "active_model": active,
        "counts": counts,
        "shadow_disagreement_rate": (
            counts["disagreements"] / counts["shadow_applications"]
            if counts["shadow_applications"]
            else None
        ),
        "unsafe_disagreement_count": sum(
            1 for r in disagreements if r["unsafe_flags"]
        ),
        "ground_truth": "GT unavailable; TP/FP/FN/TN not measurable",
        "safety_fixtures": safety_rows,
        "live_output_invariant": live_before_after,
        "disagreements": disagreements,
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    (OUTPUT_DIR / "records.jsonl").write_text(
        "\n".join(json.dumps(r, default=str) for r in records) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(counts, indent=2))
    print("disagreements", len(disagreements))
    print("hook_applied", counts["hook_applied"], "live_mutated", counts["live_mutated"])
    print("wrote", OUTPUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
