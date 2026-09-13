"""Review-only typical-condition linker.

Connects a thickness-bearing typical/detail stamp to a matching *named*
plan condition note. This is condition-linking, not physical-member
reconstruction: it does not count pieces, measure length, or infer a
section from geometry or Excel.

Objects are always ``requires_review=true`` / ``takeoff_eligible=false``
and must stay off QuantityEngine and eligible Validation counts.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services.database_loader import catalog_form, lookup_shape
from services.engineering.context_scope import (
    drawing_title_by_page,
    typical_detail_pages,
)

OBJECT_KIND_REPEATED_DETAIL = "repeated_detail_member"
OBJECT_SCOPE_REPEATED_DETAIL = "repeated_detail_evidence"
PREDICTION_SOURCE_REPEATED_DETAIL = "REPEATED_DETAIL"

# Nearest typical-title association on the same sheet as a seed stamp.
_TITLE_ASSOCIATION_RADIUS = 600.0

# Inspectable condition catalog. Add a new rule only when a typical title
# and plan-note wording are both unique. Do not match generic BRACE / TYP /
# SEE TYP DET / sheet numbers.
CONDITION_RULES: Tuple[Dict[str, Any], ...] = (
    {
        "condition_id": "bottom_flange_brace",
        "typical_title_patterns": (
            re.compile(
                r"TYPICAL\s+BEAM\s+(?:BOTTOM\s+)?FLANGE\s+BRACE\s+DETAIL",
                re.I,
            ),
        ),
        "plan_note_patterns": (
            re.compile(
                r"BOT(?:TOM)?\s+(?:FLANGE|FLG)\s+BRACE.{0,60}SEE\s+TYP(?:ICAL)?\s+DET",
                re.I,
            ),
        ),
        "plan_note_reject_patterns": (
            re.compile(r"\bCROSS\s+BRACE\b", re.I),
            re.compile(r"\bRELIEVING\s+ANGLE\b", re.I),
            re.compile(r"\bHANG(?:ING)?\s+LINTEL\b", re.I),
            re.compile(r"\bLOOSE\s+LINTEL\b", re.I),
            re.compile(r"\bBRACING\b", re.I),
        ),
        "seed_reject_patterns": (
            re.compile(r"\bBRACING\b", re.I),
            re.compile(r"\bCROSS\s+BRACE\b", re.I),
            re.compile(r"\bRELIEVING\s+ANGLE\b", re.I),
            re.compile(r"\bLINTEL\b", re.I),
            re.compile(r"\bSEE\s+SCHEDULE\b", re.I),
        ),
    },
)

_TYP_CONT_RE = re.compile(r"\b(?:TYP|CONT(?:INUOUS)?)\b", re.I)
_SECTION_CANDIDATE_RE = re.compile(
    r"\b(?:2L|L|C|MC|WT|W|HSS|PIPE)\s*\d[\w./\-]*",
    re.I,
)
# Catalog-complete angles/HSS write thickness as a third X-field.
_EXPLICIT_THICKNESS_RE = re.compile(r"X(?:\d+/\d+|\d*\.\d+)$", re.I)


def is_repeated_detail_member(item: Dict[str, Any]) -> bool:
    return str(item.get("object_kind") or "") == OBJECT_KIND_REPEATED_DETAIL


def _center(bbox: Sequence[float]) -> Tuple[float, float]:
    if not bbox or len(bbox) < 4:
        return (0.0, 0.0)
    return (
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    )


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    ax, ay = _center(left)
    bx, by = _center(right)
    return math.hypot(ax - bx, ay - by)


def _page_number(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("page_number") or item.get("page") or 0)
    except (TypeError, ValueError):
        return 0


def _bbox(item: Dict[str, Any]) -> List[float]:
    raw = item.get("bbox") or item.get("bounding_box") or [0, 0, 0, 0]
    try:
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError, IndexError):
        return [0.0, 0.0, 0.0, 0.0]


def _text(item: Dict[str, Any]) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(item.get("text") or item.get("raw_text") or item.get("line_text") or ""),
    ).strip()


def _text_items(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for key in ("blocks", "lines", "callouts"):
        for raw in document.get(key) or []:
            if not isinstance(raw, dict):
                continue
            text = _text(raw)
            if not text:
                continue
            items.append(
                {
                    "text": text,
                    "page": _page_number(raw),
                    "bbox": _bbox(raw),
                    "source": key,
                }
            )
    return items


def _catalog_complete_section(text: str) -> Optional[str]:
    form = catalog_form(text)
    if not form:
        return None
    entry = lookup_shape(form)
    return str(entry["shape"]) if entry else form


def _has_explicit_thickness(section: str) -> bool:
    compact = str(section or "").upper().replace(" ", "").replace("×", "X")
    return bool(_EXPLICIT_THICKNESS_RE.search(compact))


def _thickness_bearing_section(text: str) -> Optional[str]:
    """Return a catalog-complete section with explicit thickness, or None.

    Incomplete labels such as ``L4X4`` and bare ``L`` never qualify.
    ``document_prior`` is not consulted.
    """

    if not _TYP_CONT_RE.search(text or ""):
        return None
    best: Optional[str] = None
    for match in _SECTION_CANDIDATE_RE.finditer(text or ""):
        section = _catalog_complete_section(match.group(0))
        if not section or not _has_explicit_thickness(section):
            continue
        if best is None or len(section) > len(best):
            best = section
    return best


def _rule_for_title(text: str) -> Optional[Dict[str, Any]]:
    for rule in CONDITION_RULES:
        if any(pattern.search(text) for pattern in rule["typical_title_patterns"]):
            return rule
    return None


def _plan_note_matches(text: str, rule: Dict[str, Any]) -> bool:
    if any(pattern.search(text) for pattern in rule["plan_note_reject_patterns"]):
        return False
    return any(pattern.search(text) for pattern in rule["plan_note_patterns"])


def _typical_context_page(
    document: Dict[str, Any],
    page: int,
    *,
    has_typical_title: bool,
) -> bool:
    if has_typical_title:
        return True
    if page in typical_detail_pages(document):
        return True
    title = drawing_title_by_page(document).get(page) or ""
    return bool(re.search(r"\b(?:TYPICAL\s+DETAILS?|SECTIONS?)\b", title, re.I))


def _stable_id(parts: Iterable[str]) -> str:
    seed = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"rdm_{digest}"


def _evidence_step(step_type: str, text: str, page: Optional[int] = None) -> dict:
    step = {"type": step_type, "text": text}
    if page:
        step["page"] = page
    return step


def link_repeated_detail_members(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return review-only condition links. Never reads Excel or geometry."""

    if not isinstance(document, dict):
        return []

    items = _text_items(document)
    titles: List[Dict[str, Any]] = []
    for item in items:
        rule = _rule_for_title(item["text"])
        if not rule:
            continue
        titles.append({**item, "rule": rule})

    seeds: List[Dict[str, Any]] = []
    for item in items:
        section = _thickness_bearing_section(item["text"])
        if not section:
            continue
        same_page_titles = [
            title for title in titles if title["page"] == item["page"]
        ]
        nearest = None
        nearest_distance = _TITLE_ASSOCIATION_RADIUS
        for title in same_page_titles:
            if any(
                pattern.search(item["text"])
                for pattern in title["rule"]["seed_reject_patterns"]
            ):
                continue
            distance = _distance(item["bbox"], title["bbox"])
            if distance <= nearest_distance:
                nearest = title
                nearest_distance = distance
        if nearest is None:
            continue
        if not _typical_context_page(
            document, item["page"], has_typical_title=True
        ):
            continue
        seeds.append(
            {
                **item,
                "section": section,
                "title": nearest,
                "rule": nearest["rule"],
            }
        )

    # One seed per typical title on a page, so two L4X4X1/4 TYP stamps in
    # the same detail viewport do not double the review objects.
    unique_seeds: Dict[Tuple[int, str, str], Dict[str, Any]] = {}
    for seed in seeds:
        key = (
            seed["page"],
            seed["rule"]["condition_id"],
            seed["title"]["text"],
        )
        current = unique_seeds.get(key)
        if current is None:
            unique_seeds[key] = seed
            continue
        if _distance(seed["bbox"], seed["title"]["bbox"]) < _distance(
            current["bbox"], current["title"]["bbox"]
        ):
            unique_seeds[key] = seed
    seeds = list(unique_seeds.values())
    if not seeds:
        return []

    skipped_note_pages = typical_detail_pages(document)
    members: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if item["page"] in skipped_note_pages:
            continue
        for seed in seeds:
            if item["page"] == seed["page"]:
                continue
            if not _plan_note_matches(item["text"], seed["rule"]):
                continue
            object_id = _stable_id(
                (
                    seed["rule"]["condition_id"],
                    seed["section"],
                    str(seed["page"]),
                    str(item["page"]),
                    item["text"],
                )
            )
            if object_id in seen:
                continue
            seen.add(object_id)
            members.append(_build_member(document, seed, item, object_id))
    return members


