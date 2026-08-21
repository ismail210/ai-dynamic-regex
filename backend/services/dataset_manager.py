"""Thread-safe persistence for the human-in-the-loop learning datasets."""

from __future__ import annotations

import csv
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from config import settings

UNKNOWN_COLUMNS = [
    "id", "token", "category", "prediction", "model_probability",
    "overall_confidence", "confidence_level", "uncertain", "source_file",
    "regex_suggested", "status", "reviewed_category", "reviewed_class",
    "notes", "created_at", "updated_at",
]
APPROVED_COLUMNS = [
    "token",
    "class",
    "category",
    "source",
    "approved_at",
    "unknown_id",
    "ranking_score",
    "correct",
    "eval_split",
]
HISTORY_COLUMNS = ["id", "event", "token", "detail", "actor", "created_at"]
UPLOAD_LOG_COLUMNS = [
    "id", "filename", "pages", "token_count", "known_count", "unknown_count",
    "uncertain_count", "created_at",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refresh_exact_section_artifact_safe() -> None:
    try:
        from services.exact_section_predictor import refresh_exact_section_artifact

        refresh_exact_section_artifact()
    except Exception:
        # Approval persistence must succeed even if retrieval refresh fails.
        pass


def _schedule_exact_section_refresh(*, background: bool) -> None:
    if background:
        threading.Thread(
            target=_refresh_exact_section_artifact_safe,
            daemon=True,
        ).start()
        return
    _refresh_exact_section_artifact_safe()


class DatasetManager:
    """Owns mutable review datasets; the AISC training CSV is read-only."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._ensure_files()

    def _ensure_files(self) -> None:
        with self._lock:
            for path, columns in (
                (settings.unknown_tokens_path, UNKNOWN_COLUMNS),
                (settings.approved_dataset_path, APPROVED_COLUMNS),
                (settings.history_path, HISTORY_COLUMNS),
                (settings.upload_log_path, UPLOAD_LOG_COLUMNS),
            ):
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                if not Path(path).exists():
                    self._write_rows(path, columns, [])

    @staticmethod
    def _read_rows(path: Path, columns: list[str]) -> list[dict[str, str]]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [
                {column: str(row.get(column, "")) for column in columns}
                for row in csv.DictReader(handle)
            ]

    @staticmethod
    def _write_rows(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({column: str(row.get(column, "")) for column in columns})

    def enqueue_unknown(
        self, token: str, prediction: str = "", model_probability: Any = "",
        overall_confidence: Any = "", confidence_level: str = "", uncertain: Any = True,
        source_file: str = "", regex_suggested: str = "", category: str = "",
    ) -> dict[str, str]:
        token = str(token).strip()
        with self._lock:
            rows = self._read_rows(settings.unknown_tokens_path, UNKNOWN_COLUMNS)
            for row in rows:
                if row["token"].upper() == token.upper() and row["status"] == "pending":
                    return row
            now = _now()
            row = {
                "id": str(uuid.uuid4()), "token": token, "category": category,
                "prediction": prediction, "model_probability": model_probability,
                "overall_confidence": overall_confidence, "confidence_level": confidence_level,
                "uncertain": str(bool(uncertain)).lower(), "source_file": source_file,
                "regex_suggested": regex_suggested, "status": "pending",
                "reviewed_category": "", "reviewed_class": "", "notes": "",
                "created_at": now, "updated_at": now,
            }
            rows.append(row)
            self._write_rows(settings.unknown_tokens_path, UNKNOWN_COLUMNS, rows)
            self.log_event("unknown_queued", token, f"Queued for review ({category or 'uncategorized'})", "system")
            return row

    def list_unknown(self, status: Optional[str] = None) -> list[dict[str, str]]:
        with self._lock:
            rows = self._read_rows(settings.unknown_tokens_path, UNKNOWN_COLUMNS)
            return [row for row in rows if not status or row["status"] == status]

    def review_token(
        self,
        unknown_id: str,
        action: str,
        reviewed_class: str = "",
        reviewed_category: str = "",
        notes: str = "",
        actor: str = "user",
        *,
        ranking_score: float | None = None,
        predicted_section: str = "",
        rebuild_exact_section: bool = True,
    ) -> dict[str, str]:
        batch = self.review_tokens_batch(
            [
                {
                    "unknown_id": unknown_id,
                    "action": action,
                    "reviewed_class": reviewed_class,
                    "reviewed_category": reviewed_category,
                    "notes": notes,
                    "ranking_score": ranking_score,
                    "predicted_section": predicted_section,
                }
            ],
            actor=actor,
            rebuild_exact_section=rebuild_exact_section,
        )
        if batch["errors"]:
            error = batch["errors"][0]
            if error["error_type"] == "KeyError":
                raise KeyError(error["error"])
            raise ValueError(error["error"])
        return batch["results"][0]

    def review_tokens_batch(
        self,
        items: list[dict[str, Any]],
        actor: str = "user",
        *,
        rebuild_exact_section: bool = True,
    ) -> dict[str, Any]:
        """Review many tokens with one CSV read/write pass per dataset."""

        results: list[dict[str, str]] = []
        errors: list[dict[str, str]] = []
        approved_count = 0

        with self._lock:
            unknown_rows = self._read_rows(
                settings.unknown_tokens_path, UNKNOWN_COLUMNS
            )
            unknown_by_id = {row["id"]: row for row in unknown_rows}
            approved_rows = self._read_rows(
                settings.approved_dataset_path, APPROVED_COLUMNS
            )
            history_rows = self._read_rows(settings.history_path, HISTORY_COLUMNS)

            from services.training_pipeline.preprocessing import assign_split

            for item in items:
                unknown_id = str(item.get("unknown_id") or "").strip()
                action = str(item.get("action") or "").lower().strip()
                reviewed_class = str(item.get("reviewed_class") or "")
                reviewed_category = str(item.get("reviewed_category") or "")
                notes = str(item.get("notes") or "")
                ranking_score = item.get("ranking_score")
                predicted_section = str(item.get("predicted_section") or "")

                if action not in {"approve", "reject"}:
                    errors.append(
                        {
                            "id": unknown_id,
                            "error": "action must be 'approve' or 'reject'",
                            "error_type": "ValueError",
                        }
                    )
                    continue

                record = unknown_by_id.get(unknown_id)
                if record is None:
                    errors.append(
                        {
                            "id": unknown_id,
                            "error": f"Unknown token '{unknown_id}' was not found",
                            "error_type": "KeyError",
                        }
                    )
                    continue
                if record["status"] != "pending":
                    errors.append(
                        {
                            "id": unknown_id,
                            "error": f"Unknown token has already been {record['status']}",
                            "error_type": "ValueError",
                        }
                    )
                    continue

                final_class = ""
                if action == "approve":
                    final_class = (
                        reviewed_class.strip()
                        or str(record.get("prediction") or "").strip()
                    )
                    if not final_class:
                        errors.append(
                            {
                                "id": unknown_id,
                                "error": "reviewed_class is required when approving a token",
                                "error_type": "ValueError",
                            }
                        )
                        continue

                now = _now()
                record.update(
                    {
                        "status": "approved" if action == "approve" else "rejected",
                        "reviewed_class": final_class.strip()
                        if action == "approve"
                        else reviewed_class.strip(),
                        "reviewed_category": reviewed_category.strip(),
                        "notes": notes.strip(),
                        "updated_at": now,
                    }
                )
                if action == "approve":
                    predicted = (
                        predicted_section.strip()
                        or str(record.get("prediction") or "").strip()
                    )
                    score = (
                        float(ranking_score)
                        if ranking_score is not None
                        else float(record.get("overall_confidence") or 0.0)
                    )
                    correct_flag = (
                        "1"
                        if predicted.upper().replace(" ", "")
                        == final_class.upper().replace(" ", "")
                        else "0"
                    )
                    approved_rows.append(
                        {
                            "token": record["token"],
                            "class": final_class.upper(),
                            "category": reviewed_category.strip()
                            or record["category"],
                            "source": "human_review",
                            "approved_at": now,
                            "unknown_id": record["id"],
                            "ranking_score": f"{float(score):.6f}",
                            "correct": correct_flag,
                            "eval_split": assign_split(
                                record["id"] or record["token"]
                            ),
                        }
                    )
                    approved_count += 1

                history_rows.append(
                    {
                        "id": str(uuid.uuid4()),
                        "event": f"token_{record['status']}",
                        "token": record["token"],
                        "detail": f"class={reviewed_class or record['prediction']}; {notes}".strip(
                            "; "
                        ),
                        "actor": actor,
                        "created_at": now,
                    }
                )
                results.append(record)

            if results:
                self._write_rows(
                    settings.unknown_tokens_path, UNKNOWN_COLUMNS, unknown_rows
                )
            if approved_count:
                self._write_rows(
                    settings.approved_dataset_path,
                    APPROVED_COLUMNS,
                    approved_rows,
                )
            if results:
                self._write_rows(
                    settings.history_path, HISTORY_COLUMNS, history_rows
                )

        if approved_count and rebuild_exact_section:
            _schedule_exact_section_refresh(background=len(items) > 1)

        return {
            "results": results,
            "errors": errors,
            "approved": approved_count,
        }

    def log_event(self, event: str, token: str = "", detail: str = "", actor: str = "system") -> dict[str, str]:
        with self._lock:
            rows = self._read_rows(settings.history_path, HISTORY_COLUMNS)
            row = {
                "id": str(uuid.uuid4()), "event": event, "token": token,
                "detail": detail, "actor": actor, "created_at": _now(),
            }
            rows.append(row)
            self._write_rows(settings.history_path, HISTORY_COLUMNS, rows)
            return row

    def log_upload(
        self, filename: str, pages: Any, token_count: Any, known_count: Any,
        unknown_count: Any, uncertain_count: Any,
    ) -> dict[str, str]:
        with self._lock:
            rows = self._read_rows(settings.upload_log_path, UPLOAD_LOG_COLUMNS)
            row = {
                "id": str(uuid.uuid4()), "filename": filename, "pages": pages,
                "token_count": token_count, "known_count": known_count,
                "unknown_count": unknown_count, "uncertain_count": uncertain_count,
                "created_at": _now(),
            }
            rows.append(row)
            self._write_rows(settings.upload_log_path, UPLOAD_LOG_COLUMNS, rows)
            return row

    def get_history(self, limit: int = 100) -> list[dict[str, str]]:
        with self._lock:
            return list(reversed(self._read_rows(settings.history_path, HISTORY_COLUMNS)))[0:max(0, limit)]

    def unknown_counts(self) -> dict[str, int]:
        rows = self.list_unknown()
        return {
            "total": len(rows), "pending": sum(row["status"] == "pending" for row in rows),
            "approved": sum(row["status"] == "approved" for row in rows),
            "rejected": sum(row["status"] == "rejected" for row in rows),
        }

    def approved_count(self) -> int:
        with self._lock:
            return len(self._read_rows(settings.approved_dataset_path, APPROVED_COLUMNS))

    def upload_count(self) -> int:
        with self._lock:
            return len(self._read_rows(settings.upload_log_path, UPLOAD_LOG_COLUMNS))

    @staticmethod
    def _read_frame(path: Path, columns: list[str]) -> pd.DataFrame:
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame(columns=columns)
        return pd.read_csv(path, dtype=str, keep_default_na=False)

    def load_aisc_dataset(self) -> pd.DataFrame:
        return self._read_frame(settings.training_dataset_path, ["token", "class"])

    def load_approved_dataset(self) -> pd.DataFrame:
        frame = self._read_frame(settings.approved_dataset_path, APPROVED_COLUMNS)
        for column in APPROVED_COLUMNS:
            if column not in frame:
                frame[column] = ""
        return frame[APPROVED_COLUMNS]

    def build_merged_training_frame(self) -> pd.DataFrame:
        aisc = self.load_aisc_dataset()
        if "category" not in aisc:
            aisc["category"] = ""
        approved = self.load_approved_dataset()[["token", "class", "category"]]
        merged = pd.concat([aisc[["token", "class", "category"]], approved], ignore_index=True)
        merged = merged.fillna("").astype(str)
        return merged[(merged["token"].str.strip() != "") & (merged["class"].str.strip() != "")]


dataset_manager = DatasetManager()
