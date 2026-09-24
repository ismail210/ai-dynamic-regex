"""Build the reviewer annotation package for column-schedule matrices.

Every record is a PROPOSAL prefilled from existing PDF word coordinates and
is written with independent extraction and physical review statuses. Nothing
here is gold until a human approves it. Defaults are conservative: lifecycle
only when printed, physical interpretation unknown, ``count_candidate =
false``, and no inferred quantity.

Usage (from ``backend/``)::

    ESTIMA3D_PROJECT_RULE_ROOT=<dir with the project folders> \
        python scripts/build_column_schedule_gold_package.py --out ../docs/project_rule_phase2/gold_annotation

Rendered page images go to ``<out>/images`` (git-ignored: they are copies of
private drawings).
"""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_BACKEND = _Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.engineering import schedule_grid as sg
from services.engineering.feet_inch_filter import FEET_INCH_SEGMENT_RE
from services.family_codes import MODERN_FAMILY_ALTERNATION
from services.exact_section_predictor import catalog_valid_exact_section
from services.pdf_parser import extract_document_structure

PACKAGE_VERSION = "2.0"
ROOT_ENV = "ESTIMA3D_PROJECT_RULE_ROOT"
REVIEW_STATES = (
    "PENDING_REVIEW",
    "APPROVED",
    "CORRECTED",
    "REJECTED",
    "UNSURE",
)

# Development pages (gold) and exclusion examples. Ketcham / Sidwell are
# held out and deliberately absent.
PAGES = [
    {"project_id": "Burrville", "document_id": "REAL-Burrville", "path": "Burrville/Burrville ES - ST.pdf",
     "page": 28, "role": "development", "template_family": "PerkinsEastman-Yun-S501"},
    {"project_id": "GCDC", "document_id": "REAL-GCDC", "path": "GCDC Building/GCDC Building 4 - ST1.pdf",
     "page": 77, "role": "development", "template_family": "Gensler-IMEG-S05"},
    {"project_id": "Springhill", "document_id": "REAL-Springhill", "path": "Springhill ES/ST - Springhill Lake.pdf",
     "page": 26, "role": "development", "template_family": "PerkinsEastman-Yun-S501"},
    {"project_id": "H5 Herndon", "document_id": "REAL-H5", "path": "H5 Herndon/ST.pdf",
     "page": 7, "role": "exclusion", "template_family": "VSW"},
    {"project_id": "H5 Herndon", "document_id": "REAL-H5", "path": "H5 Herndon/ST.pdf",
     "page": 8, "role": "exclusion", "template_family": "VSW"},
    {"project_id": "H5 Herndon", "document_id": "REAL-H5", "path": "H5 Herndon/ST.pdf",
     "page": 23, "role": "exclusion", "template_family": "VSW"},
]
HELD_OUT = ["Ketcham", "Sidwell"]

_SHEET_RE = re.compile(r"^S-?\d{2,3}(?:\.\d+)?(?:_\d+)?$")
_ROTATED = 45.0
# Rotated text shaped like a rolled section (loads "190k", "PL ..." callouts
# and detail references are not section cells). Catalog validity is checked
# separately, so a shaped-but-invalid label is still proposed and flagged.
_SECTION_SHAPED_RE = re.compile(rf"^(?:{MODERN_FAMILY_ALTERNATION})\d", re.IGNORECASE)

FIELDS = [
    "record_id", "project_id", "document_id", "page_number", "sheet_id", "schedule_id",
    "schedule_title_raw", "schedule_class", "region_bbox", "location_or_grid_raw",
    "location_or_grid_normalized", "level_raw", "level_normalized", "raw_cell_text",
    "canonical_section", "catalog_valid", "member_role", "lifecycle_status",
    "physical_semantics", "member_extent", "continuation_inheritance",
    "physical_segment_count", "plan_corroboration_status", "explicit_quantity",
    "count_candidate", "exclusion_reason", "source_cell_bbox", "header_path",
    "proposal_method", "extraction_review_status", "physical_review_status",
    "reviewer_notes",
]


def _text(words) -> str:
    return sg._text(sorted(words, key=lambda w: w["bbox"][0])).strip()


def _compact(words) -> str:
    return re.sub(r"\s+", "", sg._text(words)).upper()


def _sheet_id(words) -> str:
    candidates = [w for w in words if _SHEET_RE.match(str(w.get("text") or ""))]
    if not candidates:
        return ""
    return str(max(candidates, key=lambda w: float(w.get("font_size") or 0))["text"])


