"""GHX-INSPIRED geometry-association SHADOW layer (additive, Phase B/C).

Do not confuse this with ``services.semantic_preprocessor.association``
(``associate_via_ghx_pairing`` / ``associate_via_nearest_geometry`` /
``fuse_candidates``) -- that module is the EXISTING, already-shipped
association code and is left completely untouched by this file. This module
is a *parallel, opt-in* engine that never runs in production today (see
``config.Settings.ghx_inspired_association_enabled`` -- defaults False, and
nothing in ``semantic_document_service.run_semantic_pipeline`` calls this
module yet). Its only job right now is to be run in SHADOW MODE, alongside
the existing association, and compared -- see ``compare_with_existing``.

Where this comes from
----------------------
A forensic, read-only audit of the team's real production Grasshopper
definition (``estima3d_web_plan.ghx`` -- see ``docs/ghx_geometry_audit.md``
in the sibling ``ai-dynamic-regex`` R&D repo) surfaced several strong,
GENERAL geometry-association principles the team's mature workflow already
relies on: orientation-aware candidate reduction, actual-curve (not
centroid-only) distance, spatial pre-filtering, one-to-one conflict
resolution between competing labels, separate strategies for straight vs.
curved members and special drafting conventions ("DO" callouts, misc
steel), and a two-pass primary/recovery structure with an explicit
first-class "unmatched" state. NONE of the GHX's own file, code, or numeric
thresholds are used here -- see ``AssociationConfig`` below: every
GHX-reference number (dist_limit=3/4/5/10, angle_tol=2/5, Y-tolerance=0.3)
was measured in Rhino/model coordinates, not this codebase's PDF-point
coordinate system, and the mapping between the two is not established (see
docs/upstream_semantic_preprocessor.md and the coordinate-system note
below). Every threshold here is instead a fresh, conservative, PDF-point
default, clearly labeled as needing calibration against real benchmark
data -- never a blind transplant.

Coordinate system
------------------
This module operates ENTIRELY in PDF point space (1/72 inch), the same
frame as ``SemanticAnnotation.original_anchor`` / ``original_axis`` and
``services.engineering.member_geometry``'s stroke geometry. No
``CoordinateTransform`` is used or needed here -- that class exists for the
PDF<->Rhino bridge the (separate, GHX-specific) ``associate_via_ghx_pairing``
path would need, which this module deliberately has nothing to do with.

Reuse, not reinvention
-----------------------
The actual-curve point-to-segment distance and the orientation->role-hint
bucketing are NOT reimplemented here -- they are imported directly from
``services.engineering.member_geometry``, which already carries this exact
logic in production (a different call path: OCR/extraction review
metadata, ``exclusive=True`` one-to-one claiming). Local spatial
prefiltering reuses ``services.engineering.spatial_index``'s STRtree
primitives (``build_page_index`` / ``query_within_radius``), which already
exist, are already tested, and already have zero production callers of
their own (i.e. adopting them here does not touch anything live). Nothing
in this module duplicates that code; it only imports and adapts it to
``services.semantic.models.GeometryEvidence``/``SemanticAnnotation`` shapes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.engineering.member_geometry import distance_point_to_geometry
from services.engineering.spatial_index import build_page_index, query_within_radius
from services.semantic.models import GeometryEvidence, SemanticAnnotation

# ---------------------------------------------------------------------------
# Enums (Section 9/14/15)
# ---------------------------------------------------------------------------


class AssociationRoute(str, Enum):
    """WHICH strategy classified/ranked the candidates. Independent of
    ``AssociationOrigin`` (which pass produced the result)."""

    STRAIGHT = "straight"
    CURVED = "curved"
    MISC = "misc"
    SPECIAL_DO = "special_do"


class AssociationOrigin(str, Enum):
    """WHICH pass produced this evidence."""

    PRIMARY = "primary"
    RECOVERY = "recovery"
    HUMAN = "human"


class TextOrientationClass(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    DIAGONAL_AT = "diagonal_at"  # ascending, ~0-90 deg
    DIAGONAL_SC = "diagonal_sc"  # descending, ~90-180 deg


class AssociationStatus(str, Enum):
    ASSOCIATED = "associated"
    UNMATCHED = "unmatched"


class OrientationEvidence(str, Enum):
    """Phase D1 (Section 5): a hard MATCH/no-match binary throws away the
    difference between "these two are genuinely incompatible" and "we don't
    actually know one side's orientation" -- and the Burrville forensic run
    proved the second case is common (see
    docs/validation/phase_d1_orientation_forensics.md): PDF text rotation is
    silently stubbed at a default in the current extraction pipeline for a
    confirmed, specific reason (a dict-key bug in
    services.pdf_parser._span_rotation, out of scope to fix from this
    shadow-only module), so a 0.0 reading is NOT proof of true horizontal
    text. UNKNOWN must never be punished the same as a real CONFLICT."""

    MATCH = "match"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


def evaluate_orientation_evidence(
    text_class: Optional[TextOrientationClass],
    text_reliable: bool,
    geometry_class: Optional[TextOrientationClass],
    geometry_reliable: bool,
) -> OrientationEvidence:
    """Pure three-state classifier (Section 5/10). Reliability is supplied
    by the caller, never guessed here -- what counts as "reliable" text or
    geometry orientation is a data-provenance question this module cannot
    answer from an angle value alone (see the forensic report's evidence on
    why bare presence of a rotation number is not proof of reliability)."""

    if not text_reliable or not geometry_reliable or text_class is None or geometry_class is None:
        return OrientationEvidence.UNKNOWN
    return OrientationEvidence.MATCH if text_class == geometry_class else OrientationEvidence.CONFLICT


class UnmatchedReason(str, Enum):
    """First-class taxonomy (Section 15) -- never collapsed to "low
    confidence"."""

    NO_LOCAL_GEOMETRY = "NO_LOCAL_GEOMETRY"
    ORIENTATION_MISMATCH = "ORIENTATION_MISMATCH"
    MULTIPLE_VALID_CANDIDATES = "MULTIPLE_VALID_CANDIDATES"
    GEOMETRY_ALREADY_CLAIMED = "GEOMETRY_ALREADY_CLAIMED"
    OUTSIDE_DISTANCE_GATE = "OUTSIDE_DISTANCE_GATE"
    UNSUPPORTED_GEOMETRY = "UNSUPPORTED_GEOMETRY"


