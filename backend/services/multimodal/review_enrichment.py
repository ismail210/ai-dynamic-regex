"""Persist and attach multimodal evidence to the existing review queue."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from config import settings
from services.prediction.contract import confidence_overall


_LOCK = threading.Lock()
_INDEX_PATH = settings.training_dir / "multimodal_review_index.json"


def _key(source_file: str, token: str) -> str:
    return (
        f"{str(source_file or '').strip().lower()}::"
        f"{str(token or '').strip().upper().replace(' ', '')}"
    )


def _load() -> Dict[str, dict]:
    if not _INDEX_PATH.exists():
        return {}
    try:
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def index_predictions(source_file: str, predictions: Iterable[dict]) -> None:
    """Upsert review evidence without changing legacy CSV columns."""

    with _LOCK:
        index = _load()
        for prediction in predictions:
            original = prediction.get("original_token") or ""
            index[_key(source_file, original)] = {
                "original_token": original,
                "corrected_token": prediction.get("corrected_token"),
                "family": prediction.get("family"),
                "section": prediction.get("section")
                or prediction.get("predicted_shape"),
                "prediction": prediction.get("section")
                or prediction.get("predicted_shape"),
                "suggested_shape": prediction.get("section")
                or prediction.get("predicted_shape"),
                "component_id": prediction.get("component_id"),
                "material": prediction.get("material"),
                "alternatives": prediction.get("alternatives") or [],
                "top_candidate_sections": prediction.get("top_candidate_sections")
                or [],
                "why_selected": prediction.get("why_selected") or [],
                "why_rejected": prediction.get("why_rejected") or [],
                "explanation": prediction.get("explanation")
                or prediction.get("reasoning")
                or {},
                "reasoning": prediction.get("explanation")
                or prediction.get("reasoning")
                or {},
                "evidence": prediction.get("evidence") or {},
                "text_evidence": prediction.get("text_evidence") or {},
                "geometry_evidence": prediction.get("geometry_evidence") or {},
                "graph_evidence": prediction.get("graph_evidence") or {},
                "engineering_evidence": prediction.get("engineering_evidence")
                or {},
                "geometry_preview": prediction.get("geometry_preview"),
                "graph_preview": prediction.get("graph_preview"),
                "database_match": prediction.get("database_match"),
                "database_role": "verification_only",
                "multimodal_confidence": confidence_overall(
                    prediction.get("confidence")
                )
                if prediction.get("confidence") is not None
                else prediction.get("confidence"),
                "multimodal_review_status": prediction.get("review_status"),
                "multimodal_features": prediction.get("features") or {},
            }
        _INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")


def evidence_for(source_file: str, token: str) -> Optional[dict]:
    return _load().get(_key(source_file, token))


def enrich_review_rows(rows: List[dict]) -> List[dict]:
    index = _load()
    enriched = []
    for row in rows:
        evidence = index.get(_key(row.get("source_file", ""), row.get("token", "")))
        enriched.append({**row, **(evidence or {})})
    return enriched