def _base_record(page: Dict[str, Any], sheet_id: str) -> Dict[str, Any]:
    return {
        "project_id": page["project_id"],
        "document_id": page["document_id"],
        "page_number": page["page"],
        "sheet_id": sheet_id,
        "catalog_valid": False,
        "canonical_section": None,
        "lifecycle_status": "unknown",
        "physical_semantics": "unknown",
        "member_extent": None,
        "continuation_inheritance": "unknown",
        "physical_segment_count": None,
        "plan_corroboration_status": "unknown",
        "explicit_quantity": None,
        "count_candidate": False,
        "exclusion_reason": None,
        "extraction_review_status": "PENDING_REVIEW",
        "physical_review_status": "PENDING_REVIEW",
        "reviewer_notes": "",
    }


# --------------------------------------------------------------------------
# Level x location matrices (development pages)
# --------------------------------------------------------------------------


def _matrix_blocks(words: List[dict]) -> List[Dict[str, Any]]:
    """One block per ``Column Locations`` row label (stacked, one-row, or
    split into fragments such as ``Col umn Locati ons``)."""

    rows = sg._cluster_rows([w for w in words if abs(float(w.get("rotation") or 0)) < _ROTATED])
    blocks = []
    for index, row in enumerate(rows):
        ordered = sorted(row["words"], key=lambda w: w["bbox"][0])
        for start, first in enumerate(ordered):
            if not str(first.get("text") or "").upper().startswith("COL"):
                continue
            head = [w for w in ordered[start:] if w["bbox"][0] - first["bbox"][0] < 80]
            stacked = [
                w for r in rows[index + 1:index + 4] for w in r["words"]
                if abs(w["bbox"][0] - first["bbox"][0]) < 3 and w["bbox"][1] - first["bbox"][3] < 12
            ]
            # Compacted text: GCDC splits glyphs ("Col umn Locati ons"), which
            # legend_profile._COLUMN_LOCATIONS_RE does not tolerate.
            if _compact(head).startswith("COLUMNLOCATIONS"):
                bottom = max(w["bbox"][3] for w in head)
            elif _compact(head[:1]) == "COLUMN" and _compact(stacked).startswith("LOCATIONS"):
                bottom = max(w["bbox"][3] for w in stacked)
            else:
                continue
            blocks.append({"label_x": first["bbox"][0], "cl_y": row["y"], "cl_bottom": bottom})
            break
    return sorted(blocks, key=lambda b: b["cl_y"])


def _levels(words, label_x, label_right, top, bottom) -> List[Dict[str, Any]]:
    """Level datums from the left label column: name rows, then an elevation row."""

    band = [
        w for w in words
        if label_x - 15 <= w["bbox"][0] < label_right and top < w["bbox"][1] < bottom
        and abs(float(w.get("rotation") or 0)) < _ROTATED
    ]
    levels, name_rows = [], []
    for row in sg._cluster_rows(band):
        text = _text(row["words"])
        if FEET_INCH_SEGMENT_RE.fullmatch(text):
            levels.append({
                "name": " ".join(name_rows).strip(),
                "elevation": text,
                "datum_y": row["y"] - 3.0,
            })
            name_rows = []
        else:
            name_rows.append(text)
    return levels


def _vertical_lines(pdf_path: Path, page_number: int) -> List[tuple]:
    """``(x, y0, y1)`` of every vertical ruling segment on the page."""

    import fitz

    lines = []
    with fitz.open(str(pdf_path)) as doc:
        for drawing in doc[page_number - 1].get_drawings():
            for item in drawing["items"]:
                if item[0] == "l" and abs(item[1].x - item[2].x) < 0.5:
                    lines.append((item[1].x, min(item[1].y, item[2].y), max(item[1].y, item[2].y)))
                elif item[0] == "re":
                    rect = item[1]
                    lines += [(rect.x0, rect.y0, rect.y1), (rect.x1, rect.y0, rect.y1)]
    return lines


