"""Human-review helpers for A2/A7 validation (not production inference)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[2]
GOLD_DIR = BACKEND_DIR / "training" / "eval_cache_backups" / "accuracy_gold"
A2_GOLD = GOLD_DIR / "june_16page_extract_group_gold.json"
A7_GOLD = GOLD_DIR / "june_association_gold.json"
A2_REVIEW = GOLD_DIR / "a2_human_review_70.json"
A7_REVIEW = GOLD_DIR / "a7_human_review_100.json"
REPORT_DIR = BACKEND_DIR / "validation_reports" / "human_review"

A2_ENUMS = {
    "extraction_correct": {"YES", "NO", "AMBIGUOUS"},
    "grouping_correct": {"YES", "NO", "AMBIGUOUS", "NOT_APPLICABLE"},
    "operation_correct": {"YES", "NO", "AMBIGUOUS"},
    "should_abstain": {"YES", "NO", "AMBIGUOUS"},
    "verdict": {"ACCEPT", "CORRECT", "ABSTAIN", "AMBIGUOUS"},
    "reason_code": {
        "correct",
        "extraction_error",
        "grouping_error",
        "normalization_error",
        "unsafe_completion",
        "should_abstain",
        "missing_evidence",
        "ambiguous_drawing",
        "other",
    },
}

A7_ENUMS = {
    "verdict": {"CORRECT", "WRONG", "AMBIGUOUS"},
    "reason_code": {
        "correct",
        "wrong_member",
        "leader_only",
        "dimension_geometry",
        "unrelated_line",
        "shared_member",
        "multiple_candidates",
        "insufficient_evidence",
        "ambiguous",
        "other",
    },
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _na(msg: str = "N/A — no reviewed samples") -> str:
    return msg


def _rate(num: int, den: int) -> Any:
    if den <= 0:
        return _na()
    return round(num / den, 4)


def a2_is_reviewed(row: Dict[str, Any]) -> bool:
    hr = row.get("human_review") or {}
    return hr.get("verdict") is not None and str(hr.get("verdict") or "").strip() != ""


def a7_is_reviewed(link: Dict[str, Any]) -> bool:
    hr = link.get("human_review") or {}
    return hr.get("verdict") is not None and str(hr.get("verdict") or "").strip() != ""


def validate_a2_review_doc(doc: Dict[str, Any], *, gold: Optional[Dict[str, Any]] = None) -> List[str]:
    errors: List[str] = []
    rows = doc.get("rows") or []
    if len(rows) != 70:
        errors.append(f"expected_70_rows_got_{len(rows)}")
    ids = [r.get("review_id") for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_review_ids")
    if None in ids or "" in ids:
        errors.append("missing_review_id")
    if gold is not None:
        gold_ids = {r.get("gold_id") for r in gold.get("rows") or []}
        for r in rows:
            if r.get("source_gold_id") not in gold_ids:
                errors.append(f"missing_source_{r.get('source_gold_id')}")
                break
        unverified = [r for r in gold.get("rows") or [] if not r.get("human_verified")]
        if len(unverified) != 70:
            errors.append(f"gold_unverified_count_{len(unverified)}")
    for r in rows:
        hr = r.get("human_review") or {}
        for field, allowed in A2_ENUMS.items():
            val = hr.get(field)
            if val is None or val == "":
                continue
            if val not in allowed:
                errors.append(f"invalid_{field}_{val}_on_{r.get('review_id')}")
    return errors


def validate_a7_review_doc(doc: Dict[str, Any], *, gold: Optional[Dict[str, Any]] = None) -> List[str]:
    errors: List[str] = []
    links = doc.get("links") or []
    if len(links) != 100:
        errors.append(f"expected_100_links_got_{len(links)}")
    ids = [r.get("review_id") for r in links]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_review_ids")
    if gold is not None:
        gold_ids = {r.get("link_id") for r in gold.get("links") or []}
        for r in links:
            if r.get("source_link_id") not in gold_ids:
                errors.append(f"missing_source_{r.get('source_link_id')}")
                break
    for r in links:
        hr = r.get("human_review") or {}
        for field, allowed in A7_ENUMS.items():
            val = hr.get(field)
            if val is None or val == "":
                continue
            if val not in allowed:
                errors.append(f"invalid_{field}_{val}_on_{r.get('review_id')}")
    return errors


def compute_a2_metrics(doc: Dict[str, Any]) -> Dict[str, Any]:
    rows = doc.get("rows") or []
    reviewed = [r for r in rows if a2_is_reviewed(r)]
    n_rev = len(reviewed)
    coverage = _rate(n_rev, 70)

    def count_field(field: str, value: str, applicable: Optional[List[Dict[str, Any]]] = None) -> int:
        pool = applicable if applicable is not None else reviewed
        return sum(1 for r in pool if (r.get("human_review") or {}).get(field) == value)

    grouping_applicable = [
        r
        for r in reviewed
        if (r.get("human_review") or {}).get("grouping_correct") != "NOT_APPLICABLE"
        and (r.get("human_review") or {}).get("grouping_correct") is not None
    ]
    # If grouping_correct is set to YES/NO/AMBIGUOUS it is applicable; unanswered excluded
    grouping_pool = [
        r
        for r in reviewed
        if (r.get("human_review") or {}).get("grouping_correct")
        in {"YES", "NO", "AMBIGUOUS", "NOT_APPLICABLE"}
    ]
    grouping_yes_no_amb = [
        r
        for r in grouping_pool
        if (r.get("human_review") or {}).get("grouping_correct") != "NOT_APPLICABLE"
    ]

    operation_pool = [
        r
        for r in reviewed
        if (r.get("human_review") or {}).get("operation_correct") in {"YES", "NO", "AMBIGUOUS"}
    ]

    extraction_pool = [
        r
        for r in reviewed
        if (r.get("human_review") or {}).get("extraction_correct") in {"YES", "NO", "AMBIGUOUS"}
    ]

    abstain_pool = [
        r
        for r in reviewed
        if (r.get("human_review") or {}).get("should_abstain") in {"YES", "NO", "AMBIGUOUS"}
    ]

    # Normalization: compare expected_normalized_value when provided
    norm_correct = norm_incorrect = norm_ambiguous = 0
    norm_answered = 0
    for r in reviewed:
        hr = r.get("human_review") or {}
        expected = hr.get("expected_normalized_value")
        if expected is None or str(expected).strip() == "":
            continue
        norm_answered += 1
        if hr.get("verdict") == "AMBIGUOUS" or hr.get("reason_code") == "ambiguous_drawing":
            norm_ambiguous += 1
            continue
        system_val = str((r.get("system") or {}).get("normalized_value") or "").strip()
        if str(expected).strip().upper().replace(" ", "") == system_val.upper().replace(" ", ""):
            norm_correct += 1
        else:
            # ABSTAIN seed may use ABSTAIN_MISSING_THICKNESS
            if str(expected).strip().upper().startswith("ABSTAIN") and (
                hr.get("should_abstain") == "YES" or hr.get("verdict") == "ABSTAIN"
            ):
                norm_correct += 1
            else:
                norm_incorrect += 1

    # Abstention outcomes from human fields
    correct_abstention = sum(
        1
        for r in reviewed
        if (r.get("human_review") or {}).get("should_abstain") == "YES"
        and (r.get("human_review") or {}).get("verdict") in {"ABSTAIN", "ACCEPT", "CORRECT"}
        and (r.get("human_review") or {}).get("reason_code") != "unsafe_completion"
    )
    unsafe_completion = sum(
        1
        for r in reviewed
        if (r.get("human_review") or {}).get("reason_code") == "unsafe_completion"
    )
    missed_abstention = sum(
        1
        for r in reviewed
        if (r.get("human_review") or {}).get("should_abstain") == "YES"
        and (r.get("human_review") or {}).get("verdict") not in {"ABSTAIN", None}
        and (r.get("human_review") or {}).get("reason_code")
        in {"normalization_error", "unsafe_completion", "should_abstain"}
    )
    # clearer missed: human says should abstain but marks extraction/op as wrong due to completion
    missed_abstention = sum(
        1
        for r in reviewed
        if (r.get("human_review") or {}).get("should_abstain") == "YES"
        and (r.get("system") or {}).get("completion_status") != "missing_thickness"
        and (r.get("human_review") or {}).get("reason_code")
        in {"unsafe_completion", "should_abstain", "normalization_error"}
    )
    ambiguous_abstention = sum(
        1 for r in abstain_pool if (r.get("human_review") or {}).get("should_abstain") == "AMBIGUOUS"
    )

    safety = _a2_safety_findings(reviewed)

    return {
        "total": 70,
        "reviewed": n_rev,
        "remaining": 70 - n_rev,
        "coverage": coverage,
        "extraction": {
            "yes_rate": _rate(count_field("extraction_correct", "YES", extraction_pool), len(extraction_pool)),
            "no_rate": _rate(count_field("extraction_correct", "NO", extraction_pool), len(extraction_pool)),
            "ambiguous_rate": _rate(
                count_field("extraction_correct", "AMBIGUOUS", extraction_pool), len(extraction_pool)
            ),
            "n": len(extraction_pool),
        },
        "grouping": {
            "yes_rate": _rate(count_field("grouping_correct", "YES", grouping_yes_no_amb), len(grouping_yes_no_amb)),
            "no_rate": _rate(count_field("grouping_correct", "NO", grouping_yes_no_amb), len(grouping_yes_no_amb)),
            "ambiguous_rate": _rate(
                count_field("grouping_correct", "AMBIGUOUS", grouping_yes_no_amb), len(grouping_yes_no_amb)
            ),
            "n_applicable": len(grouping_yes_no_amb),
            "n_not_applicable": count_field("grouping_correct", "NOT_APPLICABLE", grouping_pool),
        },
        "operation": {
            "yes_rate": _rate(count_field("operation_correct", "YES", operation_pool), len(operation_pool)),
            "no_rate": _rate(count_field("operation_correct", "NO", operation_pool), len(operation_pool)),
            "ambiguous_rate": _rate(
                count_field("operation_correct", "AMBIGUOUS", operation_pool), len(operation_pool)
            ),
            "n": len(operation_pool),
        },
        "abstention": {
            "correct_abstention_count": correct_abstention if n_rev else _na(),
            "unsafe_completion_count": unsafe_completion if n_rev else _na(),
            "missed_abstention_count": missed_abstention if n_rev else _na(),
            "ambiguous_abstention_count": ambiguous_abstention if n_rev else _na(),
        },
        "normalization": {
            "correct": norm_correct if norm_answered else _na(),
            "incorrect": norm_incorrect if norm_answered else _na(),
            "ambiguous": norm_ambiguous if norm_answered else _na(),
            "n": norm_answered,
        },
        "safety": safety,
        "note": (
            "Human review is ready; accuracy/precision is not yet measured."
            if n_rev == 0
            else "Metrics use reviewed denominator only."
        ),
    }


def _a2_safety_findings(reviewed: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Count only observed human-flagged / system-vs-expected inventions."""

    findings = {
        "l4x4_thickness_invention": 0,
        "l5x3_thickness_invention": 0,
        "l_to_2l_invention": 0,
        "catalog_only_completion": 0,
        "excel_driven_completion": 0,
        "observed_cases": [],
    }
    if not reviewed:
        for k in list(findings.keys()):
            if k != "observed_cases":
                findings[k] = _na()
        return findings

    for r in reviewed:
        hr = r.get("human_review") or {}
        raw = str(r.get("raw_text") or "").upper().replace(" ", "")
        expected = str(hr.get("expected_normalized_value") or "").upper().replace(" ", "")
        system = str((r.get("system") or {}).get("normalized_value") or "").upper().replace(" ", "")
        section = str((r.get("system") or {}).get("section") or "").upper().replace(" ", "")
        reason = hr.get("reason_code")

        def note(kind: str) -> None:
            findings[kind] += 1
            findings["observed_cases"].append(
                {"review_id": r.get("review_id"), "kind": kind, "raw_text": r.get("raw_text")}
            )

        if reason == "unsafe_completion":
            if raw.startswith("L4X4") and raw.count("X") == 1:
                note("l4x4_thickness_invention")
            elif raw.startswith("L5X3") and raw.count("X") == 1:
                note("l5x3_thickness_invention")
            note("catalog_only_completion")
        # System invented thickness vs human expected core
        if raw in {"L4X4", "L5X3"} and (system.count("X") >= 2 or section.count("X") >= 2):
            if raw == "L4X4":
                note("l4x4_thickness_invention")
            else:
                note("l5x3_thickness_invention")
        if raw.startswith("L") and not raw.startswith("2L") and (
            system.startswith("2L") or section.startswith("2L") or expected.startswith("2L")
        ):
            if system.startswith("2L") or section.startswith("2L"):
                note("l_to_2l_invention")
        # Excel never in this dataset by construction; only count if reviewer notes it
        if "excel" in str(hr.get("notes") or "").lower() and reason == "unsafe_completion":
            note("excel_driven_completion")
    return findings


