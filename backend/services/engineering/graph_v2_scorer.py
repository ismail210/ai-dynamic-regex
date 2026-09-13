"""Offline Graph v2 candidate-compatibility scorer.

Isolated experiment module. MUST NOT be imported by the production
prediction pipeline (orchestrator, fusion, pipeline, takeoff).

Scores how compatible an *existing* AISC candidate is with local
structural context. Never generates candidates, invents thickness, or
mutates a token section.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

from services.family_codes import MODERN_FAMILY_PREFIXES, split_family
from services.token_extractor import core_section_token, normalize_engineering_token

# Soft, explainable weights. Kept small so Graph v2 cannot dominate text.
_W_SPATIAL = 0.06
_W_LEADER = 0.10
_W_ORIENT = 0.04
_W_ROLE = 0.05
_W_NEIGHBOR = 0.06
_W_FAMILY_LOCAL = 0.08

_INCOMPLETE_ANGLE_RE = re.compile(
    r"^(?:2)?L\d+(?:\.\d+)?X\d+(?:\.\d+)?$",
    re.I,
)
_COMPLETE_SECTION_RE = re.compile(
    r"^(?:2L|HSS|PIPE|WT|MC|HP|W|ST|MT|C|L|S|M)"
    r"\d",
    re.I,
)


def family_of(section: str) -> str:
    """Longest-prefix family of a designation, or empty string."""

    fam, _ = split_family(
        normalize_engineering_token(section),
        MODERN_FAMILY_PREFIXES,
    )
    return fam or ""


def is_incomplete_angle(raw_text: str) -> bool:
    """True for L/2L with two printed legs and no thickness (e.g. L4x4)."""

    core = core_section_token(raw_text)
    if not core:
        return False
    return bool(_INCOMPLETE_ANGLE_RE.fullmatch(core))


def is_explicit_complete_section(raw_text: str) -> bool:
    """True when shop/cut-stripped core looks like a complete designation."""

    core = core_section_token(raw_text)
    if not core or is_incomplete_angle(raw_text):
        return False
    if not _COMPLETE_SECTION_RE.match(core):
        return False
    # Angles / HSS need a thickness field; W/C depth-weight need X.
    fam = family_of(core)
    if fam in {"L", "2L"}:
        # Need legs + thickness (three numeric fields).
        return len([p for p in core[len(fam) :].split("X") if p]) >= 3
    if fam == "HSS":
        parts = [p for p in core[len(fam) :].split("X") if p]
        # Rect HSS needs 3 fields; round HSS needs decimal OD + wall.
        if len(parts) >= 3:
            return True
        if len(parts) == 2 and any("." in p for p in parts):
            return True
        return False
    return "X" in core[len(fam) :]


def proxy_gold_section(raw_text: str) -> Optional[str]:
    """Printed core after shop/cut strip, or None for incomplete/non-section."""

    if is_incomplete_angle(raw_text):
        return None
    core = core_section_token(raw_text)
    if not core or not is_explicit_complete_section(raw_text):
        return None
    return normalize_engineering_token(core)


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _orientation_class(degrees: Optional[float]) -> Optional[str]:
    if degrees is None:
        return None
    try:
        angle = abs(float(degrees)) % 180.0
    except (TypeError, ValueError):
        return None
    if angle <= 30.0 or angle >= 150.0:
        return "horizontal"
    if 60.0 <= angle <= 120.0:
        return "vertical"
    return "diagonal"


def index_graph(graph: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Precompute per-node adjacency for offline joins (call once per doc)."""

    if not graph:
        return None
    nodes = {str(n.get("node_id")): n for n in (graph.get("nodes") or [])}
    source_to_node: Dict[str, str] = {}
    for node in graph.get("nodes") or []:
        sid = str(node.get("source_id") or "")
        nid = str(node.get("node_id") or "")
        if sid and nid:
            source_to_node[sid] = nid

    incident: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges") or []:
        src = str(edge.get("source") or "")
        tgt = str(edge.get("target") or "")
        if src:
            incident[src].append(edge)
        if tgt and tgt != src:
            incident[tgt].append(edge)

    return {
        "graph": graph,
        "nodes": nodes,
        "source_to_node": source_to_node,
        "source_features": graph.get("source_features") or {},
        "incident": incident,
    }


