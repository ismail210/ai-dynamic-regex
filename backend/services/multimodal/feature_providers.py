"""Independent text, geometry, graph, and database feature providers."""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from services.database_loader import lookup_shape, search_similar_shapes
from services.engineering.structural_graph import (
    build_source_lookup,
    graph_features_for_token,
)
from services.feature_extractor import extract_structural_features
from services.model_predictor import predict_with_confidence


class _KeyedCache:
    """Thread-safe, bounded, content-keyed cache.

    Replaces the "single global mutable slot, overwritten on every miss"
    pattern that previously backed both the geometry page-index cache and
    the graph source-index cache. That pattern is a real correctness bug
    under concurrency, not just a performance detail: two threads handling
    *different* documents at the same time could interleave a
    check-then-write on the shared slot such that one document's cached
    index silently got used to answer another document's lookup — a
    positional token ID (e.g. ``token_p3_32``) colliding between two
    unrelated documents would then attach the wrong graph/geometry evidence
    to a prediction, with no error raised.

    Keying by content fingerprint instead of overwriting a single slot means
    a reader can only ever be served the entry for its OWN fingerprint —
    concurrent writes for different documents land in different dict
    entries, so there is no cross-document data path at all. The bounded
    size (evicting least-recently-used entries) keeps memory flat even if
    many distinct documents are analyzed in the same process lifetime.
    """

    def __init__(self, max_entries: int = 8) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: "OrderedDict[Any, Any]" = OrderedDict()

    def get(self, key: Any) -> Optional[Any]:
        with self._lock:
            value = self._entries.get(key)
            if value is not None:
                self._entries.move_to_end(key)
            return value

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


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


_PAGE_INDEX_CACHE = _KeyedCache(max_entries=8)


def _objects_fingerprint(objects: List[dict]) -> tuple:
    """Content-based identity for a document's geometry object list.

    Deliberately NOT based on Python object identity (``is``)/``id()``: two
    unrelated documents processed concurrently could otherwise be assigned
    the same memory address once one list is garbage collected, or — more
    subtly — the previous single-slot cache didn't even need an identity
    collision to fail, since a second document's ``_objects_by_page`` call
    would simply overwrite the shared slot the first document's call was
    about to read from.
    """

    if not objects:
        return (0, "", "")
    first = objects[0] or {}
    last = objects[-1] or {}
    return (
        len(objects),
        str(first.get("object_id") or first.get("geometry_id") or ""),
        str(last.get("object_id") or last.get("geometry_id") or ""),
    )


def _objects_by_page(objects: List[dict]) -> Dict[int, List[tuple[float, float, dict]]]:
    """
    Group geometry by page once per document, with centers pre-unpacked.

    Without this, every token rescans every object on the sheet set, which is
    quadratic in a dense drawing (thousands of tokens x thousands of objects).
    Cached per-document (see ``_KeyedCache``) so concurrent analyze calls for
    different documents can never read each other's page index.
    """

    fingerprint = _objects_fingerprint(objects)
    cached = _PAGE_INDEX_CACHE.get(fingerprint)
    if cached is not None:
        return cached

    index: Dict[int, List[tuple[float, float, dict]]] = {}
    for geometry in objects:
        center = geometry.get("center") or [0, 0]
        index.setdefault(int(geometry.get("page_number") or 0), []).append(
            (float(center[0]), float(center[1]), geometry)
        )
    _PAGE_INDEX_CACHE.put(fingerprint, index)
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
        # Bounded, content-keyed cache (see ``_KeyedCache``) — NOT a single
        # mutable "current graph" slot. The prior single-slot design was a
        # real accuracy bug under concurrency: this provider is a
        # process-lifetime singleton (see ``orchestrator._graph_provider``),
        # so two concurrent /analyze calls for two DIFFERENT documents could
        # interleave a check-then-write on the one shared slot such that a
        # prediction for document A got scored against document B's graph
        # source-index — silently attaching the wrong ``source_node``/
        # ``node_kind``/``degree`` evidence, with no error raised. Keying by
        # content fingerprint instead means each document's lookup can only
        # ever be served from its own cache entry.
        self._lookups = _KeyedCache(max_entries=8)

    @staticmethod
    def _fingerprint(graph: Dict[str, Any]) -> tuple:
        # Deliberately content-based, not ``id(graph)``: two different
        # documents' graph dicts could coincidentally receive the same
        # Python object id once one is garbage collected, which would be a
        # silent cross-document cache hit rather than a safe miss.
        nodes = graph.get("nodes") or []
        return (
            len(nodes),
            len(graph.get("edges") or []),
            str((nodes[0] or {}).get("node_id")) if nodes else "",
            str((nodes[-1] or {}).get("node_id")) if nodes else "",
        )

    def _source_lookup(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        # One index per graph, reused across the whole prediction loop; a
        # per-token scan of every node would be quadratic on real drawings.
        fingerprint = self._fingerprint(graph)
        cached = self._lookups.get(fingerprint)
        if cached is not None:
            return cached
        built = build_source_lookup(graph)
        self._lookups.put(fingerprint, built)
        return built

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