def compute_a7_metrics(doc: Dict[str, Any]) -> Dict[str, Any]:
    links = doc.get("links") or []
    reviewed = [r for r in links if a7_is_reviewed(r)]
    n_rev = len(reviewed)
    correct = sum(1 for r in reviewed if (r.get("human_review") or {}).get("verdict") == "CORRECT")
    wrong = sum(1 for r in reviewed if (r.get("human_review") or {}).get("verdict") == "WRONG")
    ambiguous = sum(1 for r in reviewed if (r.get("human_review") or {}).get("verdict") == "AMBIGUOUS")
    denom = correct + wrong
    precision = _rate(correct, denom)

    by_method: Dict[str, Any] = {}
    for method in ("leader_tip_to_stroke", "proximity_stroke", "ambiguous_members"):
        pool = [r for r in reviewed if r.get("association_method") == method]
        c = sum(1 for r in pool if (r.get("human_review") or {}).get("verdict") == "CORRECT")
        w = sum(1 for r in pool if (r.get("human_review") or {}).get("verdict") == "WRONG")
        a = sum(1 for r in pool if (r.get("human_review") or {}).get("verdict") == "AMBIGUOUS")
        by_method[method] = {
            "n_reviewed": len(pool),
            "correct": c,
            "wrong": w,
            "ambiguous": a,
            "precision_excluding_ambiguous": _rate(c, c + w),
        }

    return {
        "total": 100,
        "reviewed": n_rev,
        "remaining": 100 - n_rev,
        "coverage": _rate(n_rev, 100),
        "correct": correct if n_rev else _na(),
        "wrong": wrong if n_rev else _na(),
        "ambiguous": ambiguous if n_rev else _na(),
        "correct_rate": _rate(correct, n_rev),
        "wrong_rate": _rate(wrong, n_rev),
        "ambiguous_rate": _rate(ambiguous, n_rev),
        "precision_excluding_ambiguous": precision,
        "wrong_association_rate": _rate(wrong, n_rev),
        "by_method": by_method,
        "note": (
            "Human review is ready; accuracy/precision is not yet measured."
            if n_rev == 0
            else "Metrics use reviewed denominator only; precision excludes AMBIGUOUS."
        ),
    }


