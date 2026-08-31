"""
Phase 2 - Dynamic Regex Knowledge Base
======================================

A persistent, self-updating store of learned regex patterns. Each engineering
class maps to a rich record:

    {
      "pattern": "W\\d+X\\d+",
      "examples": [...capped list of representative tokens...],
      "example_count": 289,
      "coverage": 1.0,
      "confidence": 0.98,
      "confidence_level": "High",
      "distinct_structures": 1,
      "usage_count": 12,
      "source": "training" | "self-learned",
      "created_at": "2026-...",
      "updated_at": "2026-..."
    }

The KB is backed by ``training/dynamic_regex.json``. It transparently upgrades
the legacy flat format (``{class: pattern}``) to the rich format on first load,
so existing files keep working.

Thread-safety: all mutating operations take a lock, and writes are atomic
(write-to-temp then replace) to avoid corrupting the JSON on concurrent access.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import settings
from services.prediction.confidence_engine import level_from_score
from services.regex_learning_engine import learn_regex_with_report
from services.regex_validator import validate_regex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RegexKnowledgeBase:
    """In-memory cache over the persisted dynamic regex JSON file."""

    def __init__(self, path=None, max_examples: Optional[int] = None):
        self.path = path or settings.knowledge_base_path
        self.max_examples = max_examples or settings.max_examples_per_class
        self._lock = threading.RLock()
        self._data: Dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not os.path.exists(self.path):
            self._data = {}
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._data = {}
            return

        upgraded: Dict[str, dict] = {}
        for cls, value in raw.items():
            if isinstance(value, str):
                # Legacy flat format: {class: pattern}
                upgraded[cls] = self._new_record(pattern=value, source="training")
            elif isinstance(value, dict):
                upgraded[cls] = {**self._new_record(), **value}
        self._data = upgraded

    def _write(self) -> None:
        """Atomically persist the KB to disk."""

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        dir_name = os.path.dirname(self.path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------
    # Records
    # ------------------------------------------------------------------
    @staticmethod
    def _new_record(pattern: Optional[str] = None, source: str = "self-learned") -> dict:
        now = _now()
        return {
            "pattern": pattern,
            "variants": [],
            "examples": [],
            "example_count": 0,
            "coverage": 0.0,
            "confidence": 0.0,
            "confidence_level": "Low",
            "distinct_structures": 0,
            "usage_count": 0,
            "source": source,
            "created_at": now,
            "updated_at": now,
        }

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------
    def get(self, cls: str) -> Optional[dict]:
        with self._lock:
            record = self._data.get(cls)
            return dict(record) if record else None

    def get_pattern(self, cls: str) -> Optional[str]:
        record = self.get(cls)
        return record["pattern"] if record else None

    def has(self, cls: str) -> bool:
        with self._lock:
            return cls in self._data

    def all(self) -> Dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}

    def classes(self) -> List[str]:
        with self._lock:
            return sorted(self._data.keys())

    def stats(self) -> dict:
        with self._lock:
            records = list(self._data.values())
        total = len(records)
        levels = {"High": 0, "Medium": 0, "Low": 0}
        self_learned = 0
        total_usage = 0
        confidences = []
        for r in records:
            levels[r.get("confidence_level", "Low")] = (
                levels.get(r.get("confidence_level", "Low"), 0) + 1
            )
            if r.get("source") == "self-learned":
                self_learned += 1
            total_usage += r.get("usage_count", 0)
            confidences.append(r.get("confidence", 0.0))
        return {
            "total_classes": total,
            "self_learned_classes": self_learned,
            "training_classes": total - self_learned,
            "total_usage": total_usage,
            "average_confidence": round(sum(confidences) / total, 4) if total else 0.0,
            "confidence_levels": levels,
        }

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------
    def record_usage(self, cls: str, persist: bool = False) -> None:
        with self._lock:
            if cls in self._data:
                self._data[cls]["usage_count"] += 1
                self._data[cls]["updated_at"] = _now()
                if persist:
                    self._write()

    def learn_and_upsert(
        self,
        cls: str,
        new_examples: List[str],
        source: str = "self-learned",
        persist: bool = True,
    ) -> dict:
        """
        Merge ``new_examples`` into the class record, re-learn a regex from the
        combined example set, validate it, and store the result only if it is
        at least as good as the existing pattern (by confidence).

        Returns a dict describing the learning outcome and the final record.
        """

        new_examples = [str(e).strip() for e in new_examples if str(e).strip()]

        with self._lock:
            existing = self._data.get(cls)
            previous_pattern = existing["pattern"] if existing else None

            base_examples = list(existing["examples"]) if existing else []
            # Merge, de-duplicate, keep order stable.
            merged: List[str] = []
            seen = set()
            for tok in base_examples + new_examples:
                key = tok.upper()
                if key not in seen:
                    seen.add(key)
                    merged.append(tok)

            report = learn_regex_with_report(merged)
            new_pattern = report["pattern"]
            new_variants = report.get("variants", [])
            validation = validate_regex(new_pattern, merged)

            # Decide whether to accept the newly learned pattern.
            status = "unchanged"
            accepted_pattern = previous_pattern
            accepted_validation = validation

            if previous_pattern is None:
                status = "created"
                accepted_pattern = new_pattern
            else:
                prev_validation = validate_regex(previous_pattern, merged)
                if new_pattern == previous_pattern:
                    status = "reinforced"
                    accepted_pattern = previous_pattern
                    accepted_validation = prev_validation
                elif validation.confidence >= prev_validation.confidence:
                    status = "updated"
                    accepted_pattern = new_pattern
                    accepted_validation = validation
                else:
                    status = "kept_previous"
                    accepted_pattern = previous_pattern
                    accepted_validation = prev_validation

            now = _now()
            record = existing or self._new_record(source=source)
            accepted_variants = new_variants if accepted_pattern == new_pattern else record.get("variants", [])
            variant_weight = sum(
                float(item.get("confidence", 0)) * float(item.get("frequency", 0))
                for item in accepted_variants
            )
            weighted_confidence = (
                0.70 * accepted_validation.confidence + 0.30 * variant_weight
                if accepted_variants else accepted_validation.confidence
            )
            record["pattern"] = accepted_pattern
            record["variants"] = accepted_variants
            record["examples"] = merged[: self.max_examples]
            record["example_count"] = len(merged)
            record["coverage"] = round(accepted_validation.coverage, 4)
            record["confidence"] = round(min(0.97, weighted_confidence), 4)
            record["confidence_level"] = level_from_score(record["confidence"])
            record["distinct_structures"] = report["distinct_structures"]
            record["updated_at"] = now
            if existing is None:
                record["created_at"] = now
                record["source"] = source
            # A class first seen in training that later self-learns keeps a
            # combined provenance marker.
            elif source == "self-learned" and record.get("source") == "training":
                record["source"] = "training+self-learned"

            self._data[cls] = record

            if persist:
                self._write()

            return {
                "class": cls,
                "status": status,
                "previous_pattern": previous_pattern,
                "new_pattern": accepted_pattern,
                "candidate_pattern": new_pattern,
                "validation": accepted_validation.to_dict(),
                "record": dict(record),
            }

    def reset(self, data: Dict[str, dict], persist: bool = True) -> None:
        """Replace the entire KB (used by the offline builder)."""

        with self._lock:
            self._data = data
            if persist:
                self._write()


# Singleton instance shared across the application.
knowledge_base = RegexKnowledgeBase()
