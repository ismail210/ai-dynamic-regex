"""Level review: every printed statement of one schedule level's elevation.

When a plan's datum note and the column schedule disagree about a level
(OSSE: S122 note 55'-2" against S602 55'-10"), two values are not enough to
review. This module gathers what else the set prints about that level, each
with its own source, and keeps observations apart from explanations:

* the schedule's level and the plan's general datum note;
* local plan annotations -- a value printed in a drawn box on that plan
  (S122 "55' - 10"" beside slab tag S5.25), with the slab tag's definition;
* section / elevation level markers (``T.O. SLAB LEVEL 2`` / ``EL. 55' - 10"``)
  naming the level, and markers for the same surface in views the plan
  itself calls out (S122 -> 3/S-421-O), each with its view;
* a consistency check of printed numbers only: a candidate slab value minus
  the plan's printed top-of-steel offset, against the set's printed
  ``T.O. STEEL`` markers for the same level;
* candidate explanations, each marked supported / not supported /
  unresolved with its basis. None is chosen: nothing here resolves a value,
  and a value is never preferred because it is printed more often.

Display evidence only; nothing feeds prediction or quantities.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from services.engineering.level_evidence import (
    _ENCLOSED_RE,
    _clean,
    format_elevation,
    level_keys,
    parse_elevation,
)

# "T.O. SLAB LEVEL 2" / "EL. 55' - 10"" as one block or two stacked blocks.
_MARKER_RE = re.compile(r"^(?P<name>(?:T\.?\s*O\.?|TOP\s+OF)\s+[A-Z][A-Z0-9 .&/\-]*?)\s+EL(?:EV(?:ATION)?)?\.?\s*(?P<value>[-+]?\d[\d' \-/\"]*\"?)$",
                        re.IGNORECASE)
_MARKER_NAME_RE = re.compile(r"^(?:T\.?\s*O\.?|TOP\s+OF)\s+[A-Z][A-Z0-9 .&/\-]*$", re.IGNORECASE)
_MARKER_VALUE_RE = re.compile(r"^EL(?:EV(?:ATION)?)?\.?\s*(?P<value>[-+]?\d[\d' \-/\"]*\"?)$", re.IGNORECASE)
# A view title is the whole block: "9 SECTION" (not "SEE SECTION 8/S-421-O ...").
_VIEW_TITLE_RE = re.compile(r"^(?P<id>\d{1,3}|[A-Z])\s+(?P<kind>SECTION|ELEVATION|DETAIL)S?$", re.IGNORECASE)
_SHEET_REF_RE = re.compile(r"^[A-Z]{1,2}-?\d{2,4}(?:\.\d+)?(?:-[A-Z])?$")
_VIEW_ID_RE = re.compile(r"^[A-Z0-9]{1,3}$")
_SURFACES = ("SLAB", "DECK", "STEEL", "CONCRETE", "WALL", "PIER", "FOOTING", "BEAM")
STEP_RE = re.compile(r"\b(?:STEP|DEPRESS\w*|RECESS\w*|RAISED|SUNKEN|DROP(?:PED)?)\b", re.IGNORECASE)
_LEVEL_REACH = 36.0        # inches: a boxed value this close to a schedule level is a candidate
_BOX_MARGIN = 10.0         # points between a value's text and the box drawn round it
_TAG_REACH = 80.0          # a slab tag printed next to a boxed value
_LOCAL_REACH = 250.0       # "near the annotation" for local step / depression notes


def _surface(name: str) -> str | None:
    words = re.findall(r"[A-Z]+", name.upper())
    found = [w for w in words if w in _SURFACES]
    return f"top of {found[0].lower()}" if found else None


def _sheet_key(text: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper())


def _blocks_by_page(document: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for block in document.get("blocks") or []:
        if len(block.get("bbox") or []) >= 4:
            out[int(block.get("page_number") or 0)].append(block)
    return out


def _view_of(bbox: list[float], titles: list[tuple]) -> dict[str, Any] | None:
    """The view a marker belongs to: its title printed under it at lower left
    (the nearest title row below, and in it the nearest title at or left of
    the marker) -- how the sheets print section titles."""

    x, y = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    below = [(round((t_box[1] - y) / 40), x - t_box[0], view, t_box) for view, t_box in titles
             if t_box[1] > y and t_box[0] <= x + 50]
    if not below:
        return None
    _row, _left, view, t_box = min(below, key=lambda b: (b[0], abs(b[1])))
    return {**view, "bbox": [round(v, 1) for v in t_box]}


def elevation_markers(document: dict[str, Any], sheets: dict[int, str]) -> list[dict[str, Any]]:
    """Level markers of sections and elevations: ``T.O. <surface> [LEVEL n]``
    with ``EL. <value>`` on the same block or stacked just under it, each with
    the view whose title is printed under it. PDF space."""

    markers: list[dict[str, Any]] = []
    for page, blocks in _blocks_by_page(document).items():
        titles = []
        for block in blocks:
            match = _VIEW_TITLE_RE.match(_clean(block.get("text")))
            if match:
                titles.append(({"id": match["id"], "kind": match["kind"].lower()}, block["bbox"]))
        for block in blocks:
            text = _clean(block.get("text"))
            name, value, boxes = None, None, [block["bbox"]]
            match = _MARKER_RE.match(text)
            if match:
                name, value = match["name"], match["value"]
            elif _MARKER_NAME_RE.match(text):
                x0, _y0, x1, y1 = block["bbox"][:4]
                under = [b for b in blocks if b is not block and 0 <= b["bbox"][1] - y1 + 2 <= 16
                         and b["bbox"][0] < x1 + 10 and b["bbox"][2] > x0 - 10
                         and _MARKER_VALUE_RE.match(_clean(b.get("text")))]
                if under:
                    name, value = text, _MARKER_VALUE_RE.match(_clean(under[0].get("text")))["value"]
                    boxes.append(under[0]["bbox"])
            parsed = parse_elevation(value) if value else None
            if not name or not parsed:
                continue
            bbox = [round(min(b[0] for b in boxes), 1), round(min(b[1] for b in boxes), 1),
                    round(max(b[2] for b in boxes), 1), round(max(b[3] for b in boxes), 1)]
            markers.append({
                "page": page, "sheet": sheets.get(page), "bbox": bbox, "name": _clean(name).upper(),
                "surface": _surface(name), "keys": level_keys(name), "value": parsed,
                "display": format_elevation(parsed["inches"]), "view": _view_of(bbox, titles),
            })
    return markers


def plan_callouts(document: dict[str, Any], page: int) -> list[dict[str, Any]]:
    """Section / detail callouts on one plan: a view id printed just above a
    sheet reference (``9`` over ``S-421-O``). PDF space."""

    words = [w for w in document.get("words") or [] if int(w.get("page_number") or 0) == page
             and len(w.get("bbox") or []) >= 4]
    out = []
    for w in words:
        if not _SHEET_REF_RE.match(str(w.get("text") or "")):
            continue
        x0, y0, x1, _y1 = w["bbox"][:4]
        cx = (x0 + x1) / 2
        above = [v for v in words if _VIEW_ID_RE.match(str(v.get("text") or "")) and 0 < y0 - v["bbox"][3] < 12
                 and abs((v["bbox"][0] + v["bbox"][2]) / 2 - cx) < 15]
        if above:
            out.append({"view": str(above[0]["text"]), "sheet_ref": str(w["text"]), "page": page,
                        "bbox": [round(v, 1) for v in w["bbox"][:4]]})
    return out


def boxed_values(document: dict[str, Any], pdf_path: str, pages: set | None = None) -> dict[str, list[dict[str, Any]]]:
    """Bare elevations printed inside a drawn box on a page (S122 ``55' - 10"``
    in a rectangle). Only values within 3 ft of a column-schedule level are
    candidates, and only their pages' vector paths are read -- ``pages`` limits
    the read to the plans a level review needs. PDF space."""

    import fitz

    levels = [v["inches"] for s in (document.get("column_schedules") or {}).get("schedules") or []
              for line in s.get("level_lines") or [] if (v := parse_elevation(line.get("elevation_text") or ""))]
    if not levels:
        return {}
    candidates: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for line in document.get("lines") or []:
        text = _clean(line.get("text"))
        value = parse_elevation(text) if text and text[0].isdigit() else None
        if (value and value["unit"] == "ft-in" and not value["enclosure"]
                and (pages is None or int(line.get("page_number") or 0) in pages)
                and any(abs(value["inches"] - level) <= _LEVEL_REACH for level in levels)
                and len(line.get("bbox") or []) >= 4):
            candidates[int(line.get("page_number") or 0)].append({"text": text, "value": value, "bbox": line["bbox"][:4]})
    found: dict[str, list[dict[str, Any]]] = {}
    if not candidates:
        return found
    with fitz.open(pdf_path) as pdf:
        for page, values in sorted(candidates.items()):
            if not 1 <= page <= pdf.page_count:
                continue
            rects = [d["rect"] for d in pdf[page - 1].get_drawings()
                     if any(item[0] == "re" for item in d["items"]) or d.get("closePath")]
            for value in values:
                x0, y0, x1, y1 = value["bbox"]
                box = next((r for r in rects if r.x0 <= x0 + 1 and r.y0 <= y0 + 1 and r.x1 >= x1 - 1 and r.y1 >= y1 - 1
                            and r.x0 >= x0 - _BOX_MARGIN and r.y0 >= y0 - _BOX_MARGIN
                            and r.x1 <= x1 + _BOX_MARGIN and r.y1 <= y1 + _BOX_MARGIN), None)
                if box is not None:
                    found.setdefault(str(page), []).append({
                        "text": value["text"], "inches": value["value"]["inches"],
                        "bbox": [round(v, 1) for v in value["bbox"]],
                        "box_bbox": [round(box.x0, 1), round(box.y0, 1), round(box.x1, 1), round(box.y1, 1)]})
    return found


def _near(a: list[float], b: list[float], reach: float) -> bool:
    return a[0] - reach <= b[2] and b[0] - reach <= a[2] and a[1] - reach <= b[3] and b[1] - reach <= a[3]


def general_note_value(match: dict[str, Any]) -> dict[str, Any]:
    """The plan's datum-note value a level is compared with."""

    return next((v for v in match["values"] if v.get("compared")), match["values"][0])


