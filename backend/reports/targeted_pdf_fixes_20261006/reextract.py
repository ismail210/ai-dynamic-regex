"""Isolated re-extract for the 2026-10-06 targeted fixes. Writes only in this directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import fitz

from config import settings
from services.engineering.column_schedule import column_schedule_view
from services.engineering.column_trace import trace_column
from services.engineering.drawing_intelligence import _sheet_ids
from services.engineering.schedule_grid import attach_schedule_grid
from services.extraction_engine import EXTRACTION_VERSION
from services.pdf_parser import extract_document_structure

OUT = Path(__file__).resolve().parent
OLD = BACKEND / "reports" / "manual_pdf_validation_20261006"
PDFS = {
    "struct": BACKEND / "uploads" / "Struct.pdf",
    "springhill": BACKEND / "uploads" / "ST - Springhill Lake__f6ddc4a7e233.pdf",
    "brandywine": BACKEND / "uploads" / "Structural4__3aa51f661bdf.pdf",
    "burrville": BACKEND / "uploads" / "Burrville ES - ST.pdf",
}


def _row_brief(row: dict) -> dict:
    band = row.get("level_band") or {}
    return {
        "mark": row.get("mark"),
        "section": row.get("section"),
        "size_text": row.get("size_text"),
        "plate_text": row.get("plate_text"),
        "plate_notes": row.get("plate_notes"),
        "plate_status": row.get("plate_status"),
        "plate_role": row.get("plate_role"),
        "ordered_dimensions": (row.get("parsed_plate") or {}).get("ordered_dimensions"),
        "notes": (row.get("parsed_plate") or {}).get("notes"),
        "level": row.get("level"),
        "level_raw": band.get("raw"),
        "printed_elevation": band.get("printed_elevation"),
        "printed_name": band.get("printed_name"),
        "prefix_status": band.get("prefix_status"),
        "pairing": band.get("pairing"),
        "band_level": band.get("level"),
        "elevation_of": (band.get("elevation_of") or {}).get("level"),
        "name_of": (band.get("name_of") or {}).get("level"),
    }


def _summarize(document: dict) -> dict:
    grids = []
    for grid in document.get("schedule_grid") or []:
        grids.append({
            "page": grid.get("page"),
            "kind": grid.get("kind"),
            "source": grid.get("source"),
            "title": grid.get("title"),
            "rows": [_row_brief(row) for row in grid.get("rows") or []],
        })
    schedules = []
    for schedule in (document.get("column_schedules") or {}).get("schedules") or []:
        schedules.append({
            "id": schedule.get("id"),
            "title": schedule.get("title") or schedule.get("caption"),
            "level_lines": [
                {"name": line.get("name"), "elevation_text": line.get("elevation_text"), "y": line.get("y"), "block": line.get("block")}
                for line in schedule.get("level_lines") or []
            ],
        })
    return {
        "extraction_version": document.get("extraction_version"),
        "page_count": document.get("page_count"),
        "mark_map": document.get("schedule_mark_map") or {},
        "grids": grids,
        "schedules": schedules,
        "endpoint_status": _endpoint_counts(document.get("column_level_endpoints") or []),
    }


def _endpoint_counts(endpoints: list) -> dict:
    counts: dict = {}
    for item in endpoints:
        status = str(item.get("status") or "none")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _interesting_bands(summary: dict) -> list:
    wanted = ("LEVEL 1", "FIRST FLOOR", "UPPER LEVEL", "GROUND LEVEL")
    found = []
    for grid in summary["grids"]:
        for row in grid["rows"]:
            raw = str(row.get("level_raw") or "")
            if any(name in raw for name in wanted):
                found.append({"page": grid["page"], **row})
    return found


def _plates(summary: dict) -> list:
    rows = []
    for grid in summary["grids"]:
        for row in grid["rows"]:
            text = " ".join(str(row.get(key) or "") for key in ("plate_text", "size_text", "plate_notes"))
            mark = str(row.get("mark") or "")
            if mark.startswith(("BP", "CL", "MP")) or "x" in text.lower() or "*" in text:
                rows.append({"page": grid["page"], "kind": grid["kind"], "title": grid["title"], **row})
    return rows


def _render(pdf: Path, page_index: int, clip: tuple, name: str) -> None:
    document = fitz.open(pdf)
    page = document[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=fitz.Rect(*clip), alpha=False)
    pix.save(OUT / "renders" / name)
    document.close()


def main() -> None:
    flags = {
        "EXTRACTION_VERSION": EXTRACTION_VERSION,
        "schedule_grid_enabled": settings.schedule_grid_enabled,
        "schedule_ruled_tables_enabled": settings.schedule_ruled_tables_enabled,
        "schedule_mark_map_enabled": settings.schedule_mark_map_enabled,
        "schedule_mark_conflict_guard_enabled": settings.schedule_mark_conflict_guard_enabled,
        "schedule_evidence_shadow_enabled": settings.schedule_evidence_shadow_enabled,
    }
    (OUT / "run_config.json").write_text(json.dumps(flags, indent=2))
    for key, pdf in PDFS.items():
        print(f"extract {key}", flush=True)
        document = extract_document_structure(str(pdf))
        attach_schedule_grid(document, pdf_path=str(pdf))
        summary = _summarize(document)
        payload = {
            "key": key,
            "path": str(pdf),
            "bands": _interesting_bands(summary),
            "plates": _plates(summary),
            "mark_map": summary["mark_map"],
            "endpoint_status": summary["endpoint_status"],
            "schedule_level_lines": summary["schedules"],
            "grid_kinds": [
                {"page": grid["page"], "kind": grid["kind"], "source": grid["source"], "title": grid["title"], "rows": len(grid["rows"])}
                for grid in summary["grids"]
            ],
        }
        (OUT / f"extract_{key}.json").write_text(json.dumps(payload, indent=2))
        old_path = OLD / f"extract_{key}.json"
        if old_path.exists():
            old = json.loads(old_path.read_text())
            print(
                key,
                "mark_map",
                old.get("mark_map_sample"),
                "->",
                list(summary["mark_map"].items()),
                flush=True,
            )
        if key == "brandywine":
            view = column_schedule_view(document, _sheet_ids(document))
            chosen = None
            for entry in view.get("entries") or []:
                locations = entry.get("locations") or []
                if any(len(loc.get("grids") or []) == 2 for loc in locations):
                    chosen = entry
                    break
            trace_payload = {"chosen": None, "trace": None}
            if chosen:
                location = (chosen.get("locations") or [{}])[0].get("raw") or chosen.get("location_text")
                trace_payload["chosen"] = {
                    "location": location,
                    "page": chosen.get("page"),
                    "sheet": chosen.get("sheet"),
                    "sections": [s.get("designation") or s.get("printed") for s in chosen.get("sections") or []],
                }
                trace_payload["trace"] = trace_column(document, str(pdf), location)
            (OUT / "column_trace_brandywine.json").write_text(json.dumps(trace_payload, indent=2, default=str))
            print("trace", trace_payload["chosen"], (trace_payload["trace"] or {}).get("status"), flush=True)
        del document
    _render(PDFS["springhill"], 26, (490, 560, 900, 640), "springhill_p27_plate_cells.png")
    _render(PDFS["struct"], 1, (1980, 1080, 2580, 1360), "struct_p2_bearing_plate.png")
    _render(PDFS["struct"], 1, (1980, 1340, 2700, 1700), "struct_p2_icf_lintel.png")
    print("done", flush=True)


if __name__ == "__main__":
    main()
