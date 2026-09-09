"""Conservative PDF-only structural-member quantity estimates.

This first QuantityEngine deliberately counts only eligible, labeled section
predictions. Geometry and graph evidence may describe a candidate, but never
creates quantity. The result is therefore a labeled-callout estimate, not a
claim of true field quantity.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from services.database_loader import catalog_form
from services.engineering.context_scope import partition_takeoff
from services.engineering.repeated_detail_linker import is_repeated_detail_member
from services.prediction.contract import confidence_overall

LABELED_PREDICTION_SOURCES = frozenset({"FUSION", "CORRECTION", "ANNOTATION"})

METHOD_LABELED_CALLOUT = "labeled_callout"
METHOD_SCHEDULE_CELL = "schedule_cell"
METHOD_ELEVATION_CALLOUT = "elevation_callout"
METHOD_INSUFFICIENT = "insufficient"

# Explicit framing-plan multipliers only. Bare TYP/SIM stays quantity 1.
_EXPLICIT_TYP_MULTIPLIER_RE = re.compile(
    r"\b(?:TYP|SIM)(?:ICAL)?\.?\s*[x×]\s*(\d{1,2})\b",
    re.I,
)
_TYP_MULTIPLIER_CAP = 20


@dataclass
class QuantityResult:
    section: str
    physical_quantity: int
    method: str
    confidence: float
    supporting_candidate_ids: List[str] = field(default_factory=list)
    excluded_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuantityReport:
    schema_version: str = "1.0"
    quantity_definition: str = "eligible_labeled_candidate_count"
    is_true_physical_quantity: bool = False
    results: List[QuantityResult] = field(default_factory=list)
    excluded_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [result.to_dict() for result in self.results]
        return payload


def normalized_section(prediction: Dict[str, Any]) -> str:
    """Return an exact catalog section, without correcting to a near shape."""

    raw = str(prediction.get("section") or "").strip()
    return str(catalog_form(raw) or "")


def _page_number(prediction: Dict[str, Any]) -> int:
    source_text = prediction.get("source_text")
    candidate = (
        source_text.get("page_number")
        if isinstance(source_text, dict)
        else None
    )
    if candidate is None:
        candidate = prediction.get("page_number") or prediction.get("page")
    try:
        return int(candidate or 0)
    except (TypeError, ValueError):
        return 0


def _candidate_id(prediction: Dict[str, Any]) -> Optional[str]:
    candidate = prediction.get("object_id") or prediction.get("component_id")
    return str(candidate) if candidate else None


def _is_geometry_inference(prediction: Dict[str, Any]) -> bool:
    return (
        str(prediction.get("prediction_source") or "").upper() == "GEOMETRY"
        or bool(prediction.get("missing_label_prediction"))
        or bool(prediction.get("missing_label"))
    )


def _is_labeled_candidate(prediction: Dict[str, Any]) -> bool:
    source = str(prediction.get("prediction_source") or "").upper()
    return (
        prediction.get("takeoff_eligible") is True
        and source in LABELED_PREDICTION_SOURCES
        and not is_repeated_detail_member(prediction)
        and not _is_geometry_inference(prediction)
    )


def _note_blob(prediction: Dict[str, Any]) -> str:
    source_text = prediction.get("source_text") or {}
    context = prediction.get("context") or {}
    parts = [
        prediction.get("original_token"),
        prediction.get("raw_text"),
        prediction.get("quantity_note"),
        prediction.get("typical_note"),
        source_text.get("raw") if isinstance(source_text, dict) else None,
        context.get("line_text") if isinstance(context, dict) else None,
        (
            " ".join(str(item) for item in context.get("neighbor_text") or [])
            if isinstance(context, dict)
            else None
        ),
    ]
    return " ".join(str(part) for part in parts if part)


def _explicit_typ_multiplier(prediction: Dict[str, Any], method: str) -> int:
    """Apply TYP x N / SIM x N only to already eligible labeled callouts."""

    if method != METHOD_LABELED_CALLOUT:
        return 1
    match = _EXPLICIT_TYP_MULTIPLIER_RE.search(_note_blob(prediction))
    if not match:
        return 1
    try:
        value = int(match.group(1))
    except (TypeError, ValueError):
        return 1
    if value < 2 or value > _TYP_MULTIPLIER_CAP:
        return 1
    return value


def _explicit_method(prediction: Dict[str, Any]) -> str:
    """Use existing metadata only; this is not a new sheet classifier."""

    source_text = prediction.get("source_text") or {}
    extraction_method = str(
        prediction.get("extraction_method")
        or (source_text.get("extraction_method") if isinstance(source_text, dict) else "")
        or ""
    ).lower()
    object_type = str(prediction.get("engineering_object_type") or "").lower()
    if (
        object_type == "schedule_member"
        or prediction.get("schedule_id")
        or extraction_method
        in {"schedule", "schedule_ingestion", "schedule_on_drawing"}
    ):
        return METHOD_SCHEDULE_CELL

    explicit_role = str(
        prediction.get("sheet_role")
        or prediction.get("page_role")
        or prediction.get("drawing_role")
        or ""
    ).upper()
    if "ELEVATION" in explicit_role:
        return METHOD_ELEVATION_CALLOUT
    return METHOD_LABELED_CALLOUT


def _aggregate_method(methods: Iterable[str]) -> str:
    unique = set(methods)
    if unique == {METHOD_SCHEDULE_CELL}:
        return METHOD_SCHEDULE_CELL
    if unique == {METHOD_ELEVATION_CALLOUT}:
        return METHOD_ELEVATION_CALLOUT
    return METHOD_LABELED_CALLOUT


class QuantityEngine:
    """Count eligible labeled predictions without inferring missing members.

    Input is expected to be the pipeline's post-OCR-dedup prediction list.
    ``partition_takeoff`` is reused as a defensive boundary; page/detail
    classification remains owned by ``context_scope`` and is not repeated
    here.
    """

    def count(self, predictions: List[Dict[str, Any]]) -> QuantityReport:
        eligible, scope_excluded = partition_takeoff(predictions)
        excluded = {
            "scope_ineligible": len(scope_excluded),
            "geometry_inference": 0,
            "excluded_geometry_duplicates": 0,
            "excluded_schedule_duplicates": 0,
            "invalid_or_missing_section": 0,
            "unlabeled_source": 0,
        }

        labeled_keys = {
            (_page_number(prediction), normalized_section(prediction))
            for prediction in eligible
            if _is_labeled_candidate(prediction)
            and normalized_section(prediction)
        }
        callout_keys = {
            (_page_number(prediction), normalized_section(prediction))
            for prediction in eligible
            if _is_labeled_candidate(prediction)
            and normalized_section(prediction)
            and _explicit_method(prediction) != METHOD_SCHEDULE_CELL
        }

        grouped: Dict[str, Dict[str, Any]] = {}
        per_section_excluded: Dict[str, Dict[str, int]] = {}
        for prediction in eligible:
            section = normalized_section(prediction)
            if not section:
                excluded["invalid_or_missing_section"] += 1
                continue

            if _is_geometry_inference(prediction):
                section_excluded = per_section_excluded.setdefault(section, {})
                key = (_page_number(prediction), section)
                if key in labeled_keys:
                    name = "excluded_geometry_duplicates"
                else:
                    name = "geometry_inference"
                excluded[name] += 1
                section_excluded[name] = section_excluded.get(name, 0) + 1
                continue

            if not _is_labeled_candidate(prediction):
                excluded["unlabeled_source"] += 1
                section_excluded = per_section_excluded.setdefault(section, {})
                section_excluded["unlabeled_source"] = (
                    section_excluded.get("unlabeled_source", 0) + 1
                )
                continue

            method = _explicit_method(prediction)
            key = (_page_number(prediction), section)
            if method == METHOD_SCHEDULE_CELL and key in callout_keys:
                name = "excluded_schedule_duplicates"
                excluded[name] += 1
                section_excluded = per_section_excluded.setdefault(section, {})
                section_excluded[name] = section_excluded.get(name, 0) + 1
                continue

            bucket = grouped.setdefault(
                section,
                {
                    "ids": [],
                    "confidences": [],
                    "methods": [],
                    "quantity": 0,
                },
            )
            candidate_id = _candidate_id(prediction)
            if candidate_id:
                bucket["ids"].append(candidate_id)
            bucket["confidences"].append(
                confidence_overall(prediction.get("confidence"))
            )
            bucket["methods"].append(method)
            bucket["quantity"] += _explicit_typ_multiplier(prediction, method)

        results: List[QuantityResult] = []
        all_sections = set(grouped) | set(per_section_excluded)
        for section in sorted(all_sections):
            bucket = grouped.get(section)
            section_excluded = per_section_excluded.get(section, {})
            if not bucket:
                results.append(
                    QuantityResult(
                        section=section,
                        physical_quantity=0,
                        method=METHOD_INSUFFICIENT,
                        confidence=0.0,
                        excluded_counts=dict(section_excluded),
                    )
                )
                continue

            confidences = bucket["confidences"]
            results.append(
                QuantityResult(
                    section=section,
                    physical_quantity=bucket["quantity"],
                    method=_aggregate_method(bucket["methods"]),
                    confidence=round(
                        sum(confidences) / max(len(confidences), 1), 4
                    ),
                    supporting_candidate_ids=list(dict.fromkeys(bucket["ids"])),
                    excluded_counts=dict(section_excluded),
                )
            )

        if excluded["invalid_or_missing_section"]:
            results.append(
                QuantityResult(
                    section="",
                    physical_quantity=0,
                    method=METHOD_INSUFFICIENT,
                    confidence=0.0,
                    excluded_counts={
                        "invalid_or_missing_section": excluded[
                            "invalid_or_missing_section"
                        ]
                    },
                )
            )

        return QuantityReport(results=results, excluded_counts=excluded)


quantity_engine = QuantityEngine()
