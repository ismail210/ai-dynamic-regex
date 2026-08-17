"""Spatial label↔geometry association for unlabeled drawn members.

Uses the experimental STRtree candidate generator (leader-aware) to link
text labels to nearby geometry and emit geometry-backed inference tokens
when linework has no OCR callout. All associations default to human review.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Set

from services.engineering.detail_regions import region_for_point, same_region
from services.engineering.graph_builder import build_text_nodes
from services.engineering.spatial_index import (
    DEFAULT_MAX_DISTANCE,
    build_page_index,
    nearest_geometry_candidates,
)
from services.section_parser import parse_section
from services.token_extractor import normalize_engineering_token

_STEEL_LABEL_KINDS = {
    "label",
    "beam",
    "column",
    "plate",
    "brace",
    "bolt",
    "weld",
    "connection",
    "steel_section",
}


def _norm(text: str) -> str:
    return normalize_engineering_token(text)


def _section_from_label(text: str) -> Optional[str]:
    cleaned = _norm(text)
    parsed = parse_section(cleaned)
    return parsed.normalized if parsed and parsed.catalog_valid else None


def _center_from_bbox(bbox: List[float]) -> List[float]:
    return [
        round((float(bbox[0]) + float(bbox[2])) / 2.0, 3),
        round((float(bbox[1]) + float(bbox[3])) / 2.0, 3),
    ]


def _geometry_kind(obj: dict) -> str:
    return str(obj.get("geometry_kind") or obj.get("kind") or "").lower()


def _geometry_nodes_for_page(geometry: Dict[str, Any], page_number: int) -> List[dict]:
    nodes = []
    for geom_index, geom in enumerate(geometry.get("objects") or []):
        if int(geom.get("page_number") or 0) != page_number:
            continue
        kind = _geometry_kind(geom)
        if kind in {"leader", "rectangle", "border"}:
            continue
        bbox = geom.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        center = geom.get("center") or _center_from_bbox(bbox)
        geometry_id = geom.get("geometry_id") or f"idx{geom_index}"
        nodes.append(
            {
                "node_id": f"geo_{geometry_id}",
                "source_id": geometry_id,
                "kind": "geometry",
                "page_number": page_number,
                "bbox": bbox,
                "center": center,
                "geometry_kind": kind or "line",
                "region_id": geom.get("region_id"),
            }
        )
    return nodes


def _stable_geometry_token_id(geometry_id: str, section: str) -> str:
    seed = f"spatial|{geometry_id}|{section}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"geom_assoc_{digest}"


def build_spatial_association_tokens(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    *,
    existing_tokens: Optional[List[dict]] = None,
    max_distance: float = DEFAULT_MAX_DISTANCE,
) -> List[dict]:
    """Return synthetic tokens for geometry linked to labels via spatial index."""

    tokens = list(existing_tokens or document.get("engineering_tokens") or [])
    claimed_geometry: Set[str] = set()
    claimed_text: Set[str] = set()
    for token in tokens:
        if token.get("geometry_id"):
            claimed_geometry.add(str(token["geometry_id"]))
        token_id = token.get("token_id")
        if token_id:
            claimed_text.add(str(token_id))

    regions = document.get("detail_regions") or {}
    geometry_by_id = {
        str(obj.get("geometry_id") or ""): obj
        for obj in (geometry.get("objects") or [])
        if obj.get("geometry_id")
    }
    association_tokens: List[dict] = []

    pages = sorted(
        {
            int(node.get("page_number") or 0)
            for node in build_text_nodes(document)
            if node.get("page_number")
        }
        | {
            int(obj.get("page_number") or 0)
            for obj in (geometry.get("objects") or [])
            if obj.get("page_number")
        }
    )

    for page_number in pages:
        text_nodes = [
            node
            for node in build_text_nodes(document)
            if int(node.get("page_number") or 0) == page_number
            and node.get("kind") in _STEEL_LABEL_KINDS
            and _section_from_label(str(node.get("text") or ""))
        ]
        geometry_nodes = _geometry_nodes_for_page(geometry, page_number)
        if not text_nodes or not geometry_nodes:
            continue

        tree, ordered = build_page_index(geometry_nodes)
        if tree is None:
            continue

        for label in text_nodes:
            section = _section_from_label(str(label.get("text") or ""))
            if not section:
                continue
            label_region = label.get("region_id") or region_for_point(
                regions, page_number, label["center"]
            )
            candidates = nearest_geometry_candidates(
                label,
                tree,
                ordered,
                max_distance=max_distance,
                top_k=3,
            )
            for candidate in candidates:
                geom_node = next(
                    (node for node in ordered if node["node_id"] == candidate.node_id),
                    None,
                )
                if geom_node is None:
                    continue
                geom_id = str(geom_node.get("source_id") or "")
                if not geom_id or geom_id in claimed_geometry:
                    continue
                geom_obj = geometry_by_id.get(geom_id) or {}
                if geom_obj.get("nearby_text"):
                    continue
                target_region = geom_node.get("region_id") or region_for_point(
                    regions, page_number, geom_node["center"]
                )
                if not same_region(label_region, target_region):
                    continue
                bbox = geom_obj.get("bbox") or geom_node.get("bbox") or [0, 0, 0, 0]
                token_id = _stable_geometry_token_id(geom_id, section)
                association_tokens.append(
                    {
                        "token_id": token_id,
                        "text": "",
                        "raw_text": "",
                        "normalized_text": "",
                        "page": page_number,
                        "bbox": bbox,
                        "confidence": max(0.55, 0.85 - candidate.distance / 400.0),
                        "engineering_object_type": geom_obj.get("geometry_role")
                        or geom_node.get("geometry_kind")
                        or "member",
                        "geometry_id": geom_id,
                        "geometry_associated": True,
                        "spatial_association": {
                            "label_node_id": label.get("node_id"),
                            "label_text": label.get("text"),
                            "section": section,
                            "distance": candidate.distance,
                            "sources": list(candidate.sources),
                        },
                        "inferred_section": section,
                        "missing_label": True,
                        "extraction_method": "spatial_association",
                        "region_id": target_region,
                        "requires_review": True,
                    }
                )
                claimed_geometry.add(geom_id)
                break

    return association_tokens
