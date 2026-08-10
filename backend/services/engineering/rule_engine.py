"""
Engineering Rule Engine
=======================

Produces structural sanity evidence used by the multimodal fusion engine.
Rules never classify shapes by themselves; they contribute a small weighted
signal and human-readable reasons.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


SHAPE_RE = re.compile(
    r"^(?:W|WT|S|M|HP|C|MC|HSS|L|2L|PIPE|PL)[\dX./-]+$",
    re.IGNORECASE,
)
DEPTH_RE = re.compile(r"^(?:W|WT|S|M|HP|C|MC)(\d+(?:\.\d+)?)", re.IGNORECASE)


@dataclass
class RuleFinding:
    rule_id: str
    status: str  # pass | warning | fail
    message: str
    weight: float = 1.0

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "status": self.status,
            "message": self.message,
            "weight": self.weight,
        }


@dataclass
class RuleEvaluation:
    score: float
    findings: List[RuleFinding] = field(default_factory=list)
    member_role: Optional[str] = None
    material_grade: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "member_role": self.member_role,
            "material_grade": self.material_grade,
            "findings": [item.to_dict() for item in self.findings],
            "pass_count": sum(item.status == "pass" for item in self.findings),
            "warning_count": sum(item.status == "warning" for item in self.findings),
            "fail_count": sum(item.status == "fail" for item in self.findings),
        }


def _center(bbox: Sequence[float]) -> List[float]:
    return [(float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0]


_CANONICAL_ROLES = {"beam", "column", "brace", "plate", "connection", "other"}


def _infer_role(text: str, graph_preview: Optional[dict], geometry: Optional[dict]) -> str:
    """
    Structural role from explicit signals only: drawing-text keywords, then
    geometry orientation plus graph connectivity. Section family (the shape
    designation itself, e.g. "HSS8X8X1/2" or "W14X90") is NEVER used to infer
    role — a member with no explicit role keyword and no usable orientation/
    connectivity signal returns "other" (unknown) rather than a guess.

    Always returns one of ``_CANONICAL_ROLES`` so callers never need a
    family-based fallback for an unrecognized value.
    """

    upper = (text or "").upper()
    if "COL" in upper or "COLUMN" in upper:
        return "column"
    if "BRACE" in upper or "BRACING" in upper:
        return "brace"
    if "PL" in upper[:3] or "PLATE" in upper:
        return "plate"
    if "BOLT" in upper or upper.startswith("A3") or upper.startswith("A4"):
        return "connection"

    geom = geometry or {}
    has_orientation_signal = geom.get("orientation") is not None
    if not has_orientation_signal:
        # No geometry evidence at all — do not default a missing signal to
        # "beam" (0.0 degrees) just because that happens to be the numeric
        # fallback for a missing value.
        return "other"

    orientation = float(geom.get("orientation") or 0.0)
    structural_links = float((graph_preview or {}).get("structural_links") or 0.0)
    if abs(orientation) > 60 and structural_links >= 1:
        return "column"
    if abs(orientation) <= 35:
        return "beam"
    if 35 < abs(orientation) <= 60 and structural_links >= 1:
        # Diagonal orientation with confirmed structural connectivity — a
        # real, non-family-derived signal for "brace", not a shape lookup.
        return "brace"
    # Diagonal but unconfirmed (no structural_links), or steep-but-isolated:
    # not enough independent evidence to pick a role.
    return "other"


def _depth_from_label(text: str) -> Optional[float]:
    match = DEPTH_RE.match(str(text or "").replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def evaluate_engineering_rules(
    *,
    token: str,
    predicted_shape: str,
    geometry: Optional[dict] = None,
    graph: Optional[dict] = None,
    graph_preview: Optional[dict] = None,
    page_height: Optional[float] = None,
) -> RuleEvaluation:
    """
    Score engineering consistency for one predicted component.

    Returns a score in [0, 1] where 1.0 means all applicable rules passed.
    """

    findings: List[RuleFinding] = []
    role = _infer_role(predicted_shape or token, graph_preview, geometry)
    shape = str(predicted_shape or token or "").upper().replace(" ", "")

    if SHAPE_RE.match(shape):
        findings.append(
            RuleFinding(
                "notation_valid",
                "pass",
                "Predicted label matches steel notation conventions",
            )
        )
    else:
        findings.append(
            RuleFinding(
                "notation_valid",
                "warning",
                "Predicted label does not match standard steel notation",
                weight=1.2,
            )
        )

    geom = geometry or {}
    if geom.get("available") or geom.get("kind") or geom.get("object"):
        obj = geom.get("object") or geom
        length = float(obj.get("length") or 0.0)
        orientation = float(obj.get("orientation") or 0.0)
        depth = _depth_from_label(shape)
        if role == "beam" and abs(orientation) <= 40:
            findings.append(
                RuleFinding(
                    "beam_orientation",
                    "pass",
                    "Geometry orientation agrees with a beam member",
                )
            )
        elif role == "beam" and abs(orientation) > 55:
            findings.append(
                RuleFinding(
                    "beam_orientation",
                    "warning",
                    "Predicted beam has near-vertical geometry",
                    weight=1.1,
                )
            )
        if role == "column" and abs(orientation) >= 50:
            findings.append(
                RuleFinding(
                    "column_orientation",
                    "pass",
                    "Geometry orientation agrees with a column member",
                )
            )
        if depth and length > 0:
            # Heuristic: depth in inches should be much smaller than drawn member length.
            if length > depth * 2.5:
                findings.append(
                    RuleFinding(
                        "depth_geometry_agreement",
                        "pass",
                        f"Section depth {depth} is consistent with member length {length:.1f}",
                    )
                )
            else:
                findings.append(
                    RuleFinding(
                        "depth_geometry_agreement",
                        "warning",
                        "Section depth is large relative to detected geometry length",
                    )
                )
    else:
        findings.append(
            RuleFinding(
                "geometry_available",
                "warning",
                "No nearby geometry available for engineering checks",
                weight=0.6,
            )
        )

    structural_links = float((graph_preview or {}).get("structural_links") or 0.0)
    degree = float((graph_preview or {}).get("degree") or 0.0)
    if role in {"beam", "brace"} and structural_links >= 1:
        findings.append(
            RuleFinding(
                "member_connectivity",
                "pass",
                "Graph shows structural connections for this member",
            )
        )
    elif role in {"beam", "brace"} and degree == 0:
        findings.append(
            RuleFinding(
                "member_connectivity",
                "warning",
                "Beam/brace has no graph connections (possible floating member)",
                weight=1.3,
            )
        )
    elif role == "column" and structural_links >= 1:
        findings.append(
            RuleFinding(
                "column_supports",
                "pass",
                "Column participates in support relationships",
            )
        )

    if role == "connection" and structural_links == 0:
        findings.append(
            RuleFinding(
                "bolt_belongs_to_connection",
                "warning",
                "Bolt/connection has no nearby connection/plate relationship",
            )
        )
    if role == "plate" and structural_links >= 1:
        findings.append(
            RuleFinding(
                "plate_attached",
                "pass",
                "Plate is attached to a nearby member/connection",
            )
        )

    # Default material prior for wide-flange sections.
    material = "A992" if shape.startswith("W") else None
    if material:
        findings.append(
            RuleFinding(
                "material_prior",
                "pass",
                f"Default material grade {material} applied for {role}",
                weight=0.4,
            )
        )

    if not findings:
        return RuleEvaluation(score=0.5, member_role=role, material_grade=material)

    weighted = 0.0
    total = 0.0
    for item in findings:
        total += item.weight
        if item.status == "pass":
            weighted += item.weight
        elif item.status == "warning":
            weighted += 0.45 * item.weight
    score = weighted / max(total, 1e-6)
    return RuleEvaluation(
        score=max(0.0, min(1.0, score)),
        findings=findings,
        member_role=role,
        material_grade=material,
    )


def evaluate_document_rules(graph: dict) -> Dict[str, Any]:
    """Document-level sanity checks used in validation reports."""

    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    findings: List[dict] = []
    beams = [n for n in nodes if n.get("kind") in {"beam", "Beam"}]
    columns = [n for n in nodes if n.get("kind") in {"column", "Column"}]
    if beams and not columns:
        findings.append(
            {
                "rule_id": "beams_without_columns",
                "status": "warning",
                "message": "Beams detected without nearby columns on the graph",
            }
        )
    connected = {
        edge.get("relationship")
        for edge in edges
        if edge.get("relationship") in {"connected_to", "supports", "supported_by"}
    }
    if beams and not connected:
        findings.append(
            {
                "rule_id": "missing_support_edges",
                "status": "warning",
                "message": "No support/connection edges found for beam members",
            }
        )
    return {
        "finding_count": len(findings),
        "findings": findings,
        "beam_count": len(beams),
        "column_count": len(columns),
    }
