"""Grid labels, drawn axes, intersections, and mark allocation.

A printed letter or number is not a grid until a long axis-aligned line
supports it. A dimension is never a grid. An allocation that is equally
close to two intersections stays review-required. Nothing here is a quantity.
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.engineering.page_space import to_display

_LABEL = re.compile(
    r"^(?:[A-Z]|\d{1,2}|[A-Z]\.\d{1,2}|[A-Z]-\d{1,2}|\d{1,2}[A-Z])$"
)
_MARK = re.compile(r"^(?:C\d{1,3}|BP\d{1,2}|PC\d{1,2}|P\d{1,2}|F\d{1,2}|L\d{1,2})$")
_DIMENSION = re.compile(
    r"^[+\-]?\d+\s*'\s*-?\s*\d+(?:\s+\d+/\d+)?\s*\"?$"
    r"|^[+\-]?\d+(?:\s+\d+/\d+)?\s*\"$"
)
_SHEET_REF = re.compile(r"\b[A-Z]{1,2}\s*/\s*S[-.]?\d", re.I)

_DASH_GAP = 48.0
_LOGICAL_GAP = 96.0


def classify_grid_text(text: str) -> Optional[str]:
    """``label`` when the whole line could be a grid id. A rejection reason
    when it is a known lookalike. None when it is ordinary text."""

    raw = " ".join(str(text or "").split())
    if not raw:
        return None
    if _DIMENSION.match(raw):
        return "dimension"
    if re.fullmatch(r"\d{1,2}K", raw):
        return "joist_mark"
    if _SHEET_REF.search(raw):
        return "sheet_reference"
    if _MARK.match(raw):
        return "member_mark"
    if _LABEL.match(raw):
        return "label"
    return None


def _axis_type(label: str) -> str:
    if re.fullmatch(r"[A-Z]", label):
        return "letter"
    if re.fullmatch(r"\d{1,2}", label):
        return "number"
    return "unknown"


def _coord(point) -> Tuple[float, float]:
    if hasattr(point, "x"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def _display_point(rotation: int, width: float, height: float, x: float, y: float) -> Tuple[float, float]:
    box = to_display(rotation, width, height, [x, y, x, y])
    return box[0], box[1]


def display_segments(drawings: Sequence[dict], rotation: int, width: float, height: float) -> List[dict]:
    """Axis-aligned ``l`` segments in display space. Short dashes are kept so a later merge can rebuild the line."""

    segments: List[dict] = []
    for drawing in drawings or []:
        for item in drawing.get("items") or []:
            if not item or str(item[0]).lower() != "l" or len(item) < 3:
                continue
            x1, y1 = _coord(item[1])
            x2, y2 = _coord(item[2])
            x1, y1 = _display_point(rotation, width, height, x1, y1)
            x2, y2 = _display_point(rotation, width, height, x2, y2)
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            if dy <= 2.0 and dx >= 8.0:
                segments.append({
                    "orientation": "horizontal", "axis": (y1 + y2) / 2.0,
                    "start": min(x1, x2), "end": max(x1, x2),
                })
            elif dx <= 2.0 and dy >= 8.0:
                segments.append({
                    "orientation": "vertical", "axis": (x1 + x2) / 2.0,
                    "start": min(y1, y2), "end": max(y1, y2),
                })
    return segments


def _new_run(piece: dict) -> dict:
    length = float(piece["end"]) - float(piece["start"])
    return {
        "start": float(piece["start"]), "end": float(piece["end"]),
        "covered": length, "segment_count": 1,
        "dash_count": 1 if length <= 80 else 0,
        "max_gap": 0.0, "gaps": [], "linked_runs": 1,
    }


def _extend_run(run: dict, piece: dict) -> None:
    start, end = float(piece["start"]), float(piece["end"])
    join_gap = start - run["end"]
    if join_gap > 0.5:
        run["gaps"].append(round(join_gap, 1))
        run["max_gap"] = max(run["max_gap"], join_gap)
    added = max(0.0, end - run["end"])
    if added >= 4:
        run["segment_count"] += 1
        if end - start <= 80:
            run["dash_count"] += 1
        run["covered"] += added
    run["end"] = max(run["end"], end)


def merge_chains(segments: Sequence[dict], *, gap: float = _DASH_GAP) -> List[dict]:
    """Join collinear dashes into one chain per axis.

    Each chain keeps the pieces, the ink covered, and the gaps so a later
    check can tell a dashed axis from one short line.
    """

    grouped: Dict[Tuple[str, int], List[dict]] = {}
    for segment in segments:
        key = (segment["orientation"], round(float(segment["axis"])))
        grouped.setdefault(key, []).append(segment)
    keys = sorted(grouped)
    clusters: List[List[Tuple[str, int]]] = []
    for key in keys:
        if clusters and clusters[-1][-1][0] == key[0] and key[1] - clusters[-1][-1][1] <= 3:
            clusters[-1].append(key)
        else:
            clusters.append([key])
    chains: List[dict] = []
    for cluster in clusters:
        pieces = [piece for key in cluster for piece in grouped[key]]
        orientation = pieces[0]["orientation"]
        axis = sum(float(piece["axis"]) for piece in pieces) / len(pieces)
        runs: List[dict] = []
        for piece in sorted(pieces, key=lambda item: float(item["start"])):
            if runs and float(piece["start"]) <= runs[-1]["end"] + gap:
                _extend_run(runs[-1], piece)
            else:
                runs.append(_new_run(piece))
        for run in runs:
            chains.append({
                "orientation": orientation,
                "axis": axis,
                "start": run["start"],
                "end": run["end"],
                "length": run["end"] - run["start"],
                "covered": run["covered"],
                "segment_count": run["segment_count"],
                "dash_count": run["dash_count"],
                "max_gap": run["max_gap"],
                "gaps": run["gaps"],
                "linked_runs": 1,
            })
    return chains


def link_logical_axes(chains: Sequence[dict], *, gap: float = _LOGICAL_GAP) -> List[dict]:
    """Join collinear chains that a dash gap split, without bridging separate plans.

    A gap larger than ``gap`` stays two axes. Two ticks at opposite edges of
    the sheet do not become one grid line.
    """

    grouped: Dict[Tuple[str, int], List[dict]] = {}
    for chain in chains:
        key = (chain["orientation"], round(float(chain["axis"])))
        grouped.setdefault(key, []).append(dict(chain))
    linked: List[dict] = []
    for items in grouped.values():
        items.sort(key=lambda item: item["start"])
        current: Optional[dict] = None
        for chain in items:
            if current and chain["start"] <= current["end"] + gap:
                join_gap = max(0.0, chain["start"] - current["end"])
                if join_gap > 0.5:
                    current["gaps"] = list(current.get("gaps") or []) + [round(join_gap, 1)] + list(chain.get("gaps") or [])
                    current["max_gap"] = max(current.get("max_gap") or 0, chain.get("max_gap") or 0, join_gap)
                else:
                    current["gaps"] = list(current.get("gaps") or []) + list(chain.get("gaps") or [])
                    current["max_gap"] = max(current.get("max_gap") or 0, chain.get("max_gap") or 0)
                current["end"] = max(current["end"], chain["end"])
                current["length"] = current["end"] - current["start"]
                current["covered"] = (current.get("covered") or 0) + (chain.get("covered") or 0)
                current["segment_count"] = (current.get("segment_count") or 1) + (chain.get("segment_count") or 1)
                current["dash_count"] = (current.get("dash_count") or 0) + (chain.get("dash_count") or 0)
                current["linked_runs"] = (current.get("linked_runs") or 1) + (chain.get("linked_runs") or 1)
            else:
                if current:
                    linked.append(current)
                current = dict(chain)
                current["gaps"] = list(chain.get("gaps") or [])
        if current:
            linked.append(current)
    return linked


def _min_length(width: float, height: float) -> float:
    short = min(width, height) or 1.0
    return max(360.0, 0.18 * short)


def _tolerance(height: float) -> float:
    return max(32.0, 2.2 * height)


def _is_border(chain: dict, width: float, height: float) -> bool:
    """A line along the sheet edge that spans the sheet is the border, not a grid."""

    if width <= 0 or height <= 0:
        return False
    span = float(chain["length"])
    if chain["orientation"] == "horizontal":
        return span > 0.75 * width and (chain["axis"] < 70 or chain["axis"] > height - 70)
    return span > 0.75 * height and (chain["axis"] < 70 or chain["axis"] > width - 70)


def _letter_uses_edge_line(label: dict, chain: dict) -> bool:
    """A side-margin letter may use a full-width line near the sheet edge.

    A number may not. That line is the sheet border for a bottom number and the
    grid axis for a letter printed in the left or right column.
    """

    return (
        chain["orientation"] == "horizontal"
        and bool({"left", "right"} & set(label["sides"]))
        and re.fullmatch(r"[A-Z](?:\.\d{1,2})?", label["text"]) is not None
    )


def _supported(chain: dict, width: float, height: float) -> bool:
    """A logical axis, not a single short line.

    One segment must still span the long-line minimum. A dashed axis qualifies
    when several short collinear pieces cover a continuous run. A sheet border
    does not, unless the caller has already accepted it for a side-margin letter.
    """

    if _is_border(chain, width, height) and not chain.get("allow_edge_line"):
        return False
    span = float(chain["length"])
    covered = float(chain.get("covered") or span)
    ratio = covered / span if span else 0.0
    if span >= _min_length(width, height) and covered >= 220 and ratio >= 0.4:
        return True
    dashes = int(chain.get("dash_count") or 0)
    if (
        dashes >= 4
        and span >= 180
        and float(chain.get("max_gap") or 0) <= _DASH_GAP
        and covered >= 140
        and ratio >= 0.7
    ):
        return True
    return False


def _extends_inward(label: dict, chain: dict, width: float, height: float) -> bool:
    cx, cy = label["cx"], label["cy"]
    sides = label["sides"]
    if chain["orientation"] == "horizontal":
        if sides:
            return ("left" in sides and chain["end"] > cx + 40) or ("right" in sides and chain["start"] < cx - 40)
        if cx < width / 2:
            return chain["end"] > cx + 40
        return chain["start"] < cx - 40
    if sides:
        return ("top" in sides and chain["end"] > cy + 40) or ("bottom" in sides and chain["start"] < cy - 40)
    if cy < height / 2:
        return chain["end"] > cy + 40
    return chain["start"] < cy - 40


def _chain_hit(label: dict, chain: dict, width: float, height: float) -> Optional[dict]:
    cx, cy = label["cx"], label["cy"]
    tol = _tolerance(label["height"])
    if _letter_uses_edge_line(label, chain):
        chain = dict(chain)
        chain["allow_edge_line"] = True
    if not _supported(chain, width, height):
        return None
    if chain["orientation"] == "horizontal":
        distance = abs(cy - chain["axis"])
    else:
        distance = abs(cx - chain["axis"])
    if distance > tol or not _extends_inward(label, chain, width, height):
        return None
    how = "margin" if label["sides"] else "outside_margin"
    return {"distance": distance, "chain": chain, "how": how}


def _page_chains(document: Dict[str, Any], pages: Sequence[int], meta: Dict[int, dict]) -> Dict[int, List[dict]]:
    injected = document.get("grid_line_segments")
    if injected is not None:
        by_page: Dict[int, List[dict]] = {}
        for segment in injected:
            by_page.setdefault(int(segment["page"]), []).append(segment)
        return {page: link_logical_axes(merge_chains(items)) for page, items in by_page.items()}
    path = document.get("source_path")
    if not path or not Path(path).is_file():
        return {}
    import fitz
    found: Dict[int, List[dict]] = {}
    with fitz.open(path) as pdf:
        for page_number in pages:
            info = meta.get(page_number) or {}
            if page_number < 1 or page_number > pdf.page_count:
                continue
            page = pdf[page_number - 1]
            width = float(info.get("width") or page.rect.width)
            height = float(info.get("height") or page.rect.height)
            rotation = int(info.get("rotation") or page.rotation or 0)
            found[page_number] = link_logical_axes(
                merge_chains(display_segments(page.get_drawings(), rotation, width, height))
            )
    return found


def _intersections(grids: Sequence[dict], multi_view: bool) -> List[dict]:
    vertical = [grid for grid in grids if grid["status"] == "confirmed" and grid["orientation"] == "vertical"]
    horizontal = [grid for grid in grids if grid["status"] == "confirmed" and grid["orientation"] == "horizontal"]
    found = []
    for x_axis in vertical:
        for y_axis in horizontal:
            if x_axis["pdf_page"] != y_axis["pdf_page"]:
                continue
            line_x = x_axis["line"]
            line_y = y_axis["line"]
            if line_y["start"] - 20 > line_x["axis"] or line_y["end"] + 20 < line_x["axis"]:
                continue
            if line_x["start"] - 20 > line_y["axis"] or line_x["end"] + 20 < line_y["axis"]:
                continue
            point = [round(line_x["axis"], 1), round(line_y["axis"], 1)]
            if any(item["pdf_page"] == x_axis["pdf_page"] and item["point"] == point for item in found):
                continue
            status = "review_required" if multi_view else "confirmed"
            found.append({
                "grid_intersection_id": f"{x_axis['grid_id']}@{y_axis['grid_id']}@p{x_axis['pdf_page']}",
                "grid_x": x_axis["label"],
                "grid_y": y_axis["label"],
                "display": f"{x_axis['label']}/{y_axis['label']}",
                "source_labels": [x_axis["label"], y_axis["label"]],
                "point": point,
                "bbox": [point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4],
                "sheet_id": x_axis["sheet_id"],
                "pdf_page": x_axis["pdf_page"],
                "view_id": None,
                "status": status,
                "confidence": 0.55 if multi_view else 0.8,
                "evidence": [
                    f"grid label {x_axis['label']} at {x_axis['bbox']}",
                    f"vertical grid line at x={line_x['axis']:.1f}",
                    f"grid label {y_axis['label']} at {y_axis['bbox']}",
                    f"horizontal grid line at y={line_y['axis']:.1f}",
                    "intersection is the crossing of those two lines",
                ],
            })
    return found


def _spacing(intersections: Sequence[dict]) -> float:
    xs = sorted({item["point"][0] for item in intersections})
    ys = sorted({item["point"][1] for item in intersections})
    gaps = [b - a for a, b in zip(xs, xs[1:]) if b > a] + [b - a for a, b in zip(ys, ys[1:]) if b > a]
    if not gaps:
        return 120.0
    return float(statistics.median(gaps))


def _allocate(marks: Sequence[dict], intersections: Sequence[dict], multi_view: bool) -> List[dict]:
    if not marks:
        return []
    spacing = _spacing(intersections)
    allocations = []
    for mark in marks:
        ranked = []
        for item in intersections:
            if item["pdf_page"] != mark["pdf_page"]:
                continue
            distance = ((mark["cx"] - item["point"][0]) ** 2 + (mark["cy"] - item["point"][1]) ** 2) ** 0.5
            ranked.append((distance, item))
        ranked.sort(key=lambda pair: pair[0])
        if not ranked or ranked[0][0] > 0.55 * spacing:
            allocations.append({
                "mark": mark["text"], "sheet_id": mark["sheet_id"], "pdf_page": mark["pdf_page"],
                "bbox": mark["bbox"], "grid_location": None, "grid_intersection_id": None,
                "distance_to_intersection": None if not ranked else round(ranked[0][0], 1),
                "allocation_status": "unresolved", "confidence": 0.2,
                "evidence": ["no confirmed intersection is close enough; the mark is not forced onto a grid"],
            })
            continue
        best_distance, best = ranked[0]
        ambiguous = (
            len(ranked) > 1
            and ranked[1][0] - best_distance < 0.25 * spacing
            and ranked[1][0] < best_distance * 1.35
        )
        if ambiguous or multi_view:
            status = "review_required"
            confidence = 0.4
        elif best_distance <= 0.22 * spacing:
            status = "confirmed"
            confidence = 0.75
        else:
            status = "candidate"
            confidence = 0.55
        allocations.append({
            "mark": mark["text"], "sheet_id": mark["sheet_id"], "pdf_page": mark["pdf_page"],
            "bbox": mark["bbox"], "grid_location": best["display"],
            "grid_intersection_id": best["grid_intersection_id"],
            "distance_to_intersection": round(best_distance, 1),
            "allocation_status": status, "confidence": confidence,
            "evidence": [
                f"object center at ({mark['cx']:.1f}, {mark['cy']:.1f})",
                f"intersection {best['display']} at {best['point']}",
                f"distance {best_distance:.1f} against grid spacing {spacing:.1f}",
                "two intersections are similarly close" if ambiguous else "one intersection is clearly closer",
                "more than one view title is printed on this sheet" if multi_view else "one plan view on this sheet",
            ],
        })
    return allocations


def _bubble_extremes(labels: Sequence[dict]) -> Dict[tuple, float]:
    """Outermost grid-like token on each sheet edge. A second copy further in is not that column."""

    buckets: Dict[tuple, List[float]] = {}
    for label in labels:
        for side in label["sides"]:
            coord = label["cx"] if side in ("left", "right") else label["cy"]
            buckets.setdefault((int(label["pdf_page"]), side), []).append(coord)
    extremes = {}
    for key, values in buckets.items():
        side = key[1]
        extremes[key] = min(values) if side in ("left", "top") else max(values)
    return extremes


def _outer_bubble(label: dict, extremes: Dict[tuple, float]) -> bool:
    for side in label["sides"]:
        extreme = extremes.get((int(label["pdf_page"]), side))
        if extreme is None:
            continue
        coord = label["cx"] if side in ("left", "right") else label["cy"]
        if abs(coord - extreme) <= 72:
            return True
    return False


def _near_margin_band(label: dict, width: float, height: float) -> bool:
    """The 14% margin is a prior. A label just outside it can still be a bubble."""

    if label["sides"]:
        return True
    slack = 48.0
    cx, cy = label["cx"], label["cy"]
    return (
        cx <= 0.14 * width + slack or cx >= 0.86 * width - slack
        or cy <= 0.14 * height + slack or cy >= 0.86 * height - slack
    )


def _near_chain_end(label: dict, chain: dict) -> bool:
    if chain["orientation"] == "horizontal":
        return min(abs(label["cx"] - chain["start"]), abs(label["cx"] - chain["end"])) <= 100
    return min(abs(label["cy"] - chain["start"]), abs(label["cy"] - chain["end"])) <= 100


def _implied_orientation(labels: Sequence[dict]) -> Dict[int, str]:
    """A row of bubbles is a set of vertical grids. A column is a set of horizontal grids.

    When interior text makes a label look like both, the larger run wins.
    """

    implied: Dict[int, str] = {}
    by_page: Dict[int, List[int]] = {}
    for index, label in enumerate(labels):
        by_page.setdefault(int(label["pdf_page"]), []).append(index)
    for indexes in by_page.values():
        for index in indexes:
            label = labels[index]
            row = sum(1 for other in indexes if abs(labels[other]["cy"] - label["cy"]) <= 20)
            column = sum(1 for other in indexes if abs(labels[other]["cx"] - label["cx"]) <= 20)
            if row >= 3 and column >= 3:
                sides = set(label["sides"])
                on_letter_edge = bool(sides & {"left", "right"})
                on_number_edge = bool(sides & {"top", "bottom"})
                letter = re.fullmatch(r"[A-Z](?:\.\d{1,2})?", label["text"]) is not None
                number = re.fullmatch(r"\d{1,2}", label["text"]) is not None
                if letter and on_letter_edge and not on_number_edge:
                    implied[index] = "horizontal"
                elif number and on_number_edge and not on_letter_edge:
                    implied[index] = "vertical"
                elif column > row:
                    implied[index] = "horizontal"
                elif row > column:
                    implied[index] = "vertical"
                elif on_letter_edge:
                    implied[index] = "horizontal"
                elif on_number_edge:
                    implied[index] = "vertical"
            elif row >= 3:
                implied[index] = "vertical"
            elif column >= 3:
                implied[index] = "horizontal"
    return implied


def _locked_orientation(label: dict, implied: Optional[str]) -> Optional[str]:
    """A lone letter is not a vertical grid. A lone number on the top or bottom is not horizontal.

    A number printed in the letter column, such as OSSE's left-edge ``1``, keeps both axes.
    """

    if implied:
        return implied
    sides = set(label["sides"])
    on_letter_edge = bool(sides & {"left", "right"})
    on_number_edge = bool(sides & {"top", "bottom"})
    if re.fullmatch(r"[A-Z](?:\.\d{1,2})?", label["text"]):
        if on_number_edge and on_letter_edge:
            return None
        return "horizontal"
    if re.fullmatch(r"\d{1,2}", label["text"]):
        if on_letter_edge and not on_number_edge:
            return None
        return "vertical"
    return None


def _claim_key(label: dict, chain: dict) -> tuple:
    """Separate chains on one coordinate stay separate regions. One chain is one claim."""

    return (
        label["pdf_page"], chain["orientation"], round(chain["axis"]),
        round(float(chain["start"]) / 250.0),
    )


def _confirm_evidence(label: dict, line: dict, how: str) -> List[str]:
    evidence = [
        f"printed label {label['text']}",
        f"{line['orientation']} line at {line['axis']:.1f} from {line['start']:.1f} to {line['end']:.1f}",
        f"{int(line.get('segment_count') or 1)} aligned segments, covered {float(line.get('covered') or line['length']):.0f}",
    ]
    if float(line["length"]) < 360:
        evidence.append("dashed axis: several collinear segments, not one short line")
    elif how == "outside_margin":
        evidence.append("outside the margin band, at the end of a supported grid line")
    else:
        evidence.append("closest label on this line")
    return evidence


def _assign_labels(labels, chains, meta, rejected):
    """One drawn chain confirms the closest label. The same text at the other end is kept.

    A label further in than the outer bubble column must sit at the end of the line.
    A label that is not part of a bubble row or column must sit at the end of the line.
    A row of bubbles may only confirm vertical lines. A column may only confirm horizontal lines.
    """

    extremes = _bubble_extremes(labels)
    implied = _implied_orientation(labels)
    pending = []
    for index, label in enumerate(labels):
        page = int(label["pdf_page"])
        info = meta.get(page) or {}
        width, height = float(info.get("width") or 0), float(info.get("height") or 0)
        hits = [
            hit for chain in chains.get(page) or []
            if (hit := _chain_hit(label, chain, width, height))
        ]
        if not _near_margin_band(label, width, height):
            hits = []
        wanted = _locked_orientation(label, implied.get(index))
        if wanted:
            hits = [hit for hit in hits if hit["chain"]["orientation"] == wanted]
        if not label["sides"] and wanted:
            cx, cy = label["cx"], label["cy"]
            near_x = cx <= 0.14 * width + 48 or cx >= 0.86 * width - 48
            near_y = cy <= 0.14 * height + 48 or cy >= 0.86 * height - 48
            if wanted == "vertical" and not near_y:
                hits = []
            if wanted == "horizontal" and not near_x:
                hits = []
        outer = _outer_bubble(label, extremes)
        if not (wanted and outer):
            hits = [hit for hit in hits if _near_chain_end(label, hit["chain"])]
        hits.sort(key=lambda item: item["distance"])
        pending.append((label, hits))
    claimed = set()
    chosen = {}
    order = sorted(
        (index for index, (_, hits) in enumerate(pending) if hits),
        key=lambda index: (
            pending[index][1][0]["distance"],
            0 if pending[index][0]["sides"] else 1,
            index,
        ),
    )
    for index in order:
        label, hits = pending[index]
        for hit in hits:
            key = _claim_key(label, hit["chain"])
            if key in claimed:
                continue
            claimed.add(key)
            chosen[index] = hit
            break
    grids = []
    for index, (label, hits) in enumerate(pending):
        page = int(label["pdf_page"])
        hit = chosen.get(index)
        if hits and hit is None and (label["sides"] or implied.get(index)):
            status, orientation, line, confidence = "review_required", "unknown", None, 0.35
            evidence = ["a nearer label already uses the aligned grid line"]
        elif hit is not None:
            line = hit["chain"]
            other_axis = [
                item for item in hits
                if item["chain"]["orientation"] != line["orientation"]
                and item["distance"] <= hit["distance"] + 8
            ]
            if other_axis:
                status, orientation, line, confidence = "review_required", "unknown", None, 0.35
                evidence = ["this label box is aligned with both a horizontal and a vertical line"]
            else:
                status, orientation, confidence = "confirmed", line["orientation"], 0.8
                evidence = _confirm_evidence(label, line, hit["how"])
        elif label["sides"]:
            status, orientation, line, confidence = "candidate", "unknown", None, 0.3
            evidence = ["printed in the sheet margin; no supported grid line is aligned with it"]
        else:
            rejected.append({
                "text": label["text"], "pdf_page": page, "sheet_id": label["sheet_id"],
                "bbox": label["bbox"], "reason": "no_grid_line",
            })
            continue
        grids.append(_grid_record(label, page, status, orientation, line, confidence, evidence))
    for index, (label, hits) in enumerate(pending):
        if chosen.get(index) is not None or not hits or not label["sides"]:
            continue
        for hit in hits:
            line = hit["chain"]
            if not _near_chain_end(label, line):
                continue
            same = [
                other for other in grids
                if other["status"] == "confirmed"
                and other["label"] == label["text"]
                and other["pdf_page"] == label["pdf_page"]
                and other.get("line")
                and other["line"]["orientation"] == line["orientation"]
                and abs(other["line"]["axis"] - line["axis"]) <= 3
            ]
            if not same:
                continue
            if any(abs(other["bbox"][0] - label["bbox"][0]) < 30 and abs(other["bbox"][1] - label["bbox"][1]) < 30 for other in same):
                continue
            grids.append(_grid_record(
                label, int(label["pdf_page"]), "confirmed", line["orientation"], line, 0.75,
                _confirm_evidence(label, line, hit["how"]) + ["same label printed at the other end of this axis"],
            ))
            break
    return grids


def _grid_record(label, page, status, orientation, line, confidence, evidence):
    return {
        "grid_id": f"{label['text']}@p{page}@{orientation}",
        "label": label["text"],
        "axis_type": _axis_type(label["text"]),
        "pdf_page": page,
        "sheet_id": label["sheet_id"],
        "view_id": None,
        "bbox": label["bbox"],
        "orientation": orientation,
        "line_bbox": None if line is None else _line_box(line),
        "line": None if line is None else {
            "orientation": line["orientation"], "axis": round(line["axis"], 1),
            "start": round(line["start"], 1), "end": round(line["end"], 1),
            "covered": round(float(line.get("covered") or line["length"]), 1),
            "segment_count": int(line.get("segment_count") or 1),
            "max_gap": round(float(line.get("max_gap") or 0), 1),
            "fragmented": float(line["length"]) < 360,
        },
        "source_text": label["text"],
        "evidence": evidence,
        "status": status,
        "confidence": confidence,
    }
def assemble_grids(
    document: Dict[str, Any],
    labels: Sequence[dict],
    rejections: Sequence[dict],
    *,
    multi_view_pages: Sequence[int],
    meta: Dict[int, dict],
    marks: Sequence[dict],
) -> Dict[str, Any]:
    pages = sorted({int(label["pdf_page"]) for label in labels})
    chains = _page_chains(document, pages, meta) if pages else {}
    rejected = list(rejections)
    multi = set(multi_view_pages)
    grids = _assign_labels(labels, chains, meta, rejected)
    intersections: List[dict] = []
    allocations: List[dict] = []
    for page in pages:
        page_grids = [grid for grid in grids if grid["pdf_page"] == page]
        page_intersections = _intersections(page_grids, page in multi)
        intersections.extend(page_intersections)
        allocations.extend(_allocate(
            [mark for mark in marks if mark["pdf_page"] == page],
            page_intersections,
            page in multi,
        ))
    if multi:
        for allocation in allocations:
            if allocation["pdf_page"] in multi and allocation["allocation_status"] == "confirmed":
                allocation["allocation_status"] = "review_required"
                allocation["confidence"] = 0.4
    confirmed = [grid for grid in grids if grid["status"] == "confirmed"]
    candidates = [grid for grid in grids if grid["status"] != "confirmed"]
    stored = confirmed + candidates[:80]
    diagnostics = {
        "grid_label_candidates": len(labels),
        "confirmed_grid_labels": len(confirmed),
        "candidate_grid_labels": sum(1 for grid in grids if grid["status"] == "candidate"),
        "review_grid_labels": sum(1 for grid in grids if grid["status"] == "review_required"),
        "grid_lines_detected": len(confirmed),
        "grid_intersections": len(intersections),
        "objects_allocated": sum(1 for item in allocations if item["allocation_status"] in {"confirmed", "candidate"}),
        "objects_unresolved": sum(1 for item in allocations if item["allocation_status"] == "unresolved"),
        "objects_ambiguous": sum(1 for item in allocations if item["allocation_status"] == "review_required"),
        "false_positive_rejections": len(rejected),
        "logical_axes": sum(
            1 for page_chains in chains.values() for chain in page_chains
            if (chain.get("linked_runs") or 1) > 1
        ),
        "fragmented_axes_recovered": sum(
            1 for grid in confirmed if (grid.get("line") or {}).get("fragmented")
        ),
    }
    return {
        "grids": stored,
        "grid_intersections": intersections,
        "grid_allocations": allocations,
        "grid_diagnostics": diagnostics,
        "grid_rejections": rejected[:40],
    }


def _line_box(line: dict) -> List[float]:
    if line["orientation"] == "horizontal":
        return [round(line["start"], 1), round(line["axis"] - 1, 1), round(line["end"], 1), round(line["axis"] + 1, 1)]
    return [round(line["axis"] - 1, 1), round(line["start"], 1), round(line["axis"] + 1, 1), round(line["end"], 1)]
