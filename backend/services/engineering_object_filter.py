"""Select structural objects from extracted drawing text."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from services.engineering.extraction_noise_filter import (
    classify_extraction_noise_reason,
    dedupe_engineering_tokens,
    is_extraction_noise_token,
)
from services.engineering.feet_inch_filter import is_non_steel_layout_token


_SECTION = re.compile(
    r"^(?:W|S|M|HP|C|MC|WT|MT|ST|HSS|PIPE|L|2L)"
    r"\d+(?:[./]\d+)?(?:X\d+(?:[./]\d+)?){1,3}$",
    re.IGNORECASE,
)
_PLATE = re.compile(
    r"^(?:PL|PLATE)\s*\d+(?:[./]\d+)?(?:X\d+(?:[./]\d+)?){1,3}$",
    re.IGNORECASE,
)
_MEMBER_MARK = re.compile(
    r"^(?:BM|BEAM|COL|COLUMN|BR|BRACE|GIRDER|JOIST|JST)[-_ ]?\d+[A-Z]?$",
    re.IGNORECASE,
)
_CONNECTION = re.compile(
    r"^(?:BOLT|WELD|CONN|CONNECTION)[-_ ]?[A-Z0-9./]+$",
    re.IGNORECASE,
)
_STRUCTURAL_CONTEXT = re.compile(
    r"\b(?:BEAM|COLUMN|COL\.?|BRACE|PLATE|BOLT|WELD|CONNECTION|"
    r"FRAMING|SECTION|MEMBER|GIRDER|JOIST)\b",
    re.IGNORECASE,
)
_NON_OBJECT_CONTEXT = re.compile(
    r"\b(?:GENERAL\s+NOTES?|REVISION|REVISIONS|SPECIFICATIONS?|"
    r"MATERIAL\s+NOTES?|ASTM|DESIGN\s+CRITERIA|SHEET\s+INDEX|LEGEND)\b",
    re.IGNORECASE,
)
_ANONYMOUS_DIM = re.compile(
    r'^(?:\d+(?:\.\d+)?|\d+/\d+)"?$'
    r"|^(?:\d+(?:\.\d+)?|\d+/\d+)(?:IN|IN\.)?$"
    r"|^(?:\d+(?:\.\d+)?|\d+/\d+)X(?:\d+(?:\.\d+)?|\d+/\d+)"
    r"(?:X(?:\d+(?:\.\d+)?|\d+/\d+))?$",
    re.IGNORECASE,
)


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").upper().replace("×", "X"))


def _context(token: Dict[str, Any]) -> str:
    context = token.get("context") or {}
    parts: Iterable[Any] = (
        token.get("surrounding_text"),
        context.get("line_text"),
        context.get("block_text"),
        " ".join(context.get("neighbor_text") or []),
    )
    return " | ".join(str(part or "") for part in parts)


def _section_object_type(text: str, context: str) -> str:
    if re.search(r"\b(?:COL|COLUMN)\b", context, re.IGNORECASE):
        return "column"
    if re.search(r"\b(?:BRACE|BRACING)\b", context, re.IGNORECASE):
        return "brace"
    if text.startswith("HSS") or text.startswith("PIPE"):
        return "column_or_brace"
    return "steel_section"


def _member_mark_object_type(text: str) -> str:
    upper = text.upper()
    if upper.startswith(("COL", "COLUMN")):
        return "column"
    if upper.startswith(("BR", "BRACE")):
        return "brace"
    return "beam"


def classify_engineering_object(
    token: Dict[str, Any],
    *,
    document: Dict[str, Any] | None = None,
) -> str | None:
    """Return a structural object type or ``None`` for non-object text."""

    if is_non_steel_layout_token(token):
        return None

    text = _normalized(token.get("normalized_text") or token.get("text"))
    context = _context(token)
    if not text or _NON_OBJECT_CONTEXT.search(context):
        return None

    if _ANONYMOUS_DIM.fullmatch(text):
        return "anonymous_dimension"

    # Fast path: catalog sections / plates / marks — skip heavy annotation parser.
    if _SECTION.fullmatch(text):
        return _section_object_type(text, context)
    if _PLATE.fullmatch(text):
        return "plate"
    if _MEMBER_MARK.fullmatch(text):
        return _member_mark_object_type(text)
    if _CONNECTION.fullmatch(text):
        if text.startswith("BOLT"):
            return "bolt"
        if text.startswith("WELD"):
            return "weld"
        return "connection"

    # Annotation layer: bent plates / ambiguous compound dims with context.
    try:
        from services.annotation.parser import interpret_annotation
        from services.annotation.taxonomy import AnnotationType

        parsed = interpret_annotation(
            raw_text=str(token.get("raw_text") or token.get("text") or ""),
            normalized_text=str(token.get("normalized_text") or token.get("text") or ""),
            page=token.get("page"),
            bbox=token.get("bbox"),
            text_rotation=token.get("rotation"),
            nearby_text=list((token.get("context") or {}).get("neighbor_text") or []),
            page_context=context,
            fragments=list(token.get("fragments") or []),
        )
        if parsed.annotation_type == AnnotationType.BENT_PLATE.value and parsed.structure_confirmed:
            return "plate"
        if parsed.annotation_type == AnnotationType.PLATE.value and parsed.structure_confirmed:
            return "plate"
        if (
            parsed.annotation_type == AnnotationType.DIMENSION.value
            and not parsed.structure_confirmed
            and _ANONYMOUS_DIM.fullmatch(_normalized(parsed.normalized_text or text))
        ):
            return "anonymous_dimension"
        if parsed.annotation_type == AnnotationType.STANDARD_SECTION.value:
            text = _normalized(parsed.normalized_text or text)
            if _SECTION.fullmatch(text):
                return _section_object_type(text, context)
    except Exception:
        pass

    if _SECTION.fullmatch(text):
        return _section_object_type(text, context)
    if _PLATE.fullmatch(text):
        return "plate"
    if _MEMBER_MARK.fullmatch(text):
        return _member_mark_object_type(text)
    if _CONNECTION.fullmatch(text):
        if text.startswith("BOLT"):
            return "bolt"
        if text.startswith("WELD"):
            return "weld"
        return "connection"

    if _STRUCTURAL_CONTEXT.search(context):
        if re.fullmatch(r"A(?:325|490)", text) and re.search(
            r"\bBOLTS?\b", context, re.IGNORECASE
        ):
            return "bolt"
        if re.fullmatch(r"E(?:60|70|80)XX", text) and re.search(
            r"\bWELDS?\b", context, re.IGNORECASE
        ):
            return "weld"
    return None


def filter_engineering_objects(
    tokens: Iterable[Dict[str, Any]],
    *,
    document: Dict[str, Any] | None = None,
    discard_counts: Dict[str, int] | None = None,
) -> List[Dict[str, Any]]:
    """Return prediction-ready structural labels with extraction metadata."""

    selected: List[Dict[str, Any]] = []
    counts = discard_counts if discard_counts is not None else {}
    for token in tokens:
        object_type = classify_engineering_object(token, document=document)
        if object_type is None:
            continue
        reason = classify_extraction_noise_reason(
            token, document=document, object_type=object_type
        )
        if reason:
            counts[reason] = int(counts.get(reason) or 0) + 1
            continue
        selected.append({**token, "engineering_object_type": object_type})
    before = len(selected)
    deduped = dedupe_engineering_tokens(selected)
    duplicates = before - len(deduped)
    if duplicates:
        counts["duplicates"] = int(counts.get("duplicates") or 0) + duplicates
    return deduped
