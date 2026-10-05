"""Levels and elevations as independent, sourced evidence.

Reads level names and elevations from column schedules (level lines), plan
notes (top of slab / top of steel statements, datum references, notation
rules), plan values written in a notation a note defines, and spot elevation
symbols. Relationships are kept only where the drawing states them:

* a top-of-steel value is derived from a slab value only when a note gives
  the offset and its direction, and only within that note's plan;
* a schedule level and a plan are linked as a *candidate* by name, never
  merged; differing elevations are shown as a conflict, not resolved;
* a level-to-level difference is computed only between elevations printed in
  one schedule (one elevation system) and is never a column length.

Display / evidence only: nothing here feeds prediction or quantities.
"""

from __future__ import annotations

import re
from collections import defaultdict
from fractions import Fraction
from typing import Any, Dict, List, Optional

from services.engineering.column_schedule import _union_boxes, parse_length

_ENCLOSURES = {"(": ")", "<": ">", "[": "]", "{": "}"}
# Decimal-foot elevations carry two decimals (``28.66'``, ``XXX.XX'``); a
# one-decimal primed token such as ``8.1'`` is a grid name.
_DECIMAL_FEET_RE = re.compile(r"^(?P<sign>[-+−])?\s*(?P<ft>\d+\.\d{2})\s*'$")
_SEE_PLAN_RE = re.compile(r"^SEE\s+(?:PLANS?|ARCH(?:ITECTURAL)?\.?(?:\s+DRAWINGS)?)\b", re.IGNORECASE)
_SIGNS = {"+": "+", "-": "-", "−": "-"}
_QUOTES = str.maketrans({"’": "'", "‘": "'", "′": "'", "”": '"', "“": '"', "″": '"'})


def _clean(text: Any) -> str:
    """Whitespace-collapsed text with typographic foot / inch marks as ' and "."""

    return " ".join(str(text or "").translate(_QUOTES).split())


def parse_elevation(text: str) -> Optional[Dict[str, Any]]:
    """``41'-9 5/8"`` / ``(+13'-6 3/4")`` / ``(29.42')`` / ``<0' - 5 1/4">`` / ``-5'-0"``.

    The enclosure is kept, never read as a sign: a project note says what
    ``( )`` or ``< >`` means. Only an explicit ``+`` / ``-`` is a sign.
    """

    raw = _clean(text)
    body, enclosure = raw, None
    if len(body) >= 2 and body[0] in _ENCLOSURES and body[-1] == _ENCLOSURES[body[0]]:
        enclosure, body = body[0], body[1:-1].strip()
    length = parse_length(body)
    if length is not None:
        inches, unit = length["inches"], length["unit"]
    else:
        match = _DECIMAL_FEET_RE.fullmatch(body)
        if not match:
            return None
        feet = float(match["ft"])
        inches = (-feet if _SIGNS.get(match["sign"]) == "-" else feet) * 12.0
        unit = "decimal-ft"
    return {
        "raw": raw,
        "inches": round(inches, 4),
        "unit": unit,
        "sign": _SIGNS.get(body[:1]),
        "enclosure": enclosure,
    }


def is_see_plan(text: str) -> bool:
    return bool(_SEE_PLAN_RE.match(_clean(text)))


def format_elevation(inches: float) -> str:
    """Feet-inches to the nearest 1/16" (``-0'-5 1/4"``, ``329'-5 3/4"``)."""

    sixteenths = round(abs(inches) * 16)
    feet, rest = divmod(sixteenths, 12 * 16)
    whole, frac = divmod(rest, 16)
    fraction = f" {Fraction(frac, 16)}" if frac else ""
    return f"{'-' if inches < 0 and sixteenths else ''}{feet}'-{whole}{fraction}\""


# --------------------------------------------------------------------------
# Plan notes: values, offsets, datums, notation rules
# --------------------------------------------------------------------------
_V = (r"[\(\[<{]?\s*[-+−]?\s*(?:\d+\s*'\s*(?:-\s*)?\d+(?:[ -]\d+/\d+)?\s*\"|\d+(?:[ -]\d+/\d+)?\s*\""
      r"|\d+\.\d{2}\s*'|\d+\s*')\s*[\)\]>}]?")
_SURFACE = r"(?:TOP\s+OF|T/|T\.\s*O\.\s*)\s*(?P<surf>STEEL(?:\s+BEAMS?)?|SLAB|(?:ROOF\s+)?DECK)"
_VALUE_RE = re.compile(
    rf"{_SURFACE}(?:\s+AND\s+GIRDERS)?\s+(?:ELEVATION\s+)?(?:\(BOTTOM\s+OF\s+DECK\)\s+)?(?:SHALL\s+BE|IS(?!\s+AT)|=)\s*(?P<val>{_V})"
    r"\s*(?P<rel>(?:ABOVE|BELOW)\s+(?:THE\s+)?(?:TOP\s+OF\s+(?:SLAB|DECK)|DATUM)"
    r"|(?:AS\s+MEASURED\s+)?FROM\s+(?:THE\s+)?(?:TOP\s+OF\s+(?:SLAB|DECK)|DATUM))?",
    re.IGNORECASE,
)
# ``T/SLAB ELEVATION DENOTED AS 314'-0" ON PLAN`` (WL S-101): a value. A
# placeholder (``XXX'-XX"``) is not.
_DENOTED_RE = re.compile(
    rf"{_SURFACE}\s+ELEVATION\s+DENOTED\s+AS\s+(?P<val>{_V})\s+ON\s+PLAN", re.IGNORECASE
)
_LEGEND_SYMBOL_RE = re.compile(r"^[\(\[<{][#X\s'\-\"]+[\)\]>}]$")
_LEGEND_MEANING_RE = re.compile(r"^(?P<what>(?:TOP|BOTTOM)\s+OF\s+[A-Z ]+?)\s+ELEVATION(?P<rel>\s+RELATIVE\s+TO\s+DATUM)?$",
                                re.IGNORECASE)
