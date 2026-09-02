"""MobileNetV3 geometry embeddings and vector-search inference."""

from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import fitz
import joblib
import numpy as np
from PIL import Image

from config import settings
from services.multimodal.torch_runtime import load_torch


logger = logging.getLogger("takeoff.geometry_ai")

_LOCK = threading.RLock()
_RUNTIME: Optional[tuple[Any, Any, Any]] = None
_INDEX: Optional[Dict[str, Any]] = None
_INDEX_LOADED = False
_INDEX_REJECTION: Optional[str] = None
_EMBEDDING_DIM = 128
_ENCODE_BATCH_SIZE = 32


def _runtime() -> tuple[Any, Any, Any]:
    global _RUNTIME
    with _LOCK:
        if _RUNTIME is None:
            torch = load_torch()
            from torchvision.models import (
                MobileNet_V3_Small_Weights,
                mobilenet_v3_small,
            )

            # Torch defaults to a conservative thread count under uvicorn,
            # which halves crop throughput on multi-core machines.
            try:
                torch.set_num_threads(max(1, os.cpu_count() or 1))
            except (RuntimeError, ValueError):
                pass
            weights = MobileNet_V3_Small_Weights.DEFAULT
            model = mobilenet_v3_small(weights=weights)
            model.classifier = torch.nn.Identity()
            model.eval()
            _RUNTIME = (torch, model, weights.transforms())
        return _RUNTIME


def _compress_embedding(vector: np.ndarray) -> np.ndarray:
    """Deterministically pool MobileNet features into a compact vector."""

    chunks = np.array_split(vector.reshape(-1), _EMBEDDING_DIM)
    compact = np.asarray([chunk.mean() for chunk in chunks], dtype=np.float32)
    norm = float(np.linalg.norm(compact))
    return compact / norm if norm > 0 else compact


def _page_image(page: fitz.Page, zoom: float = 1.5) -> Image.Image:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")


