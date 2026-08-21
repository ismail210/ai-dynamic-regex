"""Multimodal takeoff validation — not database-existence checks.

Produces PASS / WARNING / FAIL issues across extraction, prediction,
geometry, graph, engineering rules, quantities, and labels. The same
catalog-valid section repeating across independent members is normal
structural-drawing data, not an issue, and is never flagged on its own.
Database agreement is reported as evidence only and never alone decides FAIL.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional


ISSUE_TYPES = (
    "extraction_quality",
    "prediction_confidence",
    "geometry_consistency",
    "graph_consistency",
    "engineering_rules",
    "missing_members",
    "impossible_members",
    "wrong_section_names",
    "missing_quantities",
    "incorrect_quantities",
    "missing_dimensions",
    "unknown_labels",
)

SEVERITY_RANK = {"PASS": 0, "WARNING": 1, "FAIL": 2}


def _confidence_value(prediction: dict) -> float:
    conf = prediction.get("confidence")
    if isinstance(conf, dict):
        return float(conf.get("overall") or conf.get("score") or 0.0)
    return float(conf or 0.0)


def _norm(value: Any) -> str:
    return str(value or "").upper().replace(" ", "").replace("×", "X")


def _section(prediction: dict) -> str:
    return _norm(
        prediction.get("section")
        or prediction.get("predicted_shape")
        or prediction.get("prediction")
        or prediction.get("corrected_token")
        or ""
    )


def _family(prediction: dict) -> str:
    family = prediction.get("family")
    if family:
        return str(family).strip().upper()
    section = _section(prediction)
    for prefix in ("PIPE", "HSS", "MC", "WT", "HP", "MT", "ST", "2L", "W", "S", "M", "C", "L"):
        if section.startswith(prefix):
            return prefix
    return ""


def _features(prediction: dict) -> dict:
    return prediction.get("features") or {}


def _fusion_issues(prediction: dict) -> set:
    return set(
        (_features(prediction).get("fusion") or {}).get("detected_issues") or []
    )


def _annotation_record(prediction: dict) -> dict:
    return (
        (prediction.get("annotation_interpretation") or {}).get("annotation")
        or (
            (prediction.get("explanation") or {})
            .get("annotation_interpretation", {})
            .get("annotation")
        )
        or {}
    )


def _is_confirmed_plate_annotation(prediction: dict) -> bool:
    comparison = prediction.get("comparison") or {}
    if comparison.get("match_status") == "confirmed_annotation":
        return True
    canonical_prediction = (prediction.get("canonical") or {}).get("prediction") or {}
    if (
        canonical_prediction.get("section_applicable") is False
        and str(canonical_prediction.get("annotation_type") or "").upper()
        in {"PLATE", "BENT_PLATE"}
    ):
        return True
    if not prediction.get("section_prediction_not_applicable"):
        return False
    annotation = _annotation_record(prediction)
    annotation_type = str(annotation.get("annotation_type") or "").upper()
    if annotation_type not in {"PLATE", "BENT_PLATE"}:
        return False
    return bool(annotation.get("structure_confirmed"))


def _confirmed_plate_label(prediction: dict) -> str:
    canonical_prediction = (prediction.get("canonical") or {}).get("prediction") or {}
    label = canonical_prediction.get("annotation_label")
    if label:
        return str(label)
    annotation = _annotation_record(prediction)
    thickness = annotation.get("thickness")
    annotation_type = str(
        annotation.get("annotation_type")
        or prediction.get("plate_annotation_type")
        or ""
    ).upper()
    if thickness:
        suffix = "BENT PL" if annotation_type == "BENT_PLATE" else "PL"
        thick_display = (
            str(thickness) if '"' in str(thickness) else f'{thickness}"'
        )
        return f"{thick_display} {suffix}".strip()
    return (
        prediction.get("raw_text")
        or prediction.get("original_token")
        or annotation_type.replace("_", " ").title()
        or "Plate"
    )


def _compact_correction(correction: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the decision, not the full candidate search that produced it.

    An issue is emitted per token per check, so embedding every correction
    candidate here multiplied the validation payload by an order of magnitude.
    """

    if not correction:
        return {}
    return {
        "original": correction.get("original"),
        "corrected": correction.get("corrected"),
        "confidence": correction.get("confidence"),
        "reason": correction.get("reason"),
        "source": correction.get("source"),
    }