_AT_RE = re.compile(
    rf"{_SURFACE}(?:\s+FOR\s+[A-Z ]+?)?\s+IS\s+AT\s+(?:THE\s+)?(?P<ref>REFERENCE\s+ELEVATION|BOTTOM\s+OF\s+DECK)",
    re.IGNORECASE,
)
_DATUM_REF_RE = re.compile(
    rf"DATUM\s+ELEVATION\s+(?P<d>{_V})\s+REFERENCES\s+(?:THE\s+)?TOP\s+OF\s+(?P<name>[A-Z0-9 ]+?)\s+"
    rf"(?P<surf>SLAB|DECK)\s+ELEVATION\s+(?P<val>{_V})",
    re.IGNORECASE,
)
_REF_TRUE_RE = re.compile(
    rf"REFERENCE\s+ELEVATION\s+(?:IS\s+AT|IS|OF)\s+(?P<ref>{_V}),?\s+CORRESPONDING\s+TO\s+(?:THE\s+)?"
    rf"TRUE\s+ELEVATION\s+OF\s+(?P<true>{_V})",
    re.IGNORECASE,
)
# ``TOP OF SECOND FLOOR SLAB ELEVATION +15'-4" MEASURED FROM DATUM ...`` (YS S2.01)
_NAMED_VALUE_RE = re.compile(
    rf"TOP\s+OF\s+(?P<name>[A-Z0-9 ]+?)\s+(?P<surf>SLAB|DECK)\s+ELEVATION\s+(?:IS\s+|=\s*)?(?P<val>{_V})"
    r"(?:\s+MEASURED\s+FROM\s+(?P<datum>[A-Z ]+?)(?=\.|,|$))?",
    re.IGNORECASE,
)
# ``TOP OF STEEL IS MEASURED FROM ... AND IS INDICATED THUS TOS (+0'-0")``: the
# project's own abbreviation; only values written with that prefix follow it.
_PREFIX_NOTATION_RE = re.compile(
    r"(?P<what>TOP\s+OF\s+STEEL|JOIST\s+BEARING\s+ELEVATION|BOTTOM\s+OF\s+DECK(?:\s+ELEVATION)?)\s+IS\s+"
    r"MEASURED\s+FROM\s+(?P<ref>[A-Z ]+?)\s+AND\s+IS\s+INDICATED\s+THUS\s+(?P<prefix>[A-Z]{2,4})\s*"
    r"(?P<sample>\([^)]{0,14}\))",
    re.IGNORECASE,
)
_REF_BLANK_RE = re.compile(r"REFERENCE\s+ELEVATION\s+(?:IS\s+)?DEFINED\s+ON\s*\.", re.IGNORECASE)
_NOTATION_RE = re.compile(
    r"(?P<what>TOP\s+OF\s+[A-Z]+(?:\s+BEAM)?|ELEVATIONS)\s+(?:ELEVATIONS?\s+)?(?:\([A-Z ]+\)\s+)?"
    r"(?:NOTED|INDICATED)\s+(?:ON\s+PLAN\s+|IN\s+PLAN\s+)?THUS:?\s*"
    r"(?P<sample>[\(\[<{][^\)\]>}]{0,14}[\)\]>}])(?P<rest>[^.]*(?:\.\d+'?\)?[^.]*)?)",
    re.IGNORECASE,
)
_EXCEPTION_RE = re.compile(r"UNLESS\s+NOTED(?:\s+OTHERWISE)?\s+THUS:?\s*(?P<sample>[\(\[<{][^\)\]>}]{0,14}[\)\]>}])",
                           re.IGNORECASE)
_LEGEND_RE = re.compile(
    r"(?P<sample>[\(\[<{][#X\s'\-\"]+[\)\]>}])\s*(?P<what>(?:TOP|BOTTOM)\s+OF\s+[A-Z ]+?)\s+ELEVATION"
    r"(?P<rel>\s+RELATIVE\s+TO\s+DATUM)?",
    re.IGNORECASE,
)
_AREA_RE = re.compile(r"\bSLAB\s+AT\s+(?P<area>[A-Z][A-Z ]{2,30}?)\s+SHALL\b", re.IGNORECASE)
_UNO_RE = re.compile(r"UNLESS\s+NOTED|U\.?\s*N\.?\s*O\b", re.IGNORECASE)
# Up to three words before the plan keyword keep the level in the title
# (``SECOND FLOOR FRAMING PLAN``, ``LEVEL 2 FRAMING PLAN``).
_PLAN_TITLE_RE = re.compile(
    r"(?:\b[A-Z0-9.&'/-]+\s+){0,3}\b(?:FRAMING|FOUNDATION|FLOOR|ROOF|LEVEL|DECK|MEZZANINE)\b[A-Z0-9 ./&'-]*\bPLAN\b",
    re.IGNORECASE,
)


