"""Read-only digest of the current Drawing Summary for the engineering audit.

Writes profile_digest.json in this folder. Legend-profile and artifact caches
are redirected to /tmp so the repository training cache is not touched.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402

object.__setattr__(settings, "legend_profile_cache_dir", Path("/tmp/ds_audit_legend"))
object.__setattr__(settings, "engineering_artifacts_dir", Path("/tmp/ds_audit_art"))
settings.legend_profile_cache_dir.mkdir(parents=True, exist_ok=True)
settings.engineering_artifacts_dir.mkdir(parents=True, exist_ok=True)

from services.extraction_engine import extract_engineering_document  # noqa: E402

OUT = Path(__file__).resolve().parent / "profile_digest.json"
PROJECTS = {
    "burrville": BACKEND / "uploads" / "Burrville ES - ST.pdf",
    "osse": Path("/Users/hibareda/Desktop/Testing Projects/OSSE - ST.pdf"),
    "struct": BACKEND / "uploads" / "Struct.pdf",
    "brandywine": BACKEND / "uploads" / "Structural4__3aa51f661bdf.pdf",
}
CALLOUT = re.compile(r"\b(?:SEE|DETAIL|SECTION|TYP)\b|\b[A-Z]{1,2}\d{0,2}\s*/\s*S[\d.A-Z-]", re.I)
SHEETISH = re.compile(r"\bS-?\d{2,3}(?:\.\d{1,2})?[A-Z]{0,2}(?:-[A-Z0-9]{1,2})?\b", re.I)


def _trim_entry(entry: dict) -> dict:
    plate = entry.get("plate") or {}
    return {
        "mark": entry.get("mark"),
        "page": entry.get("page"),
        "sheet": entry.get("sheet"),
        "sections": [
            {"printed": s.get("printed"), "designation": s.get("designation")}
            for s in entry.get("sections") or []
        ],
        "plate_status": plate.get("status"),
        "plate_printed": plate.get("printed"),
        "plate_type": plate.get("type"),
        "plate_note": plate.get("note"),
        "locations": entry.get("listed_location_count"),
        "location_sample": [
            (loc.get("raw") or loc.get("text")) for loc in (entry.get("locations") or [])[:4]
            if isinstance(loc, dict)
        ],
        "material": (entry.get("material") or {}).get("material"),
        "material_status": (entry.get("material") or {}).get("status"),
        "extent_status": (entry.get("extent") or {}).get("status") if isinstance(entry.get("extent"), dict) else None,
    }


def _level(level: dict) -> dict:
    elevation = level.get("elevation") or {}
    return {
        "name": level.get("name"),
        "sheet": level.get("sheet"),
        "page": level.get("page"),
        "elevation": elevation.get("display") if isinstance(elevation, dict) else elevation,
        "conflict": level.get("conflict"),
        "surface": level.get("surface"),
        "also_titled": level.get("also_titled"),
        "matches": [
            {
                "sheet": m.get("sheet"),
                "page": m.get("page"),
                "plan": m.get("plan"),
                "association": m.get("association"),
                "comparison": m.get("comparison"),
                "qualifiers": m.get("plan_qualifiers"),
                "values": [
                    {"surface": v.get("surface"), "display": v.get("display"), "raw": v.get("raw")}
                    for v in (m.get("values") or [])[:4]
                ],
            }
            for m in (level.get("plan_matches") or [])[:8]
        ],
    }


def digest(name: str, path: Path) -> dict:
    document = extract_engineering_document(path)
    profile = document.get("legend_profile") or {}
    di = profile.get("drawing_intelligence") or {}
    index = di.get("sheet_index") or {}
    pages = []
    for record in index.get("pages") or []:
        revision = record.get("revision") or {}
        pages.append({
            "page": record.get("page"),
            "rotation": record.get("rotation"),
            "sheet_id": record.get("sheet_id"),
            "sheet_id_status": record.get("sheet_id_status"),
            "title": record.get("sheet_title"),
            "title_status": record.get("title_status"),
            "issue": record.get("issue"),
            "issue_date": record.get("issue_date"),
            "issue_status": record.get("issue_status"),
            "scale": record.get("scale"),
            "scale_status": record.get("scale_status"),
            "scale_candidates": [c.get("text") for c in record.get("scale_candidates") or []],
            "revision_status": revision.get("status"),
            "revision_rows": [
                [row.get("number"), row.get("description"), row.get("date")]
                for row in (revision.get("rows") or [])
            ],
        })
    categories = di.get("page_categories") or {}
    by_cat: dict[str, list] = {}
    for page, cat in categories.items():
        sheet = next((p for p in pages if str(p["page"]) == str(page)), {})
        by_cat.setdefault(cat, []).append({
            "page": int(page), "sheet_id": sheet.get("sheet_id"), "title": sheet.get("title"),
        })
    column = di.get("column_schedule") or {}
    entries = [_trim_entry(e) for e in column.get("entries") or []]
    definitions = di.get("definitions") or []
    def_counts = Counter((d.get("component"), d.get("status")) for d in definitions)
    levels = di.get("levels") or {}
    grids = document.get("schedule_grid") or []
    mark_map = {}
    # schedule mark map lives on the document after attach_schedule_grid
    raw_map = document.get("schedule_mark_map") or {}
    if isinstance(raw_map, dict):
        mark_map = {k: (v.get("section") if isinstance(v, dict) else v) for k, v in list(raw_map.items())[:40]}
    callouts = []
    for item in (document.get("callouts") or [])[:80]:
        callouts.append({"page": item.get("page_number"), "text": item.get("text")})
    ref_lines = Counter()
    for line in document.get("lines") or []:
        text = (line.get("text") or "").strip()
        if text and CALLOUT.search(text):
            ref_lines[text[:80]] += 1
    return {
        "pdf": str(path),
        "page_count": document.get("page_count"),
        "extraction_version": document.get("extraction_version"),
        "profile_status": profile.get("status"),
        "sheet_index_in_profile": bool(index),
        "sheet_index_layout": index.get("layout"),
        "sheets": pages,
        "categories": {k: v for k, v in sorted(by_cat.items())},
        "narrative": di.get("narrative"),
        "families": di.get("steel_system", {}).get("families"),
        "column_schedules": [
            {
                "name": s.get("name"), "pages": s.get("pages"), "sheets": s.get("sheets"),
                "material_group": s.get("material_group"), "entry_count": s.get("entry_count"),
                "layout": s.get("layout"),
            }
            for s in column.get("schedules") or []
        ],
        "column_entries": entries,
        "plate_count_checks": (column.get("plate_counts") or [])[:30],
        "definition_counts": {f"{a}|{b}": n for (a, b), n in def_counts.items()},
        "definition_samples": [
            {
                "mark": d.get("mark"), "designation": d.get("designation") or d.get("printed"),
                "component": d.get("component"), "status": d.get("status"),
                "page": d.get("page"), "schedule": d.get("schedule_title"),
            }
            for d in definitions[:40]
        ],
        "schedule_levels": [_level(level) for level in levels.get("schedule_levels") or []],
        "plan_elevation_count": len(levels.get("plan_elevations") or []),
        "plan_elevation_samples": [
            {
                "page": e.get("page"), "sheet": e.get("sheet"), "name": e.get("name"),
                "surface": e.get("surface"), "status": e.get("status"),
                "display": (e.get("value") or {}).get("display") if isinstance(e.get("value"), dict) else e.get("value"),
                "raw": (e.get("value") or {}).get("raw") if isinstance(e.get("value"), dict) else None,
            }
            for e in (levels.get("plan_elevations") or [])[:25]
        ],
        "location_offset_count": len(levels.get("location_offsets") or []),
        "location_offset_samples": [
            {"text": o.get("text"), "page": o.get("page"), "sheet": o.get("sheet")}
            for o in (levels.get("location_offsets") or [])[:15]
        ],
        "notation_count": len(levels.get("notations") or []),
        "notations": [
            {"sample": n.get("sample"), "meaning": n.get("meaning"), "sheet": n.get("sheet"), "scope": n.get("scope")}
            for n in (levels.get("notations") or [])[:12]
        ],
        "interpretation_rules": [
            {"kind": r.get("kind"), "text": (r.get("text") or r.get("source_text") or "")[:180], "sheet": r.get("sheet")}
            for r in (di.get("interpretation_rules") or [])[:20]
        ],
        "unresolved": [
            {"text": (u.get("text") or u.get("value") or u.get("printed") or "")[:160], "page": u.get("page"), "reason": u.get("reason") or u.get("status")}
            for u in (di.get("unresolved") or [])[:25]
        ],
        "unresolved_count": len(di.get("unresolved") or []),
        "scope_signals": [
            {"type": s.get("type"), "value": s.get("value"), "present": (s.get("detail") or {}).get("present")}
            for s in di.get("scope_signals") or []
        ],
        "existing_new": di.get("existing_new"),
        "uncertainties": [u.get("value") for u in di.get("uncertainties") or []],
        "structural_notes": [
            {"value": (n.get("value") or "")[:200], "pages": n.get("source_pages")}
            for n in (di.get("structural_notes") or [])[:8]
        ],
        "supporting_schedules": [
            {
                "title": s.get("title"), "kind": s.get("kind"), "page": s.get("page"),
                "sheet": s.get("sheet"), "printed_rows": s.get("printed_rows"),
                "shown": s.get("shown"), "unread": len(s.get("unread_rows") or []),
            }
            for s in di.get("supporting_schedules") or []
        ],
        "schedule_insights": [
            {"value": (s.get("value") or "")[:180], "page": (s.get("detail") or {}).get("page"), "kind": (s.get("detail") or {}).get("kind")}
            for s in di.get("schedule_insights") or []
        ],
        "typical": [
            {"value": t.get("value"), "present": (t.get("detail") or {}).get("present")}
            for t in di.get("typical_conditions") or []
        ],
        "mark_map_count": len(document.get("schedule_mark_map") or {}),
        "mark_map_sample": mark_map,
        "schedule_grid_kinds": Counter((g.get("kind"), g.get("title")) for g in grids),
        "callout_samples": callouts[:40],
        "callout_count": len(document.get("callouts") or []),
        "reference_line_top": ref_lines.most_common(20),
        "column_location_count": len(di.get("column_locations") or []),
    }


def main() -> None:
    payload = {}
    for name, path in PROJECTS.items():
        print(f"extract {name} {path}", flush=True)
        payload[name] = digest(name, path)
        # Counter is not JSON serializable
        payload[name]["schedule_grid_kinds"] = {
            f"{kind}|{title}": n for (kind, title), n in payload[name]["schedule_grid_kinds"].items()
        }
        print(f"  pages={payload[name]['page_count']} sheets={len(payload[name]['sheets'])} defs={payload[name]['definition_counts']}", flush=True)
        OUT.write_text(json.dumps(payload, indent=1))
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
