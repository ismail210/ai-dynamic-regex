"""Geometry evidence providers (Section 30-32).

``GeometryEvidenceProvider`` is the explicit boundary between the semantic
pipeline and any geometry source. The semantic pipeline must run to
completion with ``provider=None`` (Section 31) -- Grasshopper/Rhino.Compute
availability can never block text correction.

``GrasshopperGeometryEvidenceProvider`` does not call Rhino.Compute itself.
No existing Rhino.Compute client was found anywhere in this repository
(verified this session -- see docs/ghx_geometry_audit.md), so there is
nothing to wrap yet. This provider instead consumes an already-captured
result payload (a dict shaped like a subset of the RH_OUT contract
documented in ghx_semantic_manifest.json / ghx_geometry_audit.md) --
produced either by a future live Compute call, or by a hand-built fixture
for tests. When a real Compute client is added, only the small function
that produces this payload needs to change; the provider's contract with
the rest of the pipeline does not.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from services.semantic.models import GeometryEvidence, GeometryProvider


class GeometryEvidenceProvider(ABC):
    @abstractmethod
    def extract_geometry(self, document_context: Dict[str, Any]) -> List[GeometryEvidence]:
        ...


class NullGeometryEvidenceProvider(GeometryEvidenceProvider):
    """The default provider: no geometry evidence, ever fails soft."""

    def extract_geometry(self, document_context: Dict[str, Any]) -> List[GeometryEvidence]:
        return []


def _fingerprint_geometry_id(
    geometry_type: str, sheet: Optional[str], points: Optional[List[List[float]]], length: Optional[float]
) -> str:
    """Deterministic geometry identity when no stable source ID exists.

    Never derived from list position (Section 12) -- built only from
    normalized, rounded geometric attributes, so the same real-world curve
    gets the same id across runs even if output ordering changes.
    """
    rounded_points = [[round(c, 2) for c in p] for p in (points or [])]
    basis = f"{geometry_type}|{sheet}|{rounded_points}|{round(length, 2) if length else None}"
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
    return f"geom_{digest}"


class GrasshopperGeometryEvidenceProvider(GeometryEvidenceProvider):
    """Wraps an already-captured RH_OUT payload; never executes the GHX itself.

    Expected ``rh_out_capture`` shape (only the outputs this pipeline needs,
    per Section 32 -- do not pull fabrication/takeoff results in here):

        {
            "source_definition_sha256": "...",
            "sheet": "...",
            "RH_OUT:BeamCrv": [{"points": [[x,y],...], "length": ..., "element_id": "..."}],
            "RH_OUT:PlanColumnClosed": [...],
            ...
        }
    """

    _OUTPUT_TO_TYPE = {
        "RH_OUT:BeamCrv": "beam_curve",
        "RH_OUT:MiscBeamCrv": "misc",
        "RH_OUT:PlanColumnClosed": "column",
        "RH_OUT:PlanColumnOpen": "column",
        "RH_OUT:PlanLine": "misc",
        "RH_OUT:PlanCrv": "misc",
        "RH_OUT:MomentRect": "moment",
    }

    def __init__(self, rh_out_capture: Dict[str, Any]):
        self._capture = rh_out_capture

    def extract_geometry(self, document_context: Dict[str, Any]) -> List[GeometryEvidence]:
        evidence: List[GeometryEvidence] = []
        sha = self._capture.get("source_definition_sha256")
        sheet = self._capture.get("sheet")
        for output_name, geometry_type in self._OUTPUT_TO_TYPE.items():
            for item in self._capture.get(output_name, []):
                points = item.get("points")
                length = item.get("length")
                element_id = item.get("element_id")
                geometry_id = (
                    f"geom_ghx_{element_id}" if element_id
                    else _fingerprint_geometry_id(geometry_type, sheet, points, length)
                )
                evidence.append(GeometryEvidence(
                    geometry_id=geometry_id,
                    provider=GeometryProvider.GRASSHOPPER,
                    geometry_type=geometry_type,
                    source_geometry_id=element_id,
                    source_definition_sha256=sha,
                    source_output=output_name,
                    sheet=sheet,
                    points=points,
                    bbox=item.get("bbox"),
                    centroid=item.get("centroid"),
                    start=item.get("start"),
                    end=item.get("end"),
                    length=length,
                    orientation=item.get("orientation"),
                    metadata={
                        **{k: v for k, v in item.items() if k not in {
                            "points", "bbox", "centroid", "start", "end", "length",
                            "orientation", "element_id",
                        }},
                        "provenance": {"rh_out": output_name, "cluster": "MAIN_BeamProcessing&Selection"},
                    },
                ))
        return evidence

    def paired_text_for(self, output_name: str) -> List[Dict[str, Any]]:
        """Existing GHX text<->curve pairing, if the capture provides one.

        Returns an empty list when the capture has no explicit pairing data
        -- this pipeline must never assume list-order alignment between
        e.g. RH_OUT:BeamTxt and RH_OUT:BeamCrv (Section 11/34); it only uses
        a pairing that the capture states explicitly (e.g. via a shared
        ``element_id``).
        """
        return self._capture.get(f"{output_name}_paired_text", [])