REASON_ORIENTATION_COMPATIBLE = "ORIENTATION_COMPATIBLE"
REASON_WITHIN_DISTANCE_GATE = "WITHIN_DISTANCE_GATE"
REASON_NEAREST_VALID_GEOMETRY = "NEAREST_VALID_GEOMETRY"
REASON_CURVE_PROXIMITY = "CURVE_PROXIMITY"
REASON_RECOVERED = "RECOVERED_WIDER_GATE"
REASON_DO_ANNOTATION = "DO_ANNOTATION_PATTERN"
REASON_ONE_TO_ONE_RESOLVED = "ONE_TO_ONE_CONFLICT_RESOLVED"
REASON_LOST_CONFLICT = "LOST_ONE_TO_ONE_CONFLICT"
REASON_ORIENTATION_UNKNOWN = "ORIENTATION_UNKNOWN"


# ---------------------------------------------------------------------------
# Configuration -- EVERY threshold here is a fresh PDF-point default, not a
# transplanted GHX value (Section 16). Values are intentionally permissive
# defaults pending calibration against real benchmark measurements (see
# backend/scripts/measure_route_association_shadow.py).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssociationConfig:
    # Orientation bucketing tolerance for the Horizontal/Vertical buckets
    # (degrees either side of 0/90). The GHX reference used ~1 deg; that
    # number is Rhino-model-space and not reused here. 10 deg is a
    # conservative starting point for OCR/vector-extracted rotation noise.
    orientation_tolerance_deg: float = 10.0

    # Straight-route primary/recovery distance gates (PDF points). Primary
    # is set to services.engineering.member_geometry's own
    # DEFAULT_MAX_ASSOCIATION_DISTANCE_PT (100pt) -- an ALREADY-CALIBRATED
    # constant from this same codebase, same PDF-point coordinate system,
    # tuned against real drawings (per that module's "Burrville framing QA"
    # comment) -- not a fresh guess and not a GHX transplant. An initial
    # arbitrary 60pt guess measurably under-associated on a real benchmark
    # drawing (see docs/validation/phase_c_shadow_association_measurement.json);
    # reusing the team's own established constant is the correct fix, not
    # further guessing. Recovery widens it further, still bounded.
    straight_primary_max_distance_pt: float = 100.0
    straight_recovery_max_distance_pt: float = 200.0

    # Curved-route gates -- no orientation gate at all (Section 11).
    curved_primary_max_distance_pt: float = 100.0
    curved_recovery_max_distance_pt: float = 200.0

    # Misc-steel route (Section 13) -- looser, still bounded.
    misc_orientation_tolerance_deg: float = 25.0
    misc_max_distance_pt: float = 130.0

    # "DO" / repetition route (Section 12).
    do_orientation_tolerance_deg: float = 15.0
    do_max_distance_pt: float = 100.0

    # Tie margin: candidates within this of each other are "too close to
    # call" (mirrors the existing ``associate_via_nearest_geometry``'s
    # posture of surfacing ambiguity rather than guessing).
    ambiguity_margin_pt: float = 8.0

    # Reference-only. The GHX recovery pass used a secondary Y-axis
    # tolerance (~0.3 model units) alongside a widened search distance.
    # NOT implemented here: no PDF-points-per-model-unit calibration exists
    # (Section 16), so a Y-tolerance gate would be fabricated, not derived.
    # Left as an explicit False so nobody assumes it is silently active.
    recovery_y_tolerance_enabled: bool = False

    # Phase D1 (Section 5/10): when True, orientation gating uses the
    # three-state MATCH/UNKNOWN/CONFLICT policy (a candidate whose
    # orientation evidence is UNKNOWN stays eligible, tagged, rather than
    # being silently rejected the same as a real CONFLICT). Default False --
    # Phase C's hard binary gate stays the production shadow default;
    # nothing changes unless a caller opts in.
    use_three_state_orientation: bool = False


