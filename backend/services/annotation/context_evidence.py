"""Assemble local evidence bundles for anonymous-dimension contextual inference."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from services.engineering.detail_regions import region_for_point
from services.engineering.document_prior import plate_context_from_prior
from services.engineering.extraction_noise_filter import token_in_title_block
from services.engineering.feet_inch_filter import is_non_steel_layout_dimension
from services.engineering.graph_builder import build_geometry_nodes, build_text_nodes
from services.engineering.spatial_index import (
    DEFAULT_MAX_DISTANCE,
    build_page_index,
    nearest_geometry_candidates,
)

_DETAIL_CALLout_RE = re.compile(
    r"\b(?:DETAIL|SECTION|SHEET|CONN(?:ECTION)?)\s*[-#]?\s*[A-Z0-9./]+\b",
    re.I,
)
_CONNECTION_KEYWORDS = re.compile(
    r"\b(?:CONN(?:ECTION)?|SHEAR|MOMENT|GUSSET|STIFFENER|SEAT|CLIP)\b",
    re.I,
)
_NOTES_REGION = re.compile(
    r"\b(?:GENERAL\s+NOTES?|SPECIFICATIONS?|LEGEND|SHEET\s+INDEX)\b",
    re.I,
)
_STRUCTURAL_OBJECT_TYPES = frozenset(
    {
        "steel_section",
        "column",
        "column_or_brace",
        "brace",
        "beam",
        "plate",
        "bolt",
        "weld",
        "connection",
    }
)


def _center(bbox: List[float]) -> List[float]:
    return [
        round((float(bbox[0]) + float(bbox[2])) / 2.0, 3),
        round((float(bbox[1]) + float(bbox[3])) / 2.0, 3),
    ]


def _dist(a: List[float], b: List[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _leader_far_from_bbox(label_center: List[float], bbox: List[float]) -> List[float]:
    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    corners = [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]
    far = max(corners, key=lambda c: _dist(label_center, [c[0], c[1]]))
    return [round(far[0], 2), round(far[1], 2)]


def _geometry_lookup(geometry: Dict[str, Any]) -> Dict[str, dict]:
    return {
        str(obj.get("geometry_id") or ""): obj
        for obj in (geometry.get("objects") or [])
        if obj.get("geometry_id")
    }


def _plate_like(geom: dict) -> bool:
    kind = str(geom.get("geometry_kind") or geom.get("kind") or "").lower()
    aspect = float(geom.get("aspect_ratio") or 1.0)
    area = float(geom.get("area") or 0.0)
    if kind in {"rectangle", "symbol"} and 20 < area < 8000:
        return True
    if kind in {"line", "polyline"} and aspect > 3.0:
        return True
    return False


def build_context_evidence(
    token: Dict[str, Any],
    *,
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    graph: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build explainable local evidence for one token."""

    page = int(token.get("page") or token.get("page_number") or 0)
    bbox = token.get("bbox") or [0, 0, 0, 0]
    center = _center(bbox)
    raw = str(token.get("raw_text") or token.get("text") or "")
    normalized = str(token.get("normalized_text") or raw)

    region_id = token.get("region_id")
    detail_regions = document.get("detail_regions") or {}
    if region_id is None and detail_regions:
        region_id = region_for_point(detail_regions, page, center)

    context = token.get("context") or {}
    nearby_text = list(dict.fromkeys(
        [
            *(context.get("neighbor_text") or []),
            context.get("line_text") or "",
            context.get("block_text") or "",
            token.get("surrounding_text") or "",
        ]
    ))
    nearby_text = [t for t in nearby_text if t and str(t).strip()]

    document_prior = document.get("document_prior") or {}
    dlp_hints = {
        "enabled": bool(document_prior.get("enabled")),
        "plate_terms": list(document_prior.get("plate_terms") or []),
        "confirms_bent_plate": bool(document_prior.get("confirms_bent_plate_abbreviation")),
        "confirms_plates": bool(document_prior.get("confirms_plates")),
    }
    prior_local = plate_context_from_prior(
        document_prior if document_prior.get("enabled") else None,
        normalized=normalized,
        compact=normalized.replace(" ", ""),
    )
    if prior_local.get("is_dimension_only"):
        dlp_hints["supports_plate"] = False
        dlp_hints["supports_bent_plate"] = False
    else:
        dlp_hints["supports_plate"] = bool(prior_local.get("supports_plate"))
        dlp_hints["supports_bent_plate"] = bool(prior_local.get("supports_bent_plate"))

    page_tokens = [
        t
        for t in (document.get("engineering_tokens") or [])
        if int(t.get("page") or 0) == page
    ]
    nearby_tokens: List[dict] = []
    for other in page_tokens:
        other_bbox = other.get("bbox")
        if not other_bbox or other is token:
            continue
        distance = _dist(center, _center(other_bbox))
        if distance <= DEFAULT_MAX_DISTANCE:
            nearby_tokens.append(
                {
                    "text": other.get("text") or other.get("normalized_text"),
                    "object_type": other.get("engineering_object_type"),
                    "distance": round(distance, 2),
                }
            )
    nearby_tokens.sort(key=lambda item: item["distance"])
    nearby_structural_count = sum(
        1
        for item in nearby_tokens
        if str(item.get("object_type") or "") in _STRUCTURAL_OBJECT_TYPES
    )

    linked_layout_dimension_text = (context.get("layout_dimension_text") or "").strip()
    layout_dimension_is_non_steel = bool(
        linked_layout_dimension_text
        and is_non_steel_layout_dimension(linked_layout_dimension_text)
    )
    in_title_block = token_in_title_block(
        token, document.get("title_blocks") or []
    )

    sheet_title = None
    detail_callout = None
    for block in document.get("title_blocks") or []:
        if int(block.get("page_number") or 0) != page:
            continue
        block_bbox = block.get("bbox")
        if block_bbox and _dist(center, _center(block_bbox)) < 400:
            sheet_title = str(block.get("text") or "")[:200] or None
            break
    blob = " ".join(nearby_text).upper()
    match = _DETAIL_CALLout_RE.search(blob)
    if match:
        detail_callout = match.group(0)

    leader_info: Dict[str, Any] = {"present": False}
    target_geometry: List[dict] = []
    geom_by_id = _geometry_lookup(geometry)
    page_geom_objs = [
        obj
        for obj in (geometry.get("objects") or [])
        if int(obj.get("page_number") or 0) == page
    ]
    geom_nodes = build_geometry_nodes({"objects": page_geom_objs})
    text_nodes = build_text_nodes({"engineering_tokens": [token]})
    if text_nodes and geom_nodes:
        tree, ordered = build_page_index(geom_nodes)
        if tree is not None:
            label_node = text_nodes[0]
            candidates = nearest_geometry_candidates(
                label_node,
                tree,
                ordered,
                max_distance=DEFAULT_MAX_DISTANCE,
                top_k=5,
            )
            node_by_id = {n["node_id"]: n for n in geom_nodes}
            for cand in candidates:
                node = node_by_id.get(cand.node_id)
                if not node:
                    continue
                source_id = str(node.get("source_id") or "")
                raw_geom = geom_by_id.get(source_id) or {}
                entry = {
                    "geometry_id": source_id,
                    "kind": node.get("geometry_kind"),
                    "bbox": node.get("bbox"),
                    "distance": cand.distance,
                    "sources": list(cand.sources),
                    "plate_like": _plate_like({**node, **raw_geom}),
                }
                target_geometry.append(entry)

            for cand in candidates:
                if "leader_endpoint_resolved" not in cand.sources:
                    continue
                node = node_by_id.get(cand.node_id)
                if not node:
                    continue
                for other in candidates:
                    if other.node_id == cand.node_id:
                        continue
                    other_node = node_by_id.get(other.node_id)
                    if other_node and other_node.get("geometry_kind") == "leader":
                        source_id = str(other_node.get("source_id") or "")
                        leader_raw = geom_by_id.get(source_id) or {}
                        endpoints = leader_raw.get("leader_endpoints") or {}
                        if not endpoints.get("far_endpoint") and other_node.get("bbox"):
                            endpoints = {
                                "far_endpoint": _leader_far_from_bbox(
                                    label_node["center"], other_node["bbox"]
                                )
                            }
                        leader_info = {
                            "present": True,
                            "leader_geometry_id": source_id,
                            "near_endpoint": endpoints.get("near_endpoint"),
                            "far_endpoint": endpoints.get("far_endpoint"),
                            "target_geometry_ids": [str(node.get("source_id") or "")],
                        }
                        break
                if leader_info.get("present"):
                    break

            if not leader_info.get("present"):
                for cand in candidates:
                    node = node_by_id.get(cand.node_id)
                    if node and node.get("geometry_kind") == "leader":
                        source_id = str(node.get("source_id") or "")
                        leader_raw = geom_by_id.get(source_id) or {}
                        endpoints = leader_raw.get("leader_endpoints") or {}
                        if not endpoints and node.get("bbox"):
                            far = _leader_far_from_bbox(label_node["center"], node["bbox"])
                            endpoints = {"far_endpoint": far}
                        leader_info = {
                            "present": True,
                            "leader_geometry_id": source_id,
                            "near_endpoint": endpoints.get("near_endpoint"),
                            "far_endpoint": endpoints.get("far_endpoint"),
                            "target_geometry_ids": [],
                        }
                        break

    graph_edges: List[dict] = []
    if graph:
        token_id = token.get("token_id")
        node_ids = [
            n.get("node_id")
            for n in (graph.get("nodes") or [])
            if n.get("source_id") == token_id
        ]
        for edge in graph.get("edges") or []:
            if edge.get("source") not in node_ids and edge.get("target") not in node_ids:
                continue
            graph_edges.append(
                {
                    "relationship": edge.get("relationship"),
                    "meta": edge.get("meta") or {},
                    "distance": edge.get("distance"),
                }
            )

    region_kind = "unknown"
    if in_title_block or _NOTES_REGION.search(blob):
        region_kind = "notes"
    elif detail_callout or _CONNECTION_KEYWORDS.search(blob):
        region_kind = "connection_detail"
    elif region_id:
        region_kind = "detail"

    if leader_info.get("present") and target_geometry:
        token_context = dict(context)
        token_context["leader"] = leader_info
        token["context"] = token_context

    evidence_bits = []
    if leader_info.get("present"):
        evidence_bits.append("leader path detected")
    if detail_callout:
        evidence_bits.append(f"detail: {detail_callout}")
    if region_kind and region_kind != "unknown":
        evidence_bits.append(f"region: {region_kind}")
    if nearby_structural_count:
        evidence_bits.append(f"nearby structural tokens: {nearby_structural_count}")
    if linked_layout_dimension_text:
        evidence_bits.append(f"layout dim: {linked_layout_dimension_text[:40]}")
    evidence_summary = "; ".join(evidence_bits) or "No strong local context."

    return {
        "token_id": token.get("token_id"),
        "page": page,
        "bbox": bbox,
        "thickness_value": normalized,
        "dimension_subtype": _dimension_subtype(normalized),
        "region_id": region_id,
        "region_kind": region_kind,
        "leader": leader_info,
        "target_geometry": target_geometry,
        "nearby_text": nearby_text[:12],
        "nearby_tokens": nearby_tokens[:8],
        "nearby_structural_count": nearby_structural_count,
        "linked_layout_dimension_text": linked_layout_dimension_text or None,
        "layout_dimension_is_non_steel": layout_dimension_is_non_steel,
        "in_title_block": in_title_block,
        "sheet_title": sheet_title,
        "detail_callout": detail_callout,
        "dlp_hints": dlp_hints,
        "graph_edges": graph_edges[:10],
        "in_notes_region": region_kind == "notes",
        "evidence_summary": evidence_summary,
    }


def _dimension_subtype(text: str) -> str:
    compact = re.sub(r"\s+", "", str(text or "").upper())
    if re.search(r"X\d", compact):
        parts = compact.split("X")
        return "compound" if len(parts) >= 3 else "linear"
    if '"' in compact or compact.endswith("IN"):
        return "thickness"
    return "linear"


def attach_context_evidence(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    graph: Optional[Dict[str, Any]] = None,
) -> int:
    """Attach evidence bundles to anonymous-dimension tokens. Returns count updated."""

    updated = 0
    for token in document.get("engineering_tokens") or []:
        if str(token.get("engineering_object_type") or "") != "anonymous_dimension":
            continue
        bundle = build_context_evidence(
            token, document=document, geometry=geometry, graph=graph
        )
        token["context_evidence"] = bundle
        updated += 1
    return updated
