"""Build the canonical, human-readable prediction explanation contract."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _finding_to_dict(finding: Any) -> Dict[str, Any]:
    if isinstance(finding, dict):
        return dict(finding)
    if hasattr(finding, "to_dict"):
        return dict(finding.to_dict())
    return {
        "rule_id": getattr(finding, "rule_id", None),
        "message": getattr(finding, "message", str(finding)),
        "severity": getattr(finding, "severity", None),
    }


def _candidate_explanations(
    section: str,
    candidate_scores: Optional[List[Dict[str, Any]]],
) -> tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    candidates = [dict(item) for item in (candidate_scores or []) if item.get("shape")]
    if not candidates:
        return [], ["Selected as the highest-scoring AI prediction."], []

    selected = next(
        (item for item in candidates if str(item.get("shape")) == str(section)),
        candidates[0],
    )
    selected_score = float(selected.get("score") or 0.0)
    runner_up_score = max(
        (
            float(item.get("score") or 0.0)
            for item in candidates
            if str(item.get("shape")) != str(section)
        ),
        default=0.0,
    )
    modality_scores = selected.get("modality_scores") or {}
    strongest = sorted(
        modality_scores.items(), key=lambda item: float(item[1]), reverse=True
    )[:2]
    why_selected = [
        f"Highest fused candidate score ({selected_score:.1%}).",
        f"Selection margin over runner-up: {max(0.0, selected_score - runner_up_score):.1%}.",
    ]
    if strongest:
        why_selected.append(
            "Strongest supporting modalities: "
            + ", ".join(f"{name} {float(score):.1%}" for name, score in strongest)
            + "."
        )

    rejected: List[Dict[str, Any]] = []
    for item in candidates:
        shape = str(item.get("shape") or "")
        if shape == str(section):
            continue
        score = float(item.get("score") or 0.0)
        scores = item.get("modality_scores") or {}
        weakest = min(scores.items(), key=lambda pair: float(pair[1])) if scores else None
        reasons = [
            f"Fused score {score:.1%} was below selected candidate {selected_score:.1%}.",
            f"Score deficit: {max(0.0, selected_score - score):.1%}.",
        ]
        if weakest:
            reasons.append(
                f"Weakest modality was {weakest[0]} at {float(weakest[1]):.1%}."
            )
        rejected.append(
            {
                "section": shape,
                "score": round(score, 4),
                "reasons": reasons,
                "modality_scores": scores,
            }
        )
    return candidates, why_selected, rejected


def build_explanation(
    *,
    family: Optional[str],
    section: str,
    ai_reasons: List[str],
    signals: Dict[str, float],
    available: Dict[str, bool],
    ai_probability: float,
    regex_contribution: float,
    database_verified: bool,
    rule_findings: Optional[List[Any]] = None,
    candidate_scores: Optional[List[Dict[str, Any]]] = None,
    text_evidence: Optional[Dict[str, Any]] = None,
    geometry_evidence: Optional[Dict[str, Any]] = None,
    graph_evidence: Optional[Dict[str, Any]] = None,
    engineering_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reasons: List[str] = list(ai_reasons or [])
    reasons.append(
        f"Text evidence {float(signals.get('text') or 0):.0%} "
        f"(AI probability {float(ai_probability):.0%})"
    )
    reasons.append(
        f"OCR evidence {float(signals.get('ocr') or 0):.0%}"
    )
    reasons.append(
        f"Layout evidence {float(signals.get('layout') or 0):.0%}"
    )
    if available.get("geometry"):
        reasons.append(f"Geometry evidence {float(signals.get('geometry') or 0):.0%}")
    else:
        reasons.append("Geometry modality unavailable")
    reasons.append(f"Graph evidence {float(signals.get('graph') or 0):.0%}")
    reasons.append(
        f"Engineering rules {float(signals.get('engineering_rules') or 0):.0%}"
    )
    reasons.append(
        "Database verified AI prediction"
        if database_verified
        else "Database did not verify prediction (reference only)"
    )
    findings = [_finding_to_dict(finding) for finding in (rule_findings or [])]
    for finding in findings[:3]:
        rule_id = finding.get("rule_id")
        message = finding.get("message")
        if rule_id:
            reasons.append(f"Rule {rule_id}: {message}")

    top_candidates, why_selected, why_rejected = _candidate_explanations(
        section, candidate_scores
    )
    summary = (
        f"AI predicted family={family or '—'} section={section} "
        f"(database {'confirmed' if database_verified else 'unverified'})"
    )
    modality_evidence = {
        "text": {
            "available": bool(available.get("text")),
            "score": round(float(signals.get("text") or 0.0), 4),
            "summary": (
                f"Text model supports {section} with AI probability "
                f"{float(ai_probability):.1%}."
            ),
            "details": dict(text_evidence or {}),
        },
        "ocr": {
            "available": bool(available.get("ocr")),
            "score": round(float(signals.get("ocr") or 0.0), 4),
            "summary": (
                "OCR confidence and correction stability are included in fusion."
            ),
            "details": {
                "extraction_confidence": (text_evidence or {}).get(
                    "extraction_confidence"
                ),
                "original_token": (text_evidence or {}).get("original_token"),
                "corrected_token": (text_evidence or {}).get("token"),
            },
        },
        "layout": {
            "available": bool(available.get("layout")),
            "score": round(float(signals.get("layout") or 0.0), 4),
            "summary": "Page position, reading order, and nearby labels inform member role.",
            "details": {
                "matched_neighbors": (text_evidence or {}).get(
                    "matched_neighbors"
                )
                or [],
            },
        },
        "geometry": {
            "available": bool(available.get("geometry")),
            "score": round(float(signals.get("geometry") or 0.0), 4),
            "summary": (
                f"Geometry {'supports' if available.get('geometry') else 'was unavailable for'} "
                f"the selected section."
            ),
            "details": dict(geometry_evidence or {}),
        },
        "graph": {
            "available": bool(available.get("graph")),
            "score": round(float(signals.get("graph") or 0.0), 4),
            "summary": (
                f"Structural graph {'supports' if available.get('graph') else 'was unavailable for'} "
                f"the selected section."
            ),
            "details": dict(graph_evidence or {}),
        },
        "engineering": {
            "available": bool(available.get("engineering_rules")),
            "score": round(float(signals.get("engineering_rules") or 0.0), 4),
            "summary": f"Engineering-rule compatibility is {float(signals.get('engineering_rules') or 0.0):.1%}.",
            "details": {
                **dict(engineering_evidence or {}),
                "findings": findings,
            },
        },
    }
    return {
        "schema_version": "2.0",
        "prediction": {"family": family, "section": section},
        "confidence": round(float(ai_probability), 4),
        "summary": summary,
        "reasons": reasons,
        "why_selected": why_selected,
        "why_rejected": why_rejected,
        "top_candidate_sections": top_candidates,
        "modality_evidence": modality_evidence,
        "text_evidence": modality_evidence["text"],
        "ocr_evidence": modality_evidence["ocr"],
        "layout_evidence": modality_evidence["layout"],
        "geometry_evidence": modality_evidence["geometry"],
        "graph_evidence": modality_evidence["graph"],
        "engineering_evidence": modality_evidence["engineering"],
        "text_similarity": round(float(signals.get("text") or 0.0), 4),
        "ocr_score": round(float(signals.get("ocr") or 0.0), 4),
        "layout_score": round(float(signals.get("layout") or 0.0), 4),
        "geometry_similarity": round(float(signals.get("geometry") or 0.0), 4),
        "graph_consistency": round(float(signals.get("graph") or 0.0), 4),
        "database_similarity": round(float(signals.get("database") or 0.0), 4),
        "ai_probability": round(float(ai_probability), 4),
        "fusion_score": round(float(ai_probability), 4),
        "matched_neighbors": (text_evidence or {}).get("matched_neighbors")
        or [],
        "regex_contribution": round(float(regex_contribution), 4),
        "matched_features": [
            name for name, is_available in available.items() if is_available
        ],
    }