DEFAULT_CONFIG = AssociationConfig()

# Geometry types this module knows how to route. Anything else is reported
# as UNSUPPORTED_GEOMETRY rather than silently ignored.
_CURVED_GEOMETRY_TYPES = {"curved_beam"}
_MISC_GEOMETRY_TYPES = {"misc"}
_STRAIGHT_GEOMETRY_TYPES = {"beam_curve", "column", "moment"}


# ---------------------------------------------------------------------------
# Evidence object (Section 17) -- deliberately NOT a GeometryAssociation and
# NOT stored on SemanticAnnotation. Kept fully separate so shadow-mode
# output can never be mistaken for, or accidentally consumed as, the
# production association. Callers that want it visible in a SemanticDocument
# should put ``.to_dict()`` output under ``document.diagnostics`` (a
# pre-existing free-form bag -- see ``run_semantic_pipeline``'s own use of
# ``diagnostics["page_classes"]`` for precedent), never a new model field.
# ---------------------------------------------------------------------------


@dataclass
class AssociationEvidence:
    source_text_id: str
    geometry_id: Optional[str]
    route: str
    association_origin: str
    text_orientation: Optional[str]
    geometry_orientation: Optional[str]
    distance: Optional[float]
    candidate_count: int
    status: str
    reason_codes: List[str] = field(default_factory=list)
    page: Optional[int] = None
    coordinate_system: str = "pdf_points"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_text_id": self.source_text_id,
            "geometry_id": self.geometry_id,
            "route": self.route,
            "association_origin": self.association_origin,
            "text_orientation": self.text_orientation,
            "geometry_orientation": self.geometry_orientation,
            "distance": self.distance,
            "candidate_count": self.candidate_count,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "page": self.page,
            "coordinate_system": self.coordinate_system,
        }


# ---------------------------------------------------------------------------
# Orientation classification (Section 4)
# ---------------------------------------------------------------------------


def classify_orientation(
    angle_deg: Optional[float], config: AssociationConfig = DEFAULT_CONFIG
) -> Optional[TextOrientationClass]:
    """Buckets a 0-180 degree axis angle into the GHX's own four-way
    vocabulary. Returns None when no angle is available at all (never
    guesses "horizontal" as a default)."""

    if angle_deg is None:
        return None
    ang = float(angle_deg) % 180.0
    tol = float(config.orientation_tolerance_deg)
    if ang <= tol or ang >= 180.0 - tol:
        return TextOrientationClass.HORIZONTAL
    if abs(ang - 90.0) <= tol:
        return TextOrientationClass.VERTICAL
    if ang < 90.0:
        return TextOrientationClass.DIAGONAL_AT
    return TextOrientationClass.DIAGONAL_SC


def orientation_compatible(
    text_class: Optional[TextOrientationClass], geometry_class: Optional[TextOrientationClass]
) -> bool:
    """Strict compatibility: same bucket. Either side unknown -> treated as
    compatible (an unknown orientation must never SILENTLY reject a
    candidate; absence of a signal is not evidence against a match)."""

    if text_class is None or geometry_class is None:
        return True
    return text_class == geometry_class


def _orientation_value(angle_deg: Optional[float], config: AssociationConfig) -> Optional[str]:
    cls = classify_orientation(angle_deg, config)
    return cls.value if cls else None


def _text_orientation_deg(annotation: SemanticAnnotation) -> Optional[float]:
    """Reads the ANNOTATION's own original rotation, never a value derived
    from corrected/rendered text (Section 5's invariant already holds
    structurally: ``original_axis``/``original_anchor`` are set once, at
    grouping time, from raw source-fragment bboxes -- see
    ``services.semantic_preprocessor.grouping``)."""

    if annotation.original_axis and len(annotation.original_axis) >= 2:
        dx, dy = float(annotation.original_axis[0]), float(annotation.original_axis[1])
        if dx != 0.0 or dy != 0.0:
            return math.degrees(math.atan2(dy, dx)) % 180.0
    for frag in annotation.source_fragments:
        if frag.rotation_deg:
            return float(frag.rotation_deg) % 180.0
    return None


def _geometry_orientation_deg(geom: GeometryEvidence) -> Optional[float]:
    if geom.orientation:
        # Stored as a 1-or-2-element list; a bare angle is stored as [angle].
        if len(geom.orientation) == 1:
            return float(geom.orientation[0]) % 180.0
        if len(geom.orientation) >= 2:
            dx, dy = float(geom.orientation[0]), float(geom.orientation[1])
            return math.degrees(math.atan2(dy, dx)) % 180.0
    if geom.start and geom.end:
        dx = float(geom.end[0]) - float(geom.start[0])
        dy = float(geom.end[1]) - float(geom.start[1])
        if dx != 0.0 or dy != 0.0:
            return math.degrees(math.atan2(dy, dx)) % 180.0
    return None


