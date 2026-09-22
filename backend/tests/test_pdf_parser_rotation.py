"""Phase D2 Part A: regression tests for the ``_span_rotation`` fix.

Root cause (proven, see docs/validation/phase_d1_orientation_forensics.md):
PyMuPDF's ``get_text("dict")`` puts the text direction vector on the LINE
dict, never on the individual span -- ``_span_rotation`` used to read
``span.get("dir")``, which is always absent, so rotation silently defaulted
to 0.0 for every span in every document. This file locks in the fix at both
the unit level (the pure function) and the integration level (the real
extraction pipeline, end to end).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.pdf_parser import _span_rotation, extract_document_structure


class SpanRotationUnitTests(unittest.TestCase):
    """Direct tests of the pure function -- no PDF needed."""

    def test_line_dir_horizontal(self):
        self.assertEqual(_span_rotation({}, line_dir=(1.0, 0.0)), 0.0)

    def test_line_dir_reversed_horizontal_is_same_axis(self):
        # (-1, 0) is the same LINE direction as (1, 0), just the opposite
        # reading direction -- atan2 gives 180.0, which the axial (%180)
        # comparison downstream already treats as equal to 0.0.
        angle = _span_rotation({}, line_dir=(-1.0, 0.0))
        self.assertEqual(angle % 180.0, 0.0)

    def test_line_dir_vertical(self):
        angle = _span_rotation({}, line_dir=(0.0, 1.0))
        self.assertEqual(angle, 90.0)

    def test_line_dir_reversed_vertical_is_same_axis(self):
        angle = _span_rotation({}, line_dir=(0.0, -1.0))
        self.assertEqual(angle % 180.0, 90.0)

    def test_line_dir_diagonal_positive(self):
        angle = _span_rotation({}, line_dir=(1.0, 1.0))
        self.assertAlmostEqual(angle, 45.0)

    def test_line_dir_diagonal_negative(self):
        angle = _span_rotation({}, line_dir=(1.0, -1.0))
        self.assertAlmostEqual(angle, -45.0)
        # Confirm the two diagonal signs are NOT the same axis.
        positive = _span_rotation({}, line_dir=(1.0, 1.0))
        self.assertNotEqual(angle % 180.0, positive % 180.0)

    def test_missing_line_dir_returns_safe_default_not_fabricated(self):
        self.assertEqual(_span_rotation({}, line_dir=None), 0.0)

    def test_malformed_line_dir_returns_safe_default(self):
        self.assertEqual(_span_rotation({}, line_dir=(1.0,)), 0.0)  # too short
        self.assertEqual(_span_rotation({}, line_dir=()), 0.0)

    def test_zero_vector_line_dir_returns_safe_default(self):
        self.assertEqual(_span_rotation({}, line_dir=(0.0, 0.0)), 0.0)

    def test_span_level_dir_takes_precedence_if_ever_present(self):
        # Forward-compatibility: if a future PyMuPDF version starts
        # populating span["dir"] directly, it must win over line_dir.
        angle = _span_rotation({"dir": (0.0, 1.0)}, line_dir=(1.0, 0.0))
        self.assertEqual(angle, 90.0)

    def test_no_direction_anywhere_returns_safe_default(self):
        self.assertEqual(_span_rotation({}), 0.0)


def _make_rotation_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((72, 100), "W18X35", fontsize=14, rotate=0)
    page.insert_text((72, 300), "W12X26", fontsize=14, rotate=90)
    doc.save(path)
    doc.close()


class PdfParserRotationIntegrationTests(unittest.TestCase):
    """End-to-end: the real extraction pipeline, on a real (synthetic) PDF."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.pdf_path = Path(self._tmpdir.name) / "rotation_sample.pdf"
        _make_rotation_pdf(self.pdf_path)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _words_by_text(self, document: dict) -> dict:
        return {w["text"]: w for w in document.get("words") or []}

    def test_line_level_dir_is_actually_consumed(self):
        document = extract_document_structure(str(self.pdf_path))
        lines = document.get("lines") or []
        rotations = {round(float(ln.get("rotation") or 0.0) % 180.0, 1) for ln in lines}
        # Before the fix this set would be exactly {0.0} -- every line
        # defaulting to zero regardless of true rotation. After the fix we
        # must see BOTH the horizontal (0) and vertical (90) axis present.
        self.assertIn(0.0, rotations)
        self.assertIn(90.0, rotations)

    def test_horizontal_text_reports_horizontal_rotation(self):
        document = extract_document_structure(str(self.pdf_path))
        words = self._words_by_text(document)
        self.assertIn("W18X35", words)
        self.assertEqual(float(words["W18X35"]["rotation"]) % 180.0, 0.0)

    def test_vertical_text_reports_vertical_rotation_not_false_zero(self):
        document = extract_document_structure(str(self.pdf_path))
        words = self._words_by_text(document)
        self.assertIn("W12X26", words)
        # This is the regression this whole fix exists for: before the fix,
        # this rotated word's "rotation" was silently 0.0 too.
        self.assertEqual(round(float(words["W12X26"]["rotation"]) % 180.0, 1), 90.0)

    def test_semantic_text_unchanged_by_rotation_fix(self):
        document = extract_document_structure(str(self.pdf_path))
        words = self._words_by_text(document)
        self.assertEqual(words["W18X35"]["text"], "W18X35")
        self.assertEqual(words["W12X26"]["text"], "W12X26")

    def test_bbox_unchanged_by_rotation_fix(self):
        document = extract_document_structure(str(self.pdf_path))
        words = self._words_by_text(document)
        for w in words.values():
            bbox = w["bbox"]
            self.assertEqual(len(bbox), 4)
            self.assertLess(bbox[0], bbox[2])
            self.assertLess(bbox[1], bbox[3])


if __name__ == "__main__":
    unittest.main()
