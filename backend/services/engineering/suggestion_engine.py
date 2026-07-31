"""
AI Suggestion Engine (Classical ML)
===================================

Does NOT use an LLM.

AI-primary: predictions come from the shared prediction orchestrator.
The AISC database never selects the expected label — it only confirms.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from services.engineering.models import Suggestion


TOKEN_RE = re.compile(
    r"\b(W\d+X\d+|HSS\d+X\d+(?:X[\d/]+)?|L\d+X\d+(?:X[\d/]+)?|PIPE\d+|PL\d+|A\d+)\b",
    re.I,
)


def _infer_type_from_label(label: str) -> str:
    s = (label or "").upper()
    if s.startswith("W") or s.startswith("S") or s.startswith("M"):
        return "Beam"
    if s.startswith("HSS") or s.startswith("PIPE"):
        return "HSS/Pipe"
    if s.startswith("L"):
        return "Angle"
    if s.startswith("PL"):
        return "Plate"
    if s.startswith("A") and s[1:].isdigit():
        return "Bolt/Material"
    return "Unknown"


def _graph_features_for_node(node: dict, graph: dict) -> Dict[str, float]:
    node_id = node.get("node_id")
    distances = []
    has_geom = 0.0
    has_label = 0.0
    for edge in graph.get("edges") or []:
        if edge.get("source") != node_id and edge.get("target") != node_id:
            continue
        if edge.get("distance") is not None:
            distances.append(float(edge["distance"]))
        if edge.get("relationship") == "nearest_geometry":
            has_geom = 1.0
        if edge.get("relationship") == "nearest_label":
            has_label = 1.0
    return {
        "edge_count": float(len(distances)),
        "min_distance": min(distances) if distances else 999.0,
        "mean_distance": (sum(distances) / len(distances)) if distances else 999.0,
        "has_geometry_link": has_geom,
        "has_label_link": has_label,
    }


def suggest_for_text_node(
    node: dict,
    *,
    graph: dict,
    excel_json: Optional[dict] = None,
) -> Suggestion:
    text = str(node.get("text") or "").strip()
    token_match = TOKEN_RE.search(text)
    token = (
        token_match.group(0).upper().replace(" ", "")
        if token_match
        else text.upper().replace(" ", "")
    )

    features = _graph_features_for_node(node, graph)
    features["text_len"] = float(len(text))
    features["font_size"] = float(node.get("font_size") or 0.0)

    excel_counts = Counter()
    for item in (excel_json or {}).get("items") or []:
        shape = str(item.get("shape") or "").upper().replace(" ", "")
        if shape:
            excel_counts[shape] += int(item.get("count") or 1)

    prediction = None
    try:
        if token and len(token) >= 2:
            from services.prediction.orchestrator import predict_token

            prediction = predict_token(token, queue_unknown=False, persist_learning=False)
    except Exception:
        prediction = None

    if prediction is not None:
        expected_label = str(
            prediction.get("section") or prediction.get("prediction") or token
        ).upper().replace(" ", "")
        family = prediction.get("family")
        expected_type = (
            str(family)
            if family
            else _infer_type_from_label(expected_label)
        )
        conf = prediction.get("confidence") or {}
        confidence = float(
            conf.get("overall") if isinstance(conf, dict) else conf or 0.0
        )
        db_match = bool(prediction.get("database_match"))
        reason = (
            f"AI prediction section={expected_label} family={family or '—'}"
            + ("; AISC confirmed" if db_match else "; AISC unverified (reference only)")
        )
        # Excel may annotate uncertain AI results — never replace AI section from DB.
        if confidence < 0.55 and excel_counts:
            top_shape, top_count = excel_counts.most_common(1)[0]
            if family and top_shape.startswith(str(family)[:1]):
                reason += f"; Excel schedule prior noted ({top_shape} x{top_count})"
                confidence = min(0.7, confidence + 0.02 * min(top_count, 5))
    elif excel_counts:
        expected_label, top_count = excel_counts.most_common(1)[0]
        expected_type = _infer_type_from_label(expected_label)
        confidence = min(0.65, 0.35 + 0.02 * top_count)
        reason = "No AI hit; used dominant Excel schedule shape"
    else:
        expected_label = token or "UNKNOWN"
        expected_type = _infer_type_from_label(expected_label)
        confidence = 0.25
        reason = "Insufficient signals; returning raw extracted text"

    if features["has_geometry_link"] and features["min_distance"] < 80:
        confidence = min(1.0, confidence + 0.05)
        reason += "; nearby geometry support"
    elif features["min_distance"] > 200:
        confidence = max(0.1, confidence - 0.08)
        reason += "; label far from geometry"

    features["database_role"] = "verification_only"
    features["ai_first"] = True

    return Suggestion(
        object_id=str(node.get("source_id") or node.get("node_id")),
        expected_label=expected_label,
        expected_type=expected_type,
        confidence=float(confidence),
        reason=reason,
        features=features,
    )


def generate_suggestions(
    *,
    document_structure: dict,
    geometry: dict,
    graph: dict,
    excel_json: Optional[dict] = None,
    match_report: Optional[dict] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Produce classical-ML suggestions for labels and mismatch findings."""

    suggestions: List[dict] = []

    priority_ids = set()
    for finding in (match_report or {}).get("findings") or []:
        if finding.get("status") in {
            "missing_label",
            "wrong_label",
            "count_mismatch",
            "extra_label",
            "missing_geometry",
        }:
            for oid in finding.get("object_ids") or []:
                priority_ids.add(oid)

    label_nodes = [
        n
        for n in graph.get("nodes") or []
        if n.get("kind") in {"label", "beam", "column", "text"}
        and TOKEN_RE.search(str(n.get("text") or ""))
    ]

    def sort_key(n: dict) -> tuple:
        oid = n.get("source_id") or n.get("node_id")
        return (0 if oid in priority_ids else 1, str(n.get("text") or ""))

    for node in sorted(label_nodes, key=sort_key)[:limit]:
        sug = suggest_for_text_node(node, graph=graph, excel_json=excel_json)
        suggestions.append(sug.to_dict())

    for finding in (match_report or {}).get("findings") or []:
        if finding.get("status") != "missing_label":
            continue
        shape = finding.get("shape")
        if not shape:
            continue
        suggestions.append(
            Suggestion(
                object_id=f"missing:{shape}",
                expected_label=shape,
                expected_type=_infer_type_from_label(shape),
                confidence=0.7,
                reason="Excel requires this shape but it was not extracted from the drawing",
                features={"source": "excel_missing_label"},
            ).to_dict()
        )

    return {
        "suggestion_count": len(suggestions),
        "suggestions": suggestions[:limit],
    }