def is_text_orientation_reliable(angle_deg: Optional[float]) -> bool:
    """Phase D1 finding: a confirmed bug in services.pdf_parser._span_rotation
    (reads span.get("dir"), which PyMuPDF never populates -- the real
    direction vector lives on the LINE dict -- so every span's computed
    rotation silently defaults to 0.0) makes an exact 0.0/180.0 reading
    indistinguishable from "never actually measured". The bug's only
    failure mode is defaulting to zero; it cannot fabricate a wrong
    NON-zero angle. So a genuinely non-zero value is trustworthy, while an
    exact-zero one is not proof of true horizontal text and must not be
    treated as reliable evidence."""

    if angle_deg is None:
        return False
    residual = angle_deg % 180.0
    residual = min(residual, 180.0 - residual)
    return residual > 1e-6


def is_geometry_orientation_reliable(angle_deg: Optional[float]) -> bool:
    """Geometry orientation is computed directly from real polyline
    endpoints (services.engineering.geometry_extractor), not subject to the
    text-side stub-default bug -- any present value is a real measurement.
    Whether that measurement reflects a TRUE member axis rather than a
    noisy merged fragment is a separate, still-open question (see the
    Phase D1 candidate-geometry-quality finding) that this flag is
    deliberately not trying to answer."""

    return angle_deg is not None


def is_do_annotation(annotation: SemanticAnnotation) -> bool:
    """Conservative textual heuristic for the "DO" repetition convention
    (Section 12) -- exact match only, never a substring, to avoid
    misclassifying a real section label that merely contains "DO"."""

    raw = (annotation.original_text or "").strip().upper()
    return raw in {"DO", "DITTO"}


# ---------------------------------------------------------------------------
# Local candidate generation (Section 7) -- page-scoped STRtree query,
# reusing services.engineering.spatial_index verbatim. One index per page,
# built once and reused across every annotation on that page (Section 29:
# cache reusable page-level spatial indexes).
# ---------------------------------------------------------------------------


class PageSpatialIndexCache:
    """Builds and memoizes one STRtree per page of ``GeometryEvidence``."""

    def __init__(self, geometry_by_page: Dict[int, List[GeometryEvidence]]):
        self._geometry_by_page = geometry_by_page
        self._cache: Dict[int, Tuple[Any, List[dict]]] = {}

    @staticmethod
    def _to_node(geom: GeometryEvidence) -> Optional[dict]:
        if geom.centroid is None and geom.bbox is None:
            return None
        center = geom.centroid or [
            (float(geom.bbox[0]) + float(geom.bbox[2])) / 2.0,
            (float(geom.bbox[1]) + float(geom.bbox[3])) / 2.0,
        ]
        return {
            "node_id": geom.geometry_id,
            "bbox": geom.bbox,
            "center": center,
            "geometry_kind": geom.geometry_type,
            "_geom": geom,
        }

    def query(self, page: int, center: Sequence[float], max_distance: float) -> List[GeometryEvidence]:
        if page not in self._cache:
            nodes = [n for n in (self._to_node(g) for g in self._geometry_by_page.get(page, [])) if n]
            self._cache[page] = build_page_index(nodes)
        tree, ordered = self._cache[page]
        if tree is None or not ordered:
            return []
        matches = query_within_radius(tree, ordered, center, max_distance=max_distance, use_bbox_distance=True)
        return [ordered[i]["_geom"] for i, _dist in matches]


# ---------------------------------------------------------------------------
# Route dispatch + per-route association (Sections 10-13)
# ---------------------------------------------------------------------------


def route_for_geometry(geom: GeometryEvidence) -> Optional[AssociationRoute]:
    if geom.geometry_type in _CURVED_GEOMETRY_TYPES:
        return AssociationRoute.CURVED
    if geom.geometry_type in _MISC_GEOMETRY_TYPES:
        return AssociationRoute.MISC
    if geom.geometry_type in _STRAIGHT_GEOMETRY_TYPES:
        return AssociationRoute.STRAIGHT
    return None  # UNSUPPORTED_GEOMETRY -- caller decides what that means


@dataclass
class _RankedCandidate:
    geometry: GeometryEvidence
    distance: float
    route: AssociationRoute
    reason_codes: List[str]
    orientation_evidence: Optional[OrientationEvidence] = None