def tag_key(text: Any) -> str:
    """A slab / deck tag as printed (``S5.25``, ``G 2.5``), for lookup."""

    return re.sub(r"\s+", "", str(text or "")).upper()


def related_occurrences(inches: float, page_lines: dict[int, list[dict[str, Any]]],
                        tag_words: dict[int, list[dict[str, Any]]], sheets: dict[int, str]) -> list[dict[str, Any]]:
    """Other places the set prints a datum value as a bare elevation -- S103
    ``55' - 2"`` beside grating tag G2.5 -- with the slab / deck tag printed
    beside it (``tag_words``: tags by page) and the ``< >`` member elevations
    printed around it. A bare value counts only with such context (otherwise
    it may be a dimension). PDF space. Observations only."""

    out = []
    for page, lines in sorted(page_lines.items()):
        for line in lines:
            text = _clean(line.get("text"))
            value = parse_elevation(text) if text and text[0].isdigit() else None
            if not (value and value["unit"] == "ft-in" and not value["enclosure"] and abs(value["inches"] - inches) < 0.01):
                continue
            bbox = line["bbox"][:4]
            tag = next((t for t in tag_words.get(page, []) if _near(bbox, t["bbox"], _TAG_REACH)), None)
            nearby = [v["inches"] for other in lines if other is not line and _near(bbox, other["bbox"][:4], _LOCAL_REACH)
                      for m in _ENCLOSED_RE.finditer(_clean(other.get("text")))
                      if (v := parse_elevation(m.group(0))) and v["enclosure"] == "<" and v["unit"] == "ft-in"
                      and abs(v["inches"] - inches) <= _LEVEL_REACH]
            if tag or nearby:
                out.append({"page": page, "sheet": sheets.get(page), "text": text, "inches": value["inches"],
                            "bbox": [round(c, 1) for c in bbox], "tag": tag, "nearby": nearby})
    return out