def _surface(text: str) -> str:
    upper = _clean(text).upper()
    if upper.startswith("BOTTOM OF") and "BASE PLATE" not in upper:
        return "bottom of " + upper[len("BOTTOM OF"):].strip().lower()
    for word, name in (("STEEL", "top of steel"), ("DECK", "top of deck"), ("SLAB", "top of slab"),
                       ("FOOTING", "top of footing"), ("PIER", "top of pier"),
                       ("BASE PLATE", "bottom of base plate"), ("FRAMING", "top of framing")):
        if word in upper:
            return name
    return upper.lower()


def _value(text: str) -> Optional[Dict[str, Any]]:
    parsed = parse_elevation(text.strip().rstrip(".,"))
    if parsed:
        parsed["display"] = format_elevation(parsed["inches"])
    return parsed


def display_boxes(document: Dict[str, Any]) -> Any:
    """``box(page, bbox)`` in the coordinates a page is displayed in.

    Extracted text keeps unrotated PDF coordinates; the source viewer draws
    highlights on the page as displayed (after /Rotate). Unrotated pages
    pass through unchanged.
    """

    meta = {int(p.get("page_number") or 0): p for p in document.get("pages") or []}

    def box(page: int, bbox: Any) -> Optional[List[float]]:
        if not bbox or len(bbox) < 4:
            return None
        x0, y0, x1, y1 = (float(v) for v in bbox[:4])
        info = meta.get(page) or {}
        rotation = int(info.get("rotation") or 0) % 360
        width, height = float(info.get("width") or 0), float(info.get("height") or 0)
        if rotation == 90:
            x0, y0, x1, y1 = width - y1, x0, width - y0, x1
        elif rotation == 180:
            x0, y0, x1, y1 = width - x1, height - y1, width - x0, height - y0
        elif rotation == 270:
            x0, y0, x1, y1 = y0, height - x1, y1, height - x0
        return [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]

    return box


def plan_titles(document: Dict[str, Any]) -> Dict[int, List[str]]:
    """Plan titles printed on each page (largest text first)."""

    found: Dict[int, List[tuple]] = defaultdict(list)
    for line in document.get("lines") or []:
        text = _clean(line.get("text"))
        match = _PLAN_TITLE_RE.search(text)
        if match and len(text) <= 90 and "NOTES" not in text.upper():
            found[int(line.get("page_number") or 0)].append((-float(line.get("font_size") or 0), match.group(0).upper()))
    titles: Dict[int, List[str]] = {}
    for page, entries in found.items():
        seen: List[str] = []
        for _, title in sorted(entries):
            title = re.sub(r"^(?:(?:AND|&|OF|THE|-)\s+)+", "", re.sub(r"\s+", " ", title).strip())
            if title not in seen:
                seen.append(title)
        titles[page] = seen[:4]
    return titles


def _note_heading(block: Dict[str, Any], blocks: List[Dict[str, Any]]) -> Optional[str]:
    bbox = block.get("bbox") or []
    if len(bbox) < 4:
        return None
    for other in blocks:
        obox = other.get("bbox") or []
        text = _clean(other.get("text"))
        if other is block or len(obox) < 4 or "NOTES" not in text.upper() or len(text) > 90:
            continue
        if 0 <= float(bbox[1]) - float(obox[3]) <= 40 and abs(float(obox[0]) - float(bbox[0])) <= 40:
            return text.rstrip(":")
    return None