def _rank_straight(
    annotation: SemanticAnnotation,
    candidates: List[GeometryEvidence],
    max_distance: float,
    config: AssociationConfig,
) -> List[_RankedCandidate]:
    anchor = annotation.original_anchor
    text_angle = _text_orientation_deg(annotation)
    text_class = classify_orientation(text_angle, config)
    text_reliable = is_text_orientation_reliable(text_angle)
    ranked: List[_RankedCandidate] = []
    for geom in candidates:
        if route_for_geometry(geom) != AssociationRoute.STRAIGHT:
            continue
        geom_angle = _geometry_orientation_deg(geom)
        geom_class = classify_orientation(geom_angle, config)
        geom_reliable = is_geometry_orientation_reliable(geom_angle)

        if config.use_three_state_orientation:
            evidence = evaluate_orientation_evidence(text_class, text_reliable, geom_class, geom_reliable)
            if evidence == OrientationEvidence.CONFLICT:
                continue
            reasons = [REASON_WITHIN_DISTANCE_GATE]
            reasons.append(REASON_ORIENTATION_COMPATIBLE if evidence == OrientationEvidence.MATCH else REASON_ORIENTATION_UNKNOWN)
        else:
            if not orientation_compatible(text_class, geom_class):
                continue
            evidence = None
            reasons = [REASON_WITHIN_DISTANCE_GATE]
            if text_class is not None and geom_class is not None:
                reasons.append(REASON_ORIENTATION_COMPATIBLE)

        d = distance_point_to_geometry(anchor, geom.to_dict())
        if d > max_distance:
            continue
        ranked.append(_RankedCandidate(geom, d, AssociationRoute.STRAIGHT, reasons, evidence))
    ranked.sort(key=lambda c: c.distance)
    return ranked


def _rank_curved(
    annotation: SemanticAnnotation,
    candidates: List[GeometryEvidence],
    max_distance: float,
    config: AssociationConfig,
) -> List[_RankedCandidate]:
    anchor = annotation.original_anchor
    ranked: List[_RankedCandidate] = []
    for geom in candidates:
        if route_for_geometry(geom) != AssociationRoute.CURVED:
            continue
        # No orientation gate for curved members (Section 11) -- sampled/
        # actual curve proximity only.
        d = distance_point_to_geometry(anchor, geom.to_dict())
        if d > max_distance:
            continue
        ranked.append(_RankedCandidate(geom, d, AssociationRoute.CURVED, [REASON_CURVE_PROXIMITY, REASON_WITHIN_DISTANCE_GATE]))
    ranked.sort(key=lambda c: c.distance)
    return ranked


def _rank_misc(
    annotation: SemanticAnnotation,
    candidates: List[GeometryEvidence],
    max_distance: float,
    config: AssociationConfig,
) -> List[_RankedCandidate]:
    anchor = annotation.original_anchor
    text_angle = _text_orientation_deg(annotation)
    loose_config = AssociationConfig(orientation_tolerance_deg=config.misc_orientation_tolerance_deg)
    text_class = classify_orientation(text_angle, loose_config)
    ranked: List[_RankedCandidate] = []
    for geom in candidates:
        if route_for_geometry(geom) != AssociationRoute.MISC:
            continue
        geom_angle = _geometry_orientation_deg(geom)
        geom_class = classify_orientation(geom_angle, loose_config)
        if not orientation_compatible(text_class, geom_class):
            continue
        d = distance_point_to_geometry(anchor, geom.to_dict())
        if d > max_distance:
            continue
        ranked.append(_RankedCandidate(geom, d, AssociationRoute.MISC, [REASON_WITHIN_DISTANCE_GATE]))
    ranked.sort(key=lambda c: c.distance)
    return ranked


def _rank_do(
    annotation: SemanticAnnotation,
    candidates: List[GeometryEvidence],
    max_distance: float,
    config: AssociationConfig,
) -> List[_RankedCandidate]:
    anchor = annotation.original_anchor
    text_angle = _text_orientation_deg(annotation)
    loose_config = AssociationConfig(orientation_tolerance_deg=config.do_orientation_tolerance_deg)
    text_class = classify_orientation(text_angle, loose_config)
    ranked: List[_RankedCandidate] = []
    for geom in candidates:
        route = route_for_geometry(geom)
        if route not in (AssociationRoute.STRAIGHT, AssociationRoute.CURVED):
            continue
        geom_angle = _geometry_orientation_deg(geom)
        geom_class = classify_orientation(geom_angle, loose_config)
        if route == AssociationRoute.STRAIGHT and not orientation_compatible(text_class, geom_class):
            continue
        d = distance_point_to_geometry(anchor, geom.to_dict())
        if d > max_distance:
            continue
        ranked.append(_RankedCandidate(geom, d, AssociationRoute.SPECIAL_DO, [REASON_DO_ANNOTATION, REASON_WITHIN_DISTANCE_GATE]))
    ranked.sort(key=lambda c: c.distance)
    return ranked


def _route_max_distance(route: AssociationRoute, origin: AssociationOrigin, config: AssociationConfig) -> float:
    if route == AssociationRoute.STRAIGHT:
        return config.straight_recovery_max_distance_pt if origin != AssociationOrigin.PRIMARY else config.straight_primary_max_distance_pt
    if route == AssociationRoute.CURVED:
        return config.curved_recovery_max_distance_pt if origin != AssociationOrigin.PRIMARY else config.curved_primary_max_distance_pt
    if route == AssociationRoute.MISC:
        return config.misc_max_distance_pt
    return config.do_max_distance_pt


