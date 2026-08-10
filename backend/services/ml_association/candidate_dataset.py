"""Deterministic label-group + candidate-row construction.

Builds the versioned association dataset (``schemas.LabelGroup`` /
``AssociationCandidateRow``) from a document's extraction output, using:

* ``graph_builder.build_text_nodes`` / ``build_geometry_nodes`` (Phase 1)
  for node shape, so this dataset's entities are identical to the
  production graph's;
* ``spatial_index`` (Phase 1, experimental) for spatially-complete,
  extraction-order-independent candidate generation and leader-endpoint
  resolution;
* ``graph_builder.build_graph`` for the CURRENT PRODUCTION heuristic's
  actual single-pick ``nearest_geometry`` selection, so
  ``HeuristicEvidence`` reflects real production behavior, not the
  experimental generator's own ranking. This never overwrites or
  influences that behavior -- it only reads it as evidence.

Nothing in this module writes to any production artifact path or is
imported by the live pipeline (see
backend/tests/test_ml_association_not_wired_into_production.py).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.engineering import graph_builder, spatial_index
from services.ml_association import identifiers
from services.ml_association.feature_builder import build_relationship_features
from services.ml_association.schemas import (
    NO_MATCH_CANDIDATE_TOKEN,
    AssociationCandidateRow,
    GeometryEvidence,
    HeuristicEvidence,
    LabelEvidence,
    LabelGroup,
)

DEFAULT_TOP_K = 5
DEFAULT_MAX_DISTANCE = spatial_index.DEFAULT_MAX_DISTANCE
DEFAULT_CANDIDATE_GENERATOR_VERSION = "spatial_index_v1"
DEFAULT_FEATURE_GENERATOR_VERSION = "feature_builder_v1"

# Mirrors graph_builder.py's own semantic_kinds set -- "a real steel label",
# not any text node (excludes plain body-prose TEXT kind).
_STEEL_LABEL_KINDS = {
    "label",
    "beam",
    "column",
    "plate",
    "brace",
    "bolt",
    "weld",
    "connection",
}

_STRUCTURAL_RELATIONS = {
    "connected_to",
    "supports",
    "supported_by",
    "inside",
    "touching",
    "intersects",
    "near",
}


def _page_dimensions(document_structure: dict, page_number: int) -> Tuple[Optional[float], Optional[float]]:
    for page in document_structure.get("pages") or []:
        if int(page.get("page_number") or 0) == page_number:
            return page.get("width"), page.get("height")
    return None, None


def _page_diagnostics(geometry: dict, graph: Optional[dict], page_number: int) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {}
    for summary in geometry.get("page_summaries") or []:
        if int(summary.get("page_number") or 0) == page_number:
            diagnostics["geometry"] = summary
            break
    if graph:
        for entry in graph.get("diagnostics") or []:
            if int(entry.get("page_number") or 0) == page_number:
                diagnostics["graph"] = entry
                break
    return diagnostics


def _edges_by_node(graph: dict) -> Dict[str, List[dict]]:
    by_node: Dict[str, List[dict]] = {}
    for edge in graph.get("edges") or []:
        by_node.setdefault(edge.get("source"), []).append(edge)
        by_node.setdefault(edge.get("target"), []).append(edge)
    return by_node


def _graph_context_for_node(
    node_id: str,
    edges_by_node: Dict[str, List[dict]],
    source_features: Dict[str, dict],
    source_id: Optional[str],
) -> Dict[str, Any]:
    incident = edges_by_node.get(node_id, [])
    relation_summary = dict(Counter(e.get("relationship") for e in incident if e.get("relationship")))
    degree = len(incident)
    if source_id and str(source_id) in source_features:
        degree = int(source_features[str(source_id)].get("degree", degree))
    return {
        "graph_degree": degree,
        "graph_relation_summary": relation_summary,
        "endpoint_degree": degree,
        "intersection_count": relation_summary.get("intersection", 0)
        + relation_summary.get("intersects", 0),
        "parallel_neighbor_count": relation_summary.get("parallel", 0),
        "perpendicular_neighbor_count": relation_summary.get("perpendicular", 0),
        "local_line_density": sum(
            relation_summary.get(rel, 0) for rel in ("distance", "adjacent")
        ),
    }


def _production_heuristic_selection(
    text_nodes: Sequence[dict], graph: dict
) -> Dict[str, Tuple[str, float]]:
    """For each label node_id, the geometry ``source_id`` (and edge
    weight) that PRODUCTION's greedy ``nearest_geometry`` edge actually
    picked -- reproduced from ``graph["edges"]``, not recomputed
    independently, so this is guaranteed to match live behavior exactly.
    """

    node_by_id = {n["node_id"]: n for n in graph.get("nodes") or []}
    selection: Dict[str, Tuple[str, float]] = {}
    for edge in graph.get("edges") or []:
        if edge.get("relationship") != "nearest_geometry":
            continue
        target_node = node_by_id.get(edge.get("target"))
        if not target_node or not target_node.get("source_id"):
            continue
        selection[edge["source"]] = (
            str(target_node["source_id"]),
            float(edge.get("weight") or 0.0),
        )
    return selection


def _nearby_label_ids(label_node: dict, page_labels: Sequence[dict], *, radius: float) -> List[str]:
    ids = []
    for other in page_labels:
        if other is label_node or not other.get("source_id"):
            continue
        d = math.hypot(
            float(other["center"][0]) - float(label_node["center"][0]),
            float(other["center"][1]) - float(label_node["center"][1]),
        )
        if d <= radius:
            ids.append(str(other["source_id"]))
    return sorted(ids)


def _nearby_steel_label_count(
    geometry_node: dict, page_labels: Sequence[dict], *, radius: float
) -> int:
    count = 0
    for label in page_labels:
        if label.get("kind") not in _STEEL_LABEL_KINDS:
            continue
        d = math.hypot(
            float(label["center"][0]) - float(geometry_node["center"][0]),
            float(label["center"][1]) - float(geometry_node["center"][1]),
        )
        if d <= radius:
            count += 1
    return count


def _build_candidate_row(
    *,
    label_node: dict,
    geometry_node: Optional[dict],
    project_id: str,
    document_id: str,
    source_file_hash: Optional[str],
    page_id_value: str,
    page_number: int,
    candidate_generator_version: str,
    feature_generator_version: str,
    extraction_version: Optional[str],
    pipeline_version: Optional[str],
    created_at: str,
    text_entity_id: str,
    heuristic_selection: Dict[str, Tuple[str, float]],
    label_node_id: str,
    candidate_sources: Sequence[str],
    context: Dict[str, Any],
    label_evidence: LabelEvidence,
) -> AssociationCandidateRow:
    geometry_entity_id = geometry_node["source_id"] if geometry_node else None
    if geometry_entity_id is not None:
        geometry_entity_id = str(geometry_entity_id)

    selected_id, selected_weight = heuristic_selection.get(label_node_id, (None, None))
    current_heuristic_selected = (
        geometry_entity_id is not None and geometry_entity_id == selected_id
    )

    relationship = build_relationship_features(
        label_node,
        geometry_node,
        page_width=context.get("page_width"),
        page_height=context.get("page_height"),
        text_height=label_evidence.text_height,
        scale_value=None,  # no scale detection exists yet -- see schema docstring
        context={
            **context,
            "candidate_generation_sources": list(candidate_sources),
            "leader_support_evidence": "leader_endpoint_resolved" in candidate_sources,
        },
    )

    geometry_evidence = None
    if geometry_node is not None:
        geometry_evidence = GeometryEvidence(
            geometry_bbox=list(geometry_node.get("bbox") or []),
            geometry_center=list(geometry_node.get("center") or []),
            geometry_kind=geometry_node.get("geometry_kind"),
            current_heuristic_role=geometry_node.get("kind"),
            length=geometry_node.get("length"),
            width=geometry_node.get("width"),
            height=None,
            area=geometry_node.get("area"),
            aspect_ratio=None,
            orientation=geometry_node.get("orientation"),
            segment_count=None,
            page_edge_distance=context.get("page_edge_distance"),
        )

    return AssociationCandidateRow(
        project_id=project_id,
        document_id=document_id,
        source_file_hash=source_file_hash,
        page_id=page_id_value,
        page_number=page_number,
        region_id=None,  # no region-detection layer exists yet (P1.4)
        text_entity_id=text_entity_id,
        geometry_entity_id=geometry_entity_id,
        association_candidate_id=identifiers.association_candidate_id(
            text_entity_id, geometry_entity_id, candidate_generator_version
        ),
        candidate_generator_version=candidate_generator_version,
        feature_generator_version=feature_generator_version,
        extraction_version=extraction_version,
        pipeline_version=pipeline_version,
        created_at=created_at,
        is_no_match_placeholder=geometry_node is None,
        label=label_evidence,
        geometry=geometry_evidence,
        relationship=relationship,
        heuristic=HeuristicEvidence(
            current_heuristic_score=selected_weight if current_heuristic_selected else None,
            current_heuristic_rank=1 if current_heuristic_selected else None,
            current_heuristic_selected=current_heuristic_selected,
        ),
    )


def build_label_groups(
    document_structure: dict,
    geometry: dict,
    *,
    project_id: str,
    document_id: str,
    created_at: str,
    source_file_hash: Optional[str] = None,
    graph: Optional[dict] = None,
    candidate_generator_version: str = DEFAULT_CANDIDATE_GENERATOR_VERSION,
    feature_generator_version: str = DEFAULT_FEATURE_GENERATOR_VERSION,
    extraction_version: Optional[str] = None,
    pipeline_version: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    include_no_match_candidate: bool = True,
    nearby_label_radius: float = DEFAULT_MAX_DISTANCE,
) -> List[LabelGroup]:
    """Build deterministic label groups for every page of a document.

    ``project_id``/``document_id`` are required, caller-supplied inputs
    -- this repository has no project-grouping concept anywhere yet
    (docs/geometry_graph_audit/09_open_questions.md), so Phase 2
    deliberately does not invent one; the caller (a human, or a future
    ingestion step) decides what project a document belongs to.

    ``created_at`` is required (not defaulted to "now") specifically so
    two calls with the same inputs and the same ``created_at`` produce
    byte-identical output -- see
    backend/tests/test_ml_association_candidate_dataset.py's
    reproducibility test.
    """

    if graph is None:
        graph = graph_builder.build_graph(document_structure, geometry)

    text_nodes = graph_builder.build_text_nodes(document_structure)
    geometry_nodes = graph_builder.build_geometry_nodes(geometry)
    heuristic_selection = _production_heuristic_selection(text_nodes, graph)
    edges_by_node = _edges_by_node(graph)
    source_features = graph.get("source_features") or {}

    by_page_text: Dict[int, List[dict]] = {}
    by_page_geometry: Dict[int, List[dict]] = {}
    for node in text_nodes:
        by_page_text.setdefault(int(node.get("page_number") or 0), []).append(node)
    for node in geometry_nodes:
        by_page_geometry.setdefault(int(node.get("page_number") or 0), []).append(node)

    groups: List[LabelGroup] = []
    for page_number in sorted(set(by_page_text) | set(by_page_geometry)):
        page_labels = [
            n for n in by_page_text.get(page_number, []) if n.get("kind") in _STEEL_LABEL_KINDS
        ]
        page_geometry = by_page_geometry.get(page_number, [])
        page_width, page_height = _page_dimensions(document_structure, page_number)
        page_diagnostics = _page_diagnostics(geometry, graph, page_number)
        page_id_value = identifiers.page_id(document_id, page_number)

        tree = None
        ordered_geometry = []
        if page_geometry:
            tree, ordered_geometry = spatial_index.build_page_index(page_geometry)

        for label_node in sorted(page_labels, key=lambda n: str(n.get("source_id") or n["node_id"])):
            text_entity_id = str(label_node.get("source_id") or label_node["node_id"])
            label_evidence = LabelEvidence(
                raw_text=label_node.get("text") or "",
                normalized_text=None,
                text_bbox=list(label_node.get("bbox") or []),
                text_center=list(label_node.get("center") or []),
                text_rotation=label_node.get("rotation"),
                text_height=label_node.get("font_size"),
                parsed_family=None,
                label_type=label_node.get("kind"),
                source_token_metadata={
                    "engineering_object_type": label_node.get("engineering_object_type"),
                },
            )

            candidates: List[AssociationCandidateRow] = []
            if tree is not None:
                spatial_candidates = spatial_index.nearest_geometry_candidates(
                    label_node, tree, ordered_geometry, max_distance=max_distance, top_k=top_k
                )
                for spatial_candidate in spatial_candidates:
                    geometry_node = next(
                        (n for n in ordered_geometry if n["node_id"] == spatial_candidate.node_id),
                        None,
                    )
                    if geometry_node is None:
                        continue
                    context = {
                        "page_width": page_width,
                        "page_height": page_height,
                        "extraction_quality_flags": [],
                        **_graph_context_for_node(
                            geometry_node["node_id"],
                            edges_by_node,
                            source_features,
                            geometry_node.get("source_id"),
                        ),
                        "nearby_steel_label_count": _nearby_steel_label_count(
                            geometry_node, page_labels, radius=max_distance
                        ),
                    }
                    candidates.append(
                        _build_candidate_row(
                            label_node=label_node,
                            geometry_node=geometry_node,
                            project_id=project_id,
                            document_id=document_id,
                            source_file_hash=source_file_hash,
                            page_id_value=page_id_value,
                            page_number=page_number,
                            candidate_generator_version=candidate_generator_version,
                            feature_generator_version=feature_generator_version,
                            extraction_version=extraction_version,
                            pipeline_version=pipeline_version,
                            created_at=created_at,
                            text_entity_id=text_entity_id,
                            heuristic_selection=heuristic_selection,
                            label_node_id=label_node["node_id"],
                            candidate_sources=spatial_candidate.sources,
                            context=context,
                            label_evidence=label_evidence,
                        )
                    )

            if include_no_match_candidate:
                candidates.append(
                    _build_candidate_row(
                        label_node=label_node,
                        geometry_node=None,
                        project_id=project_id,
                        document_id=document_id,
                        source_file_hash=source_file_hash,
                        page_id_value=page_id_value,
                        page_number=page_number,
                        candidate_generator_version=candidate_generator_version,
                        feature_generator_version=feature_generator_version,
                        extraction_version=extraction_version,
                        pipeline_version=pipeline_version,
                        created_at=created_at,
                        text_entity_id=text_entity_id,
                        heuristic_selection=heuristic_selection,
                        label_node_id=label_node["node_id"],
                        candidate_sources=[],
                        context={"extraction_quality_flags": []},
                        label_evidence=label_evidence,
                    )
                )

            group = LabelGroup(
                group_id=identifiers.group_id(text_entity_id, candidate_generator_version),
                project_id=project_id,
                document_id=document_id,
                page_id=page_id_value,
                page_number=page_number,
                region_id=None,
                text_entity_id=text_entity_id,
                label=label_evidence,
                candidates=candidates,
                nearby_label_ids=_nearby_label_ids(
                    label_node, page_labels, radius=nearby_label_radius
                ),
                extraction_diagnostics=page_diagnostics,
                candidate_generator_version=candidate_generator_version,
                feature_generator_version=feature_generator_version,
                created_at=created_at,
            )
            groups.append(group)

    groups.sort(key=lambda g: (g.page_number, g.text_entity_id))
    return groups
