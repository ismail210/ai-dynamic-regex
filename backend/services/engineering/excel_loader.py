"""
Engineering Excel Loader
========================

Loads engineering takeoff / schedule Excel files into structured JSON.

Supports:
1. Custom project takeoff sheets (flexible column mapping)
2. Enrichment from the existing AISC shapes database (via database_loader)

Output JSON::

    {
      "source_file": "...",
      "items": [ {beam/column metadata...}, ... ],
      "summary": { counts, totals },
      "column_map": {...}
    }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config import settings


COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "mark": ("mark", "id", "member", "piece", "tag", "label"),
    "shape": ("shape", "section", "size", "designation", "aisc_manual_label", "type_size"),
    "type": ("type", "member_type", "category", "kind"),
    "count": ("count", "qty", "quantity", "no", "nos", "number"),
    "length": ("length", "len", "l", "span"),
    "width": ("width", "w", "bf"),
    "depth": ("depth", "d", "height", "h"),
    "weight": ("weight", "wt", "weight_per_ft", "w_ft", "mass"),
    "material": ("material", "grade", "steel_grade", "spec"),
    "length_total": ("total_length", "length_total", "sum_length"),
}


def _norm_col(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _map_columns(columns: List[str]) -> Dict[str, str]:
    """Map normalized dataframe columns to canonical field names."""

    normalized = {_norm_col(c): c for c in columns}
    mapping: Dict[str, str] = {}
    used = set()
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized and normalized[alias] not in used:
                mapping[canonical] = normalized[alias]
                used.add(normalized[alias])
                break
    return mapping


def _to_float(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(\.\d+)?", text)
    return float(match.group(0)) if match else None


def _to_int(value: Any) -> Optional[int]:
    number = _to_float(value)
    if number is None:
        return None
    return int(round(number))


def _infer_member_type(shape: str, explicit: Optional[str] = None) -> str:
    if explicit:
        exp = str(explicit).strip().lower()
        if "col" in exp:
            return "column"
        if "beam" in exp or "girder" in exp:
            return "beam"
        if "brace" in exp:
            return "brace"
        if "plate" in exp or exp.startswith("pl"):
            return "plate"
        if "bolt" in exp:
            return "bolt"
        return exp
    s = (shape or "").upper().replace(" ", "")
    if s.startswith("W") or s.startswith("HSS") or s.startswith("C") or s.startswith("MC"):
        return "beam"
    if s.startswith("PIPE") or s.startswith("HSS"):
        return "column"
    if s.startswith("PL"):
        return "plate"
    if s.startswith("A") and s[1:].isdigit():
        return "bolt"
    return "unknown"


def load_aisc_catalog(limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Load the project AISC Excel into structured JSON (engineering metadata).

    Extends the existing database_loader without modifying its public API.
    """

    frame = pd.read_excel(settings.database_file, sheet_name=settings.database_sheet)
    items: List[dict] = []
    for _, row in frame.iterrows():
        shape = str(row.get("AISC_Manual_Label", "")).strip()
        if not shape or shape.lower() == "nan":
            continue
        item = {
            "mark": shape,
            "shape": shape.upper().replace(" ", ""),
            "type": str(row.get("Type", "")).strip(),
            "member_type": _infer_member_type(shape, str(row.get("Type", ""))),
            "count": 1,
            "length": None,
            "width": _to_float(row.get("bf") if "bf" in frame.columns else None),
            "depth": _to_float(row.get("d") if "d" in frame.columns else None),
            "weight": _to_float(row.get("W") if "W" in frame.columns else None),
            "material": "A992/A500" if str(row.get("Type", "")).upper() in {"W", "HSS"} else None,
            "metadata": {
                col: (None if pd.isna(row[col]) else row[col])
                for col in frame.columns
                if col not in {"AISC_Manual_Label", "Type"}
            },
            "source": "aisc_catalog",
        }
        # Clean metadata for JSON
        clean_meta = {}
        for k, v in item["metadata"].items():
            if isinstance(v, (int, float, str, bool)) or v is None:
                clean_meta[str(k)] = v if not (isinstance(v, float) and pd.isna(v)) else None
            else:
                clean_meta[str(k)] = str(v)
        item["metadata"] = clean_meta
        items.append(item)
        if limit is not None and len(items) >= limit:
            break

    return {
        "source_file": settings.database_file.name,
        "source_kind": "aisc_catalog",
        "item_count": len(items),
        "items": items,
        "summary": _summarize_items(items),
        "column_map": {"shape": "AISC_Manual_Label", "type": "Type", "weight": "W"},
    }