def _crop(image: Image.Image, bbox: List[float], zoom: float = 1.5) -> Image.Image:
    x0, y0, x1, y1 = (float(value) * zoom for value in bbox)
    # Larger padding gives the role classifier member context (leaders, neighbors).
    padding = max(18.0, min(48.0, max(x1 - x0, y1 - y0) * 0.25))
    box = (
        max(0, int(x0 - padding)),
        max(0, int(y0 - padding)),
        min(image.width, int(x1 + padding)),
        min(image.height, int(y1 + padding)),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("Geometry crop has no visible area")
    return image.crop(box)


_ROLE_LABELS = ("beam", "column", "brace", "plate", "connection", "other")


def orientation_bin(degrees: float) -> str:
    """Map absolute orientation degrees into a coarse drawing bin."""

    angle = abs(float(degrees or 0.0)) % 180.0
    angle = min(angle, 180.0 - angle)
    if angle <= 25.0:
        return "horizontal"
    if angle >= 65.0:
        return "vertical"
    return "diagonal"


def _role_from_label(label: str) -> str:
    text = str(label or "").strip().lower()
    if ":" in text:
        text = text.split(":", 1)[0]
    if text in _ROLE_LABELS:
        return text
    # Legacy section-string indexes: treat designation families as "other"
    # until the index is rebuilt with role labels.
    return "other"


def _orientation_from_label(label: str, fallback: str = "horizontal") -> str:
    text = str(label or "").strip().lower()
    if ":" in text:
        parts = text.split(":")
        if len(parts) > 1 and parts[1] in {"horizontal", "vertical", "diagonal"}:
            return parts[1]
    return fallback


def search_geometry_embedding(
    embedding: List[float],
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Find labeled geometry examples by cosine similarity (role + orientation).

    Rebuild the geometry embedding index after deploy so labels are
    ``role:orientation`` rather than AISC section strings. Legacy section
    indexes still load but map to role ``other``.
    """

    index = _load_index()
    if not index:
        return []
    matrix = index["embeddings"]
    query = np.asarray(embedding, dtype=np.float32)
    query /= max(float(np.linalg.norm(query)), 1e-8)
    similarities = matrix @ query
    ranked = np.argsort(-similarities)[: max(1, limit)]
    labels = index.get("labels") or []
    roles = index.get("roles") or []
    orientations = index.get("orientations") or []
    results: List[Dict[str, Any]] = []
    for position in ranked:
        if position >= len(labels):
            continue
        label = str(labels[position])
        role = (
            str(roles[position])
            if position < len(roles)
            else _role_from_label(label)
        )
        orientation = (
            str(orientations[position])
            if position < len(orientations)
            else _orientation_from_label(label)
        )
        results.append(
            {
                "role": role,
                "orientation": orientation,
                "similarity": round(float(similarities[position]), 6),
                # Backward-compatible alias; never treat as an AISC section.
                "label": f"{role}:{orientation}",
            }
        )
    return results


def encode_images(images: Iterable[Image.Image]) -> List[List[float]]:
    """Encode image crops with pretrained MobileNetV3-Small."""

    torch, model, transform = _runtime()
    pending = list(images)
    if not pending:
        return []
    output: List[List[float]] = []
    with torch.inference_mode():
        for start in range(0, len(pending), _ENCODE_BATCH_SIZE):
            # Transform per batch: holding every resized tensor at once costs
            # hundreds of megabytes on drawings with thousands of objects.
            window = pending[start : start + _ENCODE_BATCH_SIZE]
            batch = torch.stack([transform(image) for image in window])
            vectors = model(batch).detach().cpu().tolist()
            output.extend(
                _compress_embedding(np.asarray(vector, dtype=np.float32))
                .round(6)
                .tolist()
                for vector in vectors
            )
    return output


def _rejection_reason(payload: Dict[str, Any]) -> Optional[str]:
    """Explain why an index cannot produce usable role evidence.

    Section-labelled (schema 1.0) indexes collapse to role ``other`` for every
    crop and carry no orientation column, so encoding against them costs the
    bulk of analysis wall-clock while returning a constant.
    """

    labels = payload.get("labels") or []
    if not labels:
        return "Geometry embedding index is empty"
    roles = payload.get("roles") or []
    orientations = payload.get("orientations") or []
    if not roles or not orientations:
        return (
            f"Geometry embedding index is schema "
            f"{payload.get('schema_version') or '1.0'} (section labels); it "
            "resolves every crop to role 'other'. Rebuild it as schema 2.0 "
            "role:orientation via geometry training to re-enable the CV encoder"
        )
    if not any(str(role) in _ROLE_LABELS for role in roles):
        return "Geometry embedding index carries no recognised member roles"
    return None


def _load_index() -> Optional[Dict[str, Any]]:
    """Load the role-labelled embedding index, or None when unusable."""

    global _INDEX, _INDEX_LOADED, _INDEX_REJECTION
    with _LOCK:
        if _INDEX_LOADED:
            return _INDEX
        path = settings.geometry_embedding_index_path
        if not path.exists():
            _INDEX_LOADED = True
            _INDEX_REJECTION = "Geometry embedding index is not trained"
            return None
        payload = joblib.load(path)
        raw_embeddings = payload.get("embeddings")
        embeddings = np.asarray(
            raw_embeddings if raw_embeddings is not None else [],
            dtype=np.float32,
        )
        _INDEX_LOADED = True
        if embeddings.ndim != 2 or embeddings.shape[1] != _EMBEDDING_DIM:
            _INDEX_REJECTION = (
                "Geometry embedding index has an unexpected embedding shape"
            )
            return None
        rejection = _rejection_reason(payload)
        if rejection:
            _INDEX_REJECTION = rejection
            logger.warning("geometry embedding index skipped: %s", rejection)
            return None
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        payload["embeddings"] = embeddings / np.maximum(norms, 1e-8)
        _INDEX = payload
        _INDEX_REJECTION = None
        return _INDEX


def reset_index_cache() -> None:
    """Forget the cached index so a retrained one is picked up."""

    global _INDEX, _INDEX_LOADED, _INDEX_REJECTION
    with _LOCK:
        _INDEX = None
        _INDEX_LOADED = False
        _INDEX_REJECTION = None


def geometry_index_ready() -> bool:
    """Report whether the CV encoder can contribute role evidence."""

    return _load_index() is not None


def enrich_geometry_embeddings(
    pdf_path: str | Path,
    geometry: Dict[str, Any],
) -> Dict[str, Any]:
    """Crop every PDF geometry object, embed it, and attach vector evidence."""

    objects = geometry.get("objects") or []
    pending = [
        obj for obj in objects if obj.get("bbox") and not obj.get("geometry_embedding")
    ]
    index = _load_index()
    if not pending:
        if index:
            geometry["geometry_ai"] = {
                "available": True,
                "encoder": "mobilenet_v3_small_imagenet",
                "embedding_dimension": _EMBEDDING_DIM,
                "indexed_examples": len(index.get("labels") or []),
            }
        return geometry

    # Encoding without reference vectors cannot produce a similarity, so the
    # vector-geometry extractor stays in charge until the index is trained.
    if not index:
        geometry["geometry_ai"] = {
            "available": False,
            "fallback": "vector_geometry",
            "reason": _INDEX_REJECTION
            or (
                "Geometry embedding index is not trained; run geometry "
                "training from reviewed corrections to enable the CV encoder"
            ),
            "skipped_objects": len(pending),
        }
        return geometry

    by_page: Dict[int, List[dict]] = {}
    for obj in pending:
        by_page.setdefault(int(obj.get("page_number") or 0), []).append(obj)

    try:
        with fitz.open(str(pdf_path)) as document:
            for page_number, page_objects in by_page.items():
                if page_number < 1 or page_number > document.page_count:
                    continue
                image = _page_image(document.load_page(page_number - 1))
                valid_objects: List[dict] = []
                crops: List[Image.Image] = []
                for obj in page_objects:
                    try:
                        crops.append(_crop(image, obj["bbox"]))
                        valid_objects.append(obj)
                    except ValueError:
                        continue
                for obj, embedding in zip(valid_objects, encode_images(crops)):
                    matches = search_geometry_embedding(embedding, limit=5)
                    top = matches[0] if matches else None
                    margin = (
                        float(top["similarity"])
                        - float(matches[1]["similarity"])
                        if top and len(matches) > 1
                        else float(top["similarity"]) if top else 0.0
                    )
                    role = str((top or {}).get("role") or "other")
                    orientation = str(
                        (top or {}).get("orientation")
                        or orientation_bin(float(obj.get("orientation") or 0.0))
                    )
                    obj["geometry_embedding"] = embedding
                    obj["geometry_similarity"] = (
                        max(0.0, float(top["similarity"])) if top else 0.0
                    )
                    obj["geometry_confidence"] = max(
                        0.0,
                        min(
                            1.0,
                            0.85 * obj["geometry_similarity"]
                            + 0.15 * max(0.0, margin),
                        ),
                    )
                    obj["geometry_role"] = role
                    obj["geometry_orientation"] = orientation
                    obj["geometry_role_confidence"] = float(
                        obj["geometry_confidence"]
                    )
                    obj["geometry_candidates"] = matches
                    obj["geometry_features"] = {
                        "length": obj.get("length"),
                        "orientation": obj.get("orientation"),
                        "orientation_bin": orientation,
                        "role": role,
                        "aspect_ratio": obj.get("aspect_ratio"),
                        "width": obj.get("width"),
                        "height": obj.get("height"),
                        "area": obj.get("area"),
                        "bbox": obj.get("bbox"),
                        "line_thickness": obj.get("width"),
                    }
    except (ImportError, RuntimeError, OSError) as exc:
        geometry["geometry_ai"] = {
            "available": False,
            "fallback": "vector_geometry",
            "reason": str(exc),
        }
        return geometry

    geometry["geometry_ai"] = {
        "available": True,
        "encoder": "mobilenet_v3_small_imagenet",
        "embedding_dimension": _EMBEDDING_DIM,
        "indexed_examples": len((_load_index() or {}).get("labels") or []),
    }
    return geometry


def build_geometry_embedding_index(
    samples: Iterable[Dict[str, Any]],
    *,
    destination: Optional[str | Path] = None,
    max_per_label: int = 12,
    max_samples: int = 1200,
) -> Dict[str, Any]:
    """Build the supervised geometry vector index from approved crop samples.

    Page rasterization dominates wall-clock on large drawings, so each PDF page
    is rendered at most once and labels are capped to keep the index balanced.
    """

    selected: List[Dict[str, Any]] = []
    per_label: Dict[str, int] = {}
    for sample in samples:
        # Prefer explicit member_role; fall back to legacy section/label fields.
        role = str(
            sample.get("member_role")
            or sample.get("role")
            or sample.get("section")
            or sample.get("label")
            or ""
        ).strip()
        role = _role_from_label(role)
        orientation = str(
            sample.get("orientation_bin")
            or orientation_bin(float(sample.get("orientation") or 0.0))
        )
        label = f"{role}:{orientation}"
        if role not in _ROLE_LABELS:
            continue
        image_path = sample.get("image_path")
        pdf_path = sample.get("pdf_path")
        has_image = bool(image_path and Path(str(image_path)).exists())
        if not has_image and not pdf_path:
            continue
        if per_label.get(label, 0) >= max_per_label:
            continue
        per_label[label] = per_label.get(label, 0) + 1
        row = dict(sample)
        row["_role_label"] = label
        row["_role"] = role
        row["_orientation"] = orientation
        selected.append(row)
        if len(selected) >= max_samples:
            break

    # Prefer on-disk crops first so PDF rendering is only a fallback.
    selected.sort(
        key=lambda sample: 0
        if sample.get("image_path") and Path(str(sample["image_path"])).exists()
        else 1
    )

    images: List[Image.Image] = []
    labels: List[str] = []
    roles: List[str] = []
    orientations: List[str] = []
    page_cache: Dict[tuple[str, int], Image.Image] = {}
    open_documents: Dict[str, fitz.Document] = {}
    try:
        for sample in selected:
            label = str(sample.get("_role_label") or "")
            role = str(sample.get("_role") or "other")
            orientation = str(sample.get("_orientation") or "horizontal")
            image_path = sample.get("image_path")
            if image_path and Path(str(image_path)).exists():
                with Image.open(image_path) as image:
                    images.append(image.convert("RGB").copy())
                labels.append(label)
                roles.append(role)
                orientations.append(orientation)
                continue

            pdf_path = str(sample.get("pdf_path") or "")
            page_number = int(sample.get("page_number") or sample.get("page") or 0)
            bbox = sample.get("bounding_box") or sample.get("bbox")
            if not pdf_path or page_number < 1 or not bbox:
                continue
            cache_key = (pdf_path, page_number)
            page_image = page_cache.get(cache_key)
            if page_image is None:
                document = open_documents.get(pdf_path)
                if document is None:
                    document = fitz.open(pdf_path)
                    open_documents[pdf_path] = document
                if page_number > document.page_count:
                    continue
                # Slightly lower zoom keeps crops usable while cutting render cost.
                page_image = _page_image(
                    document.load_page(page_number - 1), zoom=1.25
                )
                page_cache[cache_key] = page_image
            try:
                images.append(_crop(page_image, bbox, zoom=1.25))
            except ValueError:
                continue
            labels.append(label)
            roles.append(role)
            orientations.append(orientation)
    finally:
        for document in open_documents.values():
            document.close()

    embeddings = encode_images(images)
    if not embeddings:
        raise ValueError("No labeled geometry crops were provided")
    path = Path(destination or settings.geometry_embedding_index_path)
    payload = {
        # schema 2.0: labels are role:orientation, not AISC sections.
        # Rebuild this index after deploy via the geometry training CLI.
        "schema_version": "2.0",
        "encoder": "mobilenet_v3_small_imagenet",
        "embedding_dimension": _EMBEDDING_DIM,
        "embeddings": np.asarray(embeddings, dtype=np.float32),
        "labels": labels,
        "roles": roles,
        "orientations": orientations,
    }
    joblib.dump(payload, path)
    reset_index_cache()
    return {
        "path": str(path),
        "samples": len(labels),
        "unique_labels": len(set(labels)),
        "pages_rendered": len(page_cache),
        "target": "role_orientation",
    }