def _build_member(
    document: Dict[str, Any],
    seed: Dict[str, Any],
    note: Dict[str, Any],
    object_id: str,
) -> Dict[str, Any]:
    titles = drawing_title_by_page(document)
    inherited = seed["section"]
    return {
        "object_id": object_id,
        "object_kind": OBJECT_KIND_REPEATED_DETAIL,
        "object_scope": OBJECT_SCOPE_REPEATED_DETAIL,
        "prediction_source": PREDICTION_SOURCE_REPEATED_DETAIL,
        "extraction_method": "repeated_detail_linker",
        "inherited_section": inherited,
        "section": inherited,
        "source_detail_annotation": seed["text"],
        "source_page": seed["page"],
        "source_bbox": seed["bbox"],
        "source_typical_title": seed["title"]["text"],
        "condition_id": seed["rule"]["condition_id"],
        "target_sheet": titles.get(note["page"]) or "",
        "target_page": note["page"],
        "target_bbox": note["bbox"],
        "target_condition_text": note["text"],
        "evidence_chain": [
            _evidence_step(
                "thickness_bearing_seed",
                seed["text"],
                seed["page"],
            ),
            _evidence_step("typical_title", seed["title"]["text"]),
            _evidence_step(
                "plan_condition",
                note["text"],
                note["page"],
            ),
        ],
        "confidence": 0.62,
        "requires_review": True,
        "takeoff_eligible": False,
        "review_status": "pending_review",
        "_skip_unknown_queue": True,
    }
