"""Separate legend / general-note *definitions* from real takeoff objects.

A steel designation printed inside an ABBREVIATIONS table, a LEGEND, or a
STRUCTURAL/GENERAL NOTES block (the HSS8x4x1/4 in an ``HSS8x4 = HSS8x4x1/4``
row, a W8x10 in a framing key) is a DEFINITION of project notation, not a
member that exists on the structure. It must feed the context analyzer and
the project-rule profile, but it must never be counted, priced, or routed
to human review as if it were a real member.

This module tags every engineering token with:

* ``object_scope`` -- ``"takeoff"`` (default), ``"context_definition"``,
  ``"detail_reference"``, or ``"non_member_dimension"``;
* ``takeoff_eligible`` -- ``True`` (default) or ``False``.

A token is demoted to ``context_definition`` **only** when its page was
confidently classified as a readable context page by
``legend_profile.detect_context_pages`` -- i.e. a page that matched a real
LEGEND / ABBREVIATIONS / GENERAL NOTES / STRUCTURAL NOTES / SPECIFICATIONS
heading AND did NOT pass
``legend_profile._has_strong_structural_drawing_evidence`` (renovation
``(E)``/``(N)`` member tags, OR >= 25 catalog-valid section labels, OR a
framing/schedule sheet title with >= 10 real labels -- see that function
for the business rationale). A note keyword alone never suppresses a page
that is doing real steel takeoff work. The old, softer ``document_prior``
legend score is deliberately NOT used here -- it over-flags steel-dense
framing plans (see the checkpoint-2 diagnosis in ``legend_profile.py``).

Separately, a token is demoted to ``detail_reference`` when its *sheet
drawing title* (the title-block field next to ``DRAWING TITLE:``) names a
typical/connection-detail sheet, or when the raw token is an angle/channel
with a fabrication cut length (``L3x3x1/4x0'-3"``). Those are connection
components and detail callouts, not rolled-member instances. Framing plans,
column schedules, and ``TYPICAL FRAMING PLAN`` sheets are never demoted by
this path -- the title is the evidence, not the section family.

This gate does **not** change legend/page-classifier v5. ``STEEL SECTIONS
AND DETAILS`` sheets are left eligible because they often carry the only
extracted copy of a real member.

Fail-safe: no ``legend_profile``, or no context pages, leaves every token
``takeoff_eligible = True`` unless a typical-detail title or clip-length
token is independently recognized.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from services.engineering.legend_profile import _CONTEXT_PAGE_ROLES

OBJECT_SCOPE_TAKEOFF = "takeoff"
OBJECT_SCOPE_CONTEXT_DEFINITION = "context_definition"
OBJECT_SCOPE_NON_MEMBER_DIMENSION = "non_member_dimension"
OBJECT_SCOPE_DETAIL_REFERENCE = "detail_reference"

_DRAWING_TITLE_LABEL_RE = re.compile(r"^\s*DRAWING\s+TITLE:?\s*$", re.I)
_SCALE_LABEL_RE = re.compile(r"^\s*SCALE:?\s*$", re.I)
# Sheet titles whose content is typical/connection details -- not member
# instances. "TYPICAL FRAMING PLAN" is excluded by the member-title check
# below, not by omitting TYPICAL here.
_TYPICAL_DETAIL_TITLE_RE = re.compile(
    r"\bTYPICAL\s+(?:STEEL\s+|CONCRETE\s+|MASONRY\s+|FOUNDATION\s+|EXISTING\s+(?:BUILDING\s+)?)?"
    r"DETAILS?\b"
    r"|\bCONNECTION\s+DETAILS?\b"
    r"|\bTYPICAL\s+CONNECTIONS?\b",
    re.I,
)
_MEMBER_SHEET_TITLE_RE = re.compile(
    r"\bFRAMING\s+PLAN\b|\bCOLUMN\s+SCHEDULE\b|\bBEAM\s+SCHEDULE\b"
    r"|\bBRACE(?:ING)?\s+SCHEDULE\b|\bFRAMING\s+SCHEDULE\b"
    r"|\bERECTION\s+PLAN\b|\bFOUNDATION\s+PLAN\b",
    re.I,
)
# Clip / connection angle with an explicit piece length.
# Examples: L3x3x1/4x0'-3"  and L4x3x1/4x6"
_CLIP_FABRICATION_RE = re.compile(
    r"(?:2L|L|C|MC|WT)\s*\d[\w./\-]*X\s*0\s*['’]"
    r"|(?:2L|L|C|MC|WT)\s*\d[\w./\-]*X\s*\d+\s*['’]\s*-"
    r"|(?:2L|L|C|MC|WT)\s*\d[\w./\-]*X\s*\d+\s*\"",
    re.I,
)
_FALLBACK_TITLE_MAX_CHARS = 80
_TYPICAL_MEMBER_CONTEXT_RE = re.compile(
    r"\b(?:CONT(?:INUOUS)?|RELIEVING\s+ANGLE|EDGE\s+ANGLE|SHELF\s+ANGLE|"
    r"LINTEL|LOOSE\s+LINTEL)\b",
    re.I,
)
_TYPICAL_STAMP_RE = re.compile(
    r"(?:2L|L|C|MC)\s*[\d./\-X×]+\s+TYP\b",
    re.I,
)
_CONNECTION_CONTEXT_RE = re.compile(
    r"\b(?:CLIP|GUSSET|STIFFENER|SEAT|MOMENT\s+CONN|SHEAR\s+CONN)\b",
    re.I,
)
_FULL_ANGLE_OR_CHANNEL_RE = re.compile(
    r"^(?:2L|L|C|MC)\d+(?:\.\d+)?(?:-\d+/\d+)?X\d+(?:\.\d+)?(?:-\d+/\d+)?"
    r"X(?:\d+/\d+|\d+(?:\.\d+)?)$",
    re.I,
)


def _bbox(block: Dict[str, Any]) -> Tuple[float, float, float, float]:
    raw = block.get("bbox") or [0, 0, 0, 0]
    try:
        return (
            float(raw[0] or 0),
            float(raw[1] or 0),
            float(raw[2] or 0),
            float(raw[3] or 0),
        )
    except (TypeError, ValueError, IndexError):
        return (0.0, 0.0, 0.0, 0.0)


def _block_text(block: Dict[str, Any]) -> str:
    return str(block.get("text") or "").replace("\n", " ").strip()


def drawing_title_by_page(document: Dict[str, Any]) -> Dict[int, str]:
    """Return the sheet drawing title for each page from title-block geometry.

    Uses the text sitting in the same title-block column immediately below a
    ``DRAWING TITLE:`` label -- not incidental ``SEE FRAMING PLAN`` notes on
    the same sheet, and not the sheet-index list of other drawings.
    """

    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for block in document.get("title_blocks") or []:
        try:
            page = int(block.get("page_number") or block.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        if not page:
            continue
        by_page.setdefault(page, []).append(block)

    titles: Dict[int, str] = {}
    for page, blocks in by_page.items():
        labels = [
            block
            for block in blocks
            if _DRAWING_TITLE_LABEL_RE.match(_block_text(block))
        ]
        if not labels:
            continue
        label = labels[0]
        x0, y0, _x1, y1 = _bbox(label)
        below: List[Tuple[float, str]] = []
        for block in blocks:
            if block is label:
                continue
            bx0, by0, _bx1, _by1 = _bbox(block)
            if by0 < y0 - 2 or by0 > y1 + 160:
                continue
            if bx0 < x0 - 40:
                continue
            text = _block_text(block)
            if not text or _SCALE_LABEL_RE.match(text):
                continue
            if text.upper().startswith("SCALE"):
                continue
            if re.match(r"^\s*PROJECT\b", text, re.I):
                continue
            below.append((by0, text))
        below.sort()
        parts: List[str] = []
        for _y, text in below:
            if _SCALE_LABEL_RE.match(text) or text.upper().startswith("SCALE"):
                break
            parts.append(text)
            if len(" ".join(parts)) >= 90:
                break
        titles[page] = " ".join(parts).strip()

    for page, blocks in by_page.items():
        if titles.get(page):
            continue
        for block in blocks:
            text = " ".join(_block_text(block).split())
            if not text or len(text) > _FALLBACK_TITLE_MAX_CHARS:
                continue
            if is_typical_detail_sheet_title(text) or is_member_sheet_title(text):
                titles[page] = text
                break
    return titles


def is_member_sheet_title(title: str) -> bool:
    return bool(_MEMBER_SHEET_TITLE_RE.search(title or ""))


def is_typical_detail_sheet_title(title: str) -> bool:
    """True for typical/connection-detail sheet titles that are not also
    framing/schedule titles (``TYPICAL FRAMING PLAN`` stays a member sheet)."""

    if is_member_sheet_title(title):
        return False
    return bool(_TYPICAL_DETAIL_TITLE_RE.search(title or ""))


def typical_detail_pages(document: Dict[str, Any]) -> set[int]:
    """Pages whose drawing title identifies a typical/connection-detail sheet."""

    return {
        page
        for page, title in drawing_title_by_page(document).items()
        if is_typical_detail_sheet_title(title)
    }


def is_clip_fabrication_token(item: Dict[str, Any]) -> bool:
    raw = str(
        item.get("raw_text")
        or item.get("original_token")
        or item.get("text")
        or item.get("token")
        or ""
    )
    compact = raw.replace(" ", "")
    return bool(_CLIP_FABRICATION_RE.search(raw) or _CLIP_FABRICATION_RE.search(compact))


def _local_member_context(item: Dict[str, Any]) -> str:
    context = item.get("context") or {}
    return " ".join(
        str(part or "")
        for part in (
            context.get("line_text"),
            " ".join(context.get("neighbor_text") or []),
            item.get("raw_text"),
            item.get("text"),
        )
        if part
    )


def is_specified_typical_member_token(item: Dict[str, Any]) -> bool:
    """True for a catalog-complete angle/channel that the sheet specifies
    as a typical continuous member (edge/relieving/lintel), not a clip.

    Typical-detail pages still hide connection callouts; these stamps are
    often the only extracted copy of a real takeoff angle.
    """

    if is_clip_fabrication_token(item):
        return False
    compact = re.sub(
        r"\s+",
        "",
        str(item.get("normalized_text") or item.get("text") or "").upper().replace("×", "X"),
    )
    if not _FULL_ANGLE_OR_CHANNEL_RE.match(compact):
        return False
    blob = _local_member_context(item)
    if _CONNECTION_CONTEXT_RE.search(blob):
        return False
    if _TYPICAL_MEMBER_CONTEXT_RE.search(blob):
        return True
    return bool(_TYPICAL_STAMP_RE.search(blob))


def _demote_as_detail_reference(item: Dict[str, Any]) -> None:
    item["object_scope"] = OBJECT_SCOPE_DETAIL_REFERENCE
    item["takeoff_eligible"] = False
    item["_skip_unknown_queue"] = True


def context_definition_pages(document: Dict[str, Any]) -> set[int]:
    """Page numbers whose whole content is project context (legend / notes /
    abbreviations / specifications), from the strict classifier only."""

    profile = document.get("legend_profile")
    if not isinstance(profile, dict):
        return set()
    pages: set[int] = set()
    for raw_page, role in (profile.get("context_pages") or {}).items():
        if role in _CONTEXT_PAGE_ROLES:
            try:
                pages.add(int(raw_page))
            except (TypeError, ValueError):
                continue
    return pages


def annotate_takeoff_scope(document: Dict[str, Any]) -> Dict[str, Any]:
    """Tag ``document["engineering_tokens"]`` in place. Returns a small
    diagnostic count dict."""

    tokens: List[Dict[str, Any]] = document.get("engineering_tokens") or []
    context_pages = context_definition_pages(document)
    detail_pages = typical_detail_pages(document)

    context_demoted = 0
    detail_demoted = 0
    clip_demoted = 0
    for token in tokens:
        try:
            page = int(token.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        if is_clip_fabrication_token(token):
            _demote_as_detail_reference(token)
            clip_demoted += 1
        elif is_specified_typical_member_token(token):
            token.setdefault("object_scope", OBJECT_SCOPE_TAKEOFF)
            token["takeoff_eligible"] = True
        elif page and page in context_pages:
            token["object_scope"] = OBJECT_SCOPE_CONTEXT_DEFINITION
            token["takeoff_eligible"] = False
            # Existing pipeline hook: keep these out of the unknown-token
            # review queue (see multimodal/pipeline.py).
            token["_skip_unknown_queue"] = True
            context_demoted += 1
        elif page and page in detail_pages:
            _demote_as_detail_reference(token)
            detail_demoted += 1
        else:
            token.setdefault("object_scope", OBJECT_SCOPE_TAKEOFF)
            token.setdefault("takeoff_eligible", True)

    diagnostics = (
        (document.get("legend_profile") or {}).get("diagnostics") or {}
    )
    demoted = context_demoted + detail_demoted + clip_demoted
    return {
        "context_definition_pages": sorted(context_pages),
        "context_definition_tokens": context_demoted,
        "typical_detail_pages": sorted(detail_pages),
        "detail_reference_tokens": detail_demoted + clip_demoted,
        "clip_fabrication_tokens": clip_demoted,
        "takeoff_tokens": len(tokens) - demoted,
        # Framing/schedule pages that carried a note/legend keyword but were
        # kept takeoff-eligible because they are dense with real steel
        # labels (see legend_profile._has_strong_structural_drawing_evidence).
        "full_page_demotion_blocked_pages": list(
            diagnostics.get("full_page_demotion_blocked_pages") or []
        ),
    }


def _prediction_page(item: Dict[str, Any]) -> int:
    source_text = item.get("source_text")
    if isinstance(source_text, dict) and source_text.get("page_number") is not None:
        candidate = source_text.get("page_number")
    else:
        candidate = item.get("page_number") or item.get("page")
    try:
        return int(candidate or 0)
    except (TypeError, ValueError):
        return 0


def reassert_prediction_scope(
    predictions: List[Dict[str, Any]], document: Dict[str, Any]
) -> int:
    """Stamp ``takeoff_eligible = False`` on any prediction that sits on a
    context-definition or typical-detail page, or that is a clip-length
    connection piece, regardless of how it entered the prediction list.
    The extraction-time pass only tags ``document["engineering_tokens"]``;
    geometry/graph "missing label" predictions, schedule/spatial tokens, and
    label propagation all synthesize predictions afterwards and would
    otherwise slip a phantom member onto a legend/notes/detail page.
    Returns the number newly demoted."""

    context_pages = context_definition_pages(document)
    detail_pages = typical_detail_pages(document)
    demoted = 0
    for prediction in predictions:
        if prediction.get("takeoff_eligible") is False:
            continue
        if is_clip_fabrication_token(prediction):
            _demote_as_detail_reference(prediction)
            demoted += 1
            continue
        if is_specified_typical_member_token(prediction):
            continue
        page = _prediction_page(prediction)
        if page in context_pages:
            prediction["object_scope"] = OBJECT_SCOPE_CONTEXT_DEFINITION
            prediction["takeoff_eligible"] = False
            demoted += 1
        elif page in detail_pages:
            _demote_as_detail_reference(prediction)
            demoted += 1
    return demoted


def is_takeoff_eligible(item: Dict[str, Any]) -> bool:
    """True unless the item was explicitly excluded from member takeoff.

    Context definitions, typical-detail / clip-length references, and
    anonymous dimensions that completed semantic interpretation without
    promotion all use the existing explicit ``takeoff_eligible=False``
    contract.
    """

    return item.get("takeoff_eligible", True) is not False


def partition_takeoff(items: List[Dict[str, Any]]) -> tuple[list, list]:
    """Split a prediction / token list into (takeoff, excluded)."""

    takeoff: List[Dict[str, Any]] = []
    context_definitions: List[Dict[str, Any]] = []
    for item in items:
        (takeoff if is_takeoff_eligible(item) else context_definitions).append(item)
    return takeoff, context_definitions
