"""Shadow structured schedule evidence: compatibility, provenance, safety."""

from __future__ import annotations

import os
import re
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from config import Settings, settings
from services.engineering import schedule_grid
from services.engineering.schedule_grid import (
    attach_schedule_grid,
    build_schedule_evidence,
    build_schedule_grids,
    schedule_mark_map,
)
from tests.test_struct_notation import _accept_catalog, _struct_schedule_words, _word

_BACKEND = Path(__file__).resolve().parents[1]


@contextmanager
def _flags(**values):
    """``Settings`` is frozen; same override idiom as test_legend_profile."""

    original = {name: getattr(settings, name) for name in values}
    try:
        for name, value in values.items():
            object.__setattr__(settings, name, value)
        yield
    finally:
        for name, value in original.items():
            object.__setattr__(settings, name, value)


def _rows(*lines, page: int = 1) -> list:
    return [_word(text, x, y, page) for y, cells in lines for x, text in cells]


class CompatibilityTests(unittest.TestCase):
    def test_current_mode_map_equals_legacy_map(self) -> None:
        words = _struct_schedule_words()
        legacy = schedule_mark_map(build_schedule_grids(words, catalog_fn=_accept_catalog))
        shadow = build_schedule_evidence(words, catalog_fn=_accept_catalog)
        self.assertEqual(shadow["mark_map"], legacy)
        self.assertEqual(shadow["mark_map"]["L1"], "W8X21")

    def test_widened_keeps_legacy_marks(self) -> None:
        words = _struct_schedule_words()
        legacy = schedule_mark_map(build_schedule_grids(words, catalog_fn=_accept_catalog))
        widened = build_schedule_evidence(words, discovery="widened", catalog_fn=_accept_catalog)
        for mark, section in legacy.items():
            self.assertEqual(widened["mark_map"][mark], section)

    def test_l1_record_keeps_plate_evidence_and_provenance(self) -> None:
        records = build_schedule_evidence(_struct_schedule_words(), catalog_fn=_accept_catalog)["records"]
        l1 = next(r for r in records if r["mark_normalized"] == "L1")
        self.assertEqual(l1["primary_section"], "W8X21")
        self.assertIn("lintel", l1["role_tags"])
        self.assertIn("bottom_plate", l1["role_tags"])
        self.assertEqual(l1["components"][0]["role"], "bearing_plate")
        self.assertIsNone(l1["components"][0]["quantity"])
        self.assertFalse(l1["countable_occurrence"])
        self.assertEqual(l1["page_number"], 2)
        self.assertTrue(l1["row_bbox"] and l1["region_bbox"] and l1["source_cells"])


class WidenedDiscoveryTests(unittest.TestCase):
    def _side_by_side(self) -> list:
        return _rows(
            (884, [(100, "PIER"), (160, "SCHEDULE"), (400, "COLUMN"), (460, "SCHEDULE")]),
            (900, [(100, "PIER"), (140, "TYPE"), (200, "SIZE"), (400, "MARK"), (500, "SIZE")]),
            (918, [(100, "P-1"), (200, "1'-4\""), (400, "C-1"), (500, "W8x24")]),
        )

    def test_hyphen_mark_only_in_widened_mode(self) -> None:
        words = self._side_by_side()
        catalog = lambda token: token == "W8X24"  # noqa: E731
        self.assertEqual(build_schedule_evidence(words, catalog_fn=catalog)["mark_map"], {})
        widened = build_schedule_evidence(words, discovery="widened", catalog_fn=catalog)
        self.assertEqual(widened["mark_map"], {"C-1": "W8X24"})
        self.assertNotIn("P-1", widened["mark_map"])
        self.assertEqual(widened["records"][0]["role_tags"], ["column"])

    def test_mark_letter_never_sets_family(self) -> None:
        words = _rows(
            (100, [(100, "LINTEL"), (160, "SCHEDULE")]),
            (116, [(100, "MARK"), (200, "SIZE")]),
            (134, [(100, "L-2"), (200, "4X4X1/4")]),
        )
        widened = build_schedule_evidence(words, discovery="widened")
        self.assertEqual(widened["mark_map"], {})
        self.assertEqual(widened["records"][0]["rejection_reason"], "size_not_catalog_valid")

    def test_conflicting_duplicate_mark_goes_to_review(self) -> None:
        words = _rows(
            (100, [(100, "MARK"), (200, "SIZE")]),
            (116, [(100, "L1"), (200, "W8X21")]),
        ) + _rows(
            (100, [(100, "MARK"), (200, "SIZE")]),
            (116, [(100, "L1"), (200, "W10X33")]),
            page=2,
        )
        shadow = build_schedule_evidence(words, catalog_fn=lambda t: t in {"W8X21", "W10X33"})
        self.assertEqual(shadow["mark_map"], {})
        self.assertEqual(shadow["conflicts"], ["L1"])
        self.assertTrue(all(r["resolution_status"] == "conflict" for r in shadow["records"]))

    def test_reinforcing_schedule_rejects_host_section(self) -> None:
        words = _rows(
            (80, [(100, "COLUMN"), (160, "REINFORCING"), (240, "SCHEDULE")]),
            (96, [(100, "MARK"), (160, "PLATE"), (300, "SIZE")]),
            (114, [(100, "RI-1"), (160, "9\""), (300, "W8x31")]),
        )
        shadow = build_schedule_evidence(words, discovery="widened", catalog_fn=lambda t: t == "W8X31")
        self.assertEqual(shadow["mark_map"], {})
        self.assertEqual(shadow["records"][0]["rejection_reason"], "host_member_schedule")


class FlagAndWiringTests(unittest.TestCase):
    def test_flags_default_off(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SCHEDULE_EVIDENCE_SHADOW_ENABLED", None)
            os.environ.pop("SCHEDULE_EVIDENCE_SHADOW_WIDENED", None)
            fresh = Settings()
        self.assertFalse(fresh.schedule_evidence_shadow_enabled)
        self.assertFalse(fresh.schedule_evidence_shadow_widened)

    def test_attach_is_unchanged_when_flag_off(self) -> None:
        document: dict = {"words": _struct_schedule_words()}
        with _flags(schedule_evidence_shadow_enabled=False):
            attach_schedule_grid(document)
        self.assertNotIn("schedule_evidence_shadow", document)

    def test_attach_stores_side_artifact_when_flag_on(self) -> None:
        document: dict = {"words": _struct_schedule_words()}
        with _flags(
            schedule_evidence_shadow_enabled=True, schedule_evidence_shadow_widened=True
        ), patch.object(schedule_grid, "_catalog_accepts", side_effect=_accept_catalog):
            attach_schedule_grid(document)
        shadow = document["schedule_evidence_shadow"]
        self.assertEqual(shadow["discovery"], "widened")
        self.assertEqual(document["schedule_mark_map"]["L1"], "W8X21")

    def test_shadow_artifact_not_read_by_production(self) -> None:
        pattern = re.compile(r"schedule_evidence_shadow|build_schedule_evidence")
        allowed = {
            _BACKEND / "services" / "engineering" / "schedule_grid.py",
            _BACKEND / "config.py",
        }
        offenders = [
            str(path.relative_to(_BACKEND))
            for folder in ("services", "routers")
            for path in (_BACKEND / folder).rglob("*.py")
            if path not in allowed and pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
