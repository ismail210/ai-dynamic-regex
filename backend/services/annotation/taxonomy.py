"""Engineering annotation taxonomy — states, types, and subtypes.

``Understandability`` is the canonical state vocabulary. ``AnnotationType`` is
the notation taxonomy; where the two share a name (``UNREADABLE``,
``UNSUPPORTED``) the type reuses the state's value so the strings can never
drift apart. Do not force every annotation into a steel-section class.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Understandability(str, Enum):
    """Can the annotation be interpreted at all?

    UNDERSTOOD   structure can be interpreted.
    AMBIGUOUS    readable, but several interpretations/candidates remain.
    UNREADABLE   source characters are too damaged/incomplete to trust.
    UNSUPPORTED  basically legible but outside the supported taxonomy.
    """

    UNDERSTOOD = "UNDERSTOOD"
    AMBIGUOUS = "AMBIGUOUS"
    UNREADABLE = "UNREADABLE"
    UNSUPPORTED = "UNSUPPORTED"


class AnnotationType(str, Enum):
    STANDARD_SECTION = "STANDARD_SECTION"
    PLATE = "PLATE"
    BENT_PLATE = "BENT_PLATE"
    DIMENSION = "DIMENSION"
    ANGLE = "ANGLE"
    RANGE = "RANGE"
    CALL_OUT = "CALL_OUT"
    MEMBER_MARK = "MEMBER_MARK"
    SCHEDULE_REFERENCE = "SCHEDULE_REFERENCE"
    GRID_REFERENCE = "GRID_REFERENCE"
    TEXT_NOTE = "TEXT_NOTE"
    UNKNOWN = "UNKNOWN"
    # Shared vocabulary with Understandability — single source for the strings.
    UNREADABLE = Understandability.UNREADABLE.value
    UNSUPPORTED = Understandability.UNSUPPORTED.value


class ModelState(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    APPROVED = "APPROVED"
    DISABLED = "DISABLED"


# States that must never be answered automatically.
REVIEW_STATES = frozenset(
    {Understandability.UNREADABLE.value, Understandability.UNSUPPORTED.value}
)


def _canonical_name(value: Any) -> str:
    """Accept enums, enum names, and mixed-case strings alike."""

    if isinstance(value, Enum):
        value = value.value
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    # Tolerate serialized forms such as "Understandability.UNREADABLE".
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def understandability_value(value: Any) -> str:
    """Normalize any representation of a state to its canonical value.

    An unrecognized, non-empty state is treated as UNSUPPORTED so the case
    reaches a human instead of raising ``AttributeError``/``KeyError``.
    """

    name = _canonical_name(value)
    if not name:
        return Understandability.AMBIGUOUS.value
    member = Understandability.__members__.get(name)
    return member.value if member else Understandability.UNSUPPORTED.value


def annotation_type_value(value: Any) -> str:
    """Normalize any representation of an annotation type to its value."""

    name = _canonical_name(value)
    if not name:
        return AnnotationType.UNKNOWN.value
    member = AnnotationType.__members__.get(name)
    return member.value if member else AnnotationType.UNSUPPORTED.value


def requires_review(status: Any) -> bool:
    """True when the state must not be resolved automatically."""

    return understandability_value(status) in REVIEW_STATES


SECTION_SUBTYPES = frozenset(
    {"W", "S", "M", "HP", "C", "MC", "WT", "MT", "ST", "HSS", "PIPE", "L", "2L"}
)
PLATE_SUBTYPES = frozenset({"flat_plate", "gusset_plate", "bent_plate"})
DIMENSION_SUBTYPES = frozenset({"linear", "thickness", "compound", "range"})