def build_graph_context(
    *,
    prediction: Optional[Mapping[str, Any]] = None,
    graph: Optional[Mapping[str, Any]] = None,
    graph_index: Optional[Mapping[str, Any]] = None,
    token_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble context from predictions_view evidence and optional graph.json.

    GraphSAGE role predictions in cached evidence are intentionally ignored.
    Uses geometry_role, semantic node_kind, leader edges, and neighborhood
    scalars only.
    """

    prediction = prediction or {}
    explanation = prediction.get("explanation") or {}
    graph_ev = explanation.get("graph_evidence") or {}
    geo_ev = explanation.get("geometry_evidence") or {}
    graph_details = graph_ev.get("details") if isinstance(graph_ev, dict) else {}
    if not isinstance(graph_details, dict):
        graph_details = {}
    geo_details = geo_ev.get("details") if isinstance(geo_ev, dict) else {}
    if not isinstance(geo_details, dict):
        geo_details = {}
    geo_object = geo_details.get("object") or {}
    features = geo_details.get("features") or {}
    preview = prediction.get("graph_preview") or {}

    context: Dict[str, Any] = {
        "degree": float(
            graph_details.get("degree")
            or preview.get("degree")
            or 0.0
        ),
        "structural_links": float(
            graph_details.get("structural_links")
            or preview.get("structural_links")
            or 0.0
        ),
        "min_distance": float(
            graph_details.get("min_distance")
            or preview.get("min_distance")
            or geo_details.get("nearest_distance")
            or 999.0
        ),
        "node_kind": str(
            graph_details.get("node_kind")
            or preview.get("node_kind")
            or ""
        ).lower(),
        "geometry_role": str(
            features.get("role")
            or geo_object.get("geometry_role")
            or ""
        ).lower(),
        "geometry_kind": str(geo_object.get("kind") or "").lower(),
        "orientation": features.get("orientation", geo_object.get("orientation")),
        "orientation_bin": str(
            features.get("orientation_bin") or ""
        ).lower()
        or None,
        "length": features.get("length", geo_object.get("length")),
        "leader_resolved": False,
        "leader_member_count": 0,
        "neighbor_families": [],
        "neighbor_labels": [],
        "has_graph_json": False,
        # Explicitly record that GraphSAGE prediction is not used.
        "graphsage_role_ignored": graph_details.get("prediction")
        or graph_details.get("role_prediction"),
    }

    if context["orientation_bin"] not in {"horizontal", "vertical", "diagonal"}:
        context["orientation_bin"] = _orientation_class(context.get("orientation"))

    object_id = token_id or str(
        prediction.get("object_id")
        or prediction.get("token_id")
        or ""
    )
    idx = graph_index or (index_graph(graph) if graph else None)
    if idx and object_id:
        context.update(_enrich_from_graph_index(idx, object_id))

    if context["geometry_kind"] == "leader":
        context["leader_hint"] = True
    else:
        context["leader_hint"] = bool(context["leader_resolved"])

    return context


def _enrich_from_graph_index(index: Mapping[str, Any], token_id: str) -> Dict[str, Any]:
    """Pull leader / neighborhood detail from a pre-indexed graph."""

    out: Dict[str, Any] = {"has_graph_json": True}
    source_features = index.get("source_features") or {}
    sf = source_features.get(token_id) or {}
    if sf:
        out["degree"] = float(sf.get("degree") or 0.0)
        out["structural_links"] = float(sf.get("structural_links") or 0.0)
        out["min_distance"] = float(sf.get("min_distance") or 999.0)
        out["node_kind"] = str(sf.get("node_kind") or "").lower()
        out["source_node"] = sf.get("source_node")

    nodes = index.get("nodes") or {}
    source_node = out.get("source_node") or sf.get("source_node")
    if not source_node:
        source_node = (index.get("source_to_node") or {}).get(token_id)
        if source_node:
            out["source_node"] = source_node
            node = nodes.get(str(source_node)) or {}
            out["node_kind"] = str(node.get("kind") or "").lower()

    if not source_node:
        return out

    leader_resolved = 0
    leader_targets: List[str] = []
    neighbor_labels: List[str] = []
    neighbor_families: List[str] = []
    for edge in (index.get("incident") or {}).get(str(source_node), []):
        src = str(edge.get("source") or "")
        tgt = str(edge.get("target") or "")
        other_id = tgt if src == str(source_node) else src
        other = nodes.get(other_id) or {}
        meta = edge.get("meta") or {}
        if meta.get("leader_resolved") or meta.get("source") == "leader_endpoint_resolved":
            leader_resolved += 1
            leader_targets.append(other_id)
        text = str(other.get("text") or "")
        if text and str(other.get("node_id") or "").startswith("txt_"):
            neighbor_labels.append(text)
            fam = family_of(core_section_token(text))
            if fam:
                neighbor_families.append(fam)

    out["leader_resolved"] = leader_resolved > 0
    out["leader_member_count"] = len(set(leader_targets))
    out["neighbor_labels"] = neighbor_labels[:20]
    out["neighbor_families"] = neighbor_families[:20]
    return out


def score_candidate(
    token: Mapping[str, Any],
    candidate: str,
    graph_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Score one existing candidate against local structural context.

    Returns total_score, feature_contributions, evidence_used/missing,
    and confidence. Does not mutate ``token``.
    """

    raw = str(
        token.get("raw_text")
        or token.get("original_token")
        or token.get("normalized_text")
        or ""
    )
    context = dict(graph_context or {})
    contributions: Dict[str, float] = {
        "spatial": 0.0,
        "leader": 0.0,
        "orientation": 0.0,
        "role": 0.0,
        "neighborhood": 0.0,
        "family_local": 0.0,
    }
    used: List[str] = []
    missing: List[str] = []

    cand = normalize_engineering_token(candidate)
    cand_family = family_of(cand)
    if not cand or not cand_family:
        return {
            "total_score": 0.0,
            "feature_contributions": contributions,
            "evidence_used": [],
            "evidence_missing": ["valid_candidate"],
            "confidence": 0.0,
            "candidate": candidate,
            "candidate_family": cand_family,
            "gates": {
                "explicit_protected": is_explicit_complete_section(raw),
                "incomplete_angle": is_incomplete_angle(raw),
            },
        }

    # --- Spatial ---
    min_distance = context.get("min_distance")
    degree = float(context.get("degree") or 0.0)
    links = float(context.get("structural_links") or 0.0)
    if min_distance is not None and float(min_distance) < 900:
        proximity = _clip(1.0 - float(min_distance) / 180.0)
        density = _clip(0.5 * min(1.0, degree / 8.0) + 0.5 * min(1.0, links / 4.0))
        contributions["spatial"] = round(_W_SPATIAL * (0.6 * proximity + 0.4 * density), 6)
        used.extend(["min_distance", "degree", "structural_links"])
    else:
        missing.append("min_distance")

    # --- Leader ---
    if context.get("leader_resolved") or context.get("leader_hint"):
        member_count = int(context.get("leader_member_count") or 0)
        # A resolved leader that points at few members is stronger.
        focus = 1.0 if member_count <= 1 else _clip(1.0 / math.sqrt(member_count))
        # Soft family preference when leader associates to a member: braces
        # favor L/2L/HSS; beams favor W — only as weak compatibility.
        role_hint = str(context.get("geometry_role") or context.get("node_kind") or "")
        family_boost = 0.0
        if role_hint in {"brace", "connection"} and cand_family in {"L", "2L", "HSS", "WT"}:
            family_boost = 0.35
        elif role_hint in {"beam", "girder"} and cand_family in {"W", "S", "M", "C", "MC"}:
            family_boost = 0.25
        elif role_hint in {"column"} and cand_family in {"W", "HSS", "PIPE", "HP"}:
            family_boost = 0.25
        contributions["leader"] = round(
            _W_LEADER * (0.65 * focus + 0.35 * family_boost), 6
        )
        used.append("leader_association")
        if context.get("leader_resolved"):
            used.append("leader_resolved")
    else:
        missing.append("leader")

    # --- Orientation (context only) ---
    orient = context.get("orientation_bin")
    if orient:
        used.append("orientation_bin")
        if orient == "horizontal" and cand_family in {"W", "S", "M", "C", "MC"}:
            contributions["orientation"] = round(_W_ORIENT * 0.7, 6)
        elif orient == "vertical" and cand_family in {"W", "HSS", "PIPE", "HP"}:
            contributions["orientation"] = round(_W_ORIENT * 0.7, 6)
        elif orient == "diagonal" and cand_family in {"L", "2L", "HSS", "WT", "PIPE"}:
            contributions["orientation"] = round(_W_ORIENT * 0.8, 6)
        else:
            contributions["orientation"] = round(_W_ORIENT * 0.15, 6)
    else:
        missing.append("orientation")

    # --- Role (non-GraphSAGE only) ---
    # Prefer geometry_role; fall back to semantic node_kind from text rules.
    # Never use context["graphsage_role_ignored"].
    role = str(context.get("geometry_role") or "").lower()
    if role in {"", "other", "unknown"}:
        kind = str(context.get("node_kind") or "").lower()
        if kind in {"beam", "column", "brace", "plate", "connection"}:
            role = kind
            used.append("semantic_node_kind")
        else:
            role = ""
    else:
        used.append("geometry_role")

    if role:
        compat = _role_family_compatibility(role, cand_family)
        contributions["role"] = round(_W_ROLE * compat, 6)
    else:
        missing.append("role")

    # --- Neighborhood / local labels ---
    neighbor_families = list(context.get("neighbor_families") or [])
    if neighbor_families:
        used.append("neighbor_families")
        match_rate = sum(1 for fam in neighbor_families if fam == cand_family) / len(
            neighbor_families
        )
        # Soft anti-pattern: many W neighbors should not push incomplete L → W,
        # but for W candidates this is positive.
        contributions["neighborhood"] = round(_W_NEIGHBOR * match_rate, 6)
        contributions["family_local"] = round(_W_FAMILY_LOCAL * match_rate, 6)
    else:
        missing.append("neighbor_labels")

    total = round(sum(contributions.values()), 6)
    evidence_count = len(used)
    confidence = round(
        _clip(0.15 * evidence_count + 0.4 * min(1.0, total / 0.25)),
        4,
    )

    return {
        "total_score": total,
        "feature_contributions": contributions,
        "evidence_used": used,
        "evidence_missing": missing,
        "confidence": confidence,
        "candidate": cand,
        "candidate_family": cand_family,
        "gates": {
            "explicit_protected": is_explicit_complete_section(raw),
            "incomplete_angle": is_incomplete_angle(raw),
        },
    }


def _role_family_compatibility(role: str, family: str) -> float:
    """Weak role↔family compatibility (mirrors existing project priors softly)."""

    role = (role or "").lower()
    family = (family or "").upper()
    if role == "beam":
        if family in {"W", "S", "M", "C", "MC"}:
            return 1.0
        if family in {"HSS", "PIPE"}:
            return 0.35
        if family in {"L", "2L"}:
            return 0.45
        return 0.4
    if role == "column":
        if family in {"W", "HSS", "PIPE", "HP"}:
            return 1.0
        return 0.4
    if role in {"brace", "connection"}:
        if family in {"HSS", "PIPE", "L", "2L", "WT"}:
            return 1.0
        if family in {"W"}:
            return 0.4
        return 0.45
    if role == "plate":
        return 0.2
    return 0.5


def apply_safety_gates(
    *,
    raw_text: str,
    ranked_candidates: Sequence[str],
    graph_scores: Optional[Mapping[str, Mapping[str, Any]]] = None,
    min_confidence: float = 0.25,
    min_margin: float = 0.02,
) -> Dict[str, Any]:
    """Apply Graph v2 safety gates to a ranked candidate list.

    Gate behavior:
    - explicit complete printed core → force that section if present in pool
    - incomplete angle → abstain (empty pick)
    - weak/conflicting graph evidence → keep first ranked (caller baseline)
      when graph confidence/margin is too low
    - never invent candidates outside ``ranked_candidates``
    """

    ranked = [normalize_engineering_token(c) for c in ranked_candidates if c]
    gold = proxy_gold_section(raw_text)
    incomplete = is_incomplete_angle(raw_text)
    explicit = is_explicit_complete_section(raw_text)

    if incomplete:
        return {
            "selected": "",
            "reason": "gate_incomplete_abstain",
            "overrode_explicit": False,
            "abstained": True,
        }

    if explicit and gold:
        if gold in ranked:
            return {
                "selected": gold,
                "reason": "gate_explicit_protected",
                "overrode_explicit": False,
                "abstained": False,
            }
        # Explicit printed section not in candidate pool — abstain rather
        # than invent.
        return {
            "selected": "",
            "reason": "gate_explicit_missing_from_pool",
            "overrode_explicit": False,
            "abstained": True,
        }

    if not ranked:
        return {
            "selected": "",
            "reason": "gate_no_candidates",
            "overrode_explicit": False,
            "abstained": True,
        }

    # Weak evidence: if top graph scores are missing/low/tied, do not force
    # a change — caller should keep baseline. Here we return the text-ranked
    # first candidate with a weak-evidence reason.
    if graph_scores:
        scored = []
        for cand in ranked:
            payload = graph_scores.get(cand) or graph_scores.get(
                normalize_engineering_token(cand)
            )
            if payload:
                scored.append((cand, float(payload.get("total_score") or 0.0),
                               float(payload.get("confidence") or 0.0)))
        if scored:
            scored.sort(key=lambda item: (-item[1], -item[2], item[0]))
            top = scored[0]
            second = scored[1] if len(scored) > 1 else None
            margin = top[1] - (second[1] if second else 0.0)
            if top[2] < min_confidence or margin < min_margin:
                return {
                    "selected": ranked[0],
                    "reason": "gate_weak_evidence_keep_baseline_order",
                    "overrode_explicit": False,
                    "abstained": False,
                }
            return {
                "selected": top[0],
                "reason": "graph_v2_rerank",
                "overrode_explicit": False,
                "abstained": False,
            }

    return {
        "selected": ranked[0],
        "reason": "text_order",
        "overrode_explicit": False,
        "abstained": False,
    }


def score_candidates(
    token: Mapping[str, Any],
    candidates: Iterable[str],
    graph_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Score each candidate; keys are normalized designations."""

    out: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        if not candidate:
            continue
        result = score_candidate(token, candidate, graph_context)
        out[result["candidate"]] = result
    return out