def plan_statements(document: Dict[str, Any], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    """Elevation statements printed in plan notes and legends, each scoped to
    the note's own sheet and heading. Values are read; nothing is derived here."""

    titles = plan_titles(document)
    box = display_boxes(document)
    by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for block in document.get("blocks") or []:
        by_page[int(block.get("page_number") or 0)].append(block)
    out: List[Dict[str, Any]] = []

    def add(kind: str, block: Dict[str, Any], match: "re.Match", **fields: Any) -> None:
        page = int(block.get("page_number") or 0)
        area = _AREA_RE.search(_clean(block.get("text")))
        out.append({
            "kind": kind,
            "page": page, "sheet": sheets.get(page),
            "plan": (titles.get(page) or [None])[0],
            "heading": _note_heading(block, by_page[page]),
            "area": _clean(area["area"]).upper() if area else None,
            "text": _clean(match.group(0)),
            "bbox": box(page, block.get("bbox")),
            "block_id": block.get("object_id"),
            **fields,
        })

    for page, blocks in sorted(by_page.items()):
        for block in blocks:
            text = _clean(block.get("text"))
            if not re.search(r"ELEVATION|TOP OF|T/|DATUM", text, re.IGNORECASE):
                continue
            for m in _DATUM_REF_RE.finditer(text):
                value = _value(m["val"])
                if value:
                    add("datum", block, m, name=_clean(m["name"]).upper(), surface=_surface(m["surf"]),
                        datum=_value(m["d"]), value=value,
                        relation=f"datum {_clean(m['d'])} on this plan is the top of "
                                 f"{_clean(m['name']).lower()} {m['surf'].lower()}, {value['raw']}")
            for m in _REF_TRUE_RE.finditer(text):
                ref, true = _value(m["ref"]), _value(m["true"])
                if ref and true:
                    add("datum", block, m, name=None, surface=None, datum=ref, value=true,
                        relation=f"reference elevation {ref['raw']} corresponds to true elevation {true['raw']}")
            for m in _REF_BLANK_RE.finditer(text):
                add("datum", block, m, name=None, surface=None, datum=None, value=None,
                    relation="the note leaves the sheet that defines the reference elevation blank")
            for m in _VALUE_RE.finditer(text):
                value = _value(m["val"])
                if not value:
                    continue
                rel = _clean(m["rel"]).upper()
                tail = text[m.end():m.end() + 160].split(". ")[0]
                exception = _EXCEPTION_RE.search(tail)
                common = dict(surface=_surface(m["surf"]), unless_noted=bool(_UNO_RE.search(tail)),
                              exception_notation=exception["sample"][0] if exception else None)
                if rel and re.search(r"TOP\s+OF", rel):
                    sign = {"BELOW": -1, "ABOVE": 1}.get(rel.split()[0])
                    if value["sign"]:
                        sign = -1 if value["sign"] == "-" else 1
                    add("offset", block, m, **common, offset=value, relative_to=_surface(rel),
                        direction={-1: "below", 1: "above"}.get(sign),
                        offset_inches=sign * abs(value["inches"]) if sign else None)
                else:
                    add("value", block, m, **common, value=value,
                        datum="datum elevation" if "DATUM" in rel else None)
            datum_spans = [m.span() for m in _DATUM_REF_RE.finditer(text)]
            for m in _NAMED_VALUE_RE.finditer(text):
                if any(a <= m.start() < b for a, b in datum_spans):
                    continue
                value = _value(m["val"])
                if value and not re.search(r"\b(?:STEEL|THE)\b", m["name"], re.IGNORECASE):
                    add("datum", block, m, name=_clean(m["name"]).upper(), surface=_surface(m["surf"]),
                        datum=None, value=value,
                        relation=f"top of {_clean(m['name']).lower()} {m['surf'].lower()} {value['raw']}"
                                 + (f", measured from {_clean(m['datum']).lower()}" if m["datum"] else ""))
            for m in _PREFIX_NOTATION_RE.finditer(text):
                add("notation", block, m, enclosure="(", sample=f"{m['prefix'].upper()} {m['sample']}",
                    prefix=m["prefix"].upper(), meaning=_surface(m["what"]) if "JOIST" not in m["what"].upper()
                    else "joist bearing", relative_to=_clean(m["ref"]).lower())
            for m in _DENOTED_RE.finditer(text):
                value = _value(m["val"])
                if value:
                    add("value", block, m, surface=_surface(m["surf"]), value=value, unless_noted=False,
                        exception_notation=None, datum=None)
            for m in _AT_RE.finditer(text):
                add("at", block, m, surface=_surface(m["surf"]), equals=_clean(m["ref"]).lower(),
                    unless_noted=bool(_UNO_RE.search(text[m.end():m.end() + 80])))
            for m in _NOTATION_RE.finditer(text):
                rest = _clean(m["rest"]).upper()
                relative = re.search(r"MEASURED\s+FROM\s+(?:THE\s+)?(TOP\s+OF\s+(?:SLAB|DECK)|DATUM)", rest)
                add("notation", block, m, enclosure=m["sample"][0], sample=m["sample"],
                    meaning="elevation" if m["what"].upper().startswith("ELEVATIONS") else _surface(m["what"]),
                    relative_to=(None if not relative else "datum" if "DATUM" in relative.group(1)
                                 else _surface(relative.group(1))))
            for m in _LEGEND_RE.finditer(text):
                add("notation", block, m, enclosure=m["sample"][0], sample=m["sample"], legend=True,
                    meaning=_surface(m["what"]), relative_to="datum" if m["rel"] else None)
            # A legend whose symbol is a separate text block on the same line.
            meaning = _LEGEND_MEANING_RE.match(text)
            if meaning and not _LEGEND_RE.search(text):
                symbol = next((o for o in blocks if _same_line_left(o, block)
                               and _LEGEND_SYMBOL_RE.match(_clean(o.get("text")))), None)
                if symbol:
                    sample = _clean(symbol.get("text"))
                    add("notation", block, meaning, enclosure=sample[0], sample=sample, legend=True,
                        meaning=_surface(meaning["what"]), relative_to="datum" if meaning["rel"] else None)
    # The same statement printed twice on one sheet (title strip and notes).
    unique: Dict[tuple, Dict[str, Any]] = {}
    for item in out:
        key = (item["page"], item["kind"], item.get("block_id") if item["kind"] != "datum" or item["value"] else None,
               re.sub(r"\bIS\s+", "", item["text"].upper()))
        unique.setdefault(key, item)
    return list(unique.values())


def _same_line_left(other: Dict[str, Any], block: Dict[str, Any]) -> bool:
    a, b = other.get("bbox") or [], block.get("bbox") or []
    if other is block or len(a) < 4 or len(b) < 4:
        return False
    return abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2) <= 6 and 0 <= b[0] - a[2] <= 220


