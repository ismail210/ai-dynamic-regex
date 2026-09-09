"""Collapse the same printed annotation when extraction emits it twice.

Identity is the source OCR record — never the nearest geometry object.
Two W10X19 stamps at different plan locations must stay separate even if
they share a gridline bbox.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from services.prediction.contract import confidence_overall

SOURCE_IOU_THRESHOLD = 0.6


def _as_bbox(raw: Any) -> Optional[List[float]]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        box = [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError):
        return None
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def _source_text_block(prediction: Dict[str, Any]) -> Dict[str, Any]:
    block = prediction.get("source_text")
    return block if isinstance(block, dict) else {}


def source_token_id(prediction: Dict[str, Any]) -> str:
    """Extraction record id — not component_id (that folds in member role)."""

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
    candidate = (
        source.get("page_number")
        or prediction.get("page_number")
        or prediction.get("page")
        or 0
    )
    try:
        return int(candidate or 0)
    except (TypeError, ValueError):
        return 0


def source_bbox(prediction: Dict[str, Any]) -> Optional[List[float]]:
    """Extracted text position only — never geometry_preview."""

    source = _source_text_block(prediction)
    return _as_bbox(
        source.get("bounding_box")
        or prediction.get("bounding_box")
    )


def normalized_source_text(prediction: Dict[str, Any]) -> str:
    source = _source_text_block(prediction)
    raw = (
        source.get("normalized")
        or source.get("raw")
        or prediction.get("original_token")
        or prediction.get("raw_text")
        or ""
    )
    return str(raw).upper().replace(" ", "").replace("×", "X")


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
    if not normalized_source_text(left) or (
        normalized_source_text(left) != normalized_source_text(right)
    ):
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
    merges: List[dict] = []
    for prediction in predictions:
        merged_into = None
        for index, existing in enumerate(kept):
            if same_source_annotation(
                existing, prediction, iou_threshold=iou_threshold
            ):
                merged_into = index
                break
        page = source_page(prediction)
        box = source_bbox(prediction)
        if merged_into is None:
            item = dict(prediction)
            item["page"] = page
            item["page_number"] = prediction.get("page_number") or page
            if box:
                item["bounding_box"] = box
            item["merged_from"] = []
            kept.append(item)
            continue

        survivor = kept[merged_into]
        survivor_conf = confidence_overall(survivor.get("confidence"))
        challenger_conf = confidence_overall(prediction.get("confidence"))
        dropped_id = prediction.get("object_id") or prediction.get("component_id")
        kept_id = survivor.get("object_id") or survivor.get("component_id")
        if challenger_conf > survivor_conf:
            provenance = survivor.get("merged_from") or []
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
        merges.append(
            {
                "kept": kept_id,
                "dropped": dropped_id,
                "label": normalized_source_text(prediction),
            }
        )

    return {
        "predictions": kept,
        "duplicate_count": len(merges),
        "merges": merges,
    }
