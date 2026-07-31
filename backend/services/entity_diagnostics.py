"""
Entity-level holdout diagnostics for the Model page.

Derives summaries, per-entity metrics, class→entity maps, and top
misclassifications from the persisted confusion matrix and class labels.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from services.entity_taxonomy import (
    CATEGORY_BOLT,
    CATEGORY_MATERIAL,
    CATEGORY_MISC,
    CATEGORY_PLATE,
    CATEGORY_STRUCTURAL,
    MODEL_PAGE_TAB_ORDER,
    MODEL_PAGE_TABS,
    category_for_model_class,
    category_label_for_model_page,
    map_model_classes,
)

TOP_MISCLASSIFICATION_LIMIT = 10

_SUMMARY_KEYS = {
    CATEGORY_STRUCTURAL: "steel_section_classes",
    CATEGORY_MATERIAL: "material_classes",
    CATEGORY_BOLT: "bolt_classes",
    CATEGORY_PLATE: "plate_classes",
    CATEGORY_MISC: "other_classes",
}


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _f1(precision: float, recall: float) -> float:
    denom = precision + recall
    if denom <= 0:
        return 0.0
    return 2.0 * precision * recall / denom


def _round4(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _empty_diagnostics() -> dict:
    return {
        "entity_summary": {
            "holdout_samples": 0,
            "overall_accuracy": None,
            "total_entity_types": 0,
            "steel_section_classes": 0,
            "material_classes": 0,
            "bolt_classes": 0,
            "plate_classes": 0,
            "other_classes": 0,
            "model_classes": 0,
        },
        "entity_performance": [],
        "class_entity_map": {},
        "top_misclassifications": [],
        "entity_tabs": list(MODEL_PAGE_TABS),
    }


def _normalize_matrix(
    matrix: Sequence[Sequence[Any]], size: int
) -> List[List[float]]:
    rows: List[List[float]] = []
    for row_index in range(size):
        source = matrix[row_index] if row_index < len(matrix) else []
        row = [
            float(source[col_index]) if col_index < len(source) else 0.0
            for col_index in range(size)
        ]
        rows.append(row)
    return rows


def _entity_metrics(
    cm: List[List[float]], indices: Sequence[int]
) -> dict:
    """Compute micro-style metrics over a class index subset."""

    index_set = set(indices)
    sample_count = sum(sum(cm[i]) for i in indices)
    correct = sum(cm[i][i] for i in indices)
    # Predictions into the entity from outside (false positives for the group)
    fp = sum(
        cm[r][j]
        for r in range(len(cm))
        if r not in index_set
        for j in indices
    )
    # Misses: actual entity predicted outside the entity
    fn = sum(
        cm[i][j]
        for i in indices
        for j in range(len(cm[i]))
        if j not in index_set
    )
    # Support-weighted precision/recall across classes in the entity
    weighted_precision = 0.0
    weighted_recall = 0.0
    weighted_f1 = 0.0
    weight_sum = 0.0
    for i in indices:
        support = sum(cm[i])
        tp = cm[i][i]
        col_sum = sum(cm[r][i] for r in range(len(cm)))
        precision_i = _safe_div(tp, col_sum)
        recall_i = _safe_div(tp, support)
        f1_i = _f1(precision_i, recall_i)
        if support > 0:
            weighted_precision += precision_i * support
            weighted_recall += recall_i * support
            weighted_f1 += f1_i * support
            weight_sum += support

    accuracy = _safe_div(correct, sample_count) if sample_count > 0 else None
    if weight_sum > 0:
        precision = weighted_precision / weight_sum
        recall = weighted_recall / weight_sum
        f1 = weighted_f1 / weight_sum
    else:
        # Fall back to group micro metrics when no support
        precision = _safe_div(correct, correct + fp)
        recall = _safe_div(correct, correct + fn)
        f1 = _f1(precision, recall)

    return {
        "class_count": len(indices),
        "sample_count": int(sample_count),
        "accuracy": _round4(accuracy),
        "precision": _round4(precision),
        "recall": _round4(recall),
        "f1": _round4(f1),
    }


def _top_misclassifications(
    cm: List[List[float]],
    labels: Sequence[str],
    class_map: Dict[str, dict],
    limit: int = TOP_MISCLASSIFICATION_LIMIT,
) -> List[dict]:
    pairs: List[dict] = []
    size = len(labels)
    for i in range(size):
        for j in range(size):
            if i == j:
                continue
            count = int(cm[i][j])
            if count <= 0:
                continue
            actual = labels[i]
            predicted = labels[j]
            meta = class_map.get(actual) or {
                "entity_type": category_for_model_class(actual),
                "entity_type_label": category_label_for_model_page(
                    category_for_model_class(actual)
                ),
            }
            pairs.append(
                {
                    "actual_class": actual,
                    "predicted_class": predicted,
                    "entity_type": meta["entity_type"],
                    "entity_type_label": meta["entity_type_label"],
                    "count": count,
                }
            )
    pairs.sort(
        key=lambda item: (
            -item["count"],
            item["actual_class"],
            item["predicted_class"],
        )
    )
    return pairs[: max(0, limit)]


def build_entity_diagnostics(
    model_meta: Optional[dict] = None,
    class_labels: Optional[Sequence[str]] = None,
) -> dict:
    """
    Build ModelPage entity diagnostics from persisted model metadata.

    Returns empty structures when the confusion matrix is unavailable.
    """

    model_meta = model_meta or {}
    metrics = model_meta.get("metrics") or {}
    labels_source = (
        list(class_labels)
        if class_labels is not None
        else list(model_meta.get("class_labels") or [])
    )
    matrix_source = metrics.get("confusion_matrix")
    if not matrix_source and isinstance(model_meta.get("confusion_matrix"), dict):
        cm_block = model_meta["confusion_matrix"]
        matrix_source = cm_block.get("matrix")
        if not labels_source:
            labels_source = list(cm_block.get("labels") or [])

    if not labels_source or not matrix_source:
        return _empty_diagnostics()

    labels = [str(label).strip() for label in labels_source]
    size = len(labels)
    cm = _normalize_matrix(matrix_source, size)
    class_map = map_model_classes(labels)

    # Group class indices by entity
    groups: Dict[str, List[int]] = {key: [] for key in MODEL_PAGE_TAB_ORDER}
    for index, label in enumerate(labels):
        entity = class_map[label]["entity_type"]
        groups.setdefault(entity, []).append(index)

    holdout_samples = int(sum(sum(row) for row in cm))
    correct_total = int(sum(cm[i][i] for i in range(size)))
    overall_accuracy = (
        _round4(_safe_div(correct_total, holdout_samples))
        if holdout_samples > 0
        else None
    )

    summary_counts = {key: len(groups.get(key, [])) for key in MODEL_PAGE_TAB_ORDER}
    populated_types = sum(1 for count in summary_counts.values() if count > 0)

    entity_performance: List[dict] = []
    for entity_type in MODEL_PAGE_TAB_ORDER:
        indices = groups.get(entity_type, [])
        stats = _entity_metrics(cm, indices)
        entity_performance.append(
            {
                "entity_type": entity_type,
                "entity_type_label": category_label_for_model_page(entity_type),
                **stats,
            }
        )

    return {
        "entity_summary": {
            "holdout_samples": holdout_samples,
            "overall_accuracy": overall_accuracy,
            "total_entity_types": populated_types,
            "steel_section_classes": summary_counts[CATEGORY_STRUCTURAL],
            "material_classes": summary_counts[CATEGORY_MATERIAL],
            "bolt_classes": summary_counts[CATEGORY_BOLT],
            "plate_classes": summary_counts[CATEGORY_PLATE],
            "other_classes": summary_counts[CATEGORY_MISC],
            "model_classes": size,
        },
        "entity_performance": entity_performance,
        "class_entity_map": class_map,
        "top_misclassifications": _top_misclassifications(cm, labels, class_map),
        "entity_tabs": list(MODEL_PAGE_TABS),
    }