def _strips(vlines, block) -> List[tuple]:
    """Column strips: consecutive vertical rulings that cross the location row."""

    y = (block["cl_y"] + block["cl_bottom"]) / 2
    xs = sorted(x for x, y0, y1 in vlines if y0 <= y <= y1 and x > block["label_x"])
    merged: List[float] = []
    for x in xs:
        if not merged or x - merged[-1] > 3.0:
            merged.append(x)
    strips = [(a, b) for a, b in zip(merged, merged[1:]) if b - a >= 20]
    if not strips:
        return []
    # Keep the table's regular column pitch; drops the label columns and any
    # title-block cell that happens to share the row.
    pitch = sorted(b - a for a, b in strips)[len(strips) // 2]
    return [(a, b) for a, b in strips if abs((b - a) - pitch) <= 0.25 * pitch]


def _join_fragments(words) -> str:
    """Join a strip's words: glyph fragments (gap < 1.5pt) without a space."""

    ordered = sorted(words, key=lambda w: w["bbox"][0])
    text = ""
    for index, word in enumerate(ordered):
        gap = word["bbox"][0] - ordered[index - 1]["bbox"][2] if index else 0
        text += ("" if index == 0 or gap < 1.5 else " ") + str(word.get("text") or "")
    return text.strip()


def _locations(words, block, strips) -> List[Dict[str, Any]]:
    row_words = [
        w for w in words
        if block["cl_y"] - 2 <= w["bbox"][1] <= block["cl_bottom"] + 14
        and abs(float(w.get("rotation") or 0)) < _ROTATED
    ]
    out = []
    for left, right in strips:
        inside = [w for w in row_words if left <= (w["bbox"][0] + w["bbox"][2]) / 2 < right]
        out.append({
            "raw": _join_fragments(inside),
            "bbox": sg._union_bbox(inside) or [left, block["cl_y"], right, block["cl_bottom"]],
            "strip": (left, right),
        })
    return out


def _interval(levels, y) -> str:
    ordered = sorted(levels, key=lambda lv: lv["datum_y"])  # top of page first
    above = [lv for lv in ordered if lv["datum_y"] <= y]
    below = [lv for lv in ordered if lv["datum_y"] > y]
    fmt = lambda lv: f"{lv['name']} ({lv['elevation']})"  # noqa: E731
    if above and below:
        return f"{fmt(below[0])} -> {fmt(above[-1])}"
    if below:
        return f"above {fmt(below[0])}"
    return f"below {fmt(above[-1])}" if above else ""


def _normalize_level(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.upper()).strip()


def _normalize_location(raw: str) -> str:
    return re.sub(r"\s+", "", raw.upper())


def _schedule_title(words, block_box) -> str:
    rows = sg._cluster_rows([w for w in words if abs(float(w.get("rotation") or 0)) < _ROTATED])
    best = None
    for row in rows:
        text = _text(row["words"])
        upper = text.upper()
        if "SCHEDULE" not in upper or "NOTES" in upper:
            continue
        box = sg._union_bbox(row["words"])
        dy = min(abs(box[1] - block_box[3]), abs(box[3] - block_box[1]))
        if best is None or dy < best[0]:
            best = (dy, text)
    return best[1] if best else ""


def matrix_records(page: Dict[str, Any], words: List[dict], sheet_id: str, vlines: List[tuple]) -> tuple:
    records, overlays = [], []
    previous_bottom = 0.0
    for number, block in enumerate(_matrix_blocks(words), start=1):
        # Location strips with any text; the label column and the mirrored
        # right label column carry no location text in the location row.
        locations = [loc for loc in _locations(words, block, _strips(vlines, block)) if loc["raw"]]
        if not locations:
            continue
        label_right = locations[0]["strip"][0]
        levels = _levels(words, block["label_x"], label_right, previous_bottom, block["cl_y"])
        previous_bottom = block["cl_bottom"] + 20
        if not levels:
            continue
        top = min(lv["datum_y"] for lv in levels) - 60
        bottom = max(lv["datum_y"] for lv in levels)
        right = locations[-1]["strip"][1]
        labels = [
            w for w in words
            if abs(float(w.get("rotation") or 0)) >= _ROTATED
            and _SECTION_SHAPED_RE.match(str(w.get("text") or ""))
            and top <= (w["bbox"][1] + w["bbox"][3]) / 2 <= bottom
            and label_right <= (w["bbox"][0] + w["bbox"][2]) / 2 < right
        ]
        region = [block["label_x"] - 6, top - 10, right + 4, block["cl_bottom"] + 20]
        title = _schedule_title(words, region)
        schedule_id = f"{page['document_id']}-p{page['page']}-M{number}"
        by_strip: Dict[tuple, List[dict]] = {loc["strip"]: [] for loc in locations}
        unassigned = []
        for label in labels:
            cx = (label["bbox"][0] + label["bbox"][2]) / 2
            strip = next((s for s in by_strip if s[0] <= cx < s[1]), None)
            (by_strip[strip] if strip else unassigned).append(label)
        common = {
            **_base_record(page, sheet_id),
            "schedule_id": schedule_id,
            "schedule_title_raw": title,
            "schedule_class": "level_location_matrix",
            "region_bbox": [round(v, 1) for v in region],
            "member_role": "column",
        }
        def cell(location: str, label: Optional[dict], bbox, method: str) -> Dict[str, Any]:
            raw = str(label["text"]) if label else ""
            level_raw = _interval(levels, (label["bbox"][1] + label["bbox"][3]) / 2) if label else ""
            section = catalog_valid_exact_section(raw) if raw else None
            if not label:
                reason = "no_section_label_found"
            elif not location:
                reason = "location_not_assigned"
            else:
                reason = None if section else "section_not_catalog_valid"
            return {
                **common,
                "location_or_grid_raw": location,
                "location_or_grid_normalized": _normalize_location(location),
                "level_raw": level_raw,
                "level_normalized": _normalize_level(level_raw),
                "raw_cell_text": raw,
                "canonical_section": section,
                "catalog_valid": bool(section),
                "exclusion_reason": reason,
                "source_cell_bbox": [round(v, 1) for v in bbox],
                "header_path": [title, f"Column Locations: {location or '?'}", f"Level interval: {level_raw or '(none found)'}"],
                "proposal_method": method,
            }

        for loc in locations:
            cell_labels = sorted(by_strip[loc["strip"]], key=lambda w: w["bbox"][1])
            if not cell_labels:
                records.append(cell(loc["raw"], None, loc["bbox"], "strip_without_label"))
            for label in cell_labels:
                records.append(cell(loc["raw"], label, label["bbox"], "rotated_label_in_ruled_strip_between_level_datums"))
        for label in unassigned:
            records.append(cell("", label, label["bbox"], "rotated_label_outside_ruled_strips"))
        overlays.append({"schedule_id": schedule_id, "region": region})
    return records, overlays


# --------------------------------------------------------------------------
# H5 exclusion examples (existing / reinforcing)
# --------------------------------------------------------------------------


def exclusion_records(page: Dict[str, Any], words: List[dict], sheet_id: str) -> tuple:
    evidence = sg.build_schedule_evidence(words, discovery="widened")
    regions = {r["region_id"]: r for r in evidence["regions"]}
    records, overlays = [], []
    for record in evidence["records"]:
        region = regions[record["region_id"]]
        lifecycle = record["lifecycle_status"]
        if lifecycle == "reinforcing":
            schedule_class, reason = "reinforcement_schedule", "reinforcement_of_host_member"
        elif lifecycle == "existing":
            schedule_class, reason = "existing_member_schedule", "existing_condition"
        else:
            schedule_class, reason = "unknown", "not_a_new_work_matrix"
        records.append({
            **_base_record(page, sheet_id),
            "schedule_id": f"{page['document_id']}-p{page['page']}-{record['region_id']}",
            "schedule_title_raw": "",
            "schedule_class": schedule_class,
            "region_bbox": region["region_bbox"],
            "location_or_grid_raw": record["mark_raw"],
            "location_or_grid_normalized": record["mark_normalized"],
            "level_raw": "",
            "level_normalized": "",
            "raw_cell_text": record["size_text_raw"],
            "canonical_section": record["primary_section"],
            "catalog_valid": bool(record["primary_section"]),
            "member_role": "column",
            "lifecycle_status": lifecycle,
            "physical_semantics": "definition_only",
            "exclusion_reason": reason,
            "source_cell_bbox": record["row_bbox"],
            "header_path": [f"{region['kind']} schedule", f"MARK {record['mark_raw']}"],
            "proposal_method": "schedule_evidence_widened",
        })
    for region in evidence["regions"]:
        overlays.append({"schedule_id": region["region_id"], "region": region["region_bbox"]})
    return records, overlays


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------


def render(pdf_path: Path, page_number: int, records, overlays, image_dir: Path, stem: str) -> List[str]:
    import fitz

    image_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with fitz.open(str(pdf_path)) as doc:
        page = doc[page_number - 1]
        full = image_dir / f"{stem}_page.png"
        page.get_pixmap(dpi=100).save(str(full))
        written.append(full.name)
        for index, record in enumerate(records, start=1):
            box = record.get("source_cell_bbox")
            if not box:
                continue
            rect = fitz.Rect(*box)
            page.draw_rect(rect, color=(0.85, 0.1, 0.1), width=0.8)
            page.insert_text((rect.x0, rect.y0 - 1), str(index), fontsize=6, color=(0.85, 0.1, 0.1))
        for overlay in overlays:
            region = overlay["region"]
            if not region:
                continue
            clip = fitz.Rect(region[0] - 40, region[1] - 60, region[2] + 40, region[3] + 60) & page.rect
            crop = image_dir / f"{stem}_{overlay['schedule_id'].split('-')[-1]}_crop.png"
            page.get_pixmap(dpi=200, clip=clip).save(str(crop))
            written.append(crop.name)
    return written


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def build(out_dir: Path) -> Dict[str, Any]:
    root = os.environ.get(ROOT_ENV, "")
    if not root:
        raise SystemExit(f"set {ROOT_ENV} to the folder holding the project PDFs")
    out_dir.mkdir(parents=True, exist_ok=True)
    image_dir = out_dir / "images"
    cache: Dict[str, dict] = {}
    all_records: List[Dict[str, Any]] = []
    manifest_pages = []
    for page in PAGES:
        pdf_path = Path(root) / page["path"]
        if page["path"] not in cache:
            cache[page["path"]] = extract_document_structure(str(pdf_path))
        words = [w for w in cache[page["path"]]["words"] if w.get("page_number") == page["page"]]
        sheet_id = _sheet_id(words)
        if page["role"] == "development":
            records, overlays = matrix_records(page, words, sheet_id, _vertical_lines(pdf_path, page["page"]))
        else:
            records, overlays = exclusion_records(page, words, sheet_id)
        stem = f"{page['document_id']}_p{page['page']}"
        for index, record in enumerate(records, start=1):
            record["record_id"] = f"{stem}-{index:03d}"
        images = render(pdf_path, page["page"], records, overlays, image_dir, stem)
        (out_dir / f"{stem}_prefill.jsonl").write_text(
            "".join(json.dumps({k: r.get(k) for k in FIELDS}) + "\n" for r in records), encoding="utf-8"
        )
        all_records.extend(records)
        manifest_pages.append({
            **{k: page[k] for k in ("project_id", "document_id", "page", "role", "template_family")},
            "sheet_id": sheet_id,
            "records": len(records),
            "schedules": [o["schedule_id"] for o in overlays],
            "prefill_file": f"{stem}_prefill.jsonl",
            "images": images,
        })
    with (out_dir / "annotations_prefill.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for record in all_records:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in
                             ((k, record.get(k)) for k in FIELDS)})
    manifest = {
        "package_version": PACKAGE_VERSION,
        "status": "PENDING_REVIEW",
        "review_states": list(REVIEW_STATES),
        "review_workflow": {
            "extraction": {
                "status_field": "extraction_review_status",
                "approved_states": ["APPROVED", "CORRECTED"],
                "scope": [
                    "schedule_region",
                    "schedule_title_and_type",
                    "location",
                    "level_interval",
                    "raw_cell",
                    "canonical_section",
                    "catalog_validity",
                    "lifecycle",
                ],
            },
            "physical": {
                "status_field": "physical_review_status",
                "approved_states": ["APPROVED", "CORRECTED"],
                "scope": [
                    "member_extent",
                    "continuation_or_inheritance",
                    "physical_segment_count",
                    "plan_corroboration",
                ],
            },
            "matrix_parser_gate": "All development records require extraction_review_status APPROVED or CORRECTED; physical review may remain UNSURE.",
        },
        "review_summary": {
            "records": len(all_records),
            "extraction": {"PENDING_REVIEW": len(all_records)},
            "physical": {"PENDING_REVIEW": len(all_records)},
            "matrix_parser_unblocked": False,
        },
        "note": "Prefilled proposals only. Extraction and physical interpretation are independently unapproved until reviewed by a human.",
        "pdf_root_env": ROOT_ENV,
        "held_out_projects": HELD_OUT,
        "pages": manifest_pages,
    }
    (out_dir / "package_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the column-schedule reviewer package.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = build(args.out)
    for page in manifest["pages"]:
        print(f"{page['document_id']} p{page['page']} ({page['role']}): {page['records']} records, "
              f"schedules {page['schedules']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
