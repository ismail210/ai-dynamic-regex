"""Independent text, geometry, graph, and database feature providers."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from services.database_loader import lookup_shape, search_similar_shapes
from services.engineering.structural_graph import (
    build_source_lookup,
    graph_features_for_token,
)
from services.feature_extractor import extract_structural_features
from services.model_predictor import predict_with_confidence


class TextFeatureProvider:
    name = "production_text_features"

    def extract(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Family + structural features only.

        Exact-section AI prediction runs once in the orchestrator with
        geometry/graph context — avoid a duplicate call here.
        """

        token = str(context["token"].get("normalized_text") or "")
        family_prediction = predict_with_confidence(token)
        return {
            "engineered": extract_structural_features(token),
            "model_label": family_prediction.label,
            "model_probability": float(family_prediction.probability),
            "exact_section_prediction": None,
            "exact_section_candidates": [],
            "family_fallback": family_prediction.to_dict(),
            "distribution": family_prediction.distribution,
            "extraction_confidence": float(
                context["token"].get("confidence") or 0.5
            ),
        }


_PAGE_INDEX_CACHE: Dict[str, Any] = {"objects": None, "index": {}}


def _objects_by_page(objects: List[dict]) -> Dict[int, List[tuple[float, float, dict]]]:
    """
    Group geometry by page once per document, with centers pre-unpacked.

    Without this, every token rescans every object on the sheet set, which is
    quadratic in a dense drawing (thousands of tokens x thousands of objects).
    The object list is held in the cache so its identity cannot be recycled.
    """

    if _PAGE_INDEX_CACHE["objects"] is objects:
        return _PAGE_INDEX_CACHE["index"]

    index: Dict[int, List[tuple[float, float, dict]]] = {}
    for geometry in objects:
        center = geometry.get("center") or [0, 0]
        index.setdefault(int(geometry.get("page_number") or 0), []).append(
            (float(center[0]), float(center[1]), geometry)
        )
    _PAGE_INDEX_CACHE["objects"] = objects
    _PAGE_INDEX_CACHE["index"] = index
    return index


class GeometryFeatureProvider:
    name = "pdf_geometry_features"

    def extract(self, context: Dict[str, Any]) -> Dict[str, Any]:
        token = context["token"]
        page = int(token.get("page") or 0)
        bbox = token.get("bbox") or [0, 0, 0, 0]
        center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        objects = context.get("geometry", {}).get("objects") or []
        nearest: Optional[tuple[float, dict]] = None
        for other_x, other_y, geometry in _objects_by_page(objects).get(page, ()):
            distance = math.hypot(center[0] - other_x, center[1] - other_y)
            if nearest is None or distance < nearest[0]:
                nearest = (distance, geometry)
        if not nearest:
            return {
                "available": False,
                "nearest_distance": 999.0,
                "similarity": 0.0,
                "object": None,
            }
        distance, obj = nearest
        embedding = obj.get("geometry_embedding") or []
        proximity = max(0.0, 1.0 - distance / 180.0)
        # Learned visual similarity is preferred; the vector-geometry signal
        # keeps the modality usable before the embedding index is trained.
        kind_bonus = (
            0.1
            if obj.get("kind")
            in {"line", "polyline", "dimension", "leader", "rectangle"}
            else 0.0
        )
        similarity = (
            float(obj.get("geometry_similarity") or 0.0)
            if embedding
            else min(1.0, max(0.1, proximity) + kind_bonus)
        )
        return {
            "available": True,
            "nearest_distance": round(distance, 3),
            "similarity": round(similarity, 6),
            "similarity_source": "geometry_embedding" if embedding else "vector_geometry",
            "geometry_embedding": embedding,
            "geometry_confidence": float(obj.get("geometry_confidence") or 0.0),
            "geometry_role": obj.get("geometry_role"),
            "geometry_orientation": obj.get("geometry_orientation"),
            "geometry_role_confidence": float(
                obj.get("geometry_role_confidence")
                or obj.get("geometry_confidence")
                or 0.0
            ),
            "geometry_candidates": obj.get("geometry_candidates") or [],
            "geometry_features": obj.get("geometry_features")
            or {
                "length": obj.get("length"),
                "orientation": obj.get("orientation"),
                "aspect_ratio": obj.get("aspect_ratio"),
                "width": obj.get("width"),
                "height": obj.get("height"),
                "area": obj.get("area"),
                "bbox": obj.get("bbox"),
            },
            "fallback_proximity": round(proximity, 4),
            "object": {
                "object_id": obj.get("object_id") or obj.get("geometry_id"),
                "kind": obj.get("kind"),
                "bbox": obj.get("bbox"),
                "length": obj.get("length"),
                "orientation": obj.get("orientation"),
                "geometry_role": obj.get("geometry_role"),
                "layer": obj.get("layer"),
            },
        }


class GraphFeatureProvider:
    name = "structural_graph_features"

    def __init__(self) -> None:
        self._lookup_fingerprint: Optional[tuple] = None
        self._lookup: Optional[Dict[str, Any]] = None

    @staticmethod
    def _fingerprint(graph: Dict[str, Any]) -> tuple:
        nodes = graph.get("nodes") or []
        return (
            id(graph),
            len(nodes),
            len(graph.get("edges") or []),
            str((nodes[0] or {}).get("node_id")) if nodes else "",
        )

    def _source_lookup(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        # One index per graph, reused across the whole prediction loop; a
        # per-token scan of every node would be quadratic on real drawings.
        fingerprint = self._fingerprint(graph)
        if self._lookup_fingerprint != fingerprint or self._lookup is None:
            self._lookup = build_source_lookup(graph)
            self._lookup_fingerprint = fingerprint
        return self._lookup

    def extract(self, context: Dict[str, Any]) -> Dict[str, Any]:
        graph = context.get("graph") or {}
        if not graph.get("nodes"):
            return graph_features_for_token(graph, context["token"])
        return graph_features_for_token(
            graph, context["token"], lookup=self._source_lookup(graph)
        )


class DatabaseFeatureProvider:
    name = "aisc_database_features"

    def extract(self, context: Dict[str, Any]) -> Dict[str, Any]:
        token = str(context["token"].get("normalized_text") or "")
        exact = lookup_shape(token)
        similar = search_similar_shapes(token, limit=8, minimum_score=0.35)
        return {
            "exact_match": exact,
            "database_match": exact is not None,
            "similar_shapes": similar,
            "best_similarity": (
                1.0 if exact else float(similar[0]["similarity"]) if similar else 0.0
            ),
        }
