"""
Duplicate annotation detection and merge helpers.

Identity is the EXTRACTED SOURCE ANNOTATION, never the geometry that was
later associated with it. Two predictions are the same annotation only when
they came from the same printed label on the page:

  * the same source token id (the same extraction record), or
  * the same page + same normalized label text + heavily overlapping source
    text bounding boxes (IoU >= ``iou_threshold``).

What this deliberately does NOT merge:
  * two identical labels printed at different positions (different bbox);
  * two different labels that happen to sit on the same member / gridline;
  * a label that has several candidate geometry associations (that is one
    annotation with metadata, not two predictions);
  * a real extracted label and a synthesized schedule/geometry token that
    happen to share a section string (different provenance, no source-bbox
    overlap).

Historical bug (fixed here): identity was keyed on
``prediction["geometry_preview"]["bbox"]`` -- the bbox of the *nearest
geometry object*, not the extracted text. On a dense framing plan many
distinct beam labels share a nearest gridline, so they collapsed into one;
turning geometry off (which nulls ``geometry_preview``) then fell through to
``prediction.get("bbox")`` -- a key that does not exist in the v3 payload
(it is ``bounding_box``) -- so dedup silently did nothing at all. Neither
behaviour was correct.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.prediction.contract import confidence_overall


def _norm_label(*values: Any) -> str:
    for value in values:
        text = re.sub(r"\s+", "", str(value or "")).upper()
        if text:
            return text
    return ""


def _source_bbox(prediction: dict) -> Optional[List[float]]:
    """The bbox of the extracted TEXT, in priority order. Never the
    geometry_preview bbox (that is the associated linework, not the label)."""

    source_text = prediction.get("source_text") or {}
    for candidate in (
        source_text.get("bounding_box"),
        prediction.get("bounding_box"),
        prediction.get("bbox"),
        (prediction.get("features", {}).get("text", {}) or {}).get("bbox"),
    ):
        if candidate and len(candidate) == 4:
            try:
                return [float(v) for v in candidate]
            except (TypeError, ValueError):
                continue
    return None


def _page(prediction: dict) -> int:
    source_text = prediction.get("source_text") or {}
    for candidate in (
        source_text.get("page_number"),
        prediction.get("page_number"),
        prediction.get("page"),
        (prediction.get("features", {}).get("text", {}) or {}).get("page"),
    ):
        if candidate is not None:
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
    return 0


def _token_identity(prediction: dict) -> Optional[str]:
    """A stable id for the extraction record itself (``token_p<page>_<order>``
    for real tokens, a stable hash for synthesized tokens). ``component_id``
    is deliberately NOT used as a fallback -- it folds in the geometry/rule
    derived member role, so it is not identity of the annotation."""

    value = prediction.get("object_id")
    return str(value) if value else None


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax0, ay0, ax1, ay1 = min(a[0], a[2]), min(a[1], a[3]), max(a[0], a[2]), max(a[1], a[3])
    bx0, by0, bx1, by1 = min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _same_annotation(a: dict, b: dict, iou_threshold: float) -> bool:
    if _page(a) != _page(b):
        return False
    if _norm_label(a.get("normalized_text"), a.get("raw_text"), a.get("original_token")) != _norm_label(
        b.get("normalized_text"), b.get("raw_text"), b.get("original_token")
    ):
        return False
    ida, idb = _token_identity(a), _token_identity(b)
    if ida is not None and ida == idb:
        return True
    ba, bb = _source_bbox(a), _source_bbox(b)
    if not ba or not bb:
        return False
    return _iou(ba, bb) >= iou_threshold


def merge_duplicate_predictions(
    predictions: List[dict],
    *,
    iou_threshold: float = 0.6,
    distance_threshold: Optional[float] = None,  # accepted for API compat, unused
) -> Dict[str, Any]:
    """
    Merge predictions that are the same printed annotation extracted twice.

    Keeps the highest-confidence prediction of each group and records merge
    provenance.
    """

    kept: List[dict] = []
    # (page, normalized label) -> indices into ``kept`` -- keeps the scan
    # linear in practice instead of O(n^2) over a whole sheet set.
    buckets: Dict[Tuple[int, str], List[int]] = {}
    merges: List[dict] = []

    for prediction in predictions:
        key = (
            _page(prediction),
            _norm_label(
                prediction.get("normalized_text"),
                prediction.get("raw_text"),
                prediction.get("original_token"),
            ),
        )
        merged_into: Optional[int] = None
        for index in buckets.get(key, ()):
            if _same_annotation(kept[index], prediction, iou_threshold):
                merged_into = index
                break

        if merged_into is None:
            kept.append({**prediction, "merged_from": []})
            buckets.setdefault(key, []).append(len(kept) - 1)
            continue

        survivor = kept[merged_into]
        survivor_conf = confidence_overall(survivor.get("confidence"))
        challenger_conf = confidence_overall(prediction.get("confidence"))
        dropped_id = prediction.get("component_id") or prediction.get("object_id")
        kept_id = survivor.get("component_id") or survivor.get("object_id")
        if challenger_conf > survivor_conf:
            provenance = list(survivor.get("merged_from") or [])
            provenance.append(kept_id)
            kept[merged_into] = {**prediction, "merged_from": provenance}
            kept_id = dropped_id
        else:
            survivor.setdefault("merged_from", []).append(dropped_id)
        merges.append({"kept": kept_id, "dropped": dropped_id, "label": key[1]})

    return {
        "predictions": kept,
        "duplicate_count": len(merges),
        "merges": merges,
    }
