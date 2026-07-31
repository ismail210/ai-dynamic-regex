"""
Matching Engine
===============

Compares extracted document/graph labels and geometry against an engineering
Excel JSON schedule / catalog.

Returns structured discrepancies::

    perfect_match | missing_label | wrong_label | missing_geometry |
    extra_geometry | extra_label | count_mismatch | length_mismatch | width_mismatch
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set

from services.engineering.models import MatchStatus


TOKEN_RE = re.compile(
    r"\b(W\d+X\d+|HSS\d+X\d+(?:X[\d/]+)?|L\d+X\d+(?:X[\d/]+)?|PIPE\d+|PL\d+|A\d+)\b",
    re.I,
)


def _norm(token: str) -> str:
    return str(token or "").upper().replace(" ", "").replace("-", "")


def _labels_from_graph(graph: dict) -> List[dict]:
    labels = []
    for node in graph.get("nodes") or []:
        if node.get("kind") in {"label", "beam", "column"}:
            labels.append(node)
            continue
        text = str(node.get("text") or "")
        for match in TOKEN_RE.findall(text):
            labels.append({**node, "text": match, "kind": "label"})
    return labels


def _geometry_linked_labels(graph: dict) -> Set[str]:
    """Return label node ids that have a nearest_geometry edge."""

    linked: Set[str] = set()
    node_by_id = {n["node_id"]: n for n in graph.get("nodes") or []}
    for edge in graph.get("edges") or []:
        if edge.get("relationship") != "nearest_geometry":
            continue
        src = node_by_id.get(edge["source"])
        if src and src.get("kind") in {"label", "beam", "column"}:
            linked.add(src["node_id"])
    return linked


def match_extraction_to_excel(
    *,
    document_structure: dict,
    geometry: dict,
    graph: dict,
    excel_json: dict,
    length_tolerance: float = 0.05,
    width_tolerance: float = 0.05,
) -> Dict[str, Any]:
    """
    Compare extracted content vs engineering Excel JSON.
    """

    excel_items = excel_json.get("items") or []
    excel_counts: Counter = Counter()
    excel_by_shape: Dict[str, List[dict]] = defaultdict(list)
    for item in excel_items:
        shape = _norm(item.get("shape") or item.get("mark") or "")
        if not shape:
            continue
        count = int(item.get("count") or 1)
        excel_counts[shape] += count
        excel_by_shape[shape].append(item)

    labels = _labels_from_graph(graph)
    extracted_counts: Counter = Counter()
    extracted_label_nodes: Dict[str, List[dict]] = defaultdict(list)
    for lab in labels:
        shape = _norm(lab.get("text") or "")
        if not shape:
            continue
        extracted_counts[shape] += 1
        extracted_label_nodes[shape].append(lab)

    linked_label_ids = _geometry_linked_labels(graph)
    findings: List[dict] = []

    all_shapes = set(excel_counts) | set(extracted_counts)

    for shape in sorted(all_shapes):
        expected = excel_counts.get(shape, 0)
        observed = extracted_counts.get(shape, 0)

        if expected > 0 and observed == expected:
            # Check geometry linkage for each label instance
            nodes = extracted_label_nodes.get(shape) or []
            missing_geom = [n for n in nodes if n["node_id"] not in linked_label_ids]
            if missing_geom and geometry.get("geometry_count", 0) > 0:
                findings.append(
                    {
                        "status": MatchStatus.MISSING_GEOMETRY.value,
                        "shape": shape,
                        "expected_count": expected,
                        "observed_count": observed,
                        "message": f"{shape}: label found but geometry link missing for {len(missing_geom)} instance(s)",
                        "object_ids": [n.get("source_id") or n["node_id"] for n in missing_geom],
                    }
                )
            else:
                findings.append(
                    {
                        "status": MatchStatus.PERFECT_MATCH.value,
                        "shape": shape,
                        "expected_count": expected,
                        "observed_count": observed,
                        "message": f"{shape}: perfect count match ({observed})",
                        "object_ids": [n.get("source_id") or n["node_id"] for n in nodes],
                    }
                )
            # Length / width checks against first excel row when available
            excel_row = (excel_by_shape.get(shape) or [None])[0]
            if excel_row:
                _check_size_mismatches(
                    findings,
                    shape,
                    excel_row,
                    nodes,
                    length_tolerance=length_tolerance,
                    width_tolerance=width_tolerance,
                )
            continue

        if expected > 0 and observed == 0:
            findings.append(
                {
                    "status": MatchStatus.MISSING_LABEL.value,
                    "shape": shape,
                    "expected_count": expected,
                    "observed_count": 0,
                    "message": f"{shape}: expected in Excel but not found on drawing",
                    "object_ids": [],
                }
            )
            continue

        if expected == 0 and observed > 0:
            findings.append(
                {
                    "status": MatchStatus.EXTRA_LABEL.value,
                    "shape": shape,
                    "expected_count": 0,
                    "observed_count": observed,
                    "message": f"{shape}: present on drawing but not in Excel",
                    "object_ids": [
                        n.get("source_id") or n["node_id"] for n in extracted_label_nodes.get(shape) or []
                    ],
                }
            )
            continue

        if expected != observed:
            findings.append(
                {
                    "status": MatchStatus.COUNT_MISMATCH.value,
                    "shape": shape,
                    "expected_count": expected,
                    "observed_count": observed,
                    "message": f"{shape}: Excel count {expected} vs extracted {observed}",
                    "object_ids": [
                        n.get("source_id") or n["node_id"] for n in extracted_label_nodes.get(shape) or []
                    ],
                }
            )

    # Extra geometry: geometry nodes with no nearest label
    geom_nodes = [
        n for n in graph.get("nodes") or [] if n.get("kind") in {"geometry", "dimension"}
    ]
    labeled_geom_ids = set()
    for edge in graph.get("edges") or []:
        if edge.get("relationship") == "nearest_label":
            labeled_geom_ids.add(edge["source"])
    extras = [g for g in geom_nodes if g["node_id"] not in labeled_geom_ids]
    # Cap noise: only report if there are relatively few extras or large shapes
    significant = [g for g in extras if float(g.get("area") or 0) > 500]
    if significant:
        findings.append(
            {
                "status": MatchStatus.EXTRA_GEOMETRY.value,
                "shape": None,
                "expected_count": 0,
                "observed_count": len(significant),
                "message": f"{len(significant)} geometry object(s) without nearby labels",
                "object_ids": [g.get("source_id") or g["node_id"] for g in significant[:50]],
            }
        )

    # Wrong label heuristic: extracted token not in Excel and close to known shape
    excel_shapes = set(excel_counts)
    for shape, nodes in extracted_label_nodes.items():
        if shape in excel_shapes:
            continue
        close = _closest_shape(shape, excel_shapes)
        if close:
            findings.append(
                {
                    "status": MatchStatus.WRONG_LABEL.value,
                    "shape": shape,
                    "expected_shape": close,
                    "expected_count": excel_counts.get(close, 0),
                    "observed_count": len(nodes),
                    "message": f"{shape}: possible wrong label; closest Excel shape is {close}",
                    "object_ids": [n.get("source_id") or n["node_id"] for n in nodes],
                }
            )

    status_counts = Counter(f["status"] for f in findings)
    return {
        "findings": findings,
        "summary": {
            "excel_shapes": len(excel_counts),
            "extracted_labels": int(sum(extracted_counts.values())),
            "status_counts": dict(status_counts),
            "perfect_matches": status_counts.get(MatchStatus.PERFECT_MATCH.value, 0),
            "issues": sum(v for k, v in status_counts.items() if k != MatchStatus.PERFECT_MATCH.value),
        },
        "extracted_counts": dict(extracted_counts),
        "excel_counts": dict(excel_counts),
    }


def _check_size_mismatches(
    findings: List[dict],
    shape: str,
    excel_row: dict,
    nodes: List[dict],
    *,
    length_tolerance: float,
    width_tolerance: float,
) -> None:
    expected_length = excel_row.get("length")
    expected_width = excel_row.get("width")
    if expected_length is None and expected_width is None:
        return
    for node in nodes:
        # Use linked geometry length/width when present on the node itself
        obs_length = node.get("length")
        obs_width = node.get("width")
        if expected_length is not None and obs_length is not None and float(expected_length) > 0:
            rel = abs(float(obs_length) - float(expected_length)) / float(expected_length)
            if rel > length_tolerance:
                findings.append(
                    {
                        "status": MatchStatus.LENGTH_MISMATCH.value,
                        "shape": shape,
                        "expected_length": expected_length,
                        "observed_length": obs_length,
                        "message": f"{shape}: length mismatch (excel={expected_length}, geom={obs_length})",
                        "object_ids": [node.get("source_id") or node["node_id"]],
                    }
                )
        if expected_width is not None and obs_width is not None and float(expected_width) > 0:
            rel = abs(float(obs_width) - float(expected_width)) / float(expected_width)
            if rel > width_tolerance:
                findings.append(
                    {
                        "status": MatchStatus.WIDTH_MISMATCH.value,
                        "shape": shape,
                        "expected_width": expected_width,
                        "observed_width": obs_width,
                        "message": f"{shape}: width mismatch (excel={expected_width}, geom={obs_width})",
                        "object_ids": [node.get("source_id") or node["node_id"]],
                    }
                )


def _closest_shape(shape: str, candidates: Set[str]) -> Optional[str]:
    if not candidates:
        return None
    # Simple edit-distance-ish: shared prefix + length proximity
    best = None
    best_score = 0
    for cand in candidates:
        common = 0
        for a, b in zip(shape, cand):
            if a == b:
                common += 1
            else:
                break
        score = common - abs(len(shape) - len(cand))
        if score > best_score and common >= 2:
            best_score = score
            best = cand
    return best
