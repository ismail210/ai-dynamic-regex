"""
Extensible geometry source adapters.

PDF vectors are supported now. Rhino 3DM, DXF, and DWG have explicit adapter
contracts and capability reporting so future dependencies can be added without
changing the multimodal pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.engineering.geometry_extractor import extract_geometry


@dataclass(frozen=True)
class GeometryCapability:
    format: str
    available: bool
    implementation: str
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "available": self.available,
            "implementation": self.implementation,
            "reason": self.reason,
        }


@dataclass
class GeometryDocument:
    source_file: str
    source_format: str
    coordinate_system: str = "document"
    units: Optional[str] = None
    objects: List[dict] = field(default_factory=list)
    layers: List[dict] = field(default_factory=list)
    blocks: List[dict] = field(default_factory=list)
    groups: List[dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    scale: Optional[dict] = None
    association_radius_pdf_points: Optional[float] = None

    def to_dict(self) -> dict:
        counts: Dict[str, int] = {}
        for obj in self.objects:
            kind = str(obj.get("kind") or "unknown")
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "source_file": self.source_file,
            "source_format": self.source_format,
            "coordinate_system": self.coordinate_system,
            "units": self.units,
            "geometry_count": len(self.objects),
            "counts_by_kind": counts,
            "layers": self.layers,
            "blocks": self.blocks,
            "groups": self.groups,
            "objects": self.objects,
            "metadata": self.metadata,
            "scale": self.scale or (self.metadata or {}).get("scale"),
            "scale_value": (self.metadata or {}).get("scale_value"),
            "scale_source": (self.metadata or {}).get("scale_source"),
            "scale_confidence": (self.metadata or {}).get("scale_confidence"),
            "association_radius_pdf_points": self.association_radius_pdf_points
            or (self.metadata or {}).get("association_radius_pdf_points"),
            "fragment_merge": (self.metadata or {}).get("fragment_merge"),
            "page_scales": (self.metadata or {}).get("page_scales"),
        }


class GeometryAdapter(ABC):
    """Strategy interface for vector/CAD geometry sources."""

    extensions: tuple[str, ...] = ()

    @abstractmethod
    def capability(self) -> GeometryCapability:
        raise NotImplementedError

    @abstractmethod
    def extract(
        self,
        source_path: str | Path,
        *,
        document_structure: Optional[dict] = None,
    ) -> GeometryDocument:
        raise NotImplementedError


class PdfGeometryAdapter(GeometryAdapter):
    extensions = (".pdf",)

    def capability(self) -> GeometryCapability:
        return GeometryCapability(
            format="pdf",
            available=True,
            implementation="PyMuPDF vector drawings",
        )

    def extract(
        self,
        source_path: str | Path,
        *,
        document_structure: Optional[dict] = None,
    ) -> GeometryDocument:
        extracted = extract_geometry(
            str(source_path), document_structure=document_structure
        )
        objects = []
        for obj in extracted.get("objects") or []:
            objects.append(
                {
                    **obj,
                    "object_id": obj.get("geometry_id"),
                    "source_format": "pdf",
                    "coordinates": obj.get("points") or [],
                    "angle": obj.get("orientation"),
                    "cross_section": None,
                    "centerline": (
                        obj.get("points")
                        if obj.get("kind") in {"line", "polyline", "leader"}
                        else None
                    ),
                    "profile": (
                        obj.get("points")
                        if obj.get("kind")
                        in {"rectangle", "circle", "curve", "symbol"}
                        else None
                    ),
                }
            )
        return GeometryDocument(
            source_file=Path(source_path).name,
            source_format="pdf",
            units="pdf_points",
            objects=objects,
            layers=[
                {"name": name, "source": "optional_content_group"}
                for name in (document_structure or {}).get("layers") or []
            ],
            scale=extracted.get("scale"),
            association_radius_pdf_points=extracted.get(
                "association_radius_pdf_points"
            ),
            metadata={
                "page_summaries": extracted.get("page_summaries") or [],
                "quality": "vector_heuristic",
                "scale": extracted.get("scale"),
                "scale_value": extracted.get("scale_value"),
                "scale_source": extracted.get("scale_source"),
                "scale_confidence": extracted.get("scale_confidence"),
                "association_radius_pdf_points": extracted.get(
                    "association_radius_pdf_points"
                ),
                "fragment_merge": extracted.get("fragment_merge"),
                "page_scales": extracted.get("page_scales"),
            },
        )


class DeferredCadAdapter(GeometryAdapter):
    """Capability placeholder that fails clearly instead of silently."""

    def __init__(
        self,
        source_format: str,
        extensions: tuple[str, ...],
        dependency: str,
    ) -> None:
        self.source_format = source_format
        self.extensions = extensions
        self.dependency = dependency

    def capability(self) -> GeometryCapability:
        return GeometryCapability(
            format=self.source_format,
            available=False,
            implementation="adapter contract only",
            reason=f"Install and integrate {self.dependency}",
        )

    def extract(
        self,
        source_path: str | Path,
        *,
        document_structure: Optional[dict] = None,
    ) -> GeometryDocument:
        raise NotImplementedError(
            f"{self.source_format.upper()} adapter is prepared but not enabled. "
            f"Required integration: {self.dependency}."
        )


_ADAPTERS: List[GeometryAdapter] = [
    PdfGeometryAdapter(),
    DeferredCadAdapter("3dm", (".3dm",), "rhino3dm"),
    DeferredCadAdapter("dxf", (".dxf",), "ezdxf"),
    DeferredCadAdapter(
        "dwg",
        (".dwg",),
        "an approved DWG conversion SDK (ODA/Autodesk)",
    ),
]


def geometry_capabilities() -> List[dict]:
    return [adapter.capability().to_dict() for adapter in _ADAPTERS]


def adapter_for_path(path: str | Path) -> GeometryAdapter:
    suffix = Path(path).suffix.lower()
    for adapter in _ADAPTERS:
        if suffix in adapter.extensions:
            return adapter
    raise ValueError(f"Unsupported geometry source: {suffix or 'no extension'}")


def extract_geometry_document(
    source_path: str | Path,
    *,
    document_structure: Optional[dict] = None,
) -> Dict[str, Any]:
    return adapter_for_path(source_path).extract(
        source_path,
        document_structure=document_structure,
    ).to_dict()
