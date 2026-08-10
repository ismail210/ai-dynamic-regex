"""Auto-generate geometry, graph, and fusion training samples from project data.

Sources (no manual annotation):
  - paired PDF + Excel under training/pdf and training/excel
  - paired_takeoff_dataset.csv (when present)
  - engineering_corrections.jsonl
  - approved_dataset.csv
  - persisted multimodal artifacts

Training entry points call the existing MobileNet index builder, GraphSAGE
trainer, and fusion MLP trainer; they do not rewrite those models.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from config import settings
from services.artifact_store import read_artifact
from services.database_loader import search_similar_shapes
from services.document_registry import document_source
from services.engineering.geometry_adapters import extract_geometry_document
from services.engineering.rule_engine import evaluate_engineering_rules
from services.engineering.structural_graph import build_structural_graph
from services.exact_section_predictor import predict_exact_sections
from services.extraction_engine import extract_engineering_document
from services.multimodal.encoder_registry import encoder_registry
from services.multimodal.feature_providers import (
    GeometryFeatureProvider,
    GraphFeatureProvider,
)
from services.multimodal.modular_fusion import FeatureFusion, unified_multimodal_fusion
from services.takeoff.ground_truth_excel import parse_ground_truth_excel
from services.takeoff.paired_dataset_builder import list_training_pairs


logger = logging.getLogger("takeoff.neural_dataset")

NEURAL_DATASET_DIR = settings.training_dir / "datasets" / "neural"
GEOMETRY_DIR = NEURAL_DATASET_DIR / "geometry"
GRAPH_DIR = NEURAL_DATASET_DIR / "graph"
FUSION_DIR = NEURAL_DATASET_DIR / "fusion"
CROPS_DIR = GEOMETRY_DIR / "crops"

# Fallback role supervision used only when the rule engine did not determine a
# member role. A shape family constrains the section, not always the role:
# channels and tees are not beams by virtue of their family, so they are left
# as "other" rather than teaching the role head a label the drawing never
# stated.
_ROLE_FROM_FAMILY = {
    "W": "beam",
    "S": "beam",
    "M": "beam",
    "HP": "column",
    "HSS": "column",
    "PIPE": "column",
    "L": "brace",
    "2L": "brace",
    "PL": "plate",
    "PLATE": "plate",
    "C": "other",
    "MC": "other",
    "WT": "other",
    "MT": "other",
    "ST": "other",
}


def _norm(token: str) -> str:
    return str(token or "").upper().replace(" ", "").replace("-", "")


def _family(section: str) -> str:
    text = _norm(section)
    for prefix in ("HSS", "PIPE", "PLATE", "2L", "WT", "MC", "HP"):
        if text.startswith(prefix):
            return prefix
    return "".join(ch for ch in text if ch.isalpha())[:3] or "other"


def _member_role(section: str, rules_role: Optional[str] = None) -> str:
    role = str(rules_role or "").lower().strip()
    if role in {"beam", "column", "brace", "plate", "connection", "other"}:
        return role
    return _ROLE_FROM_FAMILY.get(_family(section), "other")


def _parse_bbox(value: Any) -> Optional[List[float]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            count += 1
    return count


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _match_ground_truth(
    token: str,
    gt_by_label: Dict[str, dict],
) -> Optional[dict]:
    from difflib import SequenceMatcher

    norm = _norm(token)
    if not norm:
        return None
    hit = gt_by_label.get(norm)
    if hit:
        return hit
    if not gt_by_label:
        return None
    nearest_label, nearest_score = max(
        (
            (label, SequenceMatcher(None, norm, label).ratio())
            for label in gt_by_label
        ),
        key=lambda item: item[1],
    )
    if nearest_score >= 0.78:
        return gt_by_label[nearest_label]
    return None


def _save_geometry_crop(
    *,
    pdf_path: Path,
    page_number: int,
    bbox: List[float],
    section: str,
    sample_key: str,
) -> Optional[str]:
    """Persist one reusable crop next to the geometry dataset."""

    try:
        import fitz
        from services.multimodal.geometry_ai import _crop, _page_image
    except ImportError:
        return None
    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in section)[:48]
    destination = CROPS_DIR / f"{safe}__{sample_key}.png"
    if destination.exists():
        return str(destination)
    try:
        with fitz.open(str(pdf_path)) as document:
            if page_number < 1 or page_number > document.page_count:
                return None
            image = _crop(_page_image(document.load_page(page_number - 1)), bbox)
            image.save(destination)
        return str(destination)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.debug("geometry crop skipped %s: %s", sample_key, exc)
        return None


def _fusion_candidates(
    token: str,
    correct_section: str,
    *,
    geometry_score: float,
    graph_score: float,
) -> List[Any]:
    """Build a candidate list that always includes the Excel/correction label."""

    from services.exact_section_predictor import ExactSectionCandidate

    correct = _norm(correct_section)
    evidence = {
        "text": 0.55,
        "geometry": geometry_score,
        "graph": graph_score,
    }
    candidates: List[Any] = list(
        predict_exact_sections(token or correct_section, limit=8)
    )
    shapes = {_norm(getattr(item, "shape", None) or item.get("shape")) for item in candidates}

    def _dict_candidates() -> List[dict]:
        similar = search_similar_shapes(correct_section, limit=5, minimum_score=0.2)
        payload = [
            {
                "shape": correct_section,
                "confidence": 0.9,
                "text_similarity": 0.55,
                "evidence": dict(evidence),
            }
        ]
        for item in similar:
            shape = str(item.get("shape") or "")
            if _norm(shape) == correct:
                continue
            score = float(item.get("similarity") or 0.4)
            payload.append(
                {
                    "shape": shape,
                    "confidence": score,
                    "text_similarity": score,
                    "evidence": {
                        "text": score,
                        "geometry": max(0.1, geometry_score - 0.15),
                        "graph": max(0.1, graph_score - 0.1),
                    },
                }
            )
        return payload

    if not candidates:
        return _dict_candidates()
    if correct and correct not in shapes:
        candidates.insert(
            0,
            ExactSectionCandidate(
                shape=correct_section,
                confidence=0.92,
                text_similarity=0.55,
                evidence=dict(evidence),
            ),
        )
    return candidates


def _build_fusion_sample(
    *,
    token_record: dict,
    correct_section: str,
    geometry_features: dict,
    graph_features: dict,
    rules: dict,
) -> Optional[dict]:
    raw = str(token_record.get("text") or token_record.get("raw_text") or "")
    normalized = str(
        token_record.get("normalized_text") or _norm(raw) or correct_section
    )
    geometry_score = float(geometry_features.get("similarity") or 0.0)
    graph_score = float(
        graph_features.get("structural_consistency")
        or graph_features.get("graph_consistency")
        or graph_features.get("graph_confidence")
        or 0.0
    )
    candidates = _fusion_candidates(
        normalized,
        correct_section,
        geometry_score=geometry_score,
        graph_score=graph_score,
    )
    if len(candidates) < 2:
        return None
    exact = predict_exact_sections(normalized or correct_section, limit=1)
    model_probability = float(exact[0].confidence) if exact else 0.5
    encodings = encoder_registry.encode_all(
        {
            "text": {
                "token": normalized,
                "model_probability": model_probability,
                "extraction_confidence": float(token_record.get("confidence") or 0.5),
                "regex_confidence": 0.0,
                "candidates": candidates,
            },
            "ocr": {
                "original": raw or normalized,
                "corrected": normalized,
                "confidence": float(token_record.get("confidence") or 0.5),
                "repairs": [],
            },
            "layout": {
                "bbox": token_record.get("bbox"),
                "page": token_record.get("page"),
                "reading_order": token_record.get("reading_order"),
                "font_size": token_record.get("font_size"),
                "rotation": token_record.get("rotation"),
                "member_role": rules.get("member_role"),
                "neighbors": (token_record.get("context") or {}).get("neighbor_text")
                or [],
            },
            "geometry": {"geometry": geometry_features},
            "graph": {"graph": graph_features},
            "engineering_rules": {"rules": rules},
        }
    )
    fused = FeatureFusion().fuse(encodings)
    # Score candidates with the same attention path used at inference so the
    # stored modality_scores match production fusion inputs.
    scored = unified_multimodal_fusion.predict(
        encodings=encodings,
        candidates=candidates,
        fallback_section=correct_section,
    ).candidate_scores
    if len(scored) < 2:
        return None
    shapes = {_norm(item.get("shape")) for item in scored}
    if _norm(correct_section) not in shapes:
        scored.append(
            {
                "shape": correct_section,
                "score": 0.85,
                "modality_scores": {
                    "text": 0.55,
                    "ocr": float(encodings["ocr"].confidence),
                    "layout": float(encodings["layout"].confidence),
                    "geometry": geometry_score,
                    "graph": graph_score,
                    "engineering_rules": float(rules.get("score") or 0.5),
                },
            }
        )
    return {
        "fused_vector": fused.vector,
        "candidates": scored[:8],
        "correct_section": correct_section,
        "text_prediction": normalized,
        "geometry_prediction": (
            ((geometry_features.get("geometry_candidates") or [{}])[0] or {}).get(
                "role"
            )
            or geometry_features.get("geometry_role")
            or correct_section
        ),
        "graph_prediction": graph_features.get("graph_prediction")
        or rules.get("member_role"),
        "confidence": float(token_record.get("confidence") or model_probability),
    }


def _samples_from_pair(pair: dict) -> Dict[str, Any]:
    """Extract one PDF/Excel pair into geometry, graph, and fusion samples."""

    pdf_path = Path(pair["pdf_path"])
    excel_path = Path(pair["excel_path"])
    pair_id = str(pair.get("id") or pdf_path.stem)
    document = extract_engineering_document(pdf_path, document_id=f"pair_{pair_id}")
    geometry = extract_geometry_document(pdf_path, document_structure=document)
    graph = build_structural_graph(document, geometry)
    gt = parse_ground_truth_excel(excel_path)
    gt_by_label = {
        _norm(item["canonical_label"]): item for item in gt.get("aggregates") or []
    }

    geometry_provider = GeometryFeatureProvider()
    graph_provider = GraphFeatureProvider()
    geometry_samples: List[dict] = []
    fusion_samples: List[dict] = []
    node_labels: Dict[str, dict] = {}
    seen_geometry: set[Tuple[str, int, str, str]] = set()
    per_label_crops: Dict[str, int] = defaultdict(int)

    for token_record in document.get("engineering_tokens") or []:
        token = str(
            token_record.get("normalized_text") or token_record.get("text") or ""
        )
        gt_hit = _match_ground_truth(token, gt_by_label)
        if not gt_hit:
            continue
        correct_section = str(gt_hit["canonical_label"]).upper().replace(" ", "")
        context = {
            "token": token_record,
            "document": document,
            "geometry": geometry,
            "graph": graph,
        }
        geometry_features = geometry_provider.extract(context)
        graph_features = graph_provider.extract(context)
        rules = evaluate_engineering_rules(
            token=token,
            predicted_shape=correct_section,
            geometry=geometry_features,
            graph=graph,
            graph_preview=graph_features,
        ).to_dict()

        bbox = _parse_bbox(token_record.get("bbox"))
        page = int(token_record.get("page") or 0)
        if bbox and page > 0 and per_label_crops[correct_section] < 24:
            key = (
                pdf_path.name,
                page,
                ",".join(f"{v:.1f}" for v in bbox),
                correct_section,
            )
            if key not in seen_geometry:
                seen_geometry.add(key)
                sample_key = f"{pair_id}_{page}_{len(geometry_samples)}"
                image_path = _save_geometry_crop(
                    pdf_path=pdf_path,
                    page_number=page,
                    bbox=bbox,
                    section=correct_section,
                    sample_key=sample_key,
                )
                geometry_samples.append(
                    {
                        "pdf_path": str(pdf_path),
                        "page_number": page,
                        "bbox": bbox,
                        "section": correct_section,
                        "image_path": image_path,
                        "geometry_features": geometry_features.get("geometry_features")
                        or geometry_features.get("object")
                        or {},
                        "pair_id": pair_id,
                        "source": "paired_pdf_excel",
                    }
                )
                per_label_crops[correct_section] += 1

        source_ids = [
            token_record.get("token_id"),
            (token_record.get("line") or {}).get("id"),
            *(token_record.get("source_word_ids") or []),
        ]
        matched_node = None
        for node in graph.get("nodes") or []:
            if str(node.get("source_id") or "") in {
                str(item) for item in source_ids if item
            }:
                matched_node = node
                break
        if matched_node:
            predicted_text = _norm(token)
            node_labels[str(matched_node.get("node_id"))] = {
                "member_role": _member_role(
                    correct_section, rules.get("member_role")
                ),
                "consistent": 1.0,
                "missing_label": float(not predicted_text),
                "incorrect_label": float(predicted_text != _norm(correct_section)),
            }

        fusion = _build_fusion_sample(
            token_record=token_record,
            correct_section=correct_section,
            geometry_features=geometry_features,
            graph_features=graph_features,
            rules=rules,
        )
        if fusion:
            fusion["pair_id"] = pair_id
            fusion["source"] = "paired_pdf_excel"
            fusion_samples.append(fusion)

    # Excel-only members → missing-label graph supervision on nearby geometry.
    pdf_norms = {
        _norm(str(token.get("normalized_text") or token.get("text") or ""))
        for token in document.get("engineering_tokens") or []
    }
    for label, agg in gt_by_label.items():
        if label in pdf_norms:
            continue
        for node in graph.get("nodes") or []:
            kind = str(node.get("kind") or "")
            if kind not in {"beam", "column", "brace", "plate", "geometry"}:
                continue
            node_id = str(node.get("node_id") or "")
            if not node_id or node_id in node_labels:
                continue
            node_labels[node_id] = {
                "member_role": _member_role(agg["canonical_label"]),
                "consistent": 0.0,
                "missing_label": 1.0,
                "incorrect_label": 0.0,
            }
            break

    graph_path = GRAPH_DIR / f"{pair_id}.json"
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(
            {
                "nodes": graph.get("nodes") or [],
                "edges": graph.get("edges") or [],
                "stats": graph.get("stats") or {},
                "schema": graph.get("schema") or {},
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    graph_sample = {
        "graph_path": str(graph_path),
        "pair_id": pair_id,
        "node_labels": node_labels,
        "source": "paired_pdf_excel",
    }
    return {
        "pair_id": pair_id,
        "geometry": geometry_samples,
        "graph": [graph_sample] if node_labels else [],
        "fusion": fusion_samples,
        "matched_tokens": len(geometry_samples),
        "graph_nodes_labeled": len(node_labels),
    }


def _samples_from_corrections() -> Dict[str, List[dict]]:
    """Reuse reviewed corrections when artifacts still exist."""

    geometry_samples: List[dict] = []
    fusion_samples: List[dict] = []
    graph_labels: Dict[str, Dict[str, dict]] = defaultdict(dict)
    documents: Dict[str, Dict[str, Any]] = {}
    path = settings.engineering_corrections_path
    if not path.exists():
        return {"geometry": [], "graph": [], "fusion": []}

    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            correction = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not correction.get("ready_for_training"):
            continue
        document_id = str(correction.get("document_id") or "")
        object_id = str(correction.get("object_id") or "")
        correct_section = str(correction.get("correct_label") or "")
        if not document_id or not object_id or not correct_section:
            continue
        if document_id not in documents:
            prediction_artifact = read_artifact(document_id, "predictions.json") or {}
            documents[document_id] = {
                "predictions": prediction_artifact.get("predictions") or [],
                "geometry": read_artifact(document_id, "geometry.json") or {},
                "graph": read_artifact(document_id, "graph.json") or {},
            }
        artifacts = documents[document_id]
        prediction = next(
            (
                item
                for item in artifacts["predictions"]
                if str(item.get("object_id") or item.get("component_id") or "")
                == object_id
            ),
            None,
        )
        if not prediction:
            continue
        geometry_evidence = (prediction.get("features") or {}).get("geometry") or {}
        geometry_object = geometry_evidence.get("object") or {}
        bbox = _parse_bbox(
            geometry_object.get("bbox") or prediction.get("bounding_box")
        )
        page = int(prediction.get("page_number") or 0)
        if bbox and page:
            try:
                source = document_source(document_id)
            except (FileNotFoundError, ValueError):
                source = None
            if source:
                geometry_samples.append(
                    {
                        "pdf_path": str(source),
                        "page_number": page,
                        "bbox": bbox,
                        "section": correct_section,
                        "geometry_features": geometry_evidence.get("geometry_features")
                        or {},
                        "source": "engineering_corrections",
                    }
                )

        fusion = (prediction.get("features") or {}).get("fusion") or {}
        fused_vector = (fusion.get("fused_features") or {}).get("vector") or []
        candidates = fusion.get("candidate_scores") or []
        if fused_vector and candidates:
            fusion_samples.append(
                {
                    "fused_vector": fused_vector,
                    "candidates": candidates,
                    "correct_section": correct_section,
                    "source": "engineering_corrections",
                }
            )

        role = (
            ((prediction.get("features") or {}).get("engineering_rules") or {}).get(
                "member_role"
            )
            or prediction.get("entity_type")
            or "other"
        )
        graph_node = next(
            (
                node
                for node in artifacts["graph"].get("nodes") or []
                if str(node.get("source_id") or "") == object_id
            ),
            None,
        )
        if graph_node:
            graph_labels[document_id][str(graph_node.get("node_id"))] = {
                "member_role": _member_role(correct_section, role),
                "consistent": 1.0,
                "missing_label": float(not prediction.get("raw_text")),
                "incorrect_label": float(
                    _norm(prediction.get("section") or "") != _norm(correct_section)
                ),
            }

    graph_samples = []
    for document_id, labels in graph_labels.items():
        graph = documents.get(document_id, {}).get("graph") or {}
        if not graph:
            continue
        graph_path = GRAPH_DIR / f"artifact_{document_id}.json"
        GRAPH_DIR.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(
            json.dumps(
                {
                    "nodes": graph.get("nodes") or [],
                    "edges": graph.get("edges") or [],
                    "stats": graph.get("stats") or {},
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        graph_samples.append(
            {
                "graph_path": str(graph_path),
                "node_labels": labels,
                "source": "engineering_corrections",
            }
        )
    return {
        "geometry": geometry_samples,
        "graph": graph_samples,
        "fusion": fusion_samples,
    }


def _samples_from_paired_csv() -> List[dict]:
    """Lightweight geometry samples from the existing paired CSV."""

    path = settings.paired_dataset_path
    if not path.exists():
        return []
    try:
        import pandas as pd
    except ImportError:
        return []
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    samples: List[dict] = []
    seen: set[Tuple[str, str, str]] = set()
    for row in frame.to_dict(orient="records"):
        if str(row.get("validation_status") or "") != "ground_truth_match":
            continue
        section = _norm(row.get("canonical_label") or "")
        bbox = _parse_bbox(row.get("bbox"))
        page = int(float(row.get("page_number") or 0) or 0)
        pdf_name = str(row.get("pdf_file") or "")
        if not section or not bbox or page < 1 or not pdf_name:
            continue
        pdf_path = settings.training_pdf_dir / pdf_name
        if not pdf_path.exists():
            continue
        key = (pdf_name, section, ",".join(f"{v:.1f}" for v in bbox))
        if key in seen:
            continue
        seen.add(key)
        features = row.get("geometry_features") or "{}"
        try:
            geometry_features = json.loads(features) if isinstance(features, str) else {}
        except json.JSONDecodeError:
            geometry_features = {}
        samples.append(
            {
                "pdf_path": str(pdf_path),
                "page_number": page,
                "bbox": bbox,
                "section": section,
                "geometry_features": geometry_features.get("geometry_features")
                or geometry_features.get("object")
                or geometry_features,
                "source": "paired_takeoff_dataset.csv",
            }
        )
    return samples


def _samples_from_approved() -> List[dict]:
    """Approved review labels become fusion distractor anchors only when rich."""

    path = settings.approved_dataset_path
    if not path.exists():
        return []
    try:
        import pandas as pd
    except ImportError:
        return []
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    samples: List[dict] = []
    for row in frame.to_dict(orient="records"):
        token = str(row.get("token") or "").strip()
        label = str(row.get("class") or "").strip()
        if not token or not label or _family(label) in {"", "other"}:
            continue
        # Family-only labels are not exact-section fusion targets.
        if _norm(label) == _family(label):
            continue
        fusion = _build_fusion_sample(
            token_record={
                "text": token,
                "normalized_text": _norm(token),
                "confidence": 0.7,
                "bbox": [0, 0, 10, 10],
                "page": 1,
            },
            correct_section=_norm(label),
            geometry_features={"available": False, "similarity": 0.2},
            graph_features={"graph_consistency": 0.35, "degree": 0},
            rules={"score": 0.6, "member_role": _member_role(label)},
        )
        if fusion:
            fusion["source"] = "approved_dataset.csv"
            samples.append(fusion)
    return samples


def build_neural_training_samples(
    *,
    persist: bool = True,
    include_pairs: bool = True,
) -> Dict[str, list]:
    """
    Automatically assemble geometry / graph / fusion samples.

    Pair extraction is the primary supervised source. Corrections, the paired
    CSV, and approved labels fill gaps without requiring new annotation.
    """

    NEURAL_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    geometry: List[dict] = []
    graph: List[dict] = []
    fusion: List[dict] = []
    pair_reports: List[dict] = []

    if include_pairs:
        for pair in list_training_pairs():
            if not pair.get("ready"):
                continue
            logger.info("neural dataset pair=%s", pair.get("id"))
            try:
                report = _samples_from_pair(pair)
            except Exception as exc:  # keep one bad pair from aborting the rest
                logger.exception("pair %s failed: %s", pair.get("id"), exc)
                pair_reports.append(
                    {"pair_id": pair.get("id"), "error": str(exc)}
                )
                continue
            geometry.extend(report["geometry"])
            graph.extend(report["graph"])
            fusion.extend(report["fusion"])
            pair_reports.append(
                {
                    "pair_id": report["pair_id"],
                    "geometry_samples": len(report["geometry"]),
                    "graph_nodes_labeled": report["graph_nodes_labeled"],
                    "fusion_samples": len(report["fusion"]),
                }
            )

    corrections = _samples_from_corrections()
    geometry.extend(corrections["geometry"])
    graph.extend(corrections["graph"])
    fusion.extend(corrections["fusion"])
    geometry.extend(_samples_from_paired_csv())
    fusion.extend(_samples_from_approved())

    # Deduplicate geometry by crop key while preferring rows that already have
    # an on-disk image_path from the pair builder.
    unique_geometry: Dict[Tuple[str, int, str, str], dict] = {}
    for sample in geometry:
        bbox = sample.get("bbox") or []
        key = (
            str(sample.get("pdf_path") or sample.get("image_path") or ""),
            int(sample.get("page_number") or 0),
            ",".join(f"{float(v):.1f}" for v in bbox) if bbox else "",
            _norm(sample.get("section") or ""),
        )
        previous = unique_geometry.get(key)
        if previous is None or (
            sample.get("image_path") and not previous.get("image_path")
        ):
            unique_geometry[key] = sample
    geometry = list(unique_geometry.values())

    payload = {
        "geometry": geometry,
        "graph": graph,
        "fusion": fusion,
    }
    if persist:
        counts = {
            "geometry": _write_jsonl(GEOMETRY_DIR / "samples.jsonl", geometry),
            "graph": _write_jsonl(GRAPH_DIR / "samples.jsonl", graph),
            "fusion": _write_jsonl(FUSION_DIR / "samples.jsonl", fusion),
        }
        manifest = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "counts": counts,
            "graph_node_labels": sum(
                len(item.get("node_labels") or {}) for item in graph
            ),
            "pairs": pair_reports,
            "paths": {
                "geometry": str(GEOMETRY_DIR / "samples.jsonl"),
                "graph": str(GRAPH_DIR / "samples.jsonl"),
                "fusion": str(FUSION_DIR / "samples.jsonl"),
                "crops": str(CROPS_DIR),
            },
            "model_targets": {
                "geometry": str(settings.geometry_embedding_index_path),
                "graph": str(settings.graphsage_model_path),
                "fusion": str(settings.fusion_model_path),
            },
        }
        (NEURAL_DATASET_DIR / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        payload["manifest"] = manifest
    return payload


def load_persisted_neural_samples() -> Dict[str, list]:
    """Load previously generated JSONL datasets, hydrating graph payloads."""

    geometry = _load_jsonl(GEOMETRY_DIR / "samples.jsonl")
    fusion = _load_jsonl(FUSION_DIR / "samples.jsonl")
    graph_rows = _load_jsonl(GRAPH_DIR / "samples.jsonl")
    graph: List[dict] = []
    for row in graph_rows:
        graph_doc = row.get("graph")
        if graph_doc is None and row.get("graph_path"):
            path = Path(row["graph_path"])
            if path.exists():
                graph_doc = json.loads(path.read_text(encoding="utf-8"))
        if not graph_doc or not row.get("node_labels"):
            continue
        graph.append({"graph": graph_doc, "node_labels": row["node_labels"]})
    return {"geometry": geometry, "graph": graph, "fusion": fusion}


def train_neural_models(
    *,
    rebuild_dataset: bool = False,
    modalities: Optional[Iterable[str]] = None,
    min_samples: Optional[int] = None,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    """Train geometry / graph / fusion using persisted or freshly built samples."""

    from services.multimodal.geometry_ai import build_geometry_embedding_index
    from services.multimodal.graph_ai import train_graphsage
    from services.multimodal.learned_fusion import train_fusion_model

    wanted = set(modalities or ("geometry", "graph", "fusion"))
    if rebuild_dataset or not (GEOMETRY_DIR / "samples.jsonl").exists():
        build_neural_training_samples(persist=True)
    samples = load_persisted_neural_samples()
    thresholds = {
        "geometry": min_samples
        if min_samples is not None
        else settings.geometry_min_samples,
        "graph": min_samples if min_samples is not None else settings.graph_min_samples,
        "fusion": min_samples
        if min_samples is not None
        else settings.fusion_min_samples,
    }
    model_paths = {
        "geometry": settings.geometry_embedding_index_path,
        "graph": settings.graphsage_model_path,
        "fusion": settings.fusion_model_path,
    }
    trainers = {
        "geometry": build_geometry_embedding_index,
        "graph": train_graphsage,
        "fusion": train_fusion_model,
    }
    results: Dict[str, Any] = {}
    for modality, trainer in trainers.items():
        if modality not in wanted:
            continue
        if skip_existing and model_paths[modality].exists():
            results[modality] = {
                "trained": False,
                "skipped_existing": True,
                "path": str(model_paths[modality]),
            }
            logger.info(
                "skipping %s — model already exists at %s",
                modality,
                model_paths[modality],
            )
            continue
        rows = samples[modality]
        sample_count = (
            sum(len(row.get("node_labels") or {}) for row in rows)
            if modality == "graph"
            else len(rows)
        )
        required = int(thresholds[modality])
        if sample_count < required:
            results[modality] = {
                "trained": False,
                "samples": sample_count,
                "required": required,
            }
            continue
        logger.info(
            "training %s samples=%s",
            modality,
            sample_count,
        )
        results[modality] = {"trained": True, **trainer(rows)}
        logger.info("training %s finished %s", modality, results[modality])
    return results