def _related(occurrence: dict[str, Any], own_tags: set) -> dict[str, Any]:
    """One related occurrence with its tag's printed depth checked against
    the member elevations printed around it (numbers only). It is a separate
    condition only when its tag is not one the review's own sources carry."""

    tag = occurrence["tag"]
    row = (tag or {}).get("row") or {}
    depth_cell = next((c for c in row.get("cells") or []
                       if re.search(r"DEPTH|THICKNESS", (c.get("path") or [c.get("heading") or ""])[-1], re.IGNORECASE)
                       and c.get("text")), None)
    depth = parse_elevation(depth_cell["text"]) if depth_cell else None
    result = occurrence["inches"] - depth["inches"] if depth else None
    printed = sum(1 for n in occurrence["nearby"] if result is not None and abs(n - result) < 0.01)
    separate = bool(tag) and tag["mark"] not in own_tags
    details = [d for d in (row.get("material"), depth_cell and f"total depth {depth_cell['text']}") if d]
    beside = f" beside {tag['mark']}" + (f" ({', '.join(details)})" if details else "") if tag else ""
    note = f"Printed on {occurrence.get('sheet') or 'p. ' + str(occurrence['page'])}{beside}"
    if printed:
        depth_text = format_elevation(depth["inches"]).removeprefix("0'-")
        note += (f": {format_elevation(occurrence['inches'])} − {depth_text} = {format_elevation(result)}, "
                 f"the bracketed member elevation printed {printed} time{'s' if printed != 1 else ''} around it")
    note += (". A separate condition from the slab statements above; it does not resolve them." if separate
             else ". Whether it states the same condition as the sources above is not established.")
    return {
        "value": occurrence["text"], "separate": separate,
        "source": {"page": occurrence["page"], "sheet": occurrence.get("sheet"), "bbox": occurrence["bbox"]},
        "tag": ({"mark": tag["mark"], "material": row.get("material"),
                 "definition": {"table": row.get("table"), "page": row.get("page"), "sheet": row.get("sheet"),
                                "bbox": row.get("bbox")}} if tag else None),
        "result": format_elevation(result) if result is not None else None,
        "printed_count": printed,
        "note": note,
    }


