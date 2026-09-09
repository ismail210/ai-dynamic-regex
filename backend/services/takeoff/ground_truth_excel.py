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
from services.family_codes import MODERN_FAMILY_ALTERNATION


# Rolled-section member schedules used for section/quantity/LF/tonnage metrics.
MEMBER_SCHEDULE_SHEETS = (
    "StructuralFramingSchedule",
    "StructuralColumnSchedule",
    "StructuralBracingSchedule",
)

# Connection schedules are parsed for a separate entity class and must not
# enter structural-member Precision/Recall/F1 or member quantity.
CONNECTION_SCHEDULE_SHEETS = (
    "StructuralConnectionSchedule",
    "MomentConnectionSchedule",
)

PLATE_SCHEDULE_SHEETS = (
    "BasePlateSchedule",
    "StructuralPlateSchedule",
)

SCHEDULE_SHEETS = (
    *MEMBER_SCHEDULE_SHEETS,
    *PLATE_SCHEDULE_SHEETS,
    *CONNECTION_SCHEDULE_SHEETS,
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
    rf"^(?:{MODERN_FAMILY_ALTERNATION})\d",
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
    scope = _metric_scope_for_sheet(sheet_name)
    if scope == "rollup":
        return "rollup"
    if scope == "summary":
        return "summary"
    if sheet_name in SCHEDULE_SHEETS or scope in {
        "structural_member",
        "connection",
        "plate",
    }:
        return "schedule"
    lowered = sheet_name.lower()
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
            elif key in {"total length", "total_length"} and "total_length" not in mapping:
                mapping["total_length"] = j
            elif (
                key in {"total weight", "total_weight", "total weight (tons)"}
                and "total_weight" not in mapping
            ):
                mapping["total_weight"] = j
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
    if "moment" in name and "connection" in name:
        return "connection"
    if "column" in name:
        return "column"
    if "bracing" in name or "brace" in name:
        return "brace"
    if "framing" in name or "beam" in name:
        return "beam"
    if "plate" in name or "baseplate" in name:
        return "plate"
    if "connection" in name:
        return "connection"
    if "joist" in name:
        return "joist"
    return "miscellaneous"


def _metric_scope_for_sheet(sheet_name: str) -> str:
    """Which evaluation bucket a sheet belongs to."""

    if sheet_name in MEMBER_SCHEDULE_SHEETS:
        return "structural_member"
    if sheet_name in CONNECTION_SCHEDULE_SHEETS:
        return "connection"
    if sheet_name in PLATE_SCHEDULE_SHEETS:
        return "plate"
    name = sheet_name.lower()
    if "moment" in name and "connection" in name:
        return "connection"
    if any(key in name for key in ("framing", "column", "bracing", "brace")):
        return "structural_member"
    if "connection" in name:
        return "connection"
    if "plate" in name or "baseplate" in name:
        return "plate"
    if name == "projecthome" or "project home" in name:
        return "rollup"
    if sheet_name in SUMMARY_SHEETS or any(
        key in name for key in ("summary", "count_per_sheet", "rollup")
    ):
        return "summary"
    return "other"


def _entity_class_for_shape(shape: str, member_type: str) -> str:
    if member_type == "connection":
        return "connection"
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
    member_sheets_used: List[str] = []
    schedule_shapes: set[str] = set()
    section_rollups: Dict[str, dict] = {}

    def _cell(row, colmap: Dict[str, int], key: str):
        if key not in colmap or colmap[key] >= len(row):
            return None
        value = row.iloc[colmap[key]]
        if pd.isna(value):
            return None
        return value

    def _parse_project_home(sheet: str) -> None:
        raw = pd.read_excel(file_path, sheet_name=sheet, header=None)
        header_row, colmap = _find_header_row(raw)
        if header_row < 0 or "type" not in colmap:
            return
        sheets_used.append(sheet)
        for i in range(header_row + 1, len(raw)):
            row = raw.iloc[i]
            shape = _norm_shape(_cell(row, colmap, "type"))
            if not shape or _is_summary_row(shape):
                continue
            if not SHAPE_RE.match(shape):
                continue
            count = None
            count_val = _cell(row, colmap, "count")
            if count_val is not None:
                try:
                    count = int(float(count_val))
                except (TypeError, ValueError):
                    count = None
            tons = None
            weight_val = _cell(row, colmap, "total_weight")
            if weight_val is not None:
                try:
                    tons = float(weight_val)
                except (TypeError, ValueError):
                    tons = None
            length = _cell(row, colmap, "total_length")
            length = None if length is None else str(length)
            section_rollups[shape] = {
                "canonical_label": shape,
                "count": count,
                "total_length": length,
                "total_weight_tons": tons,
                "sheet": sheet,
            }

    def _parse_sheet(sheet: str, *, category: str) -> None:
        metric_scope = _metric_scope_for_sheet(sheet)
        if metric_scope == "rollup":
            _parse_project_home(sheet)
            return
        raw = pd.read_excel(file_path, sheet_name=sheet, header=None)
        header_row, colmap = _find_header_row(raw)
        if header_row < 0 or "type" not in colmap:
            return
        sheets_used.append(sheet)
        member_type = _sheet_member_type(sheet)
        for i in range(header_row + 1, len(raw)):
            row = raw.iloc[i]
            shape = _norm_shape(_cell(row, colmap, "type"))
            if not shape:
                continue
            if _is_summary_row(shape):
                continue
            # Skip non-shape schedule titles and BIM type names such as
            # StructuralConnection_BasePlates.
            if shape.startswith("STRUCTURAL") or "SCHEDULE" in shape:
                continue

            is_shape = bool(SHAPE_RE.match(shape))
            is_plate = bool(
                PLATE_HINT_RE.search(shape) or shape.startswith("PL")
            )
            if metric_scope == "structural_member" and not is_shape:
                continue
            if not is_shape and not is_plate:
                if not re.search(r"\d", shape):
                    continue
                # Bare dimensions such as 1/2" are not structural members.
                if re.match(r"^\d", shape) and not is_shape:
                    continue

            # Summary sheets are not a structural-member source.
            if metric_scope == "summary":
                continue

            count = 1
            count_val = _cell(row, colmap, "count")
            if count_val is not None:
                try:
                    count = max(1, int(float(count_val)))
                except (TypeError, ValueError):
                    count = 1

            length = _cell(row, colmap, "length")
            length = None if length is None else str(length)

            weight_plf = None
            weight_val = _cell(row, colmap, "weight")
            if weight_val is not None:
                try:
                    weight_plf = float(weight_val)
                except (TypeError, ValueError):
                    weight_plf = None

            overall_weight_tons = None
            ow_val = _cell(row, colmap, "overall_weight")
            if ow_val is not None:
                try:
                    overall_weight_tons = float(ow_val)
                except (TypeError, ValueError):
                    overall_weight_tons = None

            count, length = _sanitize_quantity(
                count, length=length, weight=weight_plf, sheet_name=sheet
            )

            mark_val = _cell(row, colmap, "mark")
            mark = None if mark_val is None else str(mark_val)
            comments_val = _cell(row, colmap, "comments")
            comments = None if comments_val is None else str(comments_val)

            entity_class = _entity_class_for_shape(shape, member_type)
            if metric_scope == "connection":
                entity_class = "connection"
            item = {
                "canonical_label": shape,
                "entity_class": entity_class,
                "member_type": member_type,
                "metric_scope": metric_scope,
                "quantity": count,
                "length": length,
                "weight": weight_plf,
                "weight_plf": weight_plf,
                "overall_weight_tons": overall_weight_tons,
                "tons": overall_weight_tons,
                "mark": mark,
                "comments": comments,
                "sheet": sheet,
                "source": "ground_truth_excel",
                "sheet_category": category,
            }
            items.append(item)
            if metric_scope == "structural_member":
                schedule_shapes.add(shape)
                if sheet not in member_sheets_used:
                    member_sheets_used.append(sheet)

    schedule_names: List[str] = []
    summary_names: List[str] = []
    rollup_names: List[str] = []
    for sheet in sheet_names:
        category = _sheet_category(sheet)
        if category == "schedule":
            schedule_names.append(sheet)
        elif category == "summary":
            summary_names.append(sheet)
        elif category == "rollup":
            rollup_names.append(sheet)

    for sheet in schedule_names:
        _parse_sheet(sheet, category="schedule")
    for sheet in rollup_names:
        _parse_sheet(sheet, category="rollup")
    # Summary sheets are inspected for diagnostics only; they do not enter
    # structural-member ground truth once member schedules exist.
    for sheet in summary_names:
        _parse_sheet(sheet, category="summary")

    # Legacy catch-all for oddly named sheets not caught above.
    for sheet in sheet_names:
        if sheet in schedule_names or sheet in summary_names or sheet in rollup_names:
            continue
        if not any(
            key in sheet.lower()
            for key in ("framing", "column", "bracing", "plate", "connection")
        ):
            continue
        _parse_sheet(sheet, category=_sheet_category(sheet))

    def _aggregate_scope(scope: str) -> Dict[str, dict]:
        aggregated: Dict[str, dict] = {}
        for item in items:
            if item.get("metric_scope") != scope:
                continue
            key = item["canonical_label"]
            if key not in aggregated:
                aggregated[key] = {
                    "canonical_label": key,
                    "entity_class": item["entity_class"],
                    "member_type": item["member_type"],
                    "metric_scope": scope,
                    "quantity": 0,
                    "occurrences": [],
                    "source": "ground_truth_excel",
                    "overall_weight_tons": 0.0,
                    "has_piece_tons": False,
                }
            aggregated[key]["quantity"] += int(item["quantity"] or 1)
            aggregated[key]["occurrences"].append(item)
            piece_tons = item.get("overall_weight_tons")
            if piece_tons is not None:
                aggregated[key]["overall_weight_tons"] += float(piece_tons)
                aggregated[key]["has_piece_tons"] = True
        for key, bucket in aggregated.items():
            rollup = section_rollups.get(key) or {}
            if bucket["has_piece_tons"]:
                bucket["tons"] = round(bucket["overall_weight_tons"], 6)
                bucket["tonnage_source"] = "overall_weight"
            elif rollup.get("total_weight_tons") is not None:
                bucket["tons"] = float(rollup["total_weight_tons"])
                bucket["tonnage_source"] = "project_home_total_weight"
            else:
                bucket["tons"] = None
                bucket["tonnage_source"] = None
            if rollup:
                bucket["project_home_count"] = rollup.get("count")
                bucket["project_home_total_length"] = rollup.get("total_length")
                bucket["project_home_total_weight_tons"] = rollup.get(
                    "total_weight_tons"
                )
        return aggregated

    member_aggregated = _aggregate_scope("structural_member")
    connection_aggregated = _aggregate_scope("connection")
    plate_aggregated = _aggregate_scope("plate")

    recognized_estimate_sheets = bool(schedule_names or summary_names or rollup_names)

    # Fallback: flexible / AISC-style takeoff sheets when this is not an
    # estimating-tool workbook (no member/connection/summary/rollup sheets).
    if not items and not recognized_estimate_sheets:
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
                if not shape or not SHAPE_RE.match(shape):
                    continue
                member_type = str(item.get("type") or item.get("member_type") or "miscellaneous")
                if str(member_type).lower() in {"connection", "plate"}:
                    continue
                entity_class = _entity_class_for_shape(shape, member_type)
                row = {
                    "canonical_label": shape,
                    "entity_class": entity_class,
                    "member_type": member_type,
                    "metric_scope": "structural_member",
                    "quantity": int(item.get("count") or item.get("quantity") or 1),
                    "length": item.get("length"),
                    "weight": item.get("weight"),
                    "weight_plf": item.get("weight"),
                    "overall_weight_tons": item.get("overall_weight") or item.get("tons"),
                    "tons": item.get("overall_weight") or item.get("tons"),
                    "mark": item.get("mark"),
                    "comments": item.get("material"),
                    "sheet": item.get("sheet") or "flexible_excel",
                    "source": "aisc_or_flexible_takeoff",
                    "sheet_category": "schedule",
                }
                items.append(row)
                if row["sheet"] not in member_sheets_used:
                    member_sheets_used.append(row["sheet"])
            member_aggregated = _aggregate_scope("structural_member")
            parser = "engineering_excel_loader"
        except Exception:
            parser = "ground_truth_excel"
    else:
        parser = "ground_truth_excel"

    member_items = [
        item for item in items if item.get("metric_scope") == "structural_member"
    ]
    connection_items = [
        item for item in items if item.get("metric_scope") == "connection"
    ]
    plate_items = [item for item in items if item.get("metric_scope") == "plate"]
    by_entity = Counter(i["entity_class"] for i in member_aggregated.values())
    return {
        "source_file": file_path.name,
        "source_path": str(file_path),
        "sheets_used": sheets_used,
        "member_sheets_used": member_sheets_used,
        "row_count": len(member_items),
        "unique_labels": len(member_aggregated),
        "total_quantity": int(sum(v["quantity"] for v in member_aggregated.values())),
        "entity_distribution": dict(by_entity),
        "items": member_items,
        "all_items": items,
        "connection_items": connection_items,
        "plate_items": plate_items,
        "aggregates": list(member_aggregated.values()),
        "connection_aggregates": list(connection_aggregated.values()),
        "plate_aggregates": list(plate_aggregated.values()),
        "section_rollups": section_rollups,
        "role": "ground_truth",
        "parser": parser,
        "excel_is_prediction": False,
        "member_metric_scope": "structural_member",
        "quantity_definition": "schedule_row_count",
    }
