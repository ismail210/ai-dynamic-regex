"""Shared grammar for explicit structural-plate callouts.

Annotation parsing and section-reconstruction eligibility both need to know
whether text explicitly names PL/BP/BENT PL/CAP PL/CONN PL.  Keeping the
prefix grammar here prevents those two safety boundaries from drifting while
leaving contextual plate interpretation in ``annotation.parser``.
"""

from __future__ import annotations

import re

THICKNESS_TOKEN = r"(?:\d+/\d+|\d+(?:\.\d+)?)"
PLATE_HEAD = re.compile(
    r"^(?:(?:CAP|CONN(?:ECTION)?)\s+PL(?:ATE)?|PL|PLATE|BP|BENTPLATE|BENT\s*PL(?:ATE)?)\b",
    re.I,
)
PLATE_HEAD_COMPACT = re.compile(
    r"^(?:CAPPL(?:ATE)?|CONN(?:ECTION)?PL(?:ATE)?|PL|PLATE|BP|BENTPLATE|BENTPL(?:ATE)?)",
    re.I,
)
BENT_PL_CALL = re.compile(r"\bBENT\s*PL(?:ATE)?\b", re.I)
BENT_PL_THICKNESS_FIRST = re.compile(
    rf"^{THICKNESS_TOKEN}\"?\s*BENT\s*PL(?:ATE)?\b",
    re.I,
)
THICKNESS_FIRST_PLATE = re.compile(
    rf"^{THICKNESS_TOKEN}\"?\s*(?:(?:CAP|CONN(?:ECTION)?)\s+)?PL(?:ATE)?\b",
    re.I,
)
THICKNESS_FIRST_PLATE_COMPACT = re.compile(
    rf"^{THICKNESS_TOKEN}\"?(?:CAP|CONN(?:ECTION)?)?PL(?:ATE)?",
    re.I,
)


def starts_with_plate_head(text: str) -> bool:
    """True when normalized/compact text begins with an explicit plate name."""

    value = str(text or "").strip()
    return bool(PLATE_HEAD.match(value) or PLATE_HEAD_COMPACT.match(value))


def is_thickness_first_plate(normalized: str, compact: str) -> bool:
    """Recognize thickness-first non-bent plate callouts."""

    if BENT_PL_THICKNESS_FIRST.match(normalized) or BENT_PL_THICKNESS_FIRST.match(
        compact
    ):
        return False
    return bool(
        THICKNESS_FIRST_PLATE.match(normalized)
        or THICKNESS_FIRST_PLATE_COMPACT.match(compact)
    )
