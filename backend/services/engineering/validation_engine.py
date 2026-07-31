"""
Extraction Validation Engine
============================

Validates quality of PDF text/geometry extraction and graph connectivity.

Checks
------
- Text extraction quality
- OCR / empty-page quality proxies
- Duplicate labels
- Overlapping text
- Missing text
- Invalid engineering tokens
- Geometry consistency
- Disconnected geometry
- Label far from geometry
- Invalid / missing dimensions
- Low confidence objects

Output: validation report JSON.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from services.token_extractor import extract_engineering_tokens


VALID_TOKEN_RE = re.compile(
    r"^(W\d+X\d+|HSS\d+X\d+(?:X[\d\/]+)?|L\d+X\d+(?:X[\d\/]+)?|PIPE\d+|S-\d+|A\d+|PL\d+X?\d*)$",
    re.I,
)


def validate_extraction(
    *,
    document_structure: dict,
    geometry: dict,
    graph: dict,
    object_confidences: Optional[List[dict]] = None,
    far_label_distance: float = 140.0,
) -> Dict[str, Any]:
    """Generate a structured validation report."""

    issues: List[dict] = []
    metrics: Dict[str, Any] = {}

    pages = document_structure.get("pages") or []
    words = document_structure.get("words") or []
    lines = document_structure.get("lines") or []
    blocks = document_structure.get("blocks") or []
    text = document_structure.get("text") or ""

    # ---- Text extraction quality ----
    text_len = len(text.strip())
    metrics["text_length"] = text_len
    metrics["word_count"] = len(words)
    metrics["line_count"] = len(lines)
    metrics["block_count"] = len(blocks)
    metrics["page_count"] = len(pages)

    if text_len < 20:
        issues.append(
            {
                "code": "missing_text",
                "severity": "high",
                "message": "Document text extraction produced almost no content (possible scan/OCR gap).",
            }
        )
    empty_pages = [p for p in pages if int(p.get("text_length") or 0) < 5]
    if empty_pages:
        issues.append(
            {
                "code": "ocr_quality",
                "severity": "medium",
                "message": f"{len(empty_pages)} page(s) have little/no extractable text.",
                "pages": [p.get("page_number") for p in empty_pages],
            }
        )

    # ---- Duplicate labels ----
    label_texts = []
    for node in graph.get("nodes") or []:
        if node.get("kind") in {"label", "beam", "column"}:
            label_texts.append(str(node.get("text") or "").upper().replace(" ", ""))
    dupes = {k: v for k, v in Counter(label_texts).items() if k and v > 1}
    metrics["duplicate_label_types"] = len(dupes)
    if dupes:
        issues.append(
            {
                "code": "duplicate_labels",
                "severity": "low",
                "message": f"{len(dupes)} label value(s) appear more than once.",
                "examples": dict(list(dupes.items())[:10]),
            }
        )

    # ---- Overlapping text ----
    overlap_count = 0
    for i, a in enumerate(lines[:300]):
        for b in lines[i + 1 : i + 20]:
            if a.get("page_number") != b.get("page_number"):
                continue
            if _overlap_area(a.get("bbox") or [0, 0, 0, 0], b.get("bbox") or [0, 0, 0, 0]) > 0:
                overlap_count += 1
    metrics["overlapping_text_pairs"] = overlap_count
    if overlap_count > 0:
        issues.append(
            {
                "code": "overlapping_text",
                "severity": "medium",
                "message": f"Detected {overlap_count} overlapping text line pair(s).",
            }
        )

    # ---- Invalid engineering tokens ----
    tokens = extract_engineering_tokens(text)
    invalid = [t for t in tokens if not VALID_TOKEN_RE.match(t.upper().replace(" ", ""))]
    metrics["token_count"] = len(tokens)
    metrics["invalid_token_count"] = len(invalid)
    if invalid:
        issues.append(
            {
                "code": "invalid_engineering_tokens",
                "severity": "medium",
                "message": f"{len(invalid)} token(s) failed engineering pattern validation.",
                "examples": invalid[:20],
            }
        )

    # ---- Geometry consistency ----
    geom_objects = geometry.get("objects") or []
    metrics["geometry_count"] = len(geom_objects)
    degenerate = [
        g
        for g in geom_objects
        if float(g.get("length") or 0) <= 0 and float(g.get("area") or 0) <= 0
    ]
    if degenerate:
        issues.append(
            {
                "code": "geometry_consistency",
                "severity": "medium",
                "message": f"{len(degenerate)} geometry object(s) have zero length/area.",
                "object_ids": [g.get("geometry_id") for g in degenerate[:30]],
            }
        )

    # ---- Disconnected geometry ----
    connected_ids = set()
    for edge in graph.get("edges") or []:
        if edge.get("relationship") in {"connected", "touching", "intersection", "nearest_label"}:
            connected_ids.add(edge["source"])
            connected_ids.add(edge["target"])
    geom_nodes = [n for n in graph.get("nodes") or [] if n.get("kind") in {"geometry", "dimension"}]
    disconnected = [n for n in geom_nodes if n["node_id"] not in connected_ids]
    metrics["disconnected_geometry"] = len(disconnected)
    if disconnected and len(geom_nodes) > 0 and len(disconnected) / max(len(geom_nodes), 1) > 0.5:
        issues.append(
            {
                "code": "disconnected_geometry",
                "severity": "medium",
                "message": f"{len(disconnected)} geometry node(s) appear disconnected from the graph.",
                "object_ids": [n.get("source_id") for n in disconnected[:30]],
            }
        )

    # ---- Label far from geometry ----
    far_labels = []
    for edge in graph.get("edges") or []:
        if edge.get("relationship") != "nearest_geometry":
            continue
        dist = edge.get("distance")
        if dist is not None and float(dist) > far_label_distance:
            far_labels.append(edge)
    metrics["far_label_links"] = len(far_labels)
    if far_labels:
        issues.append(
            {
                "code": "label_far_from_geometry",
                "severity": "medium",
                "message": f"{len(far_labels)} label-to-geometry link(s) exceed {far_label_distance} units.",
            }
        )

    # ---- Dimensions ----
    dim_objects = [g for g in geom_objects if g.get("kind") == "dimension"]
    metrics["dimension_count"] = len(dim_objects)
    invalid_dims = [d for d in dim_objects if float(d.get("length") or 0) < 1]
    if invalid_dims:
        issues.append(
            {
                "code": "invalid_dimensions",
                "severity": "low",
                "message": f"{len(invalid_dims)} dimension object(s) look invalid.",
                "object_ids": [d.get("geometry_id") for d in invalid_dims[:20]],
            }
        )
    label_nodes = [n for n in graph.get("nodes") or [] if n.get("kind") in {"label", "beam", "column"}]
    if label_nodes and not dim_objects:
        issues.append(
            {
                "code": "missing_dimensions",
                "severity": "low",
                "message": "Labels were found but no dimension geometry was detected.",
            }
        )

    # ---- Low confidence objects ----
    low_conf = [
        c
        for c in (object_confidences or [])
        if str(c.get("level") or "").lower() == "low" or float(c.get("overall") or 0) < 0.55
    ]
    metrics["low_confidence_objects"] = len(low_conf)
    if low_conf:
        issues.append(
            {
                "code": "low_confidence_objects",
                "severity": "high",
                "message": f"{len(low_conf)} object(s) scored low confidence.",
                "object_ids": [c.get("object_id") for c in low_conf[:40]],
            }
        )

    severity_score = sum(
        3 if i.get("severity") == "high" else 2 if i.get("severity") == "medium" else 1 for i in issues
    )
    quality = max(0.0, min(1.0, 1.0 - severity_score / 30.0))

    return {
        "valid": len([i for i in issues if i.get("severity") == "high"]) == 0,
        "quality_score": round(quality, 4),
        "issue_count": len(issues),
        "issues": issues,
        "metrics": metrics,
    }


def _overlap_area(a: List[float], b: List[float]) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float((x1 - x0) * (y1 - y0))