def load_engineering_excel(path: str | Path, sheet_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Parse a project engineering / takeoff Excel into structured JSON.
    """

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Excel file not found: {file_path}")

    frame = pd.read_excel(file_path, sheet_name=sheet_name or 0)
    if isinstance(frame, dict):
        # Multiple sheets — take the first
        sheet_name = next(iter(frame))
        frame = frame[sheet_name]

    column_map = _map_columns([str(c) for c in frame.columns])
    items: List[dict] = []

    for idx, row in frame.iterrows():
        shape_col = column_map.get("shape")
        mark_col = column_map.get("mark")
        shape = str(row[shape_col]).strip() if shape_col else ""
        mark = str(row[mark_col]).strip() if mark_col else shape
        if (not shape or shape.lower() == "nan") and (not mark or mark.lower() == "nan"):
            continue
        if not shape or shape.lower() == "nan":
            shape = mark
        type_col = column_map.get("type")
        explicit_type = str(row[type_col]).strip() if type_col else None
        item = {
            "row_index": int(idx) if isinstance(idx, (int,)) else idx,
            "mark": mark if mark.lower() != "nan" else shape,
            "shape": shape.upper().replace(" ", ""),
            "type": explicit_type,
            "member_type": _infer_member_type(shape, explicit_type),
            "count": _to_int(row[column_map["count"]]) if "count" in column_map else 1,
            "length": _to_float(row[column_map["length"]]) if "length" in column_map else None,
            "width": _to_float(row[column_map["width"]]) if "width" in column_map else None,
            "depth": _to_float(row[column_map["depth"]]) if "depth" in column_map else None,
            "weight": _to_float(row[column_map["weight"]]) if "weight" in column_map else None,
            "material": (
                str(row[column_map["material"]]).strip()
                if "material" in column_map and not pd.isna(row[column_map["material"]])
                else None
            ),
            "length_total": _to_float(row[column_map["length_total"]]) if "length_total" in column_map else None,
            "source": "engineering_excel",
        }
        if item["count"] is None:
            item["count"] = 1
        items.append(item)

    return {
        "source_file": file_path.name,
        "source_kind": "engineering_excel",
        "sheet_name": sheet_name,
        "item_count": len(items),
        "items": items,
        "summary": _summarize_items(items),
        "column_map": column_map,
    }


def _summarize_items(items: List[dict]) -> Dict[str, Any]:
    by_type: Dict[str, int] = {}
    by_shape: Dict[str, int] = {}
    total_count = 0
    total_weight = 0.0
    total_length = 0.0
    for item in items:
        mt = item.get("member_type") or "unknown"
        shape = item.get("shape") or "UNKNOWN"
        count = int(item.get("count") or 1)
        by_type[mt] = by_type.get(mt, 0) + count
        by_shape[shape] = by_shape.get(shape, 0) + count
        total_count += count
        if item.get("weight") is not None:
            total_weight += float(item["weight"]) * count
        length = item.get("length_total")
        if length is None and item.get("length") is not None:
            length = float(item["length"]) * count
        if length is not None:
            total_length += float(length)
    return {
        "total_count": total_count,
        "unique_shapes": len(by_shape),
        "by_member_type": by_type,
        "by_shape": by_shape,
        "total_weight": round(total_weight, 3),
        "total_length": round(total_length, 3),
    }


def excel_to_json(path: str | Path, sheet_name: Optional[str] = None) -> Dict[str, Any]:
    """Public alias used by the API layer."""

    return load_engineering_excel(path, sheet_name=sheet_name)