def level_review(level: dict[str, Any], match: dict[str, Any], *, markers: list[dict[str, Any]],
                 boxed: list[dict[str, Any]], callouts: list[dict[str, Any]], tags: list[dict[str, Any]],
                 steps: list[dict[str, Any]], steel_rule: dict[str, Any] | None,
                 other_levels: list[dict[str, Any]], related: list[dict[str, Any]] = ()) -> dict[str, Any]:
    """Everything printed about one schedule level whose linked plan's datum
    note disagrees with the schedule. ``boxed`` / ``tags`` / ``steps`` are on
    the plan's page; ``related`` (``related_occurrences``) are other places
    the general note's value is printed; all boxes are display space."""

    keys = level_keys(level["name"])
    ordinals = {k[1] for k in keys if k[1] is not None}
    surface = level.get("surface")
    note = general_note_value(match)
    items: list[dict[str, Any]] = [
        {"role": "schedule", "label": f"Column schedule · {level['schedule']}", "value": level["printed"],
         "inches": level["elevation"]["inches"], "surface": surface,
         "source": {"page": level["page"], "sheet": level.get("sheet"), "bbox": level.get("bbox")},
         "scope": "the schedule's level line"},
        {"role": "general_note", "label": f"General datum note · {match.get('sheet') or 'p. ' + str(match['page'])}",
         "value": note.get("raw") or note.get("display"), "inches": note["inches"], "surface": note.get("surface"),
         "source": note["source"], "scope": "the sheet's datum statement (no area named)"},
    ]
    near = level["elevation"]["inches"]
    for value in boxed:
        if abs(value["inches"] - near) > _LEVEL_REACH and abs(value["inches"] - note["inches"]) > _LEVEL_REACH:
            continue
        tag = next((t for t in tags if _near(value["box_bbox"], t["bbox"], _TAG_REACH)), None)
        local_steps = [s for s in steps if _near(value["box_bbox"], s["bbox"], _LOCAL_REACH)]
        items.append({
            "role": "local_annotation",
            "label": f"Local plan annotation · {match.get('sheet') or 'p. ' + str(match['page'])}",
            "value": value["text"], "inches": value["inches"], "surface": None,
            "source": {"page": match["page"], "sheet": match.get("sheet"), "bbox": value["box_bbox"]},
            "scope": "printed in a box at one place on the plan"
                     + (f", beside slab tag {tag['mark']}" if tag else ""),
            **({"tag": tag} if tag else {}),
            "local_steps": local_steps,
        })
    referenced = {(c["view"].upper(), _sheet_key(c["sheet_ref"])) for c in callouts}

    def called_out(marker: dict[str, Any]) -> bool:
        view = marker.get("view")
        return bool(view) and any(v == view["id"].upper() and _sheet_key(marker.get("sheet")) and
                                  ref.startswith(_sheet_key(marker.get("sheet"))) for v, ref in referenced)

    for marker in markers:
        names_level = bool(marker["keys"] & keys)
        same_surface = marker["surface"] == surface
        if not same_surface or not (names_level or called_out(marker)):
            continue
        view = marker.get("view")
        where = f"{view['kind'].title()} {view['id']} · {marker.get('sheet')}" if view else (marker.get("sheet") or "")
        items.append({
            "role": "section" if names_level else "section_local",
            "label": where, "value": marker["value"]["raw"].replace("EL.", "").strip(), "inches": marker["value"]["inches"],
            "surface": marker["surface"], "name": marker["name"],
            "source": {"page": marker["page"], "sheet": marker.get("sheet"), "bbox": marker["bbox"]},
            "scope": ("names this level" if names_level
                      else "the plan calls out this view; the marker names no level — a local condition"),
            "called_out": called_out(marker),
        })
    # Printed-number consistency: a candidate slab value minus the plan's own
    # printed top-of-steel offset, looked up among the set's printed steel
    # markers for the same level. It checks numbers; it decides nothing.
    checks: list[dict[str, Any]] = []
    steel = [m for m in markers if m["surface"] == "top of steel" and {k[1] for k in m["keys"]} & ordinals]
    if steel_rule and surface == "top of slab":
        offset = steel_rule["offset"]["inches"]
        for inches in sorted({round(i["inches"], 4) for i in items if i["role"] != "section_local"}):
            result = inches - offset
            printed = [m for m in steel if abs(m["value"]["inches"] - result) < 0.01]
            checks.append({
                "kind": "steel_offset", "slab": format_elevation(inches), "slab_inches": inches,
                "offset": steel_rule["offset"].get("raw"), "offset_inches": offset,
                "offset_text": format_elevation(offset).removeprefix("0'-"), "result": format_elevation(result),
                "result_inches": result,
                "printed": [{"page": m["page"], "sheet": m.get("sheet"), "bbox": m["bbox"], "name": m["name"],
                             "view": m.get("view")} for m in printed],
                "rule_source": steel_rule.get("source"),
            })
    values = {round(i["inches"], 4) for i in items if i["role"] in ("schedule", "general_note", "local_annotation", "section")}
    general = round(note["inches"], 4)
    others = [i for i in items if i["role"] in ("schedule", "local_annotation", "section")
              and round(i["inches"], 4) != general]
    own_tags = {i["tag"]["mark"] for i in items if i.get("tag")}
    related_items = [_related(o, own_tags) for o in related]
    explanations = _explanations(items, note, others, other_levels, checks, related_items)
    headline = (f"{_short(level['name'])} elevation requires review: the general datum note states "
                f"{format_elevation(note['inches'])}, while "
                + _join([_describe(i) for i in others]) + f" state{'s' if len(others) == 1 else ''} "
                + _join(sorted({format_elevation(i['inches']) for i in others}))
                + ". Their applicable areas have not been fully reconciled.") if others else None
    return {"level": level["name"], "schedule_id": level["schedule_id"], "plan_page": match["page"],
            "headline": headline, "items": items, "checks": checks, "explanations": explanations,
            "related": related_items,
            "distinct_values": len(values)}