def _compact_alternatives(alternatives: Any) -> List[Dict[str, Any]]:
    return [
        {
            "shape": item.get("shape") or item.get("corrected"),
            "confidence": item.get("confidence"),
        }
        for item in (alternatives or [])[:3]
        if isinstance(item, dict)
    ]


def _compact_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
    """A per-token view of an issue; the full record stays in the issue list."""

    return {
        "issue_id": issue.get("issue_id"),
        "type": issue.get("type"),
        "severity": issue.get("severity"),
        "why": issue.get("why"),
        "suggested_correction": issue.get("suggested_correction"),
        "approvable": issue.get("approvable"),
    }


def _evidence_map(prediction: dict) -> Dict[str, Any]:
    evidence = prediction.get("evidence") or {}
    explanation = prediction.get("explanation") or {}
    text = _features(prediction).get("text") or {}
    geometry = _features(prediction).get("geometry") or {}
    graph = _features(prediction).get("graph") or {}
    rules = _features(prediction).get("engineering_rules") or {}
    return {
        "contributions": evidence,
        "contribution_percentages": explanation.get("contribution_percentages") or {},
        "text_similarity": explanation.get("text_similarity"),
        "geometry_similarity": explanation.get("geometry_similarity"),
        "graph_consistency": explanation.get("graph_consistency"),
        "extraction_status": text.get("extraction_status") or text.get("status"),
        "extraction_confidence": text.get("extraction_confidence"),
        "extraction_diagnostics": text.get("extraction_diagnostics") or {},
        "geometry_available": bool(geometry.get("available")),
        "geometry_preview": prediction.get("geometry_preview"),
        "graph_preview": prediction.get("graph_preview"),
        "graph_degree": graph.get("degree"),
        "engineering_rules": rules,
        "database_match": bool(prediction.get("database_match")),
        "database_role": "verification_only",
        "family": prediction.get("family"),
        "section": _section(prediction),
        "alternatives": _compact_alternatives(prediction.get("alternatives")),
        "correction": _compact_correction(
            prediction.get("correction") or explanation.get("correction") or {}
        ),
    }


def _suggested_from_prediction(prediction: dict) -> Optional[Dict[str, Any]]:
    correction = (
        prediction.get("correction")
        or (prediction.get("explanation") or {}).get("correction")
        or {}
    )
    if correction.get("corrected"):
        return {
            "section": correction.get("corrected"),
            "confidence": correction.get("confidence"),
            "reason": correction.get("reason"),
            "source": "ai_correction_engine",
        }
    alternatives = prediction.get("alternatives") or []
    if alternatives:
        top = alternatives[0]
        return {
            "section": top.get("shape") or top.get("corrected"),
            "confidence": top.get("confidence"),
            "reason": "Top multimodal alternative",
            "source": "alternative_candidates",
        }
    return None


def _issue(
    *,
    issue_type: str,
    severity: str,
    why: str,
    evidence: Dict[str, Any],
    suggested_correction: Optional[Dict[str, Any]] = None,
    component_id: Optional[str] = None,
    object_id: Optional[str] = None,
    original_token: Optional[str] = None,
    predicted_shape: Optional[str] = None,
    approvable: bool = False,
) -> Dict[str, Any]:
    return {
        "issue_id": f"{issue_type}:{component_id or object_id or predicted_shape or 'doc'}",
        "type": issue_type,
        "severity": severity,
        "status": severity,
        "why": why,
        "evidence": evidence,
        "suggested_correction": suggested_correction,
        "approvable": bool(approvable and suggested_correction),
        "component_id": component_id,
        "object_id": object_id,
        "original_token": original_token,
        "predicted_shape": predicted_shape,
        "database_decides": False,
    }


def _worst(statuses: List[str]) -> str:
    if not statuses:
        return "PASS"
    return max(statuses, key=lambda item: SEVERITY_RANK.get(item, 0))


