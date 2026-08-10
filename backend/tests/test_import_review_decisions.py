"""Regression tests for the batch review-decision importer script.

Uses synthetic label groups/decisions only, written to a temp directory
-- never touches the real, git-ignored pilot data. Exercises the
accept/reject/skip paths and the feature-flag gate.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from services.ml_association import outcome_store  # noqa: E402
from services.ml_association.candidate_dataset import build_label_groups  # noqa: E402
from services.ml_association.review_export import build_export_payload  # noqa: E402

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_review_decisions.py"
_spec = importlib.util.spec_from_file_location("import_review_decisions", _MODULE_PATH)
importer = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = importer
_spec.loader.exec_module(importer)  # type: ignore[union-attr]


def _token(token_id: str, text: str, page: int, x: float, y: float, w: float = 40, h: float = 12):
    return {
        "token_id": token_id,
        "text": text,
        "page": page,
        "bbox": [x, y, x + w, y + h],
        "font_size": 10,
        "rotation": 0,
        "line": {},
        "engineering_object_type": "beam",
    }


def _geom(geometry_id: str, page: int, x: float, y: float, w: float = 10, h: float = 10, kind: str = "line"):
    return {
        "geometry_id": geometry_id,
        "page_number": page,
        "bbox": [x, y, x + w, y + h],
        "center": [x + w / 2.0, y + h / 2.0],
        "kind": kind,
        "length": w,
        "width": w,
        "area": w * h,
        "orientation": 0.0,
        "nearby_text": None,
    }


def _synthetic_document_and_geometry():
    document_structure = {
        "engineering_tokens": [_token("token_1", "W12X26", 1, 100, 100)],
        "pages": [{"page_number": 1, "width": 1000, "height": 1000, "rotation": 0}],
        "lines": [],
    }
    geometry = {
        "objects": [
            _geom("geom_near", 1, 90, 90, w=110, h=2),
            _geom("geom_far", 1, 500, 500, w=10, h=2),
        ],
        "page_summaries": [],
    }
    return document_structure, geometry


class ImportReviewDecisionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._prior_flag = settings.ml_association_dataset_enabled
        object.__setattr__(settings, "ml_association_dataset_enabled", True)
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(object.__setattr__, settings, "ml_association_dataset_enabled", self._prior_flag)

        self.tmp_path = Path(self._tmp.name)
        self.exports_dir = self.tmp_path / "exports"
        self.decisions_dir = self.tmp_path / "decisions"
        self.outcomes_path = self.tmp_path / "outcomes.jsonl"
        self.exports_dir.mkdir()
        self.decisions_dir.mkdir()

        document_structure, geometry = _synthetic_document_and_geometry()
        groups = build_label_groups(
            document_structure,
            geometry,
            project_id="project_test",
            document_id="doc_test",
            created_at="2026-01-01T00:00:00+00:00",
        )
        self.assertTrue(groups, "synthetic fixture should produce at least one label group")
        self.group = groups[0]
        payload = build_export_payload(self.group, svg_relative_path=f"{self.group.group_id}.svg")
        (self.exports_dir / f"{self.group.group_id}.json").write_text(
            json.dumps(payload.model_dump(mode="json")), encoding="utf-8"
        )

    def _write_decision(self, filename: str, **overrides) -> None:
        candidate = next(c for c in self.group.candidates if not c.is_no_match_placeholder)
        decision = {
            "export_schema_version": "2.0",
            "group_id": self.group.group_id,
            "project_id": self.group.project_id,
            "document_id": self.group.document_id,
            "page_id": self.group.page_id,
            "text_entity_id": self.group.text_entity_id,
            "review_label": "direct_target",
            "reviewed_target_geometry_ids": [candidate.geometry_entity_id],
            "candidate_generation_miss": False,
            "callout_scope": "single",
            "reviewer_id": "reviewer_a",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "annotation_notes": None,
        }
        decision.update(overrides)
        (self.decisions_dir / filename).write_text(json.dumps(decision), encoding="utf-8")

    def test_valid_decision_is_accepted_and_persisted(self) -> None:
        self._write_decision(f"{self.group.group_id}.decision.json")
        summary = importer.import_all(self.decisions_dir, self.exports_dir, self.outcomes_path)
        self.assertEqual(summary["accepted"], [f"{self.group.group_id}.decision.json"])
        self.assertEqual(summary["rejected"], [])
        outcomes = outcome_store.load_all_outcomes(self.outcomes_path)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].group_id, self.group.group_id)

    def test_two_reviewers_on_same_group_both_persist(self) -> None:
        self._write_decision(f"{self.group.group_id}.decision.json", reviewer_id="reviewer_a")
        (self.decisions_dir / f"{self.group.group_id}.decision.json").rename(
            self.decisions_dir / f"{self.group.group_id}.reviewer_a.decision.json"
        )
        self._write_decision(f"{self.group.group_id}.reviewer_b.decision.json", reviewer_id="reviewer_b")

        summary = importer.import_all(self.decisions_dir, self.exports_dir, self.outcomes_path)
        self.assertEqual(len(summary["accepted"]), 2)
        outcomes = outcome_store.history_for_group(self.group.group_id, self.outcomes_path)
        self.assertEqual({o.reviewer_id for o in outcomes}, {"reviewer_a", "reviewer_b"})

    def test_malformed_review_label_is_rejected_not_written(self) -> None:
        self._write_decision(f"{self.group.group_id}.decision.json", review_label="not_a_real_label")
        summary = importer.import_all(self.decisions_dir, self.exports_dir, self.outcomes_path)
        self.assertEqual(summary["accepted"], [])
        self.assertEqual(summary["rejected"], [f"{self.group.group_id}.decision.json"])
        self.assertFalse(self.outcomes_path.exists())

    def test_missing_export_file_is_skipped_not_crashed(self) -> None:
        (self.decisions_dir / "group_nonexistent.decision.json").write_text(
            json.dumps({"group_id": "group_nonexistent"}), encoding="utf-8"
        )
        summary = importer.import_all(self.decisions_dir, self.exports_dir, self.outcomes_path)
        self.assertEqual(summary["rejected"], ["group_nonexistent.decision.json"])

    def test_main_refuses_to_run_when_feature_flag_disabled(self) -> None:
        object.__setattr__(settings, "ml_association_dataset_enabled", False)
        self._write_decision(f"{self.group.group_id}.decision.json")
        argv = sys.argv
        sys.argv = [
            "import_review_decisions.py",
            "--decisions-dir",
            str(self.decisions_dir),
            "--exports-dir",
            str(self.exports_dir),
            "--outcomes-path",
            str(self.outcomes_path),
        ]
        try:
            exit_code = importer.main()
        finally:
            sys.argv = argv
        self.assertEqual(exit_code, 2)
        self.assertFalse(self.outcomes_path.exists())


if __name__ == "__main__":
    unittest.main()