def _short(name: str) -> str:
    text = re.sub(r"^\s*(?:T\.?\s*O\.?|TOP\s+OF)\s+(?:SLAB\s+|STEEL\s+|DECK\s+)?", "", str(name or ""), flags=re.IGNORECASE)
    return text.title() or str(name)


def _describe(item: dict[str, Any]) -> str:
    return {"schedule": "the column schedule", "local_annotation": "a local slab annotation",
            "section": "a section"}.get(item["role"], "a source")


def _join(parts: list[str]) -> str:
    parts = list(dict.fromkeys(parts))
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _explanations(items: list[dict[str, Any]], note: dict[str, Any], others: list[dict[str, Any]],
                  other_levels: list[dict[str, Any]], checks: list[dict[str, Any]],
                  related: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Candidate explanations with what the printed evidence says about each.
    ``supported`` / ``not_supported`` need printed evidence; everything else
    stays ``unresolved``."""

    local = [i for i in items if i["role"] == "local_annotation"]
    steps = [s for i in local for s in i.get("local_steps") or []]
    surfaces = {i.get("surface") for i in items if i["role"] in ("general_note", "section") and i.get("surface")}
    agreeing = [o for o in other_levels if o.get("comparison") == "agrees"]
    value = format_elevation(note["inches"])
    stated = (f"In the reviewed evidence, {value} is stated for this level only in the general note; {len(others)} "
              f"other source{'s' if len(others) != 1 else ''} state{'s' if len(others) == 1 else ''} "
              + _join(sorted({format_elevation(i["inches"]) for i in others})) + ".")
    also = ""
    if related:
        elsewhere = _join([(r["source"].get("sheet") or f"p. {r['source']['page']}")
                           + (f" beside {r['tag']['mark']}" if r.get("tag") else "") for r in related])
        also = f" {value} is also printed on {elsewhere}" + (
            " — a separate condition (below), not a statement about the slab." if all(r["separate"] for r in related)
            else " (below); whether that states the same condition is not established.")
    out = [
        {"id": "local_elevations", "label": "Different local slab elevations",
         "status": "supported" if steps else "unresolved",
         "basis": (f"A step / depression note is printed near the local annotation: {steps[0]['text']}" if steps else
                   "No slab step, depression or raised-slab note is printed near the local annotation; the "
                   "areas the sections and the annotation cover have not been compared with the general note.")},
        {"id": "surfaces", "label": "Different physical surfaces",
         "status": "not_supported" if surfaces == {"top of slab"} else "unresolved",
         "basis": ("The general note, the schedule level and the sections all name the top of slab."
                   if surfaces == {"top of slab"} else "The sources do not all name the same surface.")},
        {"id": "datum", "label": "Different datum systems",
         "status": "not_supported" if agreeing else "unresolved",
         "basis": ("The same kind of datum note agrees with the schedule for "
                   + ", ".join(f"{_short(o['level'])} ({o['sheet']})" for o in agreeing) + "."
                   if agreeing else "No other level's datum note was compared with the schedule.")},
        {"id": "general_note_scope", "label": "The general note does not govern a local condition",
         "status": "unresolved",
         "basis": "The note states one datum for the floor without naming an area; the other values are printed "
                  "at particular places. Which areas each covers is not stated."},
        {"id": "inconsistent", "label": "An inconsistent annotation",
         "status": "unresolved",
         "basis": stated + also + " Printing a value more often does not make it govern."},
    ]
    printed = [c for c in checks if c["printed"]]
    unprinted = [c for c in checks if not c["printed"]]
    if printed:
        out.append({"id": "steel_check", "label": "Consistency with the printed top-of-steel level",
                    "status": "observation",
                    "basis": "; ".join(f"{c['slab']} − {c['offset_text']} = {c['result']}, printed as "
                                       f"{c['printed'][0]['name']} on " + ", ".join(sorted({p['sheet'] or '' for p in c['printed']}))
                                       for c in printed)
                             + ("; " + "; ".join(f"{c['slab']} − {c['offset_text']} = {c['result']}, "
                                                "not found among the extracted level markers" for c in unprinted) if unprinted else "")
                             + ". This checks printed numbers only; it does not establish which value governs."})
    return out
