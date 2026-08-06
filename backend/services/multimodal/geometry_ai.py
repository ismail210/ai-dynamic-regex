"""MobileNetV3 geometry embeddings and vector-search inference."""

from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import fitz
import joblib
import numpy as np
from PIL import Image

from config import settings
from services.multimodal.torch_runtime import load_torch


_LOCK = threading.RLock()
_RUNTIME: Optional[tuple[Any, Any, Any]] = None
_INDEX: Optional[Dict[str, Any]] = None
_EMBEDDING_DIM = 128


def _runtime() -> tuple[Any, Any, Any]:
    global _RUNTIME
    with _LOCK:
        if _RUNTIME is None:
            torch = load_torch()
            from torchvision.models import (
                MobileNet_V3_Small_Weights,
                mobilenet_v3_small,
            )

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
    padding = max(10.0, min(32.0, max(x1 - x0, y1 - y0) * 0.15))
    box = (
        max(0, int(x0 - padding)),
        max(0, int(y0 - padding)),
        min(image.width, int(x1 + padding)),
        min(image.height, int(y1 + padding)),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("Geometry crop has no visible area")
    return image.crop(box)


def encode_images(images: Iterable[Image.Image]) -> List[List[float]]:
    """Encode image crops with pretrained MobileNetV3-Small."""

    torch, model, transform = _runtime()
    prepared = [transform(image) for image in images]
    if not prepared:
        return []
    output: List[List[float]] = []
    with torch.inference_mode():
        for start in range(0, len(prepared), 32):
            batch = torch.stack(prepared[start : start + 32])
            vectors = model(batch).detach().cpu().tolist()
            output.extend(
                _compress_embedding(np.asarray(vector, dtype=np.float32))
                .round(6)
                .tolist()
                for vector in vectors
            )
    return output


def _load_index() -> Optional[Dict[str, Any]]:
    global _INDEX
    path = settings.geometry_embedding_index_path
    if _INDEX is None and path.exists():
        payload = joblib.load(path)
        raw_embeddings = payload.get("embeddings")
        embeddings = np.asarray(
            raw_embeddings if raw_embeddings is not None else [],
            dtype=np.float32,
        )
        if embeddings.ndim == 2 and embeddings.shape[1] == _EMBEDDING_DIM:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            payload["embeddings"] = embeddings / np.maximum(norms, 1e-8)
            _INDEX = payload
    return _INDEX


def search_geometry_embedding(
    embedding: List[float],
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Find labeled geometry examples by cosine similarity."""

    index = _load_index()
    if not index:
        return []
    matrix = index["embeddings"]
    query = np.asarray(embedding, dtype=np.float32)
    query /= max(float(np.linalg.norm(query)), 1e-8)
    similarities = matrix @ query
    ranked = np.argsort(-similarities)[: max(1, limit)]
    labels = index.get("labels") or []
    return [
        {
            "section": str(labels[position]),
            "similarity": round(float(similarities[position]), 6),
        }
        for position in ranked
        if position < len(labels)
    ]


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
            "reason": (
                "Geometry embedding index is not trained; run geometry "
                "training from reviewed corrections to enable the CV encoder"
            ),
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
                    obj["geometry_candidates"] = matches
                    obj["geometry_features"] = {
                        "length": obj.get("length"),
                        "orientation": obj.get("orientation"),
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
        label = str(sample.get("section") or sample.get("label") or "").strip()
        if not label:
            continue
        image_path = sample.get("image_path")
        pdf_path = sample.get("pdf_path")
        has_image = bool(image_path and Path(str(image_path)).exists())
        if not has_image and not pdf_path:
            continue
        if per_label.get(label, 0) >= max_per_label:
            continue
        per_label[label] = per_label.get(label, 0) + 1
        selected.append(sample)
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
    page_cache: Dict[tuple[str, int], Image.Image] = {}
    open_documents: Dict[str, fitz.Document] = {}
    try:
        for sample in selected:
            label = str(sample.get("section") or sample.get("label") or "").strip()
            image_path = sample.get("image_path")
            if image_path and Path(str(image_path)).exists():
                with Image.open(image_path) as image:
                    images.append(image.convert("RGB").copy())
                labels.append(label)
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
    finally:
        for document in open_documents.values():
            document.close()

    embeddings = encode_images(images)
    if not embeddings:
        raise ValueError("No labeled geometry crops were provided")
    path = Path(destination or settings.geometry_embedding_index_path)
    payload = {
        "schema_version": "1.0",
        "encoder": "mobilenet_v3_small_imagenet",
        "embedding_dimension": _EMBEDDING_DIM,
        "embeddings": np.asarray(embeddings, dtype=np.float32),
        "labels": labels,
    }
    joblib.dump(payload, path)
    global _INDEX
    _INDEX = payload
    return {
        "path": str(path),
        "samples": len(labels),
        "unique_labels": len(set(labels)),
        "pages_rendered": len(page_cache),
    }