def _distance_diagnosis(
    annotation: SemanticAnnotation,
    candidates: List[GeometryEvidence],
    origin: AssociationOrigin,
    config: AssociationConfig,
) -> Tuple[bool, bool]:
    """Diagnostic-only, ignoring every orientation gate: returns
    ``(any_routable_type_present, any_within_its_own_route_distance_gate)``.
    Used strictly to tell "nothing was even close" (OUTSIDE_DISTANCE_GATE /
    UNSUPPORTED_GEOMETRY) apart from "something was close but orientation
    rejected it" (ORIENTATION_MISMATCH) -- conflating the two (checking
    supported-type presence at a WIDE blanket radius, then blaming
    orientation for everything else) was a real bug caught by the first
    real-drawing benchmark run: a routable candidate merely existing
    somewhere in the wide primary-query radius is not evidence that its OWN
    route's (possibly tighter) distance gate would also have passed."""

    anchor = annotation.original_anchor
    any_type = False
    any_within_distance = False
    for geom in candidates:
        route = route_for_geometry(geom)
        if route is None:
            continue
        any_type = True
        d = distance_point_to_geometry(anchor, geom.to_dict())
        if d <= _route_max_distance(route, origin, config):
            any_within_distance = True
    return any_type, any_within_distance


def _rank_for_annotation(
    annotation: SemanticAnnotation,
    local_candidates: List[GeometryEvidence],
    *,
    origin: AssociationOrigin,
    config: AssociationConfig,
) -> List[_RankedCandidate]:
    """Tries every route whose geometry type is actually present locally,
    merges the ranked results. A DO-pattern annotation tries the DO route
    FIRST (Section 12), independent of what geometry types are nearby."""

    scale = 1.0 if origin == AssociationOrigin.PRIMARY else (
        DEFAULT_CONFIG.straight_recovery_max_distance_pt / DEFAULT_CONFIG.straight_primary_max_distance_pt
    )

    if is_do_annotation(annotation):
        return _rank_do(annotation, local_candidates, config.do_max_distance_pt * scale, config)

    results: List[_RankedCandidate] = []
    results += _rank_straight(
        annotation, local_candidates,
        (config.straight_recovery_max_distance_pt if origin != AssociationOrigin.PRIMARY else config.straight_primary_max_distance_pt),
        config,
    )
    results += _rank_curved(
        annotation, local_candidates,
        (config.curved_recovery_max_distance_pt if origin != AssociationOrigin.PRIMARY else config.curved_primary_max_distance_pt),
        config,
    )
    results += _rank_misc(annotation, local_candidates, config.misc_max_distance_pt * scale, config)
    results.sort(key=lambda c: c.distance)
    return results


# ---------------------------------------------------------------------------
# One-to-one conflict resolution (Section 8) -- deterministic greedy global
# assignment: sort every (annotation, candidate) pair across ALL annotations
# by distance, claim geometry for the nearest unclaimed pairing first, and
# let a loser fall through to its next candidate. Ties broken by
# annotation_id so the result is reproducible.
# ---------------------------------------------------------------------------


def resolve_one_to_one(
    ranked_by_annotation: Dict[str, List[_RankedCandidate]],
) -> Dict[str, Optional[_RankedCandidate]]:
    all_pairs: List[Tuple[float, str, int]] = []
    for ann_id, ranked in ranked_by_annotation.items():
        for idx, cand in enumerate(ranked):
            all_pairs.append((cand.distance, ann_id, idx))
    all_pairs.sort(key=lambda p: (p[0], p[1], p[2]))

    claimed_geometry: set = set()
    resolved: Dict[str, Optional[_RankedCandidate]] = {ann_id: None for ann_id in ranked_by_annotation}
    settled: set = set()

    for _distance, ann_id, idx in all_pairs:
        if ann_id in settled:
            continue
        cand = ranked_by_annotation[ann_id][idx]
        gid = cand.geometry.geometry_id
        # Only the annotation's OWN best still-available candidate counts --
        # skip if a closer, not-yet-tried candidate of its own exists.
        own_ranked = ranked_by_annotation[ann_id]
        best_available = next((c for c in own_ranked if c.geometry.geometry_id not in claimed_geometry), None)
        if best_available is None:
            settled.add(ann_id)
            continue
        if best_available.geometry.geometry_id != gid:
            continue  # this pair isn't the annotation's current best; wait
        # Ambiguity check: is the runner-up within the tie margin?
        alternatives = [c for c in own_ranked if c.geometry.geometry_id not in claimed_geometry]
        if len(alternatives) > 1 and (alternatives[1].distance - alternatives[0].distance) <= DEFAULT_CONFIG.ambiguity_margin_pt:
            resolved[ann_id] = None
            settled.add(ann_id)
            continue
        claimed_geometry.add(gid)
        resolved[ann_id] = best_available
        settled.add(ann_id)

    return resolved


# ---------------------------------------------------------------------------
# Top-level orchestration (Phase C)
# ---------------------------------------------------------------------------


