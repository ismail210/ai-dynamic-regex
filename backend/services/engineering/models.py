"""
Shared dataclasses and typed models for the engineering validation domain.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GeometryKind(str, Enum):
    LINE = "line"
    POLYLINE = "polyline"
    CURVE = "curve"
    ARC = "arc"
    CIRCLE = "circle"
    RECTANGLE = "rectangle"
    DIMENSION = "dimension"
    LEADER = "leader"
    SYMBOL = "symbol"
    BLOCK = "block"
    PATH = "path"
    UNKNOWN = "unknown"


class NodeKind(str, Enum):
    TEXT = "text"
    GEOMETRY = "geometry"
    DIMENSION = "dimension"
    LABEL = "label"
    BEAM = "beam"
    COLUMN = "column"
    PLATE = "plate"
    BRACE = "brace"
    BOLT = "bolt"
    WELD = "weld"
    CONNECTION = "connection"
    OTHER = "other"


class RelationKind(str, Enum):
    NEAREST_LABEL = "nearest_label"
    NEAREST_GEOMETRY = "nearest_geometry"
    DISTANCE = "distance"
    INTERSECTION = "intersection"
    CONTAINMENT = "containment"
    TOUCHING = "touching"
    CONNECTED = "connected"
    CONNECTED_TO = "connected_to"
    SUPPORTS = "supports"
    INTERSECTS = "intersects"
    INSIDE = "inside"
    ADJACENT = "adjacent"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"
    ABOVE = "above"
    BELOW = "below"
    LEFT_OF = "left_of"
    RIGHT_OF = "right_of"
    REFERENCE = "reference"


class MatchStatus(str, Enum):
    PERFECT_MATCH = "perfect_match"
    MISSING_LABEL = "missing_label"
    WRONG_LABEL = "wrong_label"
    MISSING_GEOMETRY = "missing_geometry"
    EXTRA_GEOMETRY = "extra_geometry"
    EXTRA_LABEL = "extra_label"
    COUNT_MISMATCH = "count_mismatch"
    LENGTH_MISMATCH = "length_mismatch"
    WIDTH_MISMATCH = "width_mismatch"


def to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses / enums to JSON-safe structures."""

    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, Enum):
        return obj.value
    if dataclasses_is_dataclass(obj):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


def dataclasses_is_dataclass(obj: Any) -> bool:
    return hasattr(obj, "__dataclass_fields__")


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def as_list(self) -> List[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    @property
    def width(self) -> float:
        return abs(self.x1 - self.x0)

    @property
    def height(self) -> float:
        return abs(self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> List[float]:
        return [round((self.x0 + self.x1) / 2.0, 2), round((self.y0 + self.y1) / 2.0, 2)]


@dataclass
class ObjectConfidence:
    text_confidence: float = 0.0
    geometry_confidence: float = 0.0
    matching_confidence: float = 0.0
    overall: float = 0.0
    level: str = "Low"
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_confidence": round(self.text_confidence, 4),
            "geometry_confidence": round(self.geometry_confidence, 4),
            "matching_confidence": round(self.matching_confidence, 4),
            "overall": round(self.overall, 4),
            "level": self.level,
            "reasons": list(self.reasons),
        }


@dataclass
class Suggestion:
    object_id: str
    expected_label: str
    expected_type: str
    confidence: float
    reason: str
    features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "expected_label": self.expected_label,
            "expected_type": self.expected_type,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "features": self.features,
        }
