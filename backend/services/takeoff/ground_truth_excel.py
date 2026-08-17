"""
Ground-truth Excel parser for structural project estimate workbooks.

IMPORTANT
---------
Excel is used ONLY as ground truth during dataset creation and takeoff
validation — never as an inference input for production prediction.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from services.entity_taxonomy import classify_category


SCHEDULE_SHEETS = (
    "StructuralFramingSchedule",
    "StructuralColumnSchedule",
    "BasePlateSchedule",
    "StructuralPlateSchedule",
    "StructuralConnectionSchedule",
    "MomentConnectionSchedule",
    "StructuralBracingSchedule",
    "StructuralJoistSchedule",
)

# Rollup / summary sheets — only used when no detailed schedule row exists
# for the same shape. Their "count" column often holds total length (inches)
# rather than piece count, which produced misleading quantities like x1092.
SUMMARY_SHEETS = (
    "Steel Elements Summary",
    "Summary",
    "Count_per_Sheet",
)

SUMMARY_ROW_RE = re.compile(
    r"^(?:GRAND)?TOTAL\b|SUBTOTAL\b|^SUMMARY\b|^SUM\b|^COUNT\b|^TYPE\b",
    re.I,
)
# A single schedule row with more pieces than this is almost always a
# mis-mapped length/weight column, not a real member count.
MAX_SCHEDULE_ROW_COUNT = 200

SHAPE_RE = re.compile(
    r"^(W|WT|M|S|HP|C|MC|L|2L|HSS|PIPE|MT|ST)\d",
    re.I,
)
PLATE_HINT_RE = re.compile(r"plate|pl\d|baseplate|stiffener|connection", re.I)


def _norm_shape(value: Any) -> str:
    text = str(value or "").strip().upper().replace(" ", "")
    if not text or text in {"NAN", "NONE", "TYPE"}:
        return ""
    return text


def _is_summary_row(shape: str) -> bool:
    """True for GRANDTOTAL / TOTAL / SUBTOTAL rows, not real members."""

    if not shape:
        return True
    if SUMMARY_ROW_RE.match(shape):
        return True
    if shape.startswith("GRANDTOTAL"):
        return True
    return False


def _sanitize_quantity(
    count: int,
    *,
    length: Any,
    weight: Any,
    sheet_name: str,
) -> tuple[int, Any]:
    """Clamp implausible counts and recover length when count looks mis-mapped.

    Real-project workbooks often put total length (e.g. 1092 inches) in the
    count column on rollup sheets like Steel Elements Summary.
    """

    if count <= MAX_SCHEDULE_ROW_COUNT:
        return count, length
    # Large integer with no length — treat as total length, not piece count.
    if length in (None, "", "nan") and count >= 100:
        return 1, str(count)
    # Still too large even with length present — cap to 1 rather than
    # inflating validation missing counts.
    if count > MAX_SCHEDULE_ROW_COUNT:
        return 1, length
    return count, length


def _sheet_category(sheet_name: str) -> str:
    if sheet_name in SCHEDULE_SHEETS:
        return "schedule"
    lowered = sheet_name.lower()
    if sheet_name in SUMMARY_SHEETS or any(
        key in lowered for key in ("summary", "count_per_sheet", "rollup")
    ):
        return "summary"
    if any(key in lowered for key in ("framing", "column", "plate", "connection")):
        return "schedule"
    if "steel element" in lowered:
        return "summary"
    return "other"


def _find_header_row(frame: pd.DataFrame) -> Tuple[int, Dict[str, int]]:
    """Locate the header row containing Type / Length / Weight columns."""

    best_row = -1
    best_map: Dict[str, int] = {}
    for i in range(min(12, len(frame))):
        row = frame.iloc[i]
        mapping: Dict[str, int] = {}
        for j, cell in enumerate(row.tolist()):
            key = str(cell or "").strip().lower()
            if key == "type" and "type" not in mapping:
                mapping["type"] = j
            elif key in {"length", "len"} and "length" not in mapping:
                mapping["length"] = j
            elif key in {"weight", "wt", "ifs_w"} and "weight" not in mapping:
                mapping["weight"] = j
            elif key in {"overall weight", "overall_weight"} and "overall_weight" not in mapping:
                mapping["overall_weight"] = j
            elif key == "count" and "count" not in mapping:
                mapping["count"] = j
            elif key == "mark" and "mark" not in mapping:
                mapping["mark"] = j
            elif key in {"comments", "comment"} and "comments" not in mapping:
                mapping["comments"] = j
            elif key in {"beam type"} and "type" not in mapping:
                mapping["type"] = j
            elif key in {"beam count"} and "count" not in mapping:
                mapping["count"] = j
        if "type" in mapping and len(mapping) >= 1:
            if len(mapping) > len(best_map):
                best_row = i
                best_map = mapping
    return best_row, best_map


def _sheet_member_type(sheet_name: str) -> str:
    name = sheet_name.lower()
    if "column" in name:
        return "column"
    if "framing" in name or "beam" in name:
        return "beam"
    if "plate" in name or "baseplate" in name:
        return "plate"
    if "connection" in name:
        return "connection"
    return "miscellaneous"


def _entity_class_for_shape(shape: str, member_type: str) -> str:
    if member_type == "plate" or PLATE_HINT_RE.search(shape):
        return "plate"
    entity = classify_category(shape)
    # Map taxonomy ids to takeoff-facing entity classes
    mapping = {
        "structural_section": "steel_section",
        "pipe": "steel_section",
        "material": "material",
        "bolt": "bolt",
        "plate": "plate",
        "miscellaneous": "miscellaneous",
    }
    return mapping.get(entity.category, "miscellaneous")


def parse_ground_truth_excel(path: str | Path) -> Dict[str, Any]:
    """
    Parse a project estimate workbook into canonical ground-truth entities.
    """

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Ground-truth Excel not found: {file_path}")

    xl = pd.ExcelFile(file_path)
    try:
        sheet_names = list(xl.sheet_names)
    finally:
        xl.close()

    items: List[dict] = []
    sheets_used: List[str] = []
    schedule_shapes: set[str] = set()

    def _parse_sheet(sheet: str, *, category: str) -> None:
        raw = pd.read_excel(file_path, sheet_name=sheet, header=None)
        header_row, colmap = _find_header_row(raw)
        if header_row < 0 or "type" not in colmap:
            return
        sheets_used.append(sheet)
        member_type = _sheet_member_type(sheet)
        for i in range(header_row + 1, len(raw)):
            row = raw.iloc[i]
            shape = _norm_shape(row.iloc[colmap["type"]] if colmap["type"] < len(row) else "")
            if not shape:
                continue
            if _is_summary_row(shape):
                continue
            # Skip non-shape schedule titles
            if shape.startswith("STRUCTURAL") or "SCHEDULE" in shape:
                continue
            if not (SHAPE_RE.match(shape) or PLATE_HINT_RE.search(shape) or shape.startswith("PL")):
                if not re.search(r"\d", shape):
                    continue

            count = 1
            if "count" in colmap and colmap["count"] < len(row):
                try:
                    count_val = row.iloc[colmap["count"]]
                    if pd.notna(count_val):
                        count = max(1, int(float(count_val)))
                except (TypeError, ValueError):
                    count = 1

            length = None
            if "length" in colmap and colmap["length"] < len(row):
                length = row.iloc[colmap["length"]]
                length = None if pd.isna(length) else str(length)

            weight = None
            if "weight" in colmap and colmap["weight"] < len(row):
                try:
                    w = row.iloc[colmap["weight"]]
                    weight = float(w) if pd.notna(w) else None
                except (TypeError, ValueError):
                    weight = None

            count, length = _sanitize_quantity(
                count, length=length, weight=weight, sheet_name=sheet
            )

            # Summary/rollup sheets only fill gaps left by detailed schedules.
            if category == "summary" and shape in schedule_shapes:
                continue

            mark = None
            if "mark" in colmap and colmap["mark"] < len(row):
                mark_val = row.iloc[colmap["mark"]]
                mark = None if pd.isna(mark_val) else str(mark_val)

            comments = None
            if "comments" in colmap and colmap["comments"] < len(row):
                c = row.iloc[colmap["comments"]]
                comments = None if pd.isna(c) else str(c)

            entity_class = _entity_class_for_shape(shape, member_type)
            item = {
                "canonical_label": shape,
                "entity_class": entity_class,
                "member_type": member_type,
                "quantity": count,
                "length": length,
                "weight": weight,
                "mark": mark,
                "comments": comments,
                "sheet": sheet,
                "source": "ground_truth_excel",
                "sheet_category": category,
            }
            items.append(item)
            if category == "schedule":
                schedule_shapes.add(shape)

    schedule_names: List[str] = []
    summary_names: List[str] = []
    for sheet in sheet_names:
        category = _sheet_category(sheet)
        if category == "schedule":
            schedule_names.append(sheet)
        elif category == "summary":
            summary_names.append(sheet)

    for sheet in schedule_names:
        _parse_sheet(sheet, category="schedule")
    for sheet in summary_names:
        _parse_sheet(sheet, category="summary")

    # Legacy catch-all for oddly named sheets not caught above.
    for sheet in sheet_names:
        if sheet in schedule_names or sheet in summary_names:
            continue
        if not any(
            key in sheet.lower()
            for key in ("framing", "column", "plate", "connection", "steel element", "summary")
        ):
            continue
        _parse_sheet(sheet, category=_sheet_category(sheet))

    # Aggregate quantities by canonical label
    aggregated: Dict[str, dict] = {}
    for item in items:
        key = item["canonical_label"]
        if key not in aggregated:
            aggregated[key] = {
                "canonical_label": key,
                "entity_class": item["entity_class"],
                "member_type": item["member_type"],
                "quantity": 0,
                "occurrences": [],
                "source": "ground_truth_excel",
            }
        aggregated[key]["quantity"] += int(item["quantity"] or 1)
        aggregated[key]["occurrences"].append(item)

    # Fallback: flexible / AISC-style takeoff sheets when schedule parser finds nothing.
    if not items:
        try:
            from services.engineering.excel_loader import load_engineering_excel

            flexible = load_engineering_excel(file_path)
            sheets_used = list(
                {
                    str(item.get("sheet") or "Sheet1")
                    for item in (flexible.get("items") or [])
                }
            ) or ["flexible_excel"]
            for item in flexible.get("items") or []:
                shape = _norm_shape(item.get("shape") or item.get("section") or "")
                if not shape:
                    continue
                member_type = str(item.get("type") or item.get("member_type") or "miscellaneous")
                entity_class = _entity_class_for_shape(shape, member_type)
                row = {
                    "canonical_label": shape,
                    "entity_class": entity_class,
                    "member_type": member_type,
                    "quantity": int(item.get("count") or item.get("quantity") or 1),
                    "length": item.get("length"),
                    "weight": item.get("weight"),
                    "mark": item.get("mark"),
                    "comments": item.get("material"),
                    "sheet": item.get("sheet") or "flexible_excel",
                    "source": "aisc_or_flexible_takeoff",
                }
                items.append(row)
                key = row["canonical_label"]
                if key not in aggregated:
                    aggregated[key] = {
                        "canonical_label": key,
                        "entity_class": entity_class,
                        "member_type": member_type,
                        "quantity": 0,
                        "occurrences": [],
                        "source": "aisc_or_flexible_takeoff",
                    }
                aggregated[key]["quantity"] += int(row["quantity"] or 1)
                aggregated[key]["occurrences"].append(row)
            parser = "engineering_excel_loader"
        except Exception:
            parser = "ground_truth_excel"
    else:
        parser = "ground_truth_excel"

    by_entity = Counter(i["entity_class"] for i in aggregated.values())
    return {
        "source_file": file_path.name,
        "source_path": str(file_path),
        "sheets_used": sheets_used,
        "row_count": len(items),
        "unique_labels": len(aggregated),
        "total_quantity": int(sum(v["quantity"] for v in aggregated.values())),
        "entity_distribution": dict(by_entity),
        "items": items,
        "aggregates": list(aggregated.values()),
        "role": "ground_truth",
        "parser": parser,
        "excel_is_prediction": False,
    }
