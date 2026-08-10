"""Regression coverage for the dense-page (>250 drawings) geometry cap.

Reproduces the defect documented in
docs/geometry_graph_audit/03_geometry_audit.md §7 and confirmed by the
ChatGPT deep-research report's local PyMuPDF experiment: the original
cap sorts by raw bounding-box area, and axis-aligned lines have zero
bbox area, so they are the first entities dropped once a page exceeds
250 raw drawings — even when every dropped line is a long, structurally
significant member and every kept "positive area" shape is an
insignificant speck.

This file exercises both ``dense_page_cap_strategy`` values (see
``services.engineering.geometry_extractor.extract_geometry``) against the
same synthetic dense page, so the A/B improvement is measured, not just
asserted narratively. Production default is now ``"length_aware"``; the
historical ``"legacy_area"`` defect remains covered by an explicit test.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.geometry_extractor import extract_geometry

LINE_COUNT = 300
RECT_COUNT = 20
LINE_LENGTH = 300.0
RECT_SIZE = 1.0  # deliberately tiny/insignificant "noise" rectangles


def _make_dense_page_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=2200, height=1700)

    # 300 independent horizontal line paths -> zero bbox area each,
    # but each is a genuinely long (300pt), structurally significant path.
    for i in range(LINE_COUNT):
        y = 10 + (i % 150) * 10
        x0 = 50 if i < 150 else 1150
        page.draw_line(
            fitz.Point(x0, y),
            fitz.Point(x0 + LINE_LENGTH, y),
            color=(0, 0, 0),
            width=1,
        )

    # 20 tiny 1x1 "noise" rectangles -> nonzero (but insignificant) bbox area.
    for i in range(RECT_COUNT):
        x = 50 + i * 20
        y = 1600
        page.draw_rect(
            fitz.Rect(x, y, x + RECT_SIZE, y + RECT_SIZE),
            color=(0, 0, 0),
            width=1,
        )

    doc.save(path)
    doc.close()


class DensePageCapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "dense.pdf"
        _make_dense_page_pdf(self.pdf)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _agreement_for(self, page_summary: dict) -> dict:
        agreement = page_summary.get("cap_strategy_agreement")
        self.assertIsNotNone(
            agreement, "cap must have triggered on this fixture (>250 raw drawings)"
        )
        return agreement

    def test_raw_drawing_count_exceeds_cap(self) -> None:
        result = extract_geometry(str(self.pdf), None)
        page_summary = result["page_summaries"][0]
        self.assertEqual(page_summary["raw_drawing_count"], LINE_COUNT + RECT_COUNT)
        self.assertTrue(page_summary["drawing_cap_applied"])
        self.assertEqual(page_summary["retained_drawing_count"], 250)
        self.assertEqual(page_summary["drawing_cap_threshold"], 250)

    def test_default_strategy_is_length_aware(self) -> None:
        explicit_default = extract_geometry(
            str(self.pdf), None, dense_page_cap_strategy="length_aware"
        )
        implicit_default = extract_geometry(str(self.pdf), None)
        ids_explicit = sorted(o["geometry_id"] for o in explicit_default["objects"])
        ids_implicit = sorted(o["geometry_id"] for o in implicit_default["objects"])
        self.assertEqual(ids_explicit, ids_implicit)
        self.assertEqual(
            implicit_default["page_summaries"][0]["dense_page_cap_strategy"],
            "length_aware",
        )

    def test_legacy_area_strategy_reproduces_the_known_defect(self) -> None:
        result = extract_geometry(
            str(self.pdf), None, dense_page_cap_strategy="legacy_area"
        )
        summary = result["page_summaries"][0]
        agreement = self._agreement_for(summary)

        # Every one of the 20 insignificant 1x1 specks survives (area > 0
        # beats area == 0 unconditionally), while the 70 excess long lines
        # (zero bbox area) are the ones dropped -- reproducing the exact
        # mechanical defect the audit and research report both describe.
        self.assertEqual(agreement["legacy_area_kept_count"], 250)
        self.assertEqual(
            agreement["zero_area_paths_dropped_by_legacy_area"],
            LINE_COUNT + RECT_COUNT - 250,
        )

        kinds = [obj["kind"] for obj in result["objects"]]
        rectangle_like = sum(1 for k in kinds if k in {"rectangle", "symbol"})
        line_like = sum(1 for k in kinds if k == "line")
        self.assertEqual(rectangle_like, RECT_COUNT, "all 20 specks should survive")
        self.assertEqual(
            line_like,
            250 - RECT_COUNT,
            "only 230 of the 300 significant lines should survive",
        )

    def test_length_aware_strategy_reduces_zero_area_path_loss(self) -> None:
        legacy = extract_geometry(
            str(self.pdf), None, dense_page_cap_strategy="legacy_area"
        )
        length_aware = extract_geometry(
            str(self.pdf), None, dense_page_cap_strategy="length_aware"
        )
        legacy_summary = legacy["page_summaries"][0]
        length_aware_summary = length_aware["page_summaries"][0]

        legacy_agreement = self._agreement_for(legacy_summary)
        length_aware_agreement = self._agreement_for(length_aware_summary)

        # Both A/B numbers are computed identically regardless of which
        # strategy is active (the diagnostic is a pure comparison), so
        # they must agree between the two calls.
        self.assertEqual(
            legacy_agreement["zero_area_paths_dropped_by_length_aware"],
            length_aware_agreement["zero_area_paths_dropped_by_length_aware"],
        )

        # The whole point of the fix: length-aware dropping loses strictly
        # fewer of the long, significant zero-area lines than the legacy
        # area-only sort did.
        self.assertLess(
            length_aware_agreement["zero_area_paths_dropped_by_length_aware"],
            legacy_agreement["zero_area_paths_dropped_by_legacy_area"],
        )

        kinds = [obj["kind"] for obj in length_aware["objects"]]
        line_like = sum(1 for k in kinds if k == "line")
        rectangle_like = sum(1 for k in kinds if k in {"rectangle", "symbol"})
        self.assertGreater(
            line_like,
            250 - RECT_COUNT,
            "length-aware strategy should retain more significant lines "
            "than the legacy area-only sort",
        )
        self.assertLess(
            rectangle_like,
            RECT_COUNT,
            "length-aware strategy should no longer unconditionally keep "
            "every insignificant nonzero-area speck",
        )

    def test_invalid_strategy_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            extract_geometry(str(self.pdf), None, dense_page_cap_strategy="bogus")

    def test_cap_diagnostics_absent_when_cap_does_not_trigger(self) -> None:
        # Reuse the small fixture pattern from test_engineering_pipeline.py
        # to confirm the new diagnostic fields degrade gracefully below the
        # cap threshold instead of raising or misreporting.
        with tempfile.TemporaryDirectory() as tmp:
            small_pdf = Path(tmp) / "small.pdf"
            doc = fitz.open()
            page = doc.new_page(width=600, height=800)
            page.draw_line(fitz.Point(50, 50), fitz.Point(200, 50), color=(0, 0, 0))
            doc.save(small_pdf)
            doc.close()

            result = extract_geometry(str(small_pdf), None)
            summary = result["page_summaries"][0]
            self.assertFalse(summary["drawing_cap_applied"])
            self.assertIsNone(summary["cap_strategy_agreement"])


if __name__ == "__main__":
    unittest.main()