def _token_issues(prediction: dict) -> List[dict]:
    issues: List[dict] = []
    confirmed_plate = _is_confirmed_plate_annotation(prediction)
    plate_label = _confirmed_plate_label(prediction) if confirmed_plate else ""
    section = _section(prediction)
    family = _family(prediction)
    confidence = _confidence_value(prediction)
    evidence = _evidence_map(prediction)
    fusion_issues = _fusion_issues(prediction)
    component_id = prediction.get("component_id") or prediction.get("object_id")
    object_id = prediction.get("object_id")
    original = prediction.get("original_token") or prediction.get("token")
    suggestion = _suggested_from_prediction(prediction)
    text = _features(prediction).get("text") or {}
    geometry = _features(prediction).get("geometry") or {}
    graph = _features(prediction).get("graph") or {}
    rules = _features(prediction).get("engineering_rules") or {}

    extraction_status = str(
        text.get("extraction_status") or text.get("status") or ""
    ).upper()
    extraction_confidence = float(text.get("extraction_confidence") or 0.5)
    if extraction_status == "INVALID" or extraction_confidence < 0.35:
        issues.append(
            _issue(
                issue_type="extraction_quality",
                severity="FAIL",
                why=(
                    f"Extraction status {extraction_status or 'INVALID'} "
                    f"with confidence {extraction_confidence:.0%}"
                ),
                evidence={
                    **evidence,
                    "extraction_status": extraction_status,
                    "extraction_confidence": extraction_confidence,
                },
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )
    elif extraction_status in {"BROKEN", "SUSPICIOUS"} or extraction_confidence < 0.6:
        issues.append(
            _issue(
                issue_type="extraction_quality",
                severity="WARNING",
                why=(
                    f"Extraction quality is {extraction_status or 'degraded'} "
                    f"({extraction_confidence:.0%})"
                ),
                evidence={
                    **evidence,
                    "extraction_status": extraction_status,
                    "extraction_confidence": extraction_confidence,
                },
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )
    else:
        issues.append(
            _issue(
                issue_type="extraction_quality",
                severity="PASS",
                why="Extraction quality is acceptable for prediction",
                evidence={
                    "extraction_status": extraction_status or "VALID",
                    "extraction_confidence": extraction_confidence,
                },
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )

    if confirmed_plate:
        if confidence < 0.45:
            issues.append(
                _issue(
                    issue_type="prediction_confidence",
                    severity="WARNING",
                    why=(
                        f"Extraction confidence is moderate ({confidence:.0%}) "
                        f"for confirmed plate annotation {plate_label}"
                    ),
                    evidence={**evidence, "confidence": confidence},
                    suggested_correction=suggestion,
                    component_id=component_id,
                    object_id=object_id,
                    original_token=original,
                    predicted_shape=plate_label,
                    approvable=True,
                )
            )
        else:
            issues.append(
                _issue(
                    issue_type="prediction_confidence",
                    severity="PASS",
                    why=(
                        f"Confirmed plate annotation {plate_label}; "
                        "section prediction not applicable"
                    ),
                    evidence={"confidence": confidence, "annotation_label": plate_label},
                    component_id=component_id,
                    object_id=object_id,
                    original_token=original,
                    predicted_shape=plate_label,
                )
            )
    elif confidence < 0.45:
        issues.append(
            _issue(
                issue_type="prediction_confidence",
                severity="FAIL",
                why=f"Prediction confidence is critically low ({confidence:.0%})",
                evidence={**evidence, "confidence": confidence},
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )
    elif confidence < 0.7:
        issues.append(
            _issue(
                issue_type="prediction_confidence",
                severity="WARNING",
                why=f"Prediction confidence is moderate ({confidence:.0%})",
                evidence={**evidence, "confidence": confidence},
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )
    else:
        issues.append(
            _issue(
                issue_type="prediction_confidence",
                severity="PASS",
                why=f"Prediction confidence is acceptable ({confidence:.0%})",
                evidence={"confidence": confidence},
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )

    geometry_available = bool(geometry.get("available"))
    geometry_score = float(
        evidence.get("geometry_similarity")
        or (prediction.get("evidence") or {}).get("geometry")
        or geometry.get("similarity")
        or 0.0
    )
    if geometry_available and (
        geometry_score < 0.35 or "geometry_conflict" in fusion_issues
    ):
        geometry_why = (
            f"Geometry evidence is weak for plate annotation ({geometry_score:.0%})"
            if confirmed_plate
            else (
                f"Geometry evidence conflicts with the predicted section "
                f"({geometry_score:.0%})"
            )
        )
        issues.append(
            _issue(
                issue_type="geometry_consistency",
                severity="FAIL" if geometry_score < 0.2 else "WARNING",
                why=geometry_why,
                evidence={
                    **evidence,
                    "geometry_score": geometry_score,
                    "geometry_preview": prediction.get("geometry_preview"),
                },
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )
    elif geometry_available:
        geometry_pass_why = (
            "Geometry is consistent with the plate annotation"
            if confirmed_plate
            else "Geometry is consistent with the AI prediction"
        )
        issues.append(
            _issue(
                issue_type="geometry_consistency",
                severity="PASS",
                why=geometry_pass_why,
                evidence={"geometry_score": geometry_score},
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )
    else:
        issues.append(
            _issue(
                issue_type="geometry_consistency",
                severity="WARNING",
                why="No linked geometry object for consistency checks",
                evidence={"geometry_available": False},
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )

    degree = float(graph.get("degree") or 0.0)
    graph_score = float(
        evidence.get("graph_consistency")
        or (prediction.get("evidence") or {}).get("graph")
        or graph.get("graph_consistency")
        or 0.0
    )
    if degree > 0 and (graph_score < 0.35 or "graph_conflict" in fusion_issues):
        graph_why = (
            f"Structural graph neighborhood is weak for plate annotation "
            f"({graph_score:.0%}, degree {int(degree)})"
            if confirmed_plate
            else (
                f"Structural graph neighborhood is inconsistent "
                f"({graph_score:.0%}, degree {int(degree)})"
            )
        )
        issues.append(
            _issue(
                issue_type="graph_consistency",
                severity="FAIL" if graph_score < 0.2 else "WARNING",
                why=graph_why,
                evidence={
                    **evidence,
                    "graph_score": graph_score,
                    "degree": degree,
                },
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )
    elif degree > 0:
        graph_pass_why = (
            "Graph neighborhood supports the plate annotation"
            if confirmed_plate
            else "Graph neighborhood supports the AI prediction"
        )
        issues.append(
            _issue(
                issue_type="graph_consistency",
                severity="PASS",
                why=graph_pass_why,
                evidence={"graph_score": graph_score, "degree": degree},
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )
    else:
        issues.append(
            _issue(
                issue_type="graph_consistency",
                severity="WARNING",
                why="No structural graph links available for this member",
                evidence={"degree": 0},
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )

    rule_score = float(rules.get("score") or 0.5)
    findings = rules.get("findings") or []
    if rule_score < 0.45 or "engineering_rule_conflict" in fusion_issues:
        rules_why = (
            f"Engineering rules score is low for plate annotation "
            f"{plate_label or '—'} (score {rule_score:.0%})"
            if confirmed_plate
            else (
                f"Engineering rules disagree with section={section or '—'} "
                f"(score {rule_score:.0%})"
            )
        )
        issues.append(
            _issue(
                issue_type="engineering_rules",
                severity="FAIL" if rule_score < 0.3 else "WARNING",
                why=rules_why,
                evidence={
                    **evidence,
                    "rule_score": rule_score,
                    "findings": findings[:5],
                    "member_role": rules.get("member_role"),
                },
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )
    else:
        rules_pass_why = (
            "Engineering rules are consistent with the plate annotation"
            if confirmed_plate
            else "Engineering rules are consistent with the prediction"
        )
        issues.append(
            _issue(
                issue_type="engineering_rules",
                severity="PASS",
                why=rules_pass_why,
                evidence={
                    "rule_score": rule_score,
                    "member_role": rules.get("member_role"),
                },
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )

    # The same catalog-valid section legitimately labels many independent
    # members (e.g. every W16X26 beam on a floor) — occurrence count alone is
    # not evidence of a problem, so it is exposed only as data
    # (predicted_quantity, below) and never raised as a review issue here.

    # Impossible / wrong section names from multimodal signals — not DB miss.
    impossible = False
    impossible_why = ""
    if confirmed_plate:
        impossible = False
    elif not section:
        impossible = True
        impossible_why = "AI produced no section label"
    elif family and section and not section.startswith(family):
        impossible = True
        impossible_why = (
            f"Section {section} is incompatible with predicted family {family}"
        )
    elif "invalid_engineering_notation" in fusion_issues and confidence < 0.7:
        impossible = True
        impossible_why = f"Section notation {section} looks impossible under multimodal evidence"
    if impossible:
        issues.append(
            _issue(
                issue_type="impossible_members",
                severity="FAIL",
                why=impossible_why,
                evidence={**evidence, "family": family, "section": section},
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )

    original_norm = _norm(original)
    corrected_norm = _norm(prediction.get("corrected_token") or section)
    if (
        original_norm
        and corrected_norm
        and original_norm != corrected_norm
        and confidence >= 0.55
    ):
        issues.append(
            _issue(
                issue_type="wrong_section_names",
                severity="WARNING",
                why=(
                    f"Extracted label {original} differs from AI section "
                    f"{corrected_norm}"
                ),
                evidence={
                    **evidence,
                    "original": original,
                    "corrected": corrected_norm,
                },
                suggested_correction=suggestion
                or {
                    "section": corrected_norm,
                    "confidence": confidence,
                    "reason": "Use AI-corrected section name",
                    "source": "ai_prediction",
                },
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=True,
            )
        )

    preview = prediction.get("geometry_preview") or {}
    has_dimension = bool(
        preview.get("length")
        or preview.get("dimension")
        or (geometry.get("object") or {}).get("length")
    )
    if geometry_available and not has_dimension:
        issues.append(
            _issue(
                issue_type="missing_dimensions",
                severity="WARNING",
                why="Linked geometry has no usable length/dimension measurement",
                evidence={
                    "geometry_preview": preview,
                    "geometry_object": geometry.get("object"),
                },
                suggested_correction={
                    "action": "attach_dimension",
                    "reason": "Link a dimension or measured length to this member",
                    "source": "geometry_encoder",
                },
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )

    # Unknown labels are AI-uncertainty issues — never "not in database".
    if confirmed_plate:
        issues.append(
            _issue(
                issue_type="unknown_labels",
                severity="PASS",
                why=(
                    f"Annotation type confirmed ({plate_label}); "
                    "no AISC section required"
                ),
                evidence={
                    "annotation_label": plate_label,
                    "section_applicable": False,
                },
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=plate_label,
            )
        )
    elif confidence < 0.55 and not suggestion:
        issues.append(
            _issue(
                issue_type="unknown_labels",
                severity="FAIL",
                why="Label remains unknown after multimodal prediction",
                evidence={**evidence, "confidence": confidence},
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
            )
        )
    elif confidence < 0.7 and (
        "database_unverified" in fusion_issues or not prediction.get("database_match")
    ):
        # Soft note only: DB miss alone never fails.
        issues.append(
            _issue(
                issue_type="unknown_labels",
                severity="WARNING",
                why=(
                    "AI label is uncertain; AISC catalog did not verify "
                    "(reference only — not a fail condition)"
                ),
                evidence={
                    "confidence": confidence,
                    "database_match": bool(prediction.get("database_match")),
                    "database_role": "verification_only",
                },
                suggested_correction=suggestion,
                component_id=component_id,
                object_id=object_id,
                original_token=original,
                predicted_shape=section,
                approvable=bool(suggestion),
            )
        )

    return issues


def _quantity_issues(
    *,
    expected_counts: Counter,
    predicted_counts: Counter,
) -> List[dict]:
    issues: List[dict] = []
    if not expected_counts:
        return issues

    for label, expected in expected_counts.items():
        predicted = int(predicted_counts.get(label, 0))
        if predicted == 0:
            issues.append(
                _issue(
                    issue_type="missing_members",
                    severity="FAIL",
                    why=f"Expected member {label} is missing from AI predictions",
                    evidence={
                        "expected_quantity": expected,
                        "predicted_quantity": 0,
                        "label": label,
                    },
                    suggested_correction={
                        "section": label,
                        "action": "add_member",
                        "reason": f"Add missing member {label} x{expected}",
                        "source": "takeoff_ground_truth",
                    },
                    predicted_shape=label,
                    approvable=True,
                )
            )
            issues.append(
                _issue(
                    issue_type="missing_quantities",
                    severity="FAIL",
                    why=f"Quantity for {label} is missing (expected {expected})",
                    evidence={
                        "expected_quantity": expected,
                        "predicted_quantity": 0,
                        "label": label,
                    },
                    suggested_correction={
                        "section": label,
                        "quantity": expected,
                        "action": "set_quantity",
                        "source": "takeoff_ground_truth",
                    },
                    predicted_shape=label,
                    approvable=True,
                )
            )
        elif predicted != expected:
            issues.append(
                _issue(
                    issue_type="incorrect_quantities",
                    severity="WARNING" if abs(predicted - expected) == 1 else "FAIL",
                    why=(
                        f"Quantity mismatch for {label}: predicted {predicted}, "
                        f"expected {expected}"
                    ),
                    evidence={
                        "expected_quantity": expected,
                        "predicted_quantity": predicted,
                        "difference": predicted - expected,
                        "label": label,
                    },
                    suggested_correction={
                        "section": label,
                        "quantity": expected,
                        "action": "set_quantity",
                        "reason": f"Correct quantity of {label} to {expected}",
                        "source": "takeoff_ground_truth",
                    },
                    predicted_shape=label,
                    approvable=True,
                )
            )
        else:
            issues.append(
                _issue(
                    issue_type="incorrect_quantities",
                    severity="PASS",
                    why=f"Quantity for {label} matches ground truth ({expected})",
                    evidence={
                        "expected_quantity": expected,
                        "predicted_quantity": predicted,
                        "label": label,
                    },
                    predicted_shape=label,
                )
            )

    for label, predicted in predicted_counts.items():
        if label and label not in expected_counts:
            issues.append(
                _issue(
                    issue_type="unknown_labels",
                    severity="WARNING",
                    why=(
                        f"AI predicted {label} x{predicted} is not present in "
                        "ground-truth takeoff (Excel is reference, not authority)"
                    ),
                    evidence={
                        "predicted_quantity": predicted,
                        "label": label,
                        "ground_truth_role": "optional_reference",
                    },
                    suggested_correction={
                        "section": label,
                        "action": "confirm_extra_member",
                        "reason": f"Confirm whether {label} should remain",
                        "source": "ai_prediction",
                    },
                    predicted_shape=label,
                    approvable=True,
                )
            )
    return issues


def validate_multimodal_predictions(
    predictions: List[dict],
    *,
    expected_excel: Optional[dict] = None,
    extraction: Optional[dict] = None,
) -> Dict[str, Any]:
    """Validate multimodal predictions into structured engineer-facing issues."""

    expected_counts: Counter = Counter()
    if expected_excel:
        for item in (
            expected_excel.get("aggregates")
            or expected_excel.get("items")
            or []
        ):
            label = _norm(
                item.get("canonical_label")
                or item.get("shape")
                or item.get("mark")
                or ""
            )
            if label:
                expected_counts[label] += int(
                    item.get("quantity") or item.get("count") or 1
                )

    predicted_counts = Counter(
        _section(prediction)
        for prediction in predictions
        if _section(prediction)
    )

    all_issues: List[dict] = []
    tokens: List[dict] = []

    # Document-level extraction quality.
    quality = (extraction or {}).get("quality") or (extraction or {}).get(
        "diagnostics"
    ) or {}
    if quality:
        score = float(quality.get("score") or quality.get("average_token_confidence") or 0)
        status = str(quality.get("status") or "").upper()
        if status == "INVALID" or score < 0.35:
            severity = "FAIL"
            why = f"Document extraction quality is invalid ({score:.0%})"
        elif status in {"BROKEN", "SUSPICIOUS"} or score < 0.65:
            severity = "WARNING"
            why = f"Document extraction quality needs review ({status or 'degraded'}, {score:.0%})"
        else:
            severity = "PASS"
            why = f"Document extraction quality is acceptable ({score:.0%})"
        all_issues.append(
            _issue(
                issue_type="extraction_quality",
                severity=severity,
                why=why,
                evidence={"document_quality": quality},
            )
        )

    dimensions = (extraction or {}).get("dimensions") or []
    if extraction is not None and not dimensions and predictions:
        all_issues.append(
            _issue(
                issue_type="missing_dimensions",
                severity="WARNING",
                why="No dimension annotations were extracted from the drawing",
                evidence={"dimension_count": 0},
                suggested_correction={
                    "action": "reextract_dimensions",
                    "reason": "Re-run extraction focusing on dimension callouts",
                    "source": "extraction_engine",
                },
            )
        )

    for prediction in predictions:
        token_issue_list = _token_issues(prediction)
        all_issues.extend(token_issue_list)
        actionable = [
            item
            for item in token_issue_list
            if item["severity"] in {"WARNING", "FAIL"}
        ]
        status = _worst([item["severity"] for item in actionable] or ["PASS"])
        suggestion = _suggested_from_prediction(prediction)
        text_features = _features(prediction).get("text") or {}
        evidence = prediction.get("evidence") or {}
        tokens.append(
            {
                "component_id": prediction.get("component_id")
                or prediction.get("object_id"),
                "object_id": prediction.get("object_id"),
                "original_token": prediction.get("original_token"),
                "corrected_token": prediction.get("corrected_token"),
                "family": prediction.get("family"),
                "section": _section(prediction),
                "detected": prediction.get("original_token"),
                "expected": (
                    _section(prediction)
                    if _section(prediction) in expected_counts
                    else None
                ),
                "predicted_shape": prediction.get("predicted_shape")
                or _section(prediction),
                "material": prediction.get("material"),
                "ocr_confidence": text_features.get("extraction_confidence"),
                "extraction_status": text_features.get("extraction_status"),
                "extraction_diagnostics": text_features.get(
                    "extraction_diagnostics"
                )
                or {},
                "context": text_features.get("context") or {},
                "surrounding_text": text_features.get("surrounding_text") or "",
                "entity_type": prediction.get("entity_type"),
                "status": status,
                "confidence": _confidence_value(prediction),
                "database_match": prediction.get("database_match"),
                "database_role": "verification_only",
                "geometry_agreement": evidence.get("geometry"),
                "graph_agreement": evidence.get("graph"),
                "engineering_rule_agreement": evidence.get("engineering_rules"),
                "database_agreement": evidence.get("database"),
                "text_agreement": evidence.get("text"),
                "detected_issues": sorted(
                    {
                        item["type"]
                        for item in actionable
                    }
                ),
                "issues": [_compact_issue(item) for item in actionable],
                "reasons": [
                    item["why"] for item in actionable
                ]
                or ["All multimodal checks passed"],
                "correction_suggestions": (
                    [suggestion]
                    if suggestion
                    else _compact_alternatives(prediction.get("alternatives"))
                ),
                "alternative_predictions": _compact_alternatives(
                    prediction.get("alternatives")
                ),
                "expected_quantity": expected_counts.get(_section(prediction))
                if expected_counts
                else None,
                "predicted_quantity": predicted_counts.get(_section(prediction)),
                "geometry_preview": prediction.get("geometry_preview"),
                "graph_preview": prediction.get("graph_preview"),
                "approvable": any(item.get("approvable") for item in actionable),
            }
        )

    all_issues.extend(
        _quantity_issues(
            expected_counts=expected_counts,
            predicted_counts=predicted_counts,
        )
    )

    actionable_issues = [
        item for item in all_issues if item["severity"] in {"WARNING", "FAIL"}
    ]
    pass_issues = [item for item in all_issues if item["severity"] == "PASS"]
    counts = Counter(item["severity"] for item in all_issues)
    type_counts = Counter(
        item["type"] for item in actionable_issues
    )
    token_counts = Counter(token["status"] for token in tokens)

    return {
        "summary": {
            "total": len(tokens),
            "pass": token_counts["PASS"],
            "warning": token_counts["WARNING"],
            "fail": token_counts["FAIL"],
            "pass_rate": round(token_counts["PASS"] / max(len(tokens), 1), 4),
            "issue_total": len(all_issues),
            "issue_pass": counts["PASS"],
            "issue_warning": counts["WARNING"],
            "issue_fail": counts["FAIL"],
            "issue_types": dict(type_counts),
            "approvable_issues": sum(
                1 for item in actionable_issues if item.get("approvable")
            ),
        },
        "tokens": tokens,
        # The full issue list is intentionally not returned: every entry also
        # appears in actionable_issues or passed_checks, and repeating it made
        # the validation payload three times larger than necessary.
        "actionable_issues": actionable_issues,
        "passed_checks": pass_issues,
        "expected_counts": dict(expected_counts),
        "predicted_counts": dict(predicted_counts),
        "policy": {
            "name": "multimodal_validation_v2",
            "database_alone_never_fails": True,
            "database_role": "verification_only",
            "validated_dimensions": list(ISSUE_TYPES),
            "severities": ["PASS", "WARNING", "FAIL"],
        },
    }
