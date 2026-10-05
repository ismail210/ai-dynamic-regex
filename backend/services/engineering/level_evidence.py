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

from services.engineering.column_schedule import _band_key, _union_boxes, band_readings, parse_length
from services.engineering.page_space import convert_boxes, display_boxes

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


# ``(+30'-8)``: feet and whole inches with only the closing inch mark missing.
_MISSING_INCH_RE = re.compile(
    r"^(?P<open>[\(\[<{]?)\s*(?P<body>[-+−]?\s*\d+\s*'\s*-\s*(?P<inch>\d{1,2}))\s*(?P<close>[\)\]>}]?)$")


def recover_missing_inch_mark(text: str) -> Optional[Dict[str, Any]]:
    """A *candidate* for a feet-inch value printed without its closing inch
    mark, or nothing. The printed text is kept as is; the candidate is never a
    read value. Anything else malformed (a fraction, inches of 12 or more,
    other text) is not guessed at."""

    raw = _clean(text)
    match = _MISSING_INCH_RE.fullmatch(raw)
    if not match or int(match["inch"]) >= 12:
        return None
    candidate = _value(f"{match['open']}{match['body']}\"{match['close']}")
    if not candidate:
        return None
    return {"printed": raw, "candidate": candidate, "flag": "closing inch mark missing"}


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


def displayed(document: Dict[str, Any]) -> Dict[str, Any]:
    """The inputs this module reads, with every box in display space
    (``page_space``): notes are read the way the sheet reads -- a heading
    above its note, a value under its label -- and the boxes go to the viewer
    as they are. The functions below expect a displayed document."""

    box = display_boxes(document)

    def flat(items: Any) -> List[Dict[str, Any]]:
        return [{**item, "bbox": box(int(item.get("page_number") or 0), item.get("bbox"))} for item in items or []]

    return {
        **document,
        "lines": flat(document.get("lines")),
        "blocks": flat(document.get("blocks")),
        "column_schedules": convert_boxes(document.get("column_schedules") or {}, box),
        "masked_text": {page: convert_boxes(items, box, int(page))
                        for page, items in (document.get("masked_text") or {}).items()},
    }


_CONTINUES_RE = re.compile(r"(?:\bAND|&|\bOF|-|,)$")


def _wrapped_lines(document: Dict[str, Any]) -> List[tuple]:
    """``(line, text)`` per line, where a title printed over several lines
    (``PARTIAL FLOOR AND`` / ``ROOF FRAMING PLAN`` / ``- AREA A``) is joined:
    the next line sits directly under it in the same size and the wording
    shows it continues."""

    by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for line in document.get("lines") or []:
        if len(line.get("bbox") or []) >= 4:
            by_page[int(line.get("page_number") or 0)].append(line)
    out: List[tuple] = []
    for lines in by_page.values():
        lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
        for i, line in enumerate(lines):
            text, last = _clean(line.get("text")), line
            for nxt in lines[i + 1:i + 40]:
                a, b = last["bbox"], nxt["bbox"]
                size = float(last.get("font_size") or 0)
                if b[1] - a[3] > max(0.8 * size, 2.0):
                    break
                stacked = (abs(float(nxt.get("font_size") or 0) - size) <= 0.5 and b[1] >= a[3] - 1
                           and min(a[2], b[2]) - max(a[0], b[0]) > 0)
                following = _clean(nxt.get("text"))
                if stacked and (_CONTINUES_RE.search(text) or following.startswith("-")):
                    text, last = f"{text} {following}", nxt
            out.append((line, text))
    return out


def is_plan_title(text: str) -> bool:
    """A line that reads as a plan title (not a note that mentions a plan)."""

    return bool(_PLAN_TITLE_RE.search(text)) and len(text) <= 90 and "NOTES" not in text.upper()


def plan_titles(document: Dict[str, Any]) -> Dict[int, List[str]]:
    """Plan titles printed on each page (largest text first)."""

    found: Dict[int, List[tuple]] = defaultdict(list)
    for line, text in _wrapped_lines(document):
        match = _PLAN_TITLE_RE.search(text)
        if match and is_plan_title(text):
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


# ``NOTES`` as a word: ``c=0 DENOTES CAMBER`` is a note, not a heading.
_NOTES_WORD_RE = re.compile(r"\bNOTES\b", re.IGNORECASE)