def run_shadow_association(
    annotations: List[SemanticAnnotation],
    geometry_by_page: Dict[int, List[GeometryEvidence]],
    *,
    config: AssociationConfig = DEFAULT_CONFIG,
) -> List[AssociationEvidence]:
    """Runs the full primary -> conflict-resolution -> recovery ->
    conflict-resolution pipeline over ``annotations``. Pure function: never
    mutates ``annotations`` or ``geometry_by_page``. Returns one
    ``AssociationEvidence`` per annotation that has an ``original_anchor``
    (annotations without one are out of scope for this module entirely --
    it never invents a position)."""

    index = PageSpatialIndexCache(geometry_by_page)
    eligible = [a for a in annotations if a.original_anchor is not None]

    # ---- Primary pass ----
    primary_ranked: Dict[str, List[_RankedCandidate]] = {}
    primary_had_local_candidates: Dict[str, bool] = {}
    # Diagnostic-only (see _distance_diagnosis): distinguishes "no supported
    # geometry type nearby" / "supported type but too far" / "close enough,
    # so any rejection must be orientation" -- used only to pick the right
    # UnmatchedReason, never to affect the actual association.
    primary_type_present: Dict[str, bool] = {}
    primary_within_distance: Dict[str, bool] = {}
    for ann in eligible:
        page = ann.page or 0
        wide = max(
            config.straight_primary_max_distance_pt,
            config.curved_primary_max_distance_pt,
            config.misc_max_distance_pt,
            config.do_max_distance_pt,
        )
        local = index.query(page, ann.original_anchor, wide)
        primary_had_local_candidates[ann.annotation_id] = bool(local)
        ranked = _rank_for_annotation(ann, local, origin=AssociationOrigin.PRIMARY, config=config)
        primary_ranked[ann.annotation_id] = ranked
        any_type, any_within = _distance_diagnosis(ann, local, AssociationOrigin.PRIMARY, config)
        primary_type_present[ann.annotation_id] = any_type
        primary_within_distance[ann.annotation_id] = any_within

    primary_resolved = resolve_one_to_one(primary_ranked)

    # ---- Recovery pass: only annotations still unresolved ----
    still_unresolved = [ann for ann in eligible if primary_resolved.get(ann.annotation_id) is None]
    recovery_ranked: Dict[str, List[_RankedCandidate]] = {}
    # Diagnostic-only: what WOULD have ranked if claimed geometry were still
    # eligible, so an unmatched annotation can be told "your best candidate
    # was claimed" instead of a misleading distance/orientation reason.
    recovery_ranked_unfiltered: Dict[str, List[_RankedCandidate]] = {}
    recovery_type_present: Dict[str, bool] = {}
    recovery_within_distance: Dict[str, bool] = {}
    already_claimed = {c.geometry.geometry_id for c in primary_resolved.values() if c is not None}
    for ann in still_unresolved:
        page = ann.page or 0
        wide = max(
            config.straight_recovery_max_distance_pt,
            config.curved_recovery_max_distance_pt,
        )
        local_all = index.query(page, ann.original_anchor, wide)
        local_free = [g for g in local_all if g.geometry_id not in already_claimed]
        recovery_ranked[ann.annotation_id] = _rank_for_annotation(
            ann, local_free, origin=AssociationOrigin.RECOVERY, config=config
        )
        recovery_ranked_unfiltered[ann.annotation_id] = _rank_for_annotation(
            ann, local_all, origin=AssociationOrigin.RECOVERY, config=config
        )
        any_type, any_within = _distance_diagnosis(ann, local_free, AssociationOrigin.RECOVERY, config)
        recovery_type_present[ann.annotation_id] = any_type
        recovery_within_distance[ann.annotation_id] = any_within

    recovery_resolved = resolve_one_to_one(recovery_ranked)

    # ---- Assemble evidence ----
    evidence: List[AssociationEvidence] = []
    for ann in eligible:
        ann_id = ann.annotation_id
        text_angle = _text_orientation_deg(ann)
        text_class = classify_orientation(text_angle, config)

        primary = primary_resolved.get(ann_id)
        if primary is not None:
            reasons = list(primary.reason_codes) + [REASON_NEAREST_VALID_GEOMETRY, REASON_ONE_TO_ONE_RESOLVED]
            evidence.append(AssociationEvidence(
                source_text_id=ann_id,
                geometry_id=primary.geometry.geometry_id,
                route=primary.route.value,
                association_origin=AssociationOrigin.PRIMARY.value,
                text_orientation=text_class.value if text_class else None,
                geometry_orientation=_orientation_value(_geometry_orientation_deg(primary.geometry), config),
                distance=round(primary.distance, 3),
                candidate_count=len(primary_ranked.get(ann_id, [])),
                status=AssociationStatus.ASSOCIATED.value,
                reason_codes=reasons,
                page=ann.page,
            ))
            continue

        recovered = recovery_resolved.get(ann_id)
        if recovered is not None:
            reasons = list(recovered.reason_codes) + [REASON_RECOVERED, REASON_ONE_TO_ONE_RESOLVED]
            evidence.append(AssociationEvidence(
                source_text_id=ann_id,
                geometry_id=recovered.geometry.geometry_id,
                route=recovered.route.value,
                association_origin=AssociationOrigin.RECOVERY.value,
                text_orientation=text_class.value if text_class else None,
                geometry_orientation=_orientation_value(_geometry_orientation_deg(recovered.geometry), config),
                distance=round(recovered.distance, 3),
                candidate_count=len(recovery_ranked.get(ann_id, [])),
                status=AssociationStatus.ASSOCIATED.value,
                reason_codes=reasons,
                page=ann.page,
            ))
            continue

        # Unmatched -- pick the most specific reason available, in priority
        # order: no geometry at all -> a specific best candidate that was
        # taken by someone closer -> a genuine too-close-to-call tie ->
        # a supported candidate existed within ITS OWN route's distance gate
        # (so a rejection must be orientation) -> a supported type existed
        # but never within its own distance gate -> no supported type at all.
        had_local = primary_had_local_candidates.get(ann_id, False)
        type_present = primary_type_present.get(ann_id, False) or recovery_type_present.get(ann_id, False)
        within_distance = primary_within_distance.get(ann_id, False) or recovery_within_distance.get(ann_id, False)
        primary_candidates = primary_ranked.get(ann_id, [])
        recovery_candidates = recovery_ranked.get(ann_id, [])
        unfiltered_recovery = recovery_ranked_unfiltered.get(ann_id, [])

        def _has_tie(ranked: List[_RankedCandidate]) -> bool:
            return len(ranked) > 1 and (ranked[1].distance - ranked[0].distance) <= DEFAULT_CONFIG.ambiguity_margin_pt

        if not had_local:
            reason = UnmatchedReason.NO_LOCAL_GEOMETRY
        elif unfiltered_recovery and unfiltered_recovery[0].geometry.geometry_id in already_claimed:
            # The best candidate this annotation could otherwise reach was
            # already claimed by a closer label's primary association.
            reason = UnmatchedReason.GEOMETRY_ALREADY_CLAIMED
        elif _has_tie(primary_candidates) or _has_tie(recovery_candidates):
            reason = UnmatchedReason.MULTIPLE_VALID_CANDIDATES
        elif not type_present:
            reason = UnmatchedReason.UNSUPPORTED_GEOMETRY
        elif within_distance:
            # A supported-type candidate was within its own route's distance
            # gate, yet nothing was ranked/resolved -- the only remaining
            # explanation left by this module's gates is orientation.
            reason = UnmatchedReason.ORIENTATION_MISMATCH
        else:
            reason = UnmatchedReason.OUTSIDE_DISTANCE_GATE

        evidence.append(AssociationEvidence(
            source_text_id=ann_id,
            geometry_id=None,
            route=(AssociationRoute.SPECIAL_DO.value if is_do_annotation(ann) else AssociationRoute.STRAIGHT.value),
            association_origin=AssociationOrigin.PRIMARY.value,
            text_orientation=text_class.value if text_class else None,
            geometry_orientation=None,
            distance=None,
            candidate_count=len(primary_candidates) + len(recovery_candidates),
            status=AssociationStatus.UNMATCHED.value,
            reason_codes=[reason.value],
            page=ann.page,
        ))

    return evidence


