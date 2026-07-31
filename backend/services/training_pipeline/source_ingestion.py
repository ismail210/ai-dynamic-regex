"""Provenance-aware adapters for continuous-learning source data."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from config import settings
from services.dataset_manager import dataset_manager
from services.engineering.correction_dataset import list_corrections
from services.training_pipeline.hashing import content_hash, sample_id


FAMILY_PREFIXES = (
    "PIPE", "HSS", "MC", "WT", "HP", "MT", "ST", "2L",
    "W", "S", "M", "C", "L",
)


def _fold(value: Any) -> str:
    text = str(value or "").upper().strip().replace("×", "X")
    return "".join(ch for ch in text if ch.isalnum() or ch in {"/", "."})


def _family(value: Any) -> Optional[str]:
    folded = _fold(value)
    for prefix in FAMILY_PREFIXES:
        if folded.startswith(prefix):
            return prefix
    return None


def _base_sample(
    *,
    modality: str,
    source_type: str,
    source_id: str,
    token: str = "",
    label: Optional[str] = None,
    supervised: bool = False,
    features: Optional[dict] = None,
    provenance: Optional[dict] = None,
    quality_status: str = "unknown",
    metadata: Optional[dict] = None,
) -> dict:
    section = _fold(label) if label else None
    family = _family(section or token)
    payload = {
        "token": str(token or ""),
        "label": section,
        "family": family,
        "features": features or {},
        "supervised": supervised,
    }
    digest = content_hash(modality=modality, payload=payload)
    return {
        "sample_id": sample_id(
            modality=modality,
            source_type=source_type,
            source_id=source_id or digest[:12],
            content=digest,
        ),
        "modality": modality,
        "content_hash": digest,
        "token": str(token or ""),
        "family": family,
        "section": section,
        "label": section,
        "supervised": supervised,
        "split": "train",
        "quality_status": quality_status,
        "features": features or {},
        "provenance": {
            "source_type": source_type,
            "source_id": source_id,
            **(provenance or {}),
        },
        "parent_sample_id": None,
        "augmented": False,
        "metadata": metadata or {},
    }


def ingest_approved_reviews() -> List[dict]:
    frame = dataset_manager.load_approved_dataset()
    rows: List[dict] = []
    for _, item in frame.iterrows():
        token = str(item.get("token") or "").strip()
        label = str(item.get("class") or "").strip()
        if not token or not label:
            continue
        rows.append(
            _base_sample(
                modality="text",
                source_type="approved_review",
                source_id=str(item.get("unknown_id") or token),
                token=token,
                label=label,
                supervised=True,
                quality_status="approved",
                provenance={
                    "created_at": str(item.get("approved_at") or ""),
                    "actor": "reviewer",
                    "path": str(settings.approved_dataset_path),
                },
                metadata={"category": str(item.get("category") or "")},
            )
        )
    return rows


def ingest_corrections() -> List[dict]:
    rows: List[dict] = []
    for item in list_corrections(limit=100000):
        if not item.get("ready_for_training"):
            continue
        label = str(item.get("correct_label") or "").strip()
        if not label:
            continue
        prediction = item.get("prediction") or {}
        token = str(
            prediction.get("original_token")
            or prediction.get("token")
            or label
        )
        features = dict(item.get("input_features") or {})
        if item.get("correct_geometry"):
            features["geometry"] = item.get("correct_geometry")
        rows.append(
            _base_sample(
                modality="text",
                source_type="corrected_prediction",
                source_id=str(item.get("sample_id") or ""),
                token=token,
                label=label,
                supervised=True,
                features=features,
                quality_status="corrected",
                provenance={
                    "document_id": str(item.get("document_id") or ""),
                    "object_id": str(item.get("object_id") or ""),
                    "created_at": str(item.get("timestamp") or ""),
                    "actor": "engineer",
                    "path": str(settings.engineering_corrections_path),
                },
                metadata={"user_decision": item.get("user_decision")},
            )
        )
        if features.get("geometry") or item.get("correct_geometry"):
            rows.append(
                _base_sample(
                    modality="geometry",
                    source_type="corrected_prediction",
                    source_id=str(item.get("sample_id") or "") + ":geometry",
                    token=token,
                    label=label,
                    supervised=True,
                    features={
                        "geometry": features.get("geometry")
                        or item.get("correct_geometry")
                    },
                    quality_status="corrected",
                    provenance={
                        "document_id": str(item.get("document_id") or ""),
                        "object_id": str(item.get("object_id") or ""),
                        "created_at": str(item.get("timestamp") or ""),
                    },
                )
            )
    return rows


def ingest_historical_datasets() -> List[dict]:
    rows: List[dict] = []
    if settings.training_dataset_path.exists():
        frame = pd.read_csv(
            settings.training_dataset_path, dtype=str, keep_default_na=False
        )
        for index, item in frame.iterrows():
            token = str(item.get("token") or "").strip()
            label = str(item.get("class") or "").strip()
            if not token or not label:
                continue
            rows.append(
                _base_sample(
                    modality="text",
                    source_type="historical_aisc",
                    source_id=f"aisc:{index}:{token}",
                    token=token,
                    label=label,
                    supervised=True,
                    quality_status="historical",
                    provenance={"path": str(settings.training_dataset_path)},
                )
            )
    return rows


def ingest_paired_takeoff() -> List[dict]:
    rows: List[dict] = []
    path = settings.paired_dataset_path
    if not path.exists():
        return rows
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    for index, item in frame.iterrows():
        token = str(
            item.get("token")
            or item.get("pdf_token")
            or item.get("excel_shape")
            or ""
        ).strip()
        label = str(
            item.get("target_section")
            or item.get("excel_shape")
            or item.get("class")
            or token
        ).strip()
        if not label:
            continue
        supervised = str(item.get("validation_status") or "").lower() in {
            "match",
            "approved",
            "pdf+excel",
            "excel_only",
            "",
        } or bool(item.get("excel_shape"))
        features = {
            "page": item.get("page_number") or item.get("page"),
            "bbox": item.get("bbox"),
            "line_context": item.get("line_context"),
            "geometry_features": item.get("geometry_features"),
            "graph_features": item.get("graph_features"),
            "engineering_rules": item.get("engineering_rules"),
        }
        rows.append(
            _base_sample(
                modality="text",
                source_type="excel_takeoff",
                source_id=f"paired:{index}:{label}",
                token=token or label,
                label=label,
                supervised=supervised,
                features=features,
                quality_status=str(item.get("validation_status") or "paired"),
                provenance={"path": str(path)},
                metadata={"pair_id": item.get("pair_id") or item.get("source_pair")},
            )
        )
        if item.get("geometry_features"):
            rows.append(
                _base_sample(
                    modality="geometry",
                    source_type="excel_takeoff",
                    source_id=f"paired-geo:{index}:{label}",
                    token=token or label,
                    label=label,
                    supervised=supervised,
                    features={"geometry_features": item.get("geometry_features")},
                    quality_status=str(item.get("validation_status") or "paired"),
                )
            )
        if item.get("graph_features"):
            rows.append(
                _base_sample(
                    modality="graph",
                    source_type="excel_takeoff",
                    source_id=f"paired-graph:{index}:{label}",
                    token=token or label,
                    label=label,
                    supervised=supervised,
                    features={"graph_features": item.get("graph_features")},
                    quality_status=str(item.get("validation_status") or "paired"),
                )
            )
    return rows


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ingest_engineering_artifacts() -> List[dict]:
    """PDF extraction, geometry, graph, and prediction artifacts."""

    rows: List[dict] = []
    root = settings.engineering_artifacts_dir
    if not root.exists():
        return rows
    for document_dir in sorted(root.iterdir()):
        if not document_dir.is_dir():
            continue
        multimodal = document_dir / "multimodal"
        base = multimodal if multimodal.exists() else document_dir
        document = _load_json(base / "document.json") or {}
        geometry = _load_json(base / "geometry.json") or {}
        graph = _load_json(base / "graph.json") or {}
        predictions = _load_json(base / "predictions.json") or {}
        validation = _load_json(base / "validation.json") or {}
        document_id = (
            document.get("document_id")
            or document_dir.name
        )
        pred_rows = predictions.get("predictions") or predictions.get("items") or []
        for index, prediction in enumerate(pred_rows):
            token = str(
                prediction.get("original_token")
                or prediction.get("token")
                or ""
            )
            label = str(
                prediction.get("section")
                or prediction.get("predicted_shape")
                or prediction.get("corrected_token")
                or ""
            )
            supervised = str(prediction.get("review_status") or "") in {
                "auto_accepted",
                "approved",
            } or bool(prediction.get("database_match")) is False and False
            # Unreviewed predictions stay unlabeled for diagnostics.
            if prediction.get("review_status") in {"approved", "auto_accepted"}:
                supervised = True
            features_bundle = prediction.get("features") or {}
            text_features = features_bundle.get("text") or {}
            ocr_features = features_bundle.get("ocr") or {}
            geometry_features = features_bundle.get("geometry") or {}
            graph_features = features_bundle.get("graph") or {}
            engineering_features = (
                features_bundle.get("engineering_rules") or {}
            )
            fusion = features_bundle.get("fusion") or {}
            rows.append(
                _base_sample(
                    modality="text",
                    source_type="pdf_extraction",
                    source_id=f"{document_id}:pred:{index}",
                    token=token,
                    label=label if supervised else None,
                    supervised=supervised,
                    features={
                        "extraction": text_features,
                        "surrounding_text": text_features.get("surrounding_text"),
                    },
                    quality_status=str(
                        text_features.get("extraction_status") or "extracted"
                    ),
                    provenance={
                        "document_id": document_id,
                        "object_id": str(
                            prediction.get("object_id")
                            or prediction.get("component_id")
                            or ""
                        ),
                        "path": str(base),
                    },
                    metadata={"review_status": prediction.get("review_status")},
                )
            )
            rows.append(
                _base_sample(
                    modality="ocr",
                    source_type="pdf_extraction",
                    source_id=f"{document_id}:ocr:{index}",
                    token=token,
                    label=label if supervised else None,
                    supervised=supervised,
                    features={"ocr": ocr_features},
                    quality_status=str(
                        text_features.get("extraction_status") or "extracted"
                    ),
                    provenance={"document_id": document_id},
                )
            )
            rows.append(
                _base_sample(
                    modality="layout",
                    source_type="pdf_extraction",
                    source_id=f"{document_id}:layout:{index}",
                    token=token,
                    label=label if supervised else None,
                    supervised=supervised,
                    features={
                        "layout": {
                            "page": text_features.get("page"),
                            "bbox": text_features.get("bbox"),
                            "reading_order": text_features.get(
                                "reading_order"
                            ),
                            "rotation": text_features.get("rotation"),
                            "font_size": text_features.get("font_size"),
                            "neighbors": text_features.get("neighbors") or [],
                        }
                    },
                    quality_status="extracted",
                    provenance={"document_id": document_id},
                )
            )
            if geometry_features or prediction.get("geometry_preview"):
                rows.append(
                    _base_sample(
                        modality="geometry",
                        source_type="future_geometry",
                        source_id=f"{document_id}:geo:{index}",
                        token=token,
                        label=label if supervised else None,
                        supervised=supervised,
                        features={
                            "geometry": geometry_features,
                            "geometry_preview": prediction.get("geometry_preview"),
                        },
                        quality_status="extracted",
                        provenance={"document_id": document_id},
                    )
                )
            if graph_features or prediction.get("graph_preview"):
                rows.append(
                    _base_sample(
                        modality="graph",
                        source_type="future_graph",
                        source_id=f"{document_id}:graph:{index}",
                        token=token,
                        label=label if supervised else None,
                        supervised=supervised,
                        features={
                            "graph": graph_features,
                            "graph_preview": prediction.get("graph_preview"),
                        },
                        quality_status="extracted",
                        provenance={"document_id": document_id},
                    )
                )
            rows.append(
                _base_sample(
                    modality="engineering",
                    source_type="fusion_prediction",
                    source_id=f"{document_id}:engineering:{index}",
                    token=token,
                    label=label if supervised else None,
                    supervised=supervised,
                    features={
                        "engineering_rules": engineering_features,
                    },
                    quality_status="extracted",
                    provenance={"document_id": document_id},
                )
            )
            rows.append(
                _base_sample(
                    modality="fusion",
                    source_type="fusion_prediction",
                    source_id=f"{document_id}:fusion:{index}",
                    token=token,
                    label=label if supervised else None,
                    supervised=supervised,
                    features={
                        "fusion": fusion,
                        "evidence": prediction.get("evidence") or {},
                        "contributions": (
                            (prediction.get("explanation") or {}).get(
                                "contributions"
                            )
                            or fusion.get("weights")
                            or {}
                        ),
                        "text": text_features,
                        "geometry": geometry_features,
                        "graph": graph_features,
                        "ocr": ocr_features,
                        "engineering_rules": engineering_features,
                    },
                    quality_status="extracted",
                    provenance={"document_id": document_id},
                )
            )

        # Document-level unlabeled geometry/graph inventory for future models.
        for index, obj in enumerate((geometry.get("objects") or [])[:500]):
            rows.append(
                _base_sample(
                    modality="geometry",
                    source_type="future_geometry",
                    source_id=f"{document_id}:geom-obj:{index}",
                    token="",
                    label=None,
                    supervised=False,
                    features={"object": obj},
                    quality_status="unlabeled",
                    provenance={"document_id": document_id},
                )
            )
        for index, node in enumerate((graph.get("nodes") or [])[:500]):
            rows.append(
                _base_sample(
                    modality="graph",
                    source_type="future_graph",
                    source_id=f"{document_id}:graph-node:{index}",
                    token=str(node.get("text") or ""),
                    label=None,
                    supervised=False,
                    features={"node": node},
                    quality_status="unlabeled",
                    provenance={"document_id": document_id},
                )
            )
        if validation:
            rows.append(
                _base_sample(
                    modality="fusion",
                    source_type="validation_artifact",
                    source_id=f"{document_id}:validation",
                    token="",
                    label=None,
                    supervised=False,
                    features={"validation_summary": validation.get("summary") or {}},
                    quality_status="diagnostic",
                    provenance={"document_id": document_id},
                )
            )
    return rows


def dedupe_samples(samples: Iterable[dict]) -> List[dict]:
    """Deduplicate by provenance identity and content hash."""

    seen = set()
    unique: List[dict] = []
    for sample in samples:
        key = (
            sample.get("provenance", {}).get("source_type"),
            sample.get("provenance", {}).get("source_id"),
            sample.get("content_hash"),
            sample.get("modality"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(sample)
    return unique


def ingest_all_sources() -> Dict[str, List[dict]]:
    """Collect and dedupe samples across all continuous-learning sources."""

    buckets = {
        "approved_review": ingest_approved_reviews(),
        "corrected_prediction": ingest_corrections(),
        "historical_aisc": ingest_historical_datasets(),
        "excel_takeoff": ingest_paired_takeoff(),
        "engineering_artifacts": ingest_engineering_artifacts(),
    }
    combined = dedupe_samples(
        sample for group in buckets.values() for sample in group
    )
    by_modality: Dict[str, List[dict]] = {
        "text": [],
        "ocr": [],
        "layout": [],
        "geometry": [],
        "graph": [],
        "engineering": [],
        "fusion": [],
    }
    for sample in combined:
        modality = sample.get("modality")
        if modality in by_modality:
            by_modality[modality].append(sample)
    return {
        "by_modality": by_modality,
        "source_counts": {key: len(value) for key, value in buckets.items()},
        "total": len(combined),
        "supervised_total": sum(1 for sample in combined if sample.get("supervised")),
    }


def source_inventory() -> Dict[str, Any]:
    ingested = ingest_all_sources()
    class_counts: Counter = Counter()
    for sample in ingested["by_modality"]["text"]:
        if sample.get("supervised") and sample.get("label"):
            class_counts[str(sample["label"])] += 1
    return {
        "sources": ingested["source_counts"],
        "total_samples": ingested["total"],
        "supervised_samples": ingested["supervised_total"],
        "modality_counts": {
            key: len(value) for key, value in ingested["by_modality"].items()
        },
        "top_labels": dict(class_counts.most_common(20)),
    }
