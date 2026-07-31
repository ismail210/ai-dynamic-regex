"""
Automatic Takeoff Interfaces (Future)
=====================================

Architecture stubs for generating:
- Engineering Excel
- Structural Takeoff
- Material / steel quantities
- Beam / column counts
- Length / weight summaries

Do NOT fully implement exporters yet — only prepare interfaces and
summary builders that other modules can call later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class TakeoffQuantity:
    shape: str
    member_type: str
    count: int = 0
    total_length: float = 0.0
    total_weight: float = 0.0
    material: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shape": self.shape,
            "member_type": self.member_type,
            "count": self.count,
            "total_length": round(self.total_length, 3),
            "total_weight": round(self.total_weight, 3),
            "material": self.material,
            "notes": self.notes,
        }


@dataclass
class TakeoffSummary:
    beam_count: int = 0
    column_count: int = 0
    plate_count: int = 0
    other_count: int = 0
    length_summary: float = 0.0
    weight_summary: float = 0.0
    quantities: List[TakeoffQuantity] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beam_count": self.beam_count,
            "column_count": self.column_count,
            "plate_count": self.plate_count,
            "other_count": self.other_count,
            "length_summary": round(self.length_summary, 3),
            "weight_summary": round(self.weight_summary, 3),
            "quantities": [q.to_dict() for q in self.quantities],
        }


class TakeoffExporter(Protocol):
    """Future exporter protocol for Excel / CSV / BIM takeoff packages."""

    def export(self, summary: TakeoffSummary, destination: str) -> str:
        ...


class BaseTakeoffExporter(ABC):
    """Abstract base for future concrete exporters."""

    @abstractmethod
    def export(self, summary: TakeoffSummary, destination: str) -> str:
        raise NotImplementedError


class ExcelTakeoffExporter(BaseTakeoffExporter):
    """Placeholder — not implemented yet."""

    def export(self, summary: TakeoffSummary, destination: str) -> str:
        raise NotImplementedError(
            "Excel takeoff export is intentionally not implemented yet. "
            "Use build_takeoff_preview() for architecture-ready summaries."
        )


class CsvTakeoffExporter(BaseTakeoffExporter):
    """Placeholder — not implemented yet."""

    def export(self, summary: TakeoffSummary, destination: str) -> str:
        raise NotImplementedError(
            "CSV takeoff export is intentionally not implemented yet."
        )


def build_takeoff_preview(
    *,
    excel_json: Optional[dict] = None,
    match_report: Optional[dict] = None,
    graph: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Build a future-facing takeoff preview from current pipeline artifacts.

    This does not write Excel files; it only prepares structured quantities.
    """

    quantities: Dict[str, TakeoffQuantity] = {}
    for item in (excel_json or {}).get("items") or []:
        shape = str(item.get("shape") or "UNKNOWN").upper().replace(" ", "")
        member_type = str(item.get("member_type") or "unknown")
        key = f"{member_type}:{shape}"
        qty = quantities.get(key) or TakeoffQuantity(shape=shape, member_type=member_type)
        count = int(item.get("count") or 1)
        qty.count += count
        if item.get("length") is not None:
            qty.total_length += float(item["length"]) * count
        if item.get("length_total") is not None:
            qty.total_length = float(item["length_total"])
        if item.get("weight") is not None:
            qty.total_weight += float(item["weight"]) * count
        if item.get("material"):
            qty.material = item.get("material")
        quantities[key] = qty

    # If Excel absent, fall back to extracted graph labels
    if not quantities and graph:
        from collections import Counter

        counts: Counter = Counter()
        types: Dict[str, str] = {}
        for node in graph.get("nodes") or []:
            if node.get("kind") not in {"label", "beam", "column"}:
                continue
            shape = str(node.get("text") or "").upper().replace(" ", "")
            if not shape:
                continue
            counts[shape] += 1
            types[shape] = node.get("kind") or "label"
        for shape, count in counts.items():
            member_type = "beam" if types.get(shape) == "beam" else (
                "column" if types.get(shape) == "column" else "unknown"
            )
            quantities[f"{member_type}:{shape}"] = TakeoffQuantity(
                shape=shape,
                member_type=member_type,
                count=count,
                notes="Derived from drawing labels (no Excel schedule)",
            )

    summary = TakeoffSummary(quantities=list(quantities.values()))
    for q in summary.quantities:
        mt = q.member_type.lower()
        if "beam" in mt:
            summary.beam_count += q.count
        elif "column" in mt:
            summary.column_count += q.count
        elif "plate" in mt:
            summary.plate_count += q.count
        else:
            summary.other_count += q.count
        summary.length_summary += q.total_length
        summary.weight_summary += q.total_weight

    payload = summary.to_dict()
    payload["status"] = "preview_only"
    payload["export_ready"] = False
    payload["message"] = (
        "Takeoff preview generated. Full Engineering Excel / Structural Takeoff "
        "exporters are architected but not implemented yet."
    )
    if match_report:
        payload["match_issues"] = (match_report.get("summary") or {}).get("issues", 0)
    return payload
