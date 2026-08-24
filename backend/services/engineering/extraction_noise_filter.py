"""Drop non-takeoff tokens during engineering-object selection."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from services.engineering.feet_inch_filter import (
    is_non_steel_layout_dimension,
    is_non_steel_layout_token,
)

_TITLE_BLOCK_ROLES = frozenset({"title", "title_block", "border", "sheet_index"})
_STANDALONE_GRADE_RE = re.compile(r"^A(?:36|572|992|500|913|325|490)$", re.I)
_STANDALONE_SHEET_RE = re.compile(r"^S-\d+$", re.I)
_STANDALONE_SPEC_RE = re.compile(r"^(?:ASTM|AISC)\b", re.I)
_STRUCTURAL_NEARBY_RE = re.compile(
    r"\b(?:BEAM|COLUMN|COL\.?|BRACE|PLATE|PL\b|BENT|BOLTS?|WELDS?|CONN(?:ECTION)?|"
    r"GUSSET|STIFFENER|HSS|W\d|DETAIL|FRAMING|MEMBER|POST)\b",
    re.I,
)
_DETAIL_CONTEXT_RE = re.compile(
    r"\b(?:DETAIL|SECTION|SHEAR|MOMENT|CONN(?:ECTION)?|GUSSET|STIFFENER|CLIP|SEAT)\b",
    re.I,
)
_FRACTIONAL_THICKNESS_RE = re.compile(r'^\d+/\d+"?$', re.I)
_SEMANTIC_DEDUP_TYPES = frozenset(
    {"steel_section", "column", "column_or_brace", "brace", "beam"}
)


def _bbox_overlap(a: list, b: list, *, min_ratio: float = 0.25) -> bool:
    if not a or not b or len(a) < 4 or len(b) < 4:
        return False
    x0 = max(float(a[0]), float(b[0]))
    y0 = max(float(a[1]), float(b[1]))
    x1 = min(float(a[2]), float(b[2]))
    y1 = min(float(a[3]), float(b[3]))
    if x1 <= x0 or y1 <= y0:
        return False
    inter = (x1 - x0) * (y1 - y0)
    area_a = max(1.0, (float(a[2]) - float(a[0])) * (float(a[3]) - float(a[1])))
    return inter / area_a >= min_ratio


def token_in_title_block(
    token: Dict[str, Any],
    title_blocks: Optional[Iterable[Dict[str, Any]]] = None,
) -> bool:
    """True when token bbox overlaps a detected title-block region."""

    page = int(token.get("page") or token.get("page_number") or 0)
    bbox = token.get("bbox")
    if not bbox:
        return False
    block_role = str((token.get("context") or {}).get("block_role") or "").lower()
    if block_role in _TITLE_BLOCK_ROLES:
        return True
    for block in title_blocks or ():
        if int(block.get("page_number") or 0) != page:
            continue
        block_bbox = block.get("bbox")
        if block_bbox and _bbox_overlap(bbox, block_bbox):
            return True
    return False


def is_standalone_reference_label(text: str) -> bool:
    """Material grades and sheet refs with no local structural meaning."""

    compact = re.sub(r"\s+", "", str(text or "").upper())
    if not compact:
        return False
    return bool(
        _STANDALONE_GRADE_RE.fullmatch(compact)
        or _STANDALONE_SHEET_RE.fullmatch(compact)
        or _STANDALONE_SPEC_RE.search(compact)
    )


def linked_layout_is_non_steel(token: Dict[str, Any]) -> bool:
    """True when OCR token overlaps a layout dimension that is not steel."""

    layout_text = (token.get("context") or {}).get("layout_dimension_text")
    if not layout_text:
        return False
    return is_non_steel_layout_dimension(str(layout_text))


def _anonymous_context_blob(token: Dict[str, Any]) -> str:
    context_parts = [
        token.get("surrounding_text") or "",
        (token.get("context") or {}).get("line_text") or "",
        (token.get("context") or {}).get("block_text") or "",
        " ".join((token.get("context") or {}).get("neighbor_text") or []),
    ]
    return " | ".join(part for part in context_parts if part)


def _has_detail_callout_context(token: Dict[str, Any], blob: str) -> bool:
    if _DETAIL_CONTEXT_RE.search(blob):
        return True
    block_role = str((token.get("context") or {}).get("block_role") or "").lower()
    if block_role in {"detail", "callout", "connection_detail"}:
        return True
    if token.get("layout_dimension_id"):
        return True
    return False


def is_weak_anonymous_dimension(token: Dict[str, Any]) -> bool:
    """Drop anonymous dims unless structural or detail-context signals exist."""

    blob = _anonymous_context_blob(token)
    if _STRUCTURAL_NEARBY_RE.search(blob):
        return False
    if re.search(
        r"\b(?:GENERAL\s+NOTES?|SPECIFICATIONS?|LEGEND|SHEET\s+INDEX|MATERIAL\s+NOTES?)\b",
        blob,
        re.I,
    ):
        return True
    if linked_layout_is_non_steel(token):
        return True
    normalized = re.sub(
        r"\s+",
        "",
        str(token.get("normalized_text") or token.get("text") or "").upper(),
    )
    if _FRACTIONAL_THICKNESS_RE.match(normalized) and _has_detail_callout_context(
        token, blob
    ):
        return False
    return True


def is_extraction_noise_token(
    token: Dict[str, Any],
    *,
    document: Optional[Dict[str, Any]] = None,
    object_type: Optional[str] = None,
) -> bool:
    """True when token should not enter steel takeoff extraction/analysis."""

    return classify_extraction_noise_reason(token, document=document, object_type=object_type) is not None


def classify_extraction_noise_reason(
    token: Dict[str, Any],
    *,
    document: Optional[Dict[str, Any]] = None,
    object_type: Optional[str] = None,
) -> str | None:
    """Return a discard reason label or None when token is steel-relevant."""

    if is_non_steel_layout_token(token):
        return "layout_dims"

    doc = document or {}
    title_blocks = doc.get("title_blocks") or []
    if token_in_title_block(token, title_blocks):
        return "title_block"

    text = re.sub(
        r"\s+",
        "",
        str(token.get("normalized_text") or token.get("text") or "").upper(),
    )
    context = " | ".join(
        str(part or "")
        for part in (
            token.get("surrounding_text"),
            (token.get("context") or {}).get("line_text"),
            (token.get("context") or {}).get("block_text"),
            " ".join((token.get("context") or {}).get("neighbor_text") or []),
        )
        if part
    )
    if is_standalone_reference_label(text) and not _STRUCTURAL_NEARBY_RE.search(context):
        return "standalone_refs"

    if linked_layout_is_non_steel(token):
        return "layout_dims"

    resolved_type = object_type or token.get("engineering_object_type")
    if resolved_type == "anonymous_dimension" and is_weak_anonymous_dimension(token):
        return "weak_anonymous"

    return None


def dedupe_engineering_tokens(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate labels at the same page and nearby coordinates."""

    seen: set[tuple] = set()
    deduped: List[Dict[str, Any]] = []
    for token in tokens:
        page = int(token.get("page") or 0)
        normalized = re.sub(
            r"\s+",
            "",
            str(token.get("normalized_text") or token.get("text") or "").upper(),
        )
        bbox = token.get("bbox") or [0, 0, 0, 0]
        key = (
            page,
            normalized,
            round(float(bbox[0]), 0),
            round(float(bbox[1]), 0),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(token)
    return deduped


def dedupe_semantic_members(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse repeated member labels on one page into one representative token."""

    passthrough: List[Dict[str, Any]] = []
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for token in tokens:
        object_type = str(token.get("engineering_object_type") or "")
        if object_type not in _SEMANTIC_DEDUP_TYPES:
            passthrough.append(token)
            continue
        page = int(token.get("page") or 0)
        normalized = re.sub(
            r"\s+",
            "",
            str(token.get("normalized_text") or token.get("text") or "").upper(),
        )
        key = (page, normalized, object_type)
        groups.setdefault(key, []).append(token)

    collapsed: List[Dict[str, Any]] = []
    for members in groups.values():
        ranked = sorted(
            members,
            key=lambda item: (
                -float(item.get("confidence") or 0.0),
                float((item.get("bbox") or [0, 0, 0, 0])[0]),
            ),
        )
        representative = dict(ranked[0])
        duplicate_bboxes = [
            list(item.get("bbox") or [])
            for item in ranked[1:]
            if item.get("bbox")
        ]
        representative["repeat_count"] = len(members)
        if duplicate_bboxes:
            representative["duplicate_bboxes"] = duplicate_bboxes
            representative.setdefault("diagnostics", {})[
                "semantic_member_duplicates"
            ] = len(duplicate_bboxes)
        collapsed.append(representative)

    return passthrough + collapsed
