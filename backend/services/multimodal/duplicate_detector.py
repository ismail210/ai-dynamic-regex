"""
Duplicate component detection and merge helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from services.prediction.contract import confidence_overall


def _center(bbox: Sequence[float]) -> Tuple[float, float]:
    return (
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    )


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    ac, bc = _center(a), _center(b)
    return ((ac[0] - bc[0]) ** 2 + (ac[1] - bc[1]) ** 2) ** 0.5


def merge_duplicate_predictions(
    predictions: List[dict],
    *,
    distance_threshold: float = 18.0,
) -> Dict[str, Any]:
    """
    Merge near-identical OCR/label detections on the same page.

    Keeps the highest-confidence prediction and records merge provenance.
    """

    kept: List[dict] = []
    merges: List[dict] = []
    for prediction in predictions:
        geom = prediction.get("geometry_preview") or {}
        bbox = geom.get("bbox") or prediction.get("bbox")
        page = (
            prediction.get("page")
            or (prediction.get("features", {}).get("geometry", {}) or {}).get("page")
            or 0
        )
        label = str(
            prediction.get("predicted_shape")
            or prediction.get("corrected_token")
            or prediction.get("original_token")
            or ""
        ).upper().replace(" ", "")
        merged_into = None
        if bbox:
            for index, existing in enumerate(kept):
                existing_geom = existing.get("geometry_preview") or {}
                existing_bbox = existing_geom.get("bbox") or existing.get("bbox")
                existing_page = existing.get("page") or 0
                existing_label = str(
                    existing.get("predicted_shape")
                    or existing.get("corrected_token")
                    or ""
                ).upper().replace(" ", "")
                if int(existing_page) != int(page) or not existing_bbox:
                    continue
                if existing_label != label:
                    continue
                if _distance(existing_bbox, bbox) <= distance_threshold:
                    merged_into = index
                    break
        if merged_into is None:
            item = dict(prediction)
            item["page"] = page
            if bbox:
                item["bbox"] = bbox
            item["merged_from"] = []
            kept.append(item)
            continue

        survivor = kept[merged_into]
        survivor_conf = confidence_overall(survivor.get("confidence"))
        challenger_conf = confidence_overall(prediction.get("confidence"))
        if challenger_conf > survivor_conf:
            provenance = survivor.get("merged_from") or []
            provenance.append(survivor.get("component_id") or survivor.get("object_id"))
            kept[merged_into] = {
                **prediction,
                "page": page,
                "bbox": bbox,
                "merged_from": provenance,
            }
        else:
            survivor.setdefault("merged_from", []).append(
                prediction.get("component_id") or prediction.get("object_id")
            )
        merges.append(
            {
                "kept": kept[merged_into].get("component_id")
                or kept[merged_into].get("object_id"),
                "dropped": prediction.get("component_id") or prediction.get("object_id"),
                "label": label,
            }
        )

    return {
        "predictions": kept,
        "duplicate_count": len(merges),
        "merges": merges,
    }
