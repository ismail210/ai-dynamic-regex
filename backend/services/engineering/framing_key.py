"""Graphical framing keys: what each part of a member callout means, read
from the key's own printed labels and leader lines.

A structural set often defines its beam-callout notation with a drawn
example instead of a sentence (OSSE S-001-O "STRUCTURAL STEEL FRAMING KEY":
``W18X40 [35] c=1 1/4" <+12'-3">`` with a leader from ``[35]`` to
"# OF SHEAR STUDS. SEE TYPICAL DETAIL", from ``c=1 1/4"`` to "CAMBER" and
from ``<+12'-3">`` to "TOP OF STEEL ELEVATION RELATIVE TO DATUM").

The meaning of a part is the label its leader ends at -- printed text, kept
as printed. Nothing is assumed from common practice: a part with no leader,
or whose leader ends at no label, has no meaning here. ``field`` only names
the printed label's subject for display and grounding; it never turns the
example's numbers into quantities (the ``35`` in the example is not a stud
count of anything).

Evidence only: nothing here changes prediction, schedules or quantities.
Boxes are in PDF space, like the rest of the extracted document.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from services.engineering.column_schedule import _union_boxes
from services.engineering.level_evidence import _inside_any

_KEY_HEADING_RE = re.compile(r"\b(?:FRAMING|BEAM|STEEL|MEMBER)\b.*\b(?:KEY|LEGEND)\b|\b(?:KEY|LEGEND)\b.*\bFRAMING\b",
                             re.IGNORECASE)
_SECTION_RE = re.compile(r"\b(?:W|HSS|MC|WT|C|L|S|HP)\d+(?:\.\d+)?[xX][\d./]+(?:[xX][\d./]+)*")
# Parts a callout example can carry after the section.
_PART_RES = (
    # [35], [8;8], or a placeholder a key prints for the number ([X], [#], [N]).
    ("bracketed integer", re.compile(r"\[\s*(?:\d+(?:\s*;\s*\d+)*|[X#N])\s*\]")),
    ("c= value", re.compile(r"\bc\s*=\s*\d+(?:\s+\d+/\d+|/\d+)?\s*\"?", re.IGNORECASE)),
    ("angle-bracketed elevation", re.compile(r"<\s*[-+−]?\s*\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?\s*\"\s*>")),
)
_FIELDS = (
    ("shear_studs", re.compile(r"SHEAR\s+STUDS?", re.IGNORECASE)),
    ("camber", re.compile(r"\bCAMBER\b", re.IGNORECASE)),
    ("top_of_steel_elevation", re.compile(r"TOP\s+OF\s+STEEL", re.IGNORECASE)),
    ("reaction", re.compile(r"\bREACTION\b", re.IGNORECASE)),
)
_REGION = 320.0        # how far around the heading the key's drawing extends
_TIP_REACH = 6.0       # a leader's tip touches the text it points at
_LABEL_REACH = 40.0    # a leader ends next to its label
_LEADER_MAX_WIDTH = 0.8
_LEADER_MIN_LENGTH = 20.0


def _distance(point: tuple, box: List[float]) -> float:
    dx = max(box[0] - point[0], 0.0, point[0] - box[2])
    dy = max(box[1] - point[1], 0.0, point[1] - box[3])
    return math.hypot(dx, dy)


def _segments(drawings: List[dict], region: List[float]) -> List[tuple]:
    out = []
    for path in drawings:
        if float(path.get("width") or 0.0) >= _LEADER_MAX_WIDTH:
            continue
        for item in path["items"]:
            if item[0] == "l":
                # Points are fitz.Point (get_drawings) or (x, y) tuples (get_cdrawings).
                (ax, ay), (bx, by) = tuple(item[1])[:2], tuple(item[2])[:2]
                if all(region[0] <= x <= region[2] and region[1] <= y <= region[3] for x, y in ((ax, ay), (bx, by))):
                    out.append((ax, ay, bx, by))
    return out


def _leaders(target: List[float], segments: List[tuple]) -> List[tuple]:
    """``(tip, far end)`` of each line that starts at ``target`` and leaves
    it, followed through segments joined end to end (a leader with a knee).
    Arrowhead strokes have both ends at the target and are not leaders."""

    def near(x: float, y: float) -> bool:
        return _distance((x, y), target) <= _TIP_REACH

    out = []
    for s in segments:
        a, b = near(s[0], s[1]), near(s[2], s[3])
        if a == b:
            continue
        tip, end = ((s[0], s[1]), (s[2], s[3])) if a else ((s[2], s[3]), (s[0], s[1]))
        for _hop in range(3):
            joined = next((t for t in segments if t is not s and (
                math.hypot(t[0] - end[0], t[1] - end[1]) < 1.5 or math.hypot(t[2] - end[0], t[3] - end[1]) < 1.5)), None)
            if joined is None:
                break
            nxt = (joined[2], joined[3]) if math.hypot(joined[0] - end[0], joined[1] - end[1]) < 1.5 else (joined[0], joined[1])
            if near(*nxt) or nxt == end:
                break
            s, end = joined, nxt
        # Arrowhead strokes are a few points long; a leader reaches its label.
        if math.hypot(end[0] - tip[0], end[1] - tip[1]) >= _LEADER_MIN_LENGTH:
            out.append((tip, end))
    return out


def _label(end: tuple, lines: List[Dict[str, Any]], exclude: List[float]) -> Optional[Dict[str, Any]]:
    """The printed label a leader ends at, with the lines that continue it
    (same left edge, next rows): "# OF SHEAR STUDS." + "SEE TYPICAL DETAIL"."""

    candidates = [ln for ln in lines if ln["bbox"] != exclude and _distance(end, ln["bbox"]) <= _LABEL_REACH]
    if not candidates:
        return None
    first = min(candidates, key=lambda ln: _distance(end, ln["bbox"]))
    # The whole label block: lines sharing its left edge, stacked with no gap.
    column = sorted((ln for ln in lines if ln["bbox"] != exclude and abs(ln["bbox"][0] - first["bbox"][0]) < 3),
                    key=lambda ln: ln["bbox"][1])
    at = column.index(first)
    top = bottom = at
    while top > 0 and -4 <= column[top]["bbox"][1] - column[top - 1]["bbox"][3] < 8:
        top -= 1
    while bottom < len(column) - 1 and -4 <= column[bottom + 1]["bbox"][1] - column[bottom]["bbox"][3] < 8:
        bottom += 1
    block = column[top:bottom + 1]
    return {"text": " ".join(ln["text"] for ln in block), "bbox": _union_boxes([ln["bbox"] for ln in block])}


def _field(label: str) -> Optional[str]:
    return next((name for name, pattern in _FIELDS if pattern.search(label)), None)


def read_page_keys(page: Any, page_no: int, sheet: Optional[str] = None) -> List[Dict[str, Any]]:
    """Framing keys printed on one PyMuPDF page."""

    lines = []
    for block in page.get_text("dict")["blocks"]:
        for ln in block.get("lines", []):
            text = " ".join(s["text"] for s in ln["spans"]).strip()
            if text:
                lines.append({"text": " ".join(text.split()), "bbox": [round(v, 1) for v in ln["bbox"]]})
    keys = []
    drawings: Optional[List[dict]] = None   # read once, and only when a key has an example callout
    for heading in (ln for ln in lines if _KEY_HEADING_RE.search(ln["text"]) and len(ln["text"]) < 60):
        hx0, _hy0, hx1, hy1 = heading["bbox"]
        region = [hx0 - _REGION, hy1 - 4, hx1 + _REGION, hy1 + _REGION]
        inside = [ln for ln in lines if ln is not heading and _inside_any(ln["bbox"], [region])]
        segments = None
        for example in inside:
            section = _SECTION_RE.search(example["text"])
            if not section:
                continue
            parts = []
            for form, pattern in _PART_RES:
                for m in pattern.finditer(example["text"], section.end()):
                    rects = page.search_for(m.group(0), clip=example["bbox"])
                    if rects:
                        parts.append({"token": " ".join(m.group(0).split()), "form": form,
                                      "bbox": [round(v, 1) for v in rects[0]]})
            if not parts:
                continue
            if segments is None:
                if drawings is None:
                    # get_cdrawings: the same paths, without Python-level conversion.
                    drawings = page.get_cdrawings() if hasattr(page, "get_cdrawings") else page.get_drawings()
                segments = _segments(drawings, region)
            # Each leader belongs to the one part its tip is nearest to.
            owned: Dict[int, List[tuple]] = {}
            for tip, end in _leaders(example["bbox"], segments):
                index, part = min(enumerate(parts), key=lambda ip: (_distance(tip, ip[1]["bbox"]),
                                                                   abs(tip[0] - (ip[1]["bbox"][0] + ip[1]["bbox"][2]) / 2)))
                if _distance(tip, part["bbox"]) <= _TIP_REACH:
                    owned.setdefault(index, []).append((tip, end))
            for index, part in enumerate(parts):
                labels = [lab for _tip, end in owned.get(index, []) if (lab := _label(end, inside, example["bbox"]))]
                texts = {lab["text"] for lab in labels}
                if len(texts) == 1:
                    part["meaning"] = labels[0]["text"]
                    part["field"] = _field(labels[0]["text"])
                    part["label_bbox"] = labels[0]["bbox"]
                    part["status"] = "defined"
                elif len(texts) > 1:
                    part["meaning"] = None
                    part["candidates"] = sorted(texts)
                    part["status"] = "conflicting"
                else:
                    part["meaning"] = None
                    part["status"] = "no_leader"
            keys.append({
                "title": heading["text"], "page": page_no, "sheet": sheet,
                "heading_bbox": heading["bbox"], "example": example["text"], "example_bbox": example["bbox"],
                "section": section.group(0),
                "region": _union_boxes([heading["bbox"], example["bbox"]] + [p.get("label_bbox") or p["bbox"] for p in parts]),
                "parts": parts,
            })
    return keys


def read_framing_keys(document: Dict[str, Any], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    """Framing keys in the document's PDF. Only pages whose text carries a
    key heading are opened; nothing is read when the PDF is not available."""

    path = document.get("source_path")
    pages = sorted({int(ln.get("page_number") or 0) for ln in document.get("lines") or []
                    if _KEY_HEADING_RE.search(str(ln.get("text") or "")) and len(str(ln.get("text") or "")) < 60})
    if not path or not pages:
        return []
    try:
        import fitz

        with fitz.open(path) as pdf:
            return [key for page in pages if 0 < page <= pdf.page_count
                    for key in read_page_keys(pdf[page - 1], page, sheets.get(page))]
    except Exception:  # noqa: BLE001 - a missing or unreadable PDF leaves the key unread
        return []


def bracket_definition(keys: List[Dict[str, Any]]) -> Dict[str, Any]:
    """What the set's keys say a bracketed integer after a section means:
    ``defined`` (one meaning, with its sources), ``conflicting`` (keys
    disagree; every meaning kept) or ``undefined``."""

    found = [(key, part) for key in keys for part in key["parts"] if part["form"] == "bracketed integer"]
    meanings = {part["meaning"] for _key, part in found if part["status"] == "defined"}
    sources = [{"page": key["page"], "sheet": key["sheet"], "title": key["title"], "bbox": key["region"],
                "example": key["example"], "token": part["token"], "meaning": part["meaning"]}
               for key, part in found if part["status"] == "defined"]
    if len(meanings) == 1 and not any(part["status"] == "conflicting" for _k, part in found):
        part = next(part for _key, part in found if part["status"] == "defined")
        return {"status": "defined", "meaning": part["meaning"], "field": part["field"], "sources": sources}
    if meanings or any(part["status"] == "conflicting" for _k, part in found):
        return {"status": "conflicting", "meanings": sorted(meanings | {c for _k, p in found for c in p.get("candidates", [])}),
                "sources": sources}
    return {"status": "undefined", "sources": [],
            "missing": ("no framing key with a leader from a bracketed number to a printed label" if not found
                        else "the key's bracketed number has no leader to a printed label")}
