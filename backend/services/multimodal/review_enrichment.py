"""Persist and attach multimodal evidence to the existing review queue.

The index is read on every review request, so it is stored compactly, cached in
memory until the file changes, and bounded: an unbounded pretty-printed index
grew to tens of megabytes and had to be re-parsed on each call.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Iterable, List, Optional

from config import settings
from services.prediction.contract import confidence_overall


_LOCK = threading.Lock()
_INDEX_PATH = settings.training_dir / "multimodal_review_index.json"
# Reviewer evidence is only useful while the drawing is still being reviewed.
_MAX_ENTRIES = 4000

_CACHE: Dict[str, dict] | None = None
_CACHE_STAMP: tuple[int, int] | None = None


def _key(source_file: str, token: str) -> str:
    return (
        f"{str(source_file or '').strip().lower()}::"
        f"{str(token or '').strip().upper().replace(' ', '')}"
    )


def _stamp() -> tuple[int, int] | None:
    try:
        stat = _INDEX_PATH.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _load() -> Dict[str, dict]:
    """Return the index, reusing the parsed copy while the file is unchanged."""

    global _CACHE, _CACHE_STAMP

    stamp = _stamp()
    if stamp is None:
        _CACHE, _CACHE_STAMP = {}, None
        return {}
    if _CACHE is not None and _CACHE_STAMP == stamp:
        return _CACHE
    try:
        loaded = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        loaded = {}
    _CACHE, _CACHE_STAMP = loaded, stamp
    return loaded


def _explanation_digest(explanation: Dict[str, Any]) -> Dict[str, Any]:
    """Reviewer-facing reasoning only; the full record stays in the artifact."""

    if not explanation:
        return {}
    return {
        "summary": explanation.get("summary"),
        "reasons": (explanation.get("reasons") or [])[:5],
        "text_similarity": explanation.get("text_similarity"),
        "geometry_similarity": explanation.get("geometry_similarity"),
        "graph_consistency": explanation.get("graph_consistency"),
        "engineer_explanation": explanation.get("engineer_explanation") or {},
        "ai_engineer_explanation": explanation.get("ai_engineer_explanation") or {},
        "annotation": _annotation_digest(
            explanation.get("annotation_interpretation") or {}
        ),
    }


def _annotation_digest(pack: Dict[str, Any]) -> Dict[str, Any]:
    """Compact annotation state so reviewers see why a case needs a decision."""

    if not pack:
        return {}
    annotation = pack.get("annotation") or {}
    understandability = pack.get("understandability") or {}
    ambiguity = pack.get("ambiguity") or {}
    return {
        "annotation_type": annotation.get("annotation_type"),
        "subtype": annotation.get("subtype"),
        "dimensions": annotation.get("dimensions") or [],
        "thickness": annotation.get("thickness"),
        "angle_degrees": annotation.get("angle_degrees"),
        "text_rotation": annotation.get("text_rotation"),
        "understandability": understandability.get("status"),
        "understandability_reasons": (understandability.get("reasons") or [])[:3],
        "ambiguity_resolution": ambiguity.get("resolution"),
        "ambiguity_reason": ambiguity.get("reason"),
        "abstain_for_review": bool(pack.get("abstain_for_review")),
    }


def _record(prediction: dict) -> Dict[str, Any]:
    section = prediction.get("section") or prediction.get("predicted_shape")
    original = prediction.get("original_token") or ""
    explanation = prediction.get("explanation") or {}
    return {
        "original_token": original,
        "corrected_token": prediction.get("corrected_token"),
        "family": prediction.get("family"),
        "section": section,
        "prediction": section,
        "suggested_shape": section,
        "component_id": prediction.get("component_id"),
        "material": prediction.get("material"),
        "page": prediction.get("page"),
        "bbox": prediction.get("bbox"),
        "alternatives": (prediction.get("alternatives") or [])[:3],
        "top_candidate_sections": (
            explanation.get("top_candidate_sections") or []
        )[:5],
        "why_selected": (explanation.get("why_selected") or [])[:5],
        "why_rejected": (explanation.get("why_rejected") or [])[:3],
        "explanation": _explanation_digest(explanation),
        "evidence": prediction.get("evidence") or {},
        "geometry_evidence": explanation.get("geometry_evidence") or {},
        "graph_evidence": explanation.get("graph_evidence") or {},
        "geometry_preview": prediction.get("geometry_preview"),
        "graph_preview": prediction.get("graph_preview"),
        "database_match": prediction.get("database_match"),
        "database_role": "verification_only",
        "multimodal_confidence": (
            confidence_overall(prediction.get("confidence"))
            if prediction.get("confidence") is not None
            else None
        ),
        "multimodal_review_status": prediction.get("review_status"),
        # Kept because approving a review turns these into training features.
        "multimodal_features": prediction.get("features") or {},
    }


def index_predictions(source_file: str, predictions: Iterable[dict]) -> None:
    """Upsert review evidence without changing legacy CSV columns."""

    global _CACHE, _CACHE_STAMP

    with _LOCK:
        index = dict(_load())
        for prediction in predictions:
            index[_key(source_file, prediction.get("original_token") or "")] = (
                _record(prediction)
            )
        if len(index) > _MAX_ENTRIES:
            keys = list(index)[-_MAX_ENTRIES:]
            index = {key: index[key] for key in keys}
        _INDEX_PATH.write_text(
            json.dumps(index, separators=(",", ":")), encoding="utf-8"
        )
        _CACHE, _CACHE_STAMP = index, _stamp()


def evidence_for(source_file: str, token: str) -> Optional[dict]:
    return _load().get(_key(source_file, token))


def enrich_review_rows(rows: List[dict]) -> List[dict]:
    index = _load()
    enriched = []
    for row in rows:
        evidence = index.get(_key(row.get("source_file", ""), row.get("token", "")))
        enriched.append({**row, **(evidence or {})})
    return enriched
