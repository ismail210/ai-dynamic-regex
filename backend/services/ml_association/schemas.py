"""Versioned pydantic models for the ML-association review dataset.

Mirrors the style of ``services.prediction.canonical_contract`` (small,
named, nested ``BaseModel``s rather than one flat dict) since that is
this repository's established pattern for an auditable, schema-versioned
contract.

Design principle carried over from the geometry/graph audit
(``docs/geometry_graph_audit/02_logic_inventory.md``): raw extraction,
normalized text, heuristic prediction, and reviewed human truth are kept
in clearly separate, clearly named fields/models — never merged into one
ambiguous value. ``HeuristicEvidence.current_heuristic_score`` is
explicitly documented as NOT a probability, for the same reason the
audit flagged this exact confusion in the production prediction
pipeline.

Every "was this available" field that could otherwise default to a
misleading ``0``/``False`` instead carries an explicit
``*_available: bool`` sibling (e.g. ``region_available``,
``scale_available``) — per the Phase 2 spec's instruction not to hide
missing data behind default zeros.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from services.ml_association.enums import AdjudicationStatus, CalloutScope, ReviewLabel

SCHEMA_VERSION = "2.0"

# The no-valid-target candidate row's reserved geometry_entity_id / node id.
# Never collides with a real geometry_id (see identifiers.py) because real
# IDs are always prefixed "geo_" from a content hash.
NO_MATCH_CANDIDATE_TOKEN = "no_match"


class LabelEvidence(BaseModel):
    """Raw + lightly-derived evidence about the text/label entity.

    ``raw_text``/``normalized_text`` are never overwritten once written —
    same discipline as ``canonical_contract.SourceText``.
    """

    raw_text: str
    normalized_text: Optional[str] = None
    text_bbox: List[float]
    text_center: List[float]
    text_rotation: Optional[float] = None
    text_height: Optional[float] = None
    parsed_family: Optional[str] = None
    label_type: Optional[str] = None
    source_token_metadata: Dict[str, Any] = Field(default_factory=dict)


class GeometryEvidence(BaseModel):
    """Raw + lightly-derived evidence about one geometry candidate.

    ``None`` when this row is the synthetic no-valid-target placeholder
    (see ``NO_MATCH_CANDIDATE_TOKEN``).
    """

    geometry_bbox: List[float]
    geometry_center: List[float]
    geometry_kind: Optional[str] = None
    current_heuristic_role: Optional[str] = None
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    area: Optional[float] = None
    aspect_ratio: Optional[float] = None
    orientation: Optional[float] = None
    segment_count: Optional[int] = None
    page_edge_distance: Optional[float] = None


class RelationshipFeatures(BaseModel):
    """Computed label<->geometry relationship/context features.

    All distance fields are in raw PDF-point units unless a
    ``*_normalized_by_*`` sibling is populated — see
    docs/geometry_graph_audit/03_geometry_audit.md for why raw-point
    thresholds alone are not scale-aware. ``distance_normalized_by_scale``
    stays ``None`` (with ``distance_scale_available=False``) until real
    drawing-scale detection exists (open question, tracked in
    docs/geometry_graph_audit/09_open_questions.md Q4) — never silently 0.
    """

    centroid_distance: Optional[float] = None
    bbox_distance: Optional[float] = None
    nearest_endpoint_distance: Optional[float] = None

    distance_normalized_by_page: Optional[float] = None
    distance_normalized_by_text_height: Optional[float] = None
    distance_normalized_by_scale: Optional[float] = None
    distance_scale_available: bool = False

    horizontal_offset: Optional[float] = None
    vertical_offset: Optional[float] = None
    relative_orientation: Optional[float] = None

    bbox_intersects: bool = False
    bbox_contains: bool = False
    bbox_overlap_ratio: float = 0.0

    same_region: Optional[bool] = None
    region_available: bool = False

    local_line_density: Optional[int] = None
    endpoint_degree: Optional[int] = None
    intersection_count: Optional[int] = None
    parallel_neighbor_count: Optional[int] = None
    perpendicular_neighbor_count: Optional[int] = None
    nearby_steel_label_count: Optional[int] = None

    leader_support_evidence: bool = False
    leader_path_ids: List[str] = Field(default_factory=list)

    graph_degree: Optional[int] = None
    graph_relation_summary: Dict[str, int] = Field(default_factory=dict)

    extraction_quality_flags: List[str] = Field(default_factory=list)
    candidate_generation_sources: List[str] = Field(default_factory=list)


class HeuristicEvidence(BaseModel):
    """Current production-heuristic evidence for this candidate.

    ``current_heuristic_score`` is a heuristic distance/weight-derived
    number, NOT a calibrated probability -- see
    docs/geometry_graph_audit/02_logic_inventory.md's ranking-logic
    section for the same distinction drawn about the live prediction
    pipeline. Never format or describe it as "% likely correct".
    """

    current_heuristic_score: Optional[float] = None
    current_heuristic_rank: Optional[int] = None
    current_heuristic_selected: bool = False


class AssociationCandidateRow(BaseModel):
    """One (label entity, geometry candidate, local context) row.

    ``schema_version`` is stamped per-row (not just per-file) so rows
    from different pipeline versions can be mixed in one JSONL/CSV
    export without ambiguity.
    """

    schema_version: str = SCHEMA_VERSION

    # Identity / provenance
    project_id: str
    document_id: str
    source_file_hash: Optional[str] = None
    page_id: str
    page_number: int
    region_id: Optional[str] = None
    text_entity_id: str
    geometry_entity_id: Optional[str] = None  # None for the no-match placeholder row
    association_candidate_id: str
    candidate_generator_version: str
    feature_generator_version: str
    extraction_version: Optional[str] = None
    pipeline_version: Optional[str] = None
    created_at: str

    is_no_match_placeholder: bool = False

    label: LabelEvidence
    geometry: Optional[GeometryEvidence] = None
    relationship: RelationshipFeatures = Field(default_factory=RelationshipFeatures)
    heuristic: HeuristicEvidence = Field(default_factory=HeuristicEvidence)


class LabelGroup(BaseModel):
    """One label entity plus its full candidate set (query group)."""

    schema_version: str = SCHEMA_VERSION
    group_id: str

    project_id: str
    document_id: str
    page_id: str
    page_number: int
    region_id: Optional[str] = None
    text_entity_id: str

    label: LabelEvidence
    candidates: List[AssociationCandidateRow] = Field(default_factory=list)

    nearby_label_ids: List[str] = Field(default_factory=list)
    extraction_diagnostics: Dict[str, Any] = Field(default_factory=dict)

    candidate_generator_version: str
    feature_generator_version: str
    created_at: str

    def candidate_ids(self) -> List[str]:
        return [c.association_candidate_id for c in self.candidates]

    def selected_candidate_id(self) -> Optional[str]:
        for candidate in self.candidates:
            if candidate.heuristic.current_heuristic_selected:
                return candidate.association_candidate_id
        return None


class ReviewExportPayload(BaseModel):
    """One deterministic reviewer-export bundle for a single label group.

    ``svg_relative_path`` points at the sibling SVG file (see
    ``review_export.py``) rather than embedding the SVG inline, so the
    JSON metadata and the visual artifact can be diffed/inspected
    independently.
    """

    export_schema_version: str = SCHEMA_VERSION
    group: LabelGroup
    svg_relative_path: str
    heuristic_selection_candidate_id: Optional[str] = None
    no_valid_target_option: str = NO_MATCH_CANDIDATE_TOKEN
    multi_target_supported: bool = True
    review_label_options: List[str] = Field(default_factory=lambda: [v.value for v in ReviewLabel])
    callout_scope_options: List[str] = Field(default_factory=lambda: [v.value for v in CalloutScope])
    annotation_notes_field: str = "annotation_notes"


class ReviewedOutcome(BaseModel):
    """One append-only reviewer decision for a label group.

    Never mutated after creation (enforced by ``outcome_store``, not by
    this model). A correction is a NEW ``ReviewedOutcome`` whose
    ``supersedes_outcome_id`` points at the one it replaces — the full
    history is always retrievable; only the *latest valid* outcome is
    used as training truth (see ``outcome_store.latest_outcomes``).
    """

    schema_version: str = SCHEMA_VERSION
    outcome_id: str

    group_id: str
    project_id: str
    document_id: str
    page_id: str
    text_entity_id: str

    review_label: ReviewLabel
    reviewed_target_geometry_ids: List[str] = Field(default_factory=list)
    candidate_generation_miss: bool = False
    callout_scope: CalloutScope
    adjudication_status: AdjudicationStatus = AdjudicationStatus.REVIEWED

    reviewer_id: str
    reviewed_at: str
    annotation_notes: Optional[str] = None

    prior_prediction_snapshot: Dict[str, Any] = Field(default_factory=dict)
    candidate_set_snapshot: List[str] = Field(default_factory=list)
    supersedes_outcome_id: Optional[str] = None


class ReviewImportEntry(BaseModel):
    """The raw shape a reviewer submission is parsed from.

    Deliberately looser / more permissive than ``ReviewedOutcome`` --
    this is untrusted input. ``validation.py`` turns instances of this
    (plus the ``LabelGroup`` it claims to review) into either an accepted
    ``ReviewedOutcome`` or a list of ``ValidationError``s.
    """

    export_schema_version: str
    group_id: str
    project_id: str
    document_id: str
    page_id: str
    region_id: Optional[str] = None
    text_entity_id: str

    review_label: str
    reviewed_target_geometry_ids: List[str] = Field(default_factory=list)
    candidate_generation_miss: bool = False
    callout_scope: str

    reviewer_id: Optional[str] = None
    reviewed_at: Optional[str] = None
    annotation_notes: Optional[str] = None
    supersedes_outcome_id: Optional[str] = None


class ValidationError(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class ValidationResult(BaseModel):
    valid: bool
    errors: List[ValidationError] = Field(default_factory=list)
    outcome: Optional[ReviewedOutcome] = None