def _note_heading(block: Dict[str, Any], blocks: List[Dict[str, Any]]) -> Optional[str]:
    bbox = block.get("bbox") or []
    if len(bbox) < 4:
        return None
    for other in blocks:
        obox = other.get("bbox") or []
        text = _clean(other.get("text"))
        if other is block or len(obox) < 4 or not _NOTES_WORD_RE.search(text) or len(text) > 90:
            continue
        if 0 <= float(bbox[1]) - float(obox[3]) <= 40 and abs(float(obox[0]) - float(bbox[0])) <= 40:
            return text.rstrip(":")
    return None


def plan_statements(document: Dict[str, Any], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    """Elevation statements printed in plan notes and legends, each scoped to
    the note's own sheet and heading. Values are read; nothing is derived here."""

    titles = plan_titles(document)
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
            "bbox": block.get("bbox"),
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
    # A prefix abbreviation (``TOS (+0'-0")``) names its own values, so it
    # applies on every sheet -- unless two sheets define the prefix differently.
    prefix_rules: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for page_rules in rules_by_page.values():
        for r in page_rules:
            if r.get("prefix"):
                prefix_rules[r["prefix"]].append(r)
    project_prefix = [found[0] for found in prefix_rules.values()
                      if len({(r["meaning"], r["relative_to"]) for r in found}) == 1]
    out: List[Dict[str, Any]] = []
    for page, lines in sorted(_page_lines(document).items()):
        own = rules_by_page.get(page) or legend
        own_prefixes = {o.get("prefix") for o in own}
        rules = own + [r for r in project_prefix if r["page"] != page and r["prefix"] not in own_prefixes]
        if not rules:
            continue
        for line in lines:
            text = _clean(line.get("text"))
            bbox = line["bbox"]
            if _inside_any(bbox, note_boxes.get(page, [])):
                continue
            for m in _ENCLOSED_RE.finditer(text):
                value = _value(m.group(0))
                recovered = None if value else recover_missing_inch_mark(m.group(0))
                before = text[:m.start()].rstrip().split(" ")[-1].upper() if text[:m.start()].strip() else ""
                usable = [r for r in rules if not r.get("prefix") or before.endswith(r["prefix"])]
                prefixed = [r for r in usable if r.get("prefix")]
                if value:
                    rule = _rule_for(value, prefixed or [r for r in usable if not r.get("prefix")])
                elif recovered:
                    # Read only under a prefix rule whose own sample shows the
                    # full feet-inch form the value is missing a mark of.
                    rule = _rule_for(recovered["candidate"], [r for r in prefixed if '"' in r["sample"]])
                else:
                    continue
                if not rule:
                    continue
                out.append({
                    "kind": "plan_value", "page": page, "sheet": sheets.get(page),
                    "plan": (titles.get(page) or [None])[0], "value": value,
                    "status": "read" if value else "flagged",
                    **({"printed": recovered["printed"], "candidate": recovered["candidate"],
                        "flag": recovered["flag"]} if recovered else {}),
                    "meaning": rule["meaning"], "relative_to": rule["relative_to"],
                    "rule": rule["text"], "context": text[:70], "bbox": bbox,
                    "rule_sheet": None if rule["page"] == page else (rule.get("sheet") or f"p. {rule['page']}"),
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
                    "bbox": [round(min(lb[0], float(vb["bbox"][0])), 1), round(lb[1], 1),
                             round(max(lb[2], float(vb["bbox"][2])), 1), round(float(vb["bbox"][3]), 1)],
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
            boxes = [b for b in (line.get("name_bbox"), line.get("elevation_bbox")) if b]
            # A schedule continued in several blocks prints each level once per block.
            source = {"page": line["page"], "sheet": sheets.get(line["page"]), "bbox": _union_boxes(boxes) if boxes else None}
            if key in seen:
                seen[key]["blocks"] += 1
                seen[key]["occurrences"].append(source)
                continue
            value = _value(line["elevation_text"]) if line["elevation_text"] else None
            seen[key] = {
                "schedule_id": schedule["id"], "schedule": schedule.get("caption") or schedule["title"],
                "name": line["name"], "printed": line["elevation_text"], "elevation": value,
                "status": "read" if value else "see_plan" if line["elevation_text"] and is_see_plan(line["elevation_text"])
                else "missing",
                **source, "blocks": 1, "occurrences": [source],
            }
        out.extend(seen.values())
    return out


def _level_bands(document: Dict[str, Any], sheets: Dict[int, str]) -> List[Dict[str, Any]]:
    """What a printed level band means. A Revit schedule prints each level's
    name above its line and its elevation below it, so the band between two
    lines reads ``<upper line's elevation> <lower line's name>``
    (``14' - 0" FIRST FLOOR``): the elevation and the name are of *different*
    levels. Schedule rows keep that printed band as their ``level`` label."""

    rows: Dict[str, int] = defaultdict(int)
    for grid in document.get("schedule_grid") or []:
        for row in grid.get("rows") or []:
            if row.get("level"):
                rows[_band_key(row["level"])] += 1
    names = {s["id"]: s.get("caption") or s["title"]
             for s in (document.get("column_schedules") or {}).get("schedules") or []}
    out: Dict[tuple, Dict[str, Any]] = {}
    for (page, printed), reading in band_readings(document.get("column_schedules") or {}).items():
        # A line's own name + elevation is a band only if a schedule row prints it.
        if reading["pairing"] == "paired" and not rows.get(printed):
            continue
        key = (reading["schedule_id"], printed)
        if key in out:
            out[key]["pages"].append(page)
            continue
        known = reading["pairing"] != "ambiguous"
        out[key] = {
            "schedule_id": reading["schedule_id"], "schedule": names.get(reading["schedule_id"]),
            "printed": printed, "pairing": reading["pairing"], "level": reading.get("level"),
            # Which level each printed part belongs to (None when ambiguous).
            "upper": {"name": reading["elevation_of"]["level"], "elevation": reading["elevation_of"]["text"]}
            if known else None,
            "lower": {"name": reading["name_of"]["level"], "elevation": reading["name_of"]["elevation_text"]}
            if known else None,
            "page": page, "sheet": sheets.get(page), "pages": [page],
            "schedule_rows": rows.get(printed, 0),
        }
    return list(out.values())


def plan_names_by_page(document: Dict[str, Any], statements: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    """Names each plan page goes by: its titles, its note headings, and the
    level a note names (``TOP OF SECOND FLOOR SLAB`` -> ``SECOND FLOOR PLAN``)."""

    plan_names: Dict[int, List[str]] = defaultdict(list)
    for page, names in plan_titles(document).items():
        plan_names[page].extend(names)
    for s in statements:
        for name in (s.get("heading"), s.get("name") and f"{s['name']} PLAN"):
            if name and name not in plan_names[s["page"]]:
                plan_names[s["page"]].append(name)
    return plan_names


def levels_view(document: Dict[str, Any], sheets: Dict[int, str]) -> Dict[str, Any]:
    """Levels and elevations for review: schedule levels, plan elevations,
    datum notes and notations, each with its source. Boxes are in display space."""

    document = displayed(document)
    statements = plan_statements(document, sheets)
    spots = spot_elevations(document, sheets)
    values = plan_values(document, statements, sheets)
    elevations = plan_elevations(statements, spots, values)
    plan_names = plan_names_by_page(document, statements)
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
                                             "meaning": set(), "count": 0, "flagged": 0, "examples": [],
                                             "rule_sheets": set()})
        group["meaning"].add(v["meaning"] + (f" (from {v['relative_to']})" if v["relative_to"] else ""))
        group["count"] += 1
        if v["rule_sheet"]:
            group["rule_sheets"].add(v["rule_sheet"])
        flagged = v["status"] == "flagged"
        group["flagged"] += flagged
        # Flagged values are always listed, so each one can be checked on the sheet.
        if len(group["examples"]) < 8 or flagged:
            group["examples"].append({
                "text": v["context"], "page": v["page"], "sheet": v["sheet"], "bbox": v["bbox"], "status": v["status"],
                "value": v["printed"] if flagged else v["value"]["raw"],
                **({"candidate": v["candidate"]["display"], "flag": v["flag"]} if flagged else {}),
            })
    return {
        "schedule_levels": levels,
        "level_bands": _level_bands(document, sheets),
        "plan_elevations": elevations,
        "datums": datums,
        "notations": notations,
        "noted_on_plans": [{**g, "meaning": sorted(g["meaning"]), "rule_sheets": sorted(g["rule_sheets"])}
                           for g in sorted(noted.values(), key=lambda g: g["page"])],
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