def compare_with_existing(
    evidence: List[AssociationEvidence],
    existing_geometry_id_by_annotation: Dict[str, Optional[str]],
) -> Dict[str, Any]:
    """Section 19/28's shadow-mode comparison. ``existing_geometry_id_by_annotation``
    is whatever the caller's current association path produced (e.g. via
    ``association.associate_via_nearest_geometry``) -- this function does not
    run that path itself, to keep it decoupled from any one caller."""

    agree = disagree = new_only = existing_only = both_unmatched = 0
    details: List[Dict[str, Any]] = []
    for ev in evidence:
        existing_id = existing_geometry_id_by_annotation.get(ev.source_text_id)
        new_id = ev.geometry_id
        if existing_id is None and new_id is None:
            both_unmatched += 1
            outcome = "both_unmatched"
        elif existing_id == new_id:
            agree += 1
            outcome = "agree"
        elif existing_id is None and new_id is not None:
            new_only += 1
            outcome = "new_only"
        elif existing_id is not None and new_id is None:
            existing_only += 1
            outcome = "existing_only"
        else:
            disagree += 1
            outcome = "disagree"
        details.append({
            "source_text_id": ev.source_text_id,
            "existing_geometry_id": existing_id,
            "new_geometry_id": new_id,
            "outcome": outcome,
            "new_route": ev.route,
            "new_origin": ev.association_origin,
            "new_reason_codes": list(ev.reason_codes),
        })
    total = len(evidence) or 1
    return {
        "total": len(evidence),
        "agree": agree,
        "disagree": disagree,
        "new_only": new_only,
        "existing_only": existing_only,
        "both_unmatched": both_unmatched,
        "agreement_rate": round(agree / total, 4),
        "details": details,
    }