# --------------------------------------------------------------------------
# Values printed on plans in a notation a note defines; spot elevations
# --------------------------------------------------------------------------
_ENCLOSED_RE = re.compile(r"[\(\[<{]\s*[-+−]?\s*\d[\d.'\" /\-]*[\)\]>}]")
_SPOT_LABEL_RE = re.compile(r"^(?:T/|T\.O\.\s*)(SLAB|DECK|STEEL)\.?$", re.IGNORECASE)
_MAX_PLAN_VALUES = 400


def _page_lines(document: Dict[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    lines: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for line in document.get("lines") or []:
        bbox = line.get("bbox") or []
        if len(bbox) >= 4:
            lines[int(line.get("page_number") or 0)].append(line)
    return lines


def _inside_any(bbox: List[float], boxes: List[List[float]]) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return any(b[0] - 2 <= cx <= b[2] + 2 and b[1] - 2 <= cy <= b[3] + 2 for b in boxes)


def _rule_for(value: Dict[str, Any], rules: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The note rule this bracketed value is written in. Several rules for one
    bracket on a sheet are told apart by the sign in their sample
    (``(-X')`` offsets vs ``(XXX'-XX")`` footings); otherwise they must agree."""

    candidates = [r for r in rules if r["enclosure"] == value["enclosure"]]
    if len(candidates) > 1:
        signed = [r for r in candidates if "-" in r["sample"][1:3]]
        candidates = signed if value["sign"] == "-" else [r for r in candidates if r not in signed] or candidates
    meanings = {(r["meaning"], r["relative_to"]) for r in candidates}
    if not candidates or len({m for m, _ in meanings}) > 1:
        return None
    return candidates[0]


def plan_values(document: Dict[str, Any], statements: List[Dict[str, Any]], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    """Bracketed elevations on plans, read only where a note on that sheet (or
    the project legend) says what the bracket means. Note text is excluded."""

    titles = plan_titles(document)
    box = display_boxes(document)
    legend = [s for s in statements if s["kind"] == "notation" and s.get("legend")]
    rules_by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    note_boxes: Dict[int, List[List[float]]] = defaultdict(list)
    for s in statements:
        if s["bbox"]:
            note_boxes[s["page"]].append(s["bbox"])
        if s["kind"] == "notation" and not s.get("legend"):
            rules_by_page[s["page"]].append(s)
        elif s.get("exception_notation"):
            rules_by_page[s["page"]].append({**s, "enclosure": s["exception_notation"], "meaning": s["surface"],
                                             "relative_to": None, "sample": s["exception_notation"] + "...)"})
    out: List[Dict[str, Any]] = []
    for page, lines in sorted(_page_lines(document).items()):
        rules = rules_by_page.get(page) or legend
        if not rules:
            continue
        for line in lines:
            text = _clean(line.get("text"))
            bbox = box(page, line["bbox"])
            if _inside_any(bbox, note_boxes.get(page, [])):
                continue
            for m in _ENCLOSED_RE.finditer(text):
                value = _value(m.group(0))
                before = text[:m.start()].rstrip().split(" ")[-1].upper() if text[:m.start()].strip() else ""
                usable = [r for r in rules if not r.get("prefix") or before.endswith(r["prefix"])]
                prefixed = [r for r in usable if r.get("prefix")]
                rule = value and _rule_for(value, prefixed or [r for r in usable if not r.get("prefix")])
                if not rule:
                    continue
                out.append({
                    "kind": "plan_value", "page": page, "sheet": sheets.get(page),
                    "plan": (titles.get(page) or [None])[0], "value": value,
                    "meaning": rule["meaning"], "relative_to": rule["relative_to"],
                    "rule": rule["text"], "context": text[:70], "bbox": bbox,
                })
                if len(out) >= _MAX_PLAN_VALUES:
                    return out
    return out


def masked_spot_labels(document: Dict[str, Any], pdf_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Text painted over by a later white box on pages that carry spot
    elevation labels (``T/SLAB`` masked, ``T/DECK`` typed on top). Kept in
    the extracted document so the summary never reads a masked label."""

    import fitz

    from services.engineering.column_schedule import visible_phrases

    pages = sorted({int(line.get("page_number") or 0) for line in document.get("lines") or []
                    if _SPOT_LABEL_RE.match(_clean(line.get("text")))})
    masked: Dict[str, List[Dict[str, Any]]] = {}
    if not pages:
        return masked
    with fitz.open(pdf_path) as pdf:
        for page in pages:
            if 1 <= page <= pdf.page_count:
                _, suppressed = visible_phrases(pdf[page - 1])
                if suppressed:
                    masked[str(page)] = [{"text": p["text"], "bbox": p["bbox"]} for p in suppressed]
    return masked


def _is_masked(line: Dict[str, Any], masked: List[Dict[str, Any]]) -> bool:
    # Glyph boxes (masked text) are tighter than line boxes: compare centers.
    text, bbox = _clean(line.get("text")), [float(v) for v in line["bbox"][:4]]
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return any(
        _clean(m["text"]) == text and abs((m["bbox"][0] + m["bbox"][2]) / 2 - cx) <= 3
        and abs((m["bbox"][1] + m["bbox"][3]) / 2 - cy) <= 3
        for m in masked
    )


def spot_elevations(document: Dict[str, Any], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    """``T/SLAB`` / ``T/DECK`` elevation symbols with the value printed under the label.

    A label hidden under a white mask (``document["masked_text"]``) is not read.
    """

    titles = plan_titles(document)
    box = display_boxes(document)
    masked = document.get("masked_text") or {}
    out: List[Dict[str, Any]] = []
    for page, lines in _page_lines(document).items():
        for label in lines:
            match = _SPOT_LABEL_RE.match(_clean(label.get("text")))
            if not match or _is_masked(label, masked.get(str(page), [])):
                continue
            lb = [float(v) for v in label["bbox"][:4]]
            under = [
                ln for ln in lines
                if 0 <= float(ln["bbox"][1]) - lb[3] <= 14 and float(ln["bbox"][0]) < lb[2] + 10
                and float(ln["bbox"][2]) > lb[0] - 10
            ]
            vb, value = next(((ln, v) for ln in under if (v := _value(_clean(ln.get("text"))))), (None, None))
            if value:
                out.append({
                    "kind": "spot", "page": page, "sheet": sheets.get(page), "plan": (titles.get(page) or [None])[0],
                    "surface": _surface(match.group(1)), "value": value,
                    "text": f"{_clean(label.get('text'))} {value['raw']}",
                    "bbox": box(page, [min(lb[0], float(vb["bbox"][0])), lb[1],
                                       max(lb[2], float(vb["bbox"][2])), float(vb["bbox"][3])]),
                })
    return out


# --------------------------------------------------------------------------
# Plan elevation records: read, derived by an explicit rule, or unresolved
# --------------------------------------------------------------------------
def _scope(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"plan": item.get("heading") or item.get("plan"), "area": item.get("area"),
            "page": item["page"], "sheet": item.get("sheet")}


def _source(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"page": item["page"], "sheet": item.get("sheet"), "bbox": item.get("bbox"), "text": item.get("text")}


def plan_elevations(statements: List[Dict[str, Any]], spots: List[Dict[str, Any]],
                    values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One record per elevation a plan establishes.

    A top-of-steel value is derived from a slab (or deck) value only when a
    note on the same sheet states the offset *and* its direction; the
    derivation keeps both inputs and applies only to that note's scope.
    """

    records: List[Dict[str, Any]] = []

    def record(item: Dict[str, Any], status: str, surface: Optional[str], value: Optional[Dict[str, Any]], **extra: Any) -> Dict[str, Any]:
        entry = {"status": status, "surface": surface, "value": value, **_scope(item),
                 "source": _source(item), "unless_noted": bool(item.get("unless_noted")), **extra}
        records.append(entry)
        return entry

    by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for s in statements:
        by_page[s["page"]].append(s)
    spots_by_page: Dict[int, List[tuple]] = defaultdict(list)
    for sp in spots:
        spots_by_page[sp["page"]].append((sp, record(sp, "read", sp["surface"], sp["value"])))
    for page, items in sorted(by_page.items()):
        reference = next((s for s in items if s["kind"] == "datum" and s.get("datum") and s.get("value")), None)
        bases: List[tuple] = []
        for s in items:
            if s["kind"] == "value":
                bases.append((s, record(s, "read", s["surface"], s["value"], datum=s.get("datum"))))
            elif s["kind"] == "datum" and s.get("name"):
                bases.append((s, record(s, "read", s["surface"], s["value"], name=s["name"],
                                        datum=f"plan datum {s['datum']['raw']}" if s.get("datum") else None)))
            elif s["kind"] == "at" and s["equals"] == "reference elevation":
                if reference:
                    bases.append((s, record(s, "derived", s["surface"], dict(reference["datum"]),
                                            rule=s["text"], inputs=[_source(reference)],
                                            true_elevation=reference["value"])))
                else:
                    record(s, "unresolved", s["surface"], None, rule=s["text"],
                           note="The note refers to a reference elevation this sheet does not state.")
            elif s["kind"] == "at":
                record(s, "unresolved", s["surface"], None, rule=s["text"],
                       note=f"{s['surface'].capitalize()} is at the {s['equals']}; no dimension for that is given.")
        page_spots = spots_by_page.get(page, [])
        for s in items:
            if s["kind"] != "offset":
                continue
            if s["offset_inches"] is None:
                record(s, "unresolved", s["surface"], None, offset=s["offset"], relative_to=s["relative_to"],
                       rule=s["text"], note=f"The note gives {s['offset']['raw']} from the {s['relative_to']} "
                                            "but not whether it is above or below.")
                continue
            same_block = [(b, r) for b, r in bases if b.get("block_id") == s.get("block_id") and b["surface"] == s["relative_to"]]
            sheet_wide = [(b, r) for b, r in bases if b["surface"] == s["relative_to"] and b.get("heading") == s.get("heading")]
            targets = list(same_block or sheet_wide)
            targets += [(sp, r) for sp, r in page_spots if sp["surface"] == s["relative_to"] and not same_block]
            if not targets:
                record(s, "unresolved", s["surface"], None, offset=s["offset"], relative_to=s["relative_to"],
                       rule=s["text"], note=f"No {s['relative_to']} elevation is printed with this note.")
            exceptions = [v for v in values if v["page"] == page and v["meaning"] == s["surface"]]
            for base, base_record in targets:
                inches = base_record["value"]["inches"] + s["offset_inches"]
                # "unless noted otherwise" belongs to the offset note, not to the slab value.
                record(base, "derived", s["surface"],
                       {"raw": None, "inches": round(inches, 4), "display": format_elevation(inches), "unit": "ft-in"},
                       name=base_record.get("name"), rule=s["text"], offset={"display": format_elevation(s["offset_inches"]), "raw": s["offset"]["raw"],
                                               "direction": s["direction"], "relative_to": s["relative_to"]},
                       inputs=[base_record["source"], _source(s)], unless_noted=bool(s.get("unless_noted")),
                       exceptions={"notation": s.get("exception_notation"), "count": len(exceptions),
                                   "examples": [e["context"] for e in exceptions[:6]]} if s.get("unless_noted") else None)
    return records


# --------------------------------------------------------------------------
# Levels: schedule level lines, matched to plans as candidates
# --------------------------------------------------------------------------
_ORDINALS = {"FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6, "SEVENTH": 7,
             "EIGHTH": 8, "NINTH": 9, "TENTH": 10}
_LEVEL_NOISE = {"T.O.", "T.O", "TO", "TOP", "OF", "SLAB", "FRAMING", "PLAN", "PLANS", "NOTES", "OVERALL",
                "PARTIAL", "AND", "&", "/", "-", "ELEV", "ELEVATION", "STRUCTURAL", "ENLARGED",
                "FOUNDATION"}


def level_key(name: Any) -> Optional[tuple]:
    """``(kind, ordinal, qualifiers)`` a level name and a plan title share when
    they plausibly name the same level: ``T.O. SLAB LEVEL 2`` / ``SECOND FLOOR``.
    A candidate only -- it never merges two records."""

    upper = re.sub(r"\bAREA\s+[A-Z]\b|\(.*?\)", " ", str(name or "").upper())
    tokens = [t for t in re.split(r"[\s,]+", upper) if t]
    ordinal, kind, qualifiers = None, None, set()
    for i, token in enumerate(tokens):
        if token in _ORDINALS:
            ordinal = _ORDINALS[token]
        elif re.fullmatch(r"(\d+)(?:ST|ND|RD|TH)", token):
            ordinal = int(re.match(r"\d+", token).group(0))
        elif token.isdigit() and i and tokens[i - 1] in ("LEVEL", "FLOOR"):
            ordinal = int(token)
        elif token in ("ROOF", "ROOFS"):
            kind = "roof"
        elif token in ("FLOOR", "LEVEL", "STORY", "STOREY"):
            kind = kind or "floor"
        elif token not in _LEVEL_NOISE and not token.isdigit():
            qualifiers.add(token)
    if kind is None and ordinal is None:
        return None
    return (kind or "floor", ordinal, frozenset(qualifiers))


def level_keys(name: Any) -> set:
    """Keys of each part of a combined level name (``2 SECOND FLOOR AND LOW ROOF``)."""

    parts = re.split(r"\s+(?:AND|&|/)\s+", str(name or "").upper())
    return {key for key in (level_key(part) for part in parts) if key}


def _schedule_levels(document: Dict[str, Any], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for schedule in (document.get("column_schedules") or {}).get("schedules") or []:
        seen: Dict[tuple, Dict[str, Any]] = {}
        for line in schedule.get("level_lines") or []:
            key = (line["name"], line["elevation_text"])
            if key in seen:
                seen[key]["blocks"] += 1
                continue
            value = _value(line["elevation_text"]) if line["elevation_text"] else None
            boxes = [b for b in (line.get("name_bbox"), line.get("elevation_bbox")) if b]
            seen[key] = {
                "schedule_id": schedule["id"], "schedule": schedule.get("caption") or schedule["title"],
                "name": line["name"], "printed": line["elevation_text"], "elevation": value,
                "status": "read" if value else "see_plan" if line["elevation_text"] and is_see_plan(line["elevation_text"])
                else "missing",
                "page": line["page"], "sheet": sheets.get(line["page"]),
                "bbox": _union_boxes(boxes) if boxes else None, "blocks": 1,
            }
        out.extend(seen.values())
    return out


def levels_view(document: Dict[str, Any], sheets: Dict[int, str]) -> Dict[str, Any]:
    """Levels and elevations for review: schedule levels, plan elevations,
    datum notes and notations, each with its source."""

    statements = plan_statements(document, sheets)
    spots = spot_elevations(document, sheets)
    values = plan_values(document, statements, sheets)
    elevations = plan_elevations(statements, spots, values)
    titles = plan_titles(document)

    plan_names: Dict[int, List[str]] = defaultdict(list)
    for page, names in titles.items():
        plan_names[page].extend(names)
    for s in statements:
        for name in (s.get("heading"), s.get("name") and f"{s['name']} PLAN"):
            if name and name not in plan_names[s["page"]]:
                plan_names[s["page"]].append(name)

    levels = _schedule_levels(document, sheets)
    for level in levels:
        keys = level_keys(level["name"])
        pages = sorted(p for p, names in plan_names.items()
                       if keys and any(level_keys(n) & keys for n in names) and p != level["page"])
        matches = []
        titled_only: List[str] = []
        for page in pages:
            found = [e for e in elevations if e["page"] == page and e["value"] and e["status"] in ("read", "derived")
                     and (e.get("name") is None or level_keys(e["name"]) & keys)]
            slab = [e for e in found if e["surface"] in ("top of slab", "top of deck")]
            comparison = None
            if level["elevation"] and slab:
                comparison = "agrees" if all(abs(e["value"]["inches"] - level["elevation"]["inches"]) < 0.01 for e in slab) \
                    else "differs"
            if not found:
                titled_only.append(sheets.get(page) or f"p. {page}")
                continue
            matches.append({
                "page": page, "sheet": sheets.get(page),
                "plan": next((n for n in plan_names[page] if level_keys(n) & keys), None),
                "values": [{"surface": e["surface"], "display": e["value"]["display"], "raw": e["value"].get("raw"),
                            "status": e["status"], "area": e.get("area"), "source": e["source"]} for e in found],
                "comparison": comparison,
            })
        level["plan_matches"] = matches
        level["also_titled"] = titled_only
        level["conflict"] = any(m["comparison"] == "differs" for m in matches)
        if level["status"] == "see_plan":
            slab_values = {(v["surface"], v["display"]) for m in matches for v in m["values"]
                           if v["surface"] in ("top of slab", "top of deck") and v["status"] == "read"}
            if len(slab_values) == 1:
                surface, display = next(iter(slab_values))
                level["resolved"] = {"surface": surface, "display": display,
                                     "via": next(m for m in matches if any(v["display"] == display for v in m["values"]))["sheet"]}
                level["note"] = None
            else:
                level["resolved"] = None
                level["note"] = (f"The matching plan shows {len(slab_values)} different values; the level is not reduced to one."
                                 if slab_values else "No plan with a matching title states this level's elevation.")
    datums = [
        {"page": s["page"], "sheet": s["sheet"], "plan": s.get("heading") or s.get("plan"),
         "relation": s["relation"], "status": "read" if s.get("value") else "unresolved", "source": _source(s)}
        for s in statements if s["kind"] == "datum"
    ]
    notations = [
        {"page": s["page"], "sheet": s["sheet"], "sample": s["sample"], "meaning": s["meaning"],
         "relative_to": s["relative_to"], "scope": "project legend" if s.get("legend") else (s.get("heading") or s.get("plan")),
         "source": _source(s)}
        for s in statements if s["kind"] == "notation"
    ]
    noted: Dict[int, Dict[str, Any]] = {}
    for v in values:
        group = noted.setdefault(v["page"], {"page": v["page"], "sheet": v["sheet"], "plan": v["plan"],
                                             "meaning": set(), "count": 0, "examples": []})
        group["meaning"].add(v["meaning"] + (f" (from {v['relative_to']})" if v["relative_to"] else ""))
        group["count"] += 1
        if len(group["examples"]) < 8:
            group["examples"].append({"text": v["context"], "value": v["value"]["raw"], "bbox": v["bbox"],
                                      "page": v["page"], "sheet": v["sheet"]})
    return {
        "schedule_levels": levels,
        "plan_elevations": elevations,
        "datums": datums,
        "notations": notations,
        "noted_on_plans": [{**g, "meaning": sorted(g["meaning"])} for g in sorted(noted.values(), key=lambda g: g["page"])],
    }


def level_difference(extent: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Difference between the level elevations a column's drawn ends sit on,
    when both ends are on level lines of one schedule with printed
    elevations. A reference-elevation difference, never a column length."""

    if not extent:
        return {"status": "unresolved", "note": "The schedule draws no column line for this entry."}
    ends = [extent["top"], extent["bottom"]]
    if any(end["position"] != "at" for end in ends):
        return {"status": "unresolved", "note": "One end is not drawn on a level line."}
    top, bottom = (end["line"] for end in ends)
    values = [_value(line["elevation_text"]) if line.get("elevation_text") else None for line in (top, bottom)]
    if not all(values):
        return {"status": "unresolved", "note": "A level at one end has no printed elevation in the schedule."}
    steel = ["STEEL" in str(line["name"] or "").upper() for line in (top, bottom)]
    if steel[0] != steel[1]:
        return {"status": "unresolved", "note": "The two levels name different reference surfaces."}
    inches = values[0]["inches"] - values[1]["inches"]
    return {
        "status": "computed", "inches": round(inches, 4), "display": format_elevation(inches),
        "upper": {"name": top["name"], "elevation": values[0]["raw"]},
        "lower": {"name": bottom["name"], "elevation": values[1]["raw"]},
    }