def render_combined_report(a2_metrics: Dict[str, Any], a7_metrics: Dict[str, Any]) -> str:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.4f}"
        return str(v)

    lines = [
        "# Human Review — A2 + A7",
        "",
        f"_Generated: {datetime.now(timezone.utc).isoformat()}_",
        "",
        "## A2 — Extraction / Grouping / Semantic Review",
        "",
        f"- source dataset: `{A2_REVIEW.relative_to(BACKEND_DIR)}`",
        f"- total rows = {a2_metrics['total']}",
        f"- reviewed = {a2_metrics['reviewed']}",
        f"- remaining = {a2_metrics['remaining']}",
        f"- coverage = {fmt(a2_metrics['coverage'])}",
        f"- extraction = {a2_metrics['extraction']}",
        f"- grouping = {a2_metrics['grouping']}",
        f"- operation = {a2_metrics['operation']}",
        f"- normalization = {a2_metrics['normalization']}",
        f"- abstention = {a2_metrics['abstention']}",
        f"- safety = {a2_metrics['safety']}",
        f"- note: {a2_metrics['note']}",
        "",
        "## A7 — Geometry Association Review",
        "",
        f"- source dataset: `{A7_REVIEW.relative_to(BACKEND_DIR)}`",
        f"- total links = {a7_metrics['total']}",
        f"- reviewed = {a7_metrics['reviewed']}",
        f"- remaining = {a7_metrics['remaining']}",
        f"- correct = {fmt(a7_metrics['correct'])}",
        f"- wrong = {fmt(a7_metrics['wrong'])}",
        f"- ambiguous = {fmt(a7_metrics['ambiguous'])}",
        f"- overall CORRECT/reviewed = {fmt(a7_metrics['correct_rate'])}",
        f"- precision excluding ambiguous = {fmt(a7_metrics['precision_excluding_ambiguous'])}",
        f"- breakdown by method = {a7_metrics['by_method']}",
        f"- note: {a7_metrics['note']}",
        "",
        "## Observed Failure Modes",
        "",
        (
            "None observed yet — no human judgments entered."
            if a2_metrics["reviewed"] == 0 and a7_metrics["reviewed"] == 0
            else "See reason_code tallies in finalize JSON outputs for modes actually marked by reviewers."
        ),
        "",
        "## Safety Findings",
        "",
        "From human-reviewed A2 rows only:",
        f"- unsafe L thickness completion: {a2_metrics['safety'].get('l4x4_thickness_invention')} (L4X4), "
        f"{a2_metrics['safety'].get('l5x3_thickness_invention')} (L5X3)",
        f"- L -> 2L invention: {a2_metrics['safety'].get('l_to_2l_invention')}",
        f"- catalog-only completion: {a2_metrics['safety'].get('catalog_only_completion')}",
        f"- Excel-as-predictor: {a2_metrics['safety'].get('excel_driven_completion')}",
        "- geometry treated as takeoff truth: not scored here (A7 judges association only)",
        "",
        "## Recommended Next Step",
        "",
        "Next implementation target should be selected from the measured highest-impact "
        "failure mode after human review.",
        "",
    ]
    return "\n".join(lines)
