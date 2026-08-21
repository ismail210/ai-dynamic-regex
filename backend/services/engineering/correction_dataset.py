"""
Correction Dataset Builder
==========================

Every human review decision becomes a training sample for future learning.

Stored fields:
- input features
- prediction / suggestion
- correct label
- correct geometry (optional)
- timestamp
- user decision
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings


_lock = threading.Lock()


def _corrections_path() -> Path:
    path = getattr(settings, "engineering_corrections_path", None)
    if path is None:
        path = settings.training_dir / "engineering_corrections.jsonl"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def build_training_sample(
    *,
    features: Dict[str, Any],
    prediction: Optional[Dict[str, Any]],
    correct_label: Optional[str],
    correct_geometry: Optional[Dict[str, Any]],
    user_decision: str,
    document_id: Optional[str] = None,
    object_id: Optional[str] = None,
    notes: str = "",
) -> Dict[str, Any]:
    return {
        "sample_id": f"corr_{uuid.uuid4().hex[:12]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "object_id": object_id,
        "input_features": features or {},
        "prediction": prediction or {},
        "correct_label": correct_label,
        "correct_geometry": correct_geometry,
        "user_decision": user_decision,
        "notes": notes,
        "ready_for_training": user_decision in {"approve", "edit", "correct"},
    }


def save_correction(sample: Dict[str, Any]) -> Dict[str, Any]:
    """Append one correction sample to the JSONL dataset."""

    path = _corrections_path()
    with _lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
    return sample


def record_correction(
    *,
    features: Dict[str, Any],
    prediction: Optional[Dict[str, Any]],
    correct_label: Optional[str],
    user_decision: str,
    correct_geometry: Optional[Dict[str, Any]] = None,
    document_id: Optional[str] = None,
    object_id: Optional[str] = None,
    notes: str = "",
) -> Dict[str, Any]:
    sample = build_training_sample(
        features=features,
        prediction=prediction,
        correct_label=correct_label,
        correct_geometry=correct_geometry,
        user_decision=user_decision,
        document_id=document_id,
        object_id=object_id,
        notes=notes,
    )
    return save_correction(sample)


def record_corrections_batch(entries: List[Dict[str, Any]]) -> int:
    """Append many correction samples in one locked write."""

    if not entries:
        return 0
    path = _corrections_path()
    lines = [
        json.dumps(
            build_training_sample(
                features=entry.get("features") or {},
                prediction=entry.get("prediction"),
                correct_label=entry.get("correct_label"),
                correct_geometry=entry.get("correct_geometry"),
                user_decision=str(entry.get("user_decision") or ""),
                document_id=entry.get("document_id"),
                object_id=entry.get("object_id"),
                notes=str(entry.get("notes") or ""),
            ),
            ensure_ascii=False,
        )
        for entry in entries
    ]
    with _lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return len(lines)


def list_corrections(limit: int = 200) -> List[dict]:
    path = _corrections_path()
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def corrections_summary() -> Dict[str, Any]:
    rows = list_corrections(limit=100000)
    ready = sum(1 for r in rows if r.get("ready_for_training"))
    decisions: Dict[str, int] = {}
    for r in rows:
        d = str(r.get("user_decision") or "unknown")
        decisions[d] = decisions.get(d, 0) + 1
    return {
        "total_samples": len(rows),
        "ready_for_training": ready,
        "decisions": decisions,
        "path": str(_corrections_path()),
    }
