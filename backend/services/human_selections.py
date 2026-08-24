"""
Reviewer decisions among catalog-valid completions (missing-thickness HSS
and similar cases) — the human-review resolution half of the correction
flow in services.hss_completion.

Distinct from services.engineering.correction_dataset.record_correction:
that writes a training-data log line and is never read back. This module
IS read back, by services.staged_pipeline.load_cached_analysis, so a
reviewer's choice survives a page refresh instead of the served prediction
reverting to "select a candidate".

Keyed by (document_id, object_id) -> latest selected designation. The
latest write for a key always wins (changing a prior selection is just
another write), matching the "no version-history UI, existing correction
history in engineering_corrections.jsonl still covers auditability" scope.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings
from services.prediction.canonical_contract import MatchStatus

_LOCK = threading.Lock()


def _path() -> Path:
    return settings.human_selections_path


def _load_all() -> Dict[str, Dict[str, Any]]:
    path = _path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_all(data: Dict[str, Dict[str, Any]]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_human_selection(
    *, document_id: str, object_id: str, section: str, notes: str = ""
) -> None:
    """Persist (or overwrite) the reviewer's chosen section for one object."""

    document_id = str(document_id or "")
    object_id = str(object_id or "")
    section = str(section or "")
    if not document_id or not object_id or not section:
        return
    with _LOCK:
        data = _load_all()
        document_selections = data.setdefault(document_id, {})
        document_selections[object_id] = {
            "section": section,
            "selected_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
        }
        _save_all(data)


def get_human_selections(document_id: str) -> Dict[str, str]:
    """``{object_id: selected_section}`` for one document, or ``{}``."""

    data = _load_all().get(str(document_id or ""), {})
    return {
        object_id: str(entry.get("section") or "")
        for object_id, entry in data.items()
        if isinstance(entry, dict) and entry.get("section")
    }


def get_human_selection(document_id: str, object_id: str) -> Optional[str]:
    return get_human_selections(document_id).get(str(object_id or ""))


def apply_human_selection_overlay(
    prediction: Dict[str, Any], section: str
) -> Dict[str, Any]:
    """
    Apply one reviewer-selected section onto a single prediction record --
    the same resolved shape ``services.staged_pipeline._apply_human_selections``
    produces for every persisted selection on each read. Shared here so a
    single mutation (services.human_selections + this overlay) is the one
    place that defines "what a human-resolved prediction looks like": the
    corrections router hands the caller this record back immediately
    (instead of the frontend reconstructing canonical fields itself), and
    the bulk per-document overlay applied on every GET uses the same logic.

    Never touches raw/original/normalized OCR text -- only the fields that
    represent the reviewer's decision.
    """

    resolved = dict(prediction)
    resolved["section"] = section
    resolved["human_selected_section"] = section
    resolved["decision_source"] = "human_review"
    resolved["needs_review"] = False
    resolved["review_reason"] = None
    canonical = resolved.get("canonical")
    if isinstance(canonical, dict):
        canonical = dict(canonical)
        canonical["prediction"] = {
            **(canonical.get("prediction") or {}),
            "final_label": section,
        }
        canonical["comparison"] = {
            **(canonical.get("comparison") or {}),
            "match_status": MatchStatus.HUMAN_RESOLVED.value,
        }
        canonical["needs_review"] = False
        canonical["review_reason"] = None
        resolved["canonical"] = canonical
        resolved["comparison"] = canonical["comparison"]
    return resolved
