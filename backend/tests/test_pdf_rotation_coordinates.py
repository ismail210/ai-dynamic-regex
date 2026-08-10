"""Verifies PyMuPDF's rotated-page coordinate contract against the
version actually pinned in this repository (see backend/requirements.txt).

The ChatGPT deep-research report ran this experiment against PyMuPDF
1.26.7 and concluded: ``page.get_drawings()`` returns content in
*unrotated* page space, and ``page.rotation_matrix`` is required to map
those coordinates into the visually-displayed (rotated) frame. This file
re-runs the same experiment against the pinned ``pymupdf==1.28.0`` to
confirm the contract still holds, and additionally documents (does not
yet fix) how ``geometry_extractor.extract_geometry`` behaves on a
rotated page — see
docs/geometry_graph_audit/09_open_questions.md Q3 and
docs/geometry_graph_audit/03_geometry_audit.md §2.

Full coordinate normalization (choosing a canonical display frame) is
out of scope for this phase — see
docs/geometry_graph_audit/08_prioritized_roadmap.md P1.1. This phase
only establishes the tested, verified baseline that any future
normalization work must be correct against.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.geometry_extractor import extract_geometry

# A simple horizontal line, always drawn the same way regardless of the
# rotation under test -- what changes is only page.set_rotation().
LINE_START = (40.0, 50.0)
LINE_END = (240.0, 50.0)

# Expected raw (unrotated) coordinates, and the expected *visual* position
# after applying page.rotation_matrix, for each rotation angle. Derived by
# running PyMuPDF's own documented transform, not hand-derived geometry --
# this file is a regression guard against the library's contract changing
# out from under this pipeline, not a hand-rolled rotation implementation.
ROTATIONS = (0, 90, 180, 270)


def _make_rotated_pdf(path: Path, rotation: int) -> None:
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.draw_line(
        fitz.Point(*LINE_START), fitz.Point(*LINE_END), color=(0, 0, 0), width=2
    )
    page.set_rotation(rotation)
    doc.save(path)
    doc.close()


class PdfRotationCoordinateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_drawings_returns_unrotated_coordinates_at_every_angle(self) -> None:
        for rotation in ROTATIONS:
            with self.subTest(rotation=rotation):
                pdf_path = Path(self.tmp.name) / f"rot_{rotation}.pdf"
                _make_rotated_pdf(pdf_path, rotation)

                with fitz.open(str(pdf_path)) as doc:
                    page = doc[0]
                    self.assertEqual(page.rotation, rotation)
                    drawings = page.get_drawings()
                    self.assertEqual(len(drawings), 1)
                    rect = drawings[0]["rect"]
                    # Regardless of page.rotation, the raw drawing
                    # coordinates are exactly what was drawn -- PyMuPDF
                    # does not pre-rotate get_drawings() output.
                    self.assertAlmostEqual(rect.x0, LINE_START[0])
                    self.assertAlmostEqual(rect.y0, LINE_START[1])
                    self.assertAlmostEqual(rect.x1, LINE_END[0])
                    self.assertAlmostEqual(rect.y1, LINE_END[1])

    def test_rotation_matrix_maps_to_the_correct_visual_position(self) -> None:
        # This is the specific case the deep-research report verified:
        # a 90-degree rotation should turn a horizontal line into a
        # visually vertical one once rotation_matrix is applied.
        pdf_path = Path(self.tmp.name) / "rot_90.pdf"
        _make_rotated_pdf(pdf_path, 90)

        with fitz.open(str(pdf_path)) as doc:
            page = doc[0]
            start = fitz.Point(*LINE_START) * page.rotation_matrix
            end = fitz.Point(*LINE_END) * page.rotation_matrix

            # Visually vertical: x is now constant, y spans the page height.
            self.assertAlmostEqual(start.x, end.x)
            self.assertNotAlmostEqual(start.y, end.y)

    def test_derotation_matrix_is_the_inverse_of_rotation_matrix(self) -> None:
        for rotation in ROTATIONS:
            with self.subTest(rotation=rotation):
                pdf_path = Path(self.tmp.name) / f"derot_{rotation}.pdf"
                _make_rotated_pdf(pdf_path, rotation)

                with fitz.open(str(pdf_path)) as doc:
                    page = doc[0]
                    original = fitz.Point(*LINE_START)
                    round_tripped = (
                        original * page.rotation_matrix * page.derotation_matrix
                    )
                    self.assertAlmostEqual(original.x, round_tripped.x, places=4)
                    self.assertAlmostEqual(original.y, round_tripped.y, places=4)

    def test_extract_geometry_currently_reports_unrotated_coordinates(self) -> None:
        # Documents CURRENT pipeline behavior: extract_geometry does not
        # apply page.rotation_matrix, so its bbox/points match raw
        # get_drawings() output verbatim, not the visually-rotated frame.
        # This is not asserted as "correct" -- it is the tested baseline
        # a future normalization layer (P1.1) must change deliberately,
        # not accidentally.
        for rotation in ROTATIONS:
            with self.subTest(rotation=rotation):
                pdf_path = Path(self.tmp.name) / f"extract_{rotation}.pdf"
                _make_rotated_pdf(pdf_path, rotation)

                result = extract_geometry(str(pdf_path), None)
                summary = result["page_summaries"][0]
                self.assertEqual(summary["page_rotation"], rotation)

                self.assertEqual(len(result["objects"]), 1)
                obj = result["objects"][0]
                bbox = obj["bbox"]
                self.assertAlmostEqual(bbox[0], LINE_START[0], places=1)
                self.assertAlmostEqual(bbox[1], LINE_START[1], places=1)
                self.assertAlmostEqual(bbox[2], LINE_END[0], places=1)
                self.assertAlmostEqual(bbox[3], LINE_END[1], places=1)


if __name__ == "__main__":
    unittest.main()
