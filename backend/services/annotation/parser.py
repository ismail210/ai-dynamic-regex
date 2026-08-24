"""Reusable engineering annotation parser.

Preserves raw_text forever. Semantic meaning is a candidate until context
(geometry / graph / nearby text) confirms it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from services.annotation.normalize import (
    as_float,
    as_int,
    compact_normalize,
    orientation_bin_name,
    parse_angle_degrees,
    safe_bbox,
    soft_normalize,
    split_dimension_parts,
)
from services.annotation.taxonomy import (
    AnnotationType,
    DIMENSION_SUBTYPES,
    PLATE_SUBTYPES,
    SECTION_SUBTYPES,
)
from services.database_loader import catalog_form
from services.engineering.document_prior import plate_context_from_prior
from services.section_parser import parse_section
from services.wildcard_matcher import has_wildcards


_SECTION_HEAD = re.compile(
    r"^(?:2L|HSS|PIPE|WT|MT|ST|MC|HP|W|S|M|C|L)(?=\d)",
    re.I,
)
_PLATE_HEAD = re.compile(
    r"^(?:PL|PLATE|BP|BENTPLATE|BENT\s*PL(?:ATE)?)\b",
    re.I,
)
_BENT_PL_CALL = re.compile(r"\bBENT\s*PL(?:ATE)?\b", re.I)
_BENT_PL_THICKNESS_FIRST = re.compile(
    r"^(?:\d+/\d+|\d+(?:\.\d+)?)\"?\s*BENT\s*PL(?:ATE)?\b",
    re.I,
)
_COMPOUND_DIM = re.compile(
    r"^(?:\d+(?:\.\d+)?|\d+/\d+)(?:\s*[xX×✕✖]\s*(?:\d+(?:\.\d+)?|\d+/\d+)){1,3}$"
)
_RANGE = re.compile(
    r"^(\d+(?:\.\d+)?|\d+/\d+)\s*(?:in|\"|mm|cm)?\s*/\s*"
    r"(\d+(?:\.\d+)?|\d+/\d+)\s*(?:in|\"|mm|cm)?$",
    re.I,
)
_MEMBER_MARK = re.compile(
    r"^(?:BM|BEAM|COL|COLUMN|BR|BRACE|GIRDER|JOIST|JST|PPN|MK|P)[-_ ]?\d+[A-Z]?$",
    re.I,
)
_GRID = re.compile(r"^(?:GRID|GR)\s*[A-Z0-9.-]+$", re.I)
_SCHEDULE = re.compile(r"^(?:SCH|SCHEDULE|TYP|SEE)\b", re.I)
_CORRUPT = re.compile(r"[?¿*#]|[^\x20-\x7E]")


@dataclass
class AnnotationParse:
    raw_text: str
    normalized_text: str
    annotation_type: str
    subtype: Optional[str] = None
    dimensions: List[str] = field(default_factory=list)
    thickness: Optional[str] = None
    angle_degrees: Optional[float] = None
    unit: Optional[str] = None
    plate_type: Optional[str] = None
    section_family: Optional[str] = None
    catalog_valid: bool = False
    catalog_designation: Optional[str] = None
    wildcard: bool = False
    page: Optional[int] = None
    bbox: Optional[List[float]] = None
    text_rotation: Optional[float] = None
    geometry_orientation: Optional[float] = None
    geometry_orientation_bin: Optional[str] = None
    source: str = "pdf_text"
    provenance: Dict[str, Any] = field(default_factory=dict)
    structure_confirmed: bool = False
    fragments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _extract_bent_plate_thickness(text: str) -> Optional[str]:
    """Pull thickness from bent-plate shorthand callouts."""

    normalized = soft_normalize(text)
    if _BENT_PL_THICKNESS_FIRST.match(normalized):
        match = re.match(r"^(?:\d+/\d+|\d+(?:\.\d+)?)\"?", normalized)
        if match:
            return match.group(0).rstrip('"')
    compact = compact_normalize(normalized)
    if _BENT_PL_THICKNESS_FIRST.match(compact):
        match = re.match(r"^(?:\d+/\d+|\d+(?:\.\d+)?)\"?", compact)
        if match:
            return match.group(0).rstrip('"')
    after_head = re.search(
        r"^BENT\s*PL(?:ATE)?\s+((?:\d+/\d+|\d+(?:\.\d+)?)\"?)",
        normalized,
        re.I,
    )
    if not after_head:
        after_head = re.search(
            r"^BENT\s*PL(?:ATE)?\s*((?:\d+/\d+|\d+(?:\.\d+)?)\"?)",
            compact,
            re.I,
        )
    if after_head:
        return after_head.group(1).rstrip('"')
    return None


def _unit_from_text(text: str) -> Optional[str]:
    upper = soft_normalize(text).upper()
    if re.search(r"\bMM\b", upper):
        return "mm"
    if re.search(r"\bCM\b", upper):
        return "cm"
    if re.search(r"\bIN\b|\"", upper):
        return "in"
    return None


def interpret_annotation(
    *,
    raw_text: str,
    normalized_text: str = "",
    page: Optional[int] = None,
    bbox: Optional[List[float]] = None,
    text_rotation: Optional[Any] = None,
    geometry_orientation: Optional[Any] = None,
    nearby_text: Optional[List[str]] = None,
    nearby_geometry: Optional[Dict[str, Any]] = None,
    leader: Optional[Dict[str, Any]] = None,
    page_context: Optional[str] = None,
    graph_context: Optional[Dict[str, Any]] = None,
    fragments: Optional[List[Dict[str, Any]]] = None,
    source: str = "pdf_text",
    document_prior: Optional[Dict[str, Any]] = None,
) -> AnnotationParse:
    """Parse without destroying raw text. Plate semantics need context confirm."""

    raw = str(raw_text or "")
    normalized = soft_normalize(normalized_text or raw)
    compact = compact_normalize(normalized)
    neighbors = " ".join(str(item) for item in (nearby_text or []) if item)
    context_blob = " ".join(
        part for part in (neighbors, page_context or "", str((graph_context or {}).get("node_kind") or "")) if part
    )
    angle = parse_angle_degrees(normalized)
    unit = _unit_from_text(normalized)
    geometry_object = (nearby_geometry or {}).get("object") or {}
    geom_role = str(
        (nearby_geometry or {}).get("geometry_role")
        or geometry_object.get("geometry_role")
        or ""
    ).lower()
    graph_role = str((graph_context or {}).get("graph_prediction") or (graph_context or {}).get("node_kind") or "").lower()

    result = AnnotationParse(
        raw_text=raw,
        normalized_text=normalized,
        annotation_type=AnnotationType.UNKNOWN.value,
        page=as_int(page),
        bbox=safe_bbox(bbox),
        text_rotation=as_float(text_rotation),
        geometry_orientation=as_float(geometry_orientation),
        geometry_orientation_bin=orientation_bin_name(geometry_orientation),
        source=source,
        provenance={
            "nearby_text": list(nearby_text or [])[:8],
            "has_leader": bool(leader),
            "page_context": page_context or None,
            "geometry_role": geom_role or None,
            "graph_role": graph_role or None,
        },
        fragments=list(fragments or []),
        angle_degrees=angle,
        unit=unit,
        wildcard=has_wildcards(raw) or has_wildcards(normalized),
    )

    # --- STANDARD_SECTION -------------------------------------------------
    section_match = _SECTION_HEAD.match(compact)
    # Shorthand spellings (HSS10X0.625) resolve to their catalog designation.
    catalog_spelling = catalog_form(compact)
    if section_match or catalog_spelling:
        try:
            parsed = parse_section(compact)
        except Exception:  # designation parsing must never abort interpretation
            parsed = None
        family = (getattr(parsed, "family", "") or "") or (
            section_match.group(0).upper() if section_match else ""
        )
        if family.startswith("2L"):
            family = "2L"
        result.annotation_type = AnnotationType.STANDARD_SECTION.value
        result.subtype = family if family in SECTION_SUBTYPES else family or None
        result.section_family = family or None
        result.catalog_valid = bool(
            getattr(parsed, "catalog_valid", False) or catalog_spelling
        )
        result.catalog_designation = catalog_spelling or None
        result.structure_confirmed = True
        if getattr(parsed, "thickness", None):
            result.thickness = parsed.thickness
        return result

    # --- RANGE (5 in / 7 in) ---------------------------------------------
    match = _RANGE.match(normalized.replace(" ", "")) or _RANGE.match(normalized)
    if match:
        result.annotation_type = AnnotationType.RANGE.value
        result.subtype = "range"
        result.dimensions = [match.group(1), match.group(2)]
        result.structure_confirmed = True
        return result

    # --- MEMBER / GRID / SCHEDULE ----------------------------------------
    if _MEMBER_MARK.match(compact) or _MEMBER_MARK.match(normalized):
        result.annotation_type = AnnotationType.MEMBER_MARK.value
        result.structure_confirmed = True
        return result
    if _GRID.match(compact):
        result.annotation_type = AnnotationType.GRID_REFERENCE.value
        result.structure_confirmed = True
        return result
    if _SCHEDULE.match(normalized):
        result.annotation_type = AnnotationType.SCHEDULE_REFERENCE.value
        return result

    # --- PLATE / BENT PLATE / compound dimensions ------------------------
    plate_headed = bool(
        _PLATE_HEAD.match(normalized)
        or _PLATE_HEAD.match(compact)
        or _BENT_PL_THICKNESS_FIRST.match(normalized)
        or _BENT_PL_THICKNESS_FIRST.match(compact)
    )
    bent_pl_callout = bool(
        _BENT_PL_CALL.search(normalized) or _BENT_PL_CALL.search(compact)
    )
    bent_hint = bool(
        bent_pl_callout
        or re.search(r"\bBP\b", normalized, re.I)
        or angle is not None
        or "bent" in geom_role
    )
    prior_plate = plate_context_from_prior(
        document_prior,
        normalized=normalized,
        compact=compact,
    )
    if prior_plate.get("supports_bent_plate") and (
        compact.upper().startswith("BP")
        or compact.upper().startswith("BENT")
        or bent_pl_callout
    ):
        bent_hint = True
    compound = _COMPOUND_DIM.match(
        re.sub(
            r"\s+",
            "",
            re.sub(r"^(?:PL|PLATE|BP|BENT\s*PL(?:ATE)?)\s*", "", normalized, flags=re.I),
        )
    )
    parts = split_dimension_parts(normalized)

    if plate_headed or bent_pl_callout or compound or (len(parts) >= 2 and not section_match):
        bent_thickness = _extract_bent_plate_thickness(normalized) if bent_pl_callout else None
        result.dimensions = parts[:-1] if len(parts) >= 3 else parts[:2]
        result.thickness = (
            bent_thickness
            or (parts[-1] if len(parts) >= 3 else None)
            or (parts[1] if len(parts) == 2 and plate_headed else None)
        )
        # Semantic confirmation: text alone is not enough for bare 6x4x5/6.
        context_supports_plate = bool(
            plate_headed
            or bent_pl_callout
            or "PLATE" in context_blob.upper()
            or "LEGEND_CONFIRMS_PLATES" in context_blob.upper()
            or geom_role in {"plate", "connection"}
            or graph_role in {"plate", "connection"}
            or bool(leader)
            or prior_plate.get("supports_plate")
        )
        if bent_hint and context_supports_plate:
            result.annotation_type = AnnotationType.BENT_PLATE.value
            result.subtype = "bent_plate"
            result.plate_type = "bent_plate"
            result.structure_confirmed = True
        elif context_supports_plate:
            result.annotation_type = AnnotationType.PLATE.value
            result.subtype = "flat_plate" if "gusset" not in context_blob.lower() else "gusset_plate"
            if result.subtype in PLATE_SUBTYPES:
                result.plate_type = result.subtype
            result.structure_confirmed = True
        else:
            result.annotation_type = AnnotationType.DIMENSION.value
            result.subtype = "compound" if len(parts) >= 2 else "linear"
            result.structure_confirmed = False
            result.provenance["needs_context"] = (
                "Compound dimensions seen; plate semantics not confirmed by context."
            )
        return result

    if angle is not None and not parts:
        result.annotation_type = AnnotationType.ANGLE.value
        result.structure_confirmed = True
        return result

    if len(normalized) <= 2 or not re.search(r"[A-Za-z0-9]", normalized):
        result.annotation_type = AnnotationType.UNREADABLE.value if _CORRUPT.search(raw) else AnnotationType.UNKNOWN.value
        return result

    if _CORRUPT.search(raw) and not re.search(r"[A-Za-z]{2,}", compact):
        result.annotation_type = AnnotationType.UNREADABLE.value
        return result

    result.annotation_type = AnnotationType.TEXT_NOTE.value
    return result
