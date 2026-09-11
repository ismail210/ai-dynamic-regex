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


SOURCE_IOU_THRESHOLD = 0.6


def _as_bbox(raw: Any) -> Optional[List[float]]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        box = [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError):
        return None
    x0, y0, x1, y1 = box
    if x0 == x1 or y0 == y1:
        return None
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _source_text_block(prediction: Dict[str, Any]) -> Dict[str, Any]:
    block = prediction.get("source_text")
    return block if isinstance(block, dict) else {}


def source_token_id(prediction: Dict[str, Any]) -> str:
    """Extraction record id -- not component_id, which folds in member role."""

    source = _source_text_block(prediction)
    for key in ("token_id", "source_token_id"):
        value = prediction.get(key) or source.get(key)
        if value:
            return str(value)
    object_id = str(prediction.get("object_id") or "")
    if object_id.startswith("token_"):
        return object_id
    return ""


def source_page(prediction: Dict[str, Any]) -> int:
    source = _source_text_block(prediction)
    features = prediction.get("features") if isinstance(prediction.get("features"), dict) else {}
    text_features = features.get("text") if isinstance(features.get("text"), dict) else {}
    for candidate in (
        source.get("page_number"),
        prediction.get("page_number"),
        prediction.get("page"),
        text_features.get("page"),
    ):
        if candidate is not None:
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
    return 0


def source_bbox(prediction: Dict[str, Any]) -> Optional[List[float]]:
    """Extracted text position only -- never geometry_preview."""

    source = _source_text_block(prediction)
    features = prediction.get("features") if isinstance(prediction.get("features"), dict) else {}
    text_features = features.get("text") if isinstance(features.get("text"), dict) else {}
    for candidate in (
        source.get("bounding_box"),
        prediction.get("bounding_box"),
        text_features.get("bbox"),
    ):
        box = _as_bbox(candidate)
        if box:
            return box
    return None


def normalized_source_text(prediction: Dict[str, Any]) -> str:
    source = _source_text_block(prediction)
    for value in (
        source.get("normalized"),
        source.get("raw"),
        prediction.get("normalized_text"),
        prediction.get("raw_text"),
        prediction.get("original_token"),
    ):
        text = re.sub(r"\s+", "", str(value or "")).upper().replace("×", "X")
        if text:
            return text
    return ""


def bbox_iou(left: Sequence[float], right: Sequence[float]) -> float:
    lx0, ly0, lx1, ly1 = (float(left[0]), float(left[1]), float(left[2]), float(left[3]))
    rx0, ry0, rx1, ry1 = (float(right[0]), float(right[1]), float(right[2]), float(right[3]))
    ix0, iy0 = max(lx0, rx0), max(ly0, ry0)
    ix1, iy1 = min(lx1, rx1), min(ly1, ry1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_l = max(0.0, (lx1 - lx0) * (ly1 - ly0))
    area_r = max(0.0, (rx1 - rx0) * (ry1 - ry0))
    denom = area_l + area_r - inter
    if denom <= 0:
        return 0.0
    return inter / denom


def same_source_annotation(
    left: Dict[str, Any],
    right: Dict[str, Any],
    *,
    iou_threshold: float = SOURCE_IOU_THRESHOLD,
) -> bool:
    left_id = source_token_id(left)
    right_id = source_token_id(right)
    if left_id and right_id and left_id == right_id:
        return True

    left_box = source_bbox(left)
    right_box = source_bbox(right)
    if not left_box or not right_box:
        return False
    if source_page(left) != source_page(right):
        return False
    left_label = normalized_source_text(left)
    if not left_label or left_label != normalized_source_text(right):
        return False
    return bbox_iou(left_box, right_box) >= iou_threshold


def merge_duplicate_predictions(
    predictions: List[dict],
    *,
    distance_threshold: float = 18.0,
    iou_threshold: float = SOURCE_IOU_THRESHOLD,
) -> Dict[str, Any]:
    """Merge duplicate extraction records of the same printed annotation.

    ``distance_threshold`` is unused; kept so callers do not break. Geometry
    bbox proximity must never collapse distinct plan locations.
    """

    del distance_threshold
    kept: List[dict] = []
    buckets: Dict[Tuple[str, str] | Tuple[str, int, str], List[int]] = {}
    merges: List[dict] = []

    for prediction in predictions:
        page = source_page(prediction)
        box = source_bbox(prediction)
        label = normalized_source_text(prediction)
        source_id = source_token_id(prediction)
        id_key = ("id", source_id) if source_id else None
        label_key = ("label", page, label)
        merged_into: Optional[int] = None
        candidate_indices = list(buckets.get(id_key, ())) if id_key else []
        candidate_indices.extend(
            index
            for index in buckets.get(label_key, ())
            if index not in candidate_indices
        )
        for index in candidate_indices:
            if same_source_annotation(kept[index], prediction, iou_threshold=iou_threshold):
                merged_into = index
                break

        if merged_into is None:
            item = dict(prediction)
            item["page"] = page
            item["page_number"] = prediction.get("page_number") or page
            if box:
                item["bounding_box"] = box
            item["merged_from"] = []
            kept.append(item)
            kept_index = len(kept) - 1
            if id_key:
                buckets.setdefault(id_key, []).append(kept_index)
            buckets.setdefault(label_key, []).append(kept_index)
            continue

        survivor = kept[merged_into]
        survivor_conf = confidence_overall(survivor.get("confidence"))
        challenger_conf = confidence_overall(prediction.get("confidence"))
        dropped_id = prediction.get("object_id") or prediction.get("component_id")
        kept_id = survivor.get("object_id") or survivor.get("component_id")
        if challenger_conf > survivor_conf:
            provenance = list(survivor.get("merged_from") or [])
            provenance.append(kept_id)
            replacement = dict(prediction)
            replacement["page"] = page
            replacement["page_number"] = prediction.get("page_number") or page
            if box:
                replacement["bounding_box"] = box
            replacement["merged_from"] = provenance
            kept[merged_into] = replacement
            kept_id = replacement.get("object_id") or replacement.get("component_id")
        else:
            survivor.setdefault("merged_from", []).append(dropped_id)
        merges.append({"kept": kept_id, "dropped": dropped_id, "label": label})

    return {
        "predictions": kept,
        "duplicate_count": len(merges),
        "merges": merges,
    }
