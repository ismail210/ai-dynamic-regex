"""PDF-space / display-space conversions (``page_space``), checked against
PyMuPDF's own rendering of a page with ``/Rotate``."""

from __future__ import annotations

import unittest

import fitz

from services.engineering.page_space import convert_boxes, display_boxes, to_display, to_pdf


def _word_boxes(rotation: int):
    """The word ``MARK`` as stored (PDF space) and as shown (display space)."""

    document = fitz.open()
    page = document.new_page(width=600, height=400)
    page.insert_text((100, 80), "MARK", fontsize=12)
    page.set_rotation(rotation)
    stored = next(w for w in page.get_text("words") if w[4] == "MARK")[:4]
    shown_doc = fitz.open()
    shown_doc.insert_pdf(document)
    shown = shown_doc[0]
    shown.remove_rotation()
    displayed = next(w for w in shown.get_text("words") if w[4] == "MARK")[:4]
    return page, stored, displayed


class PageSpaceTests(unittest.TestCase):
    def test_display_conversion_matches_the_rendered_page(self):
        for rotation in (0, 90, 180, 270):
            page, stored, displayed = _word_boxes(rotation)
            got = to_display(rotation, page.rect.width, page.rect.height, stored)
            with self.subTest(rotation=rotation):
                for a, b in zip(got, displayed):
                    self.assertAlmostEqual(a, b, delta=0.6)

    def test_pdf_conversion_is_the_inverse(self):
        for rotation in (0, 90, 180, 270):
            page, stored, displayed = _word_boxes(rotation)
            back = to_pdf(rotation, page.rect.width, page.rect.height, displayed)
            with self.subTest(rotation=rotation):
                for a, b in zip(back, stored):
                    self.assertAlmostEqual(a, b, delta=0.6)

    def test_boxes_convert_with_their_nearest_page(self):
        document = {"pages": [{"page_number": 1, "width": 600, "height": 400, "rotation": 0},
                              {"page_number": 2, "width": 600, "height": 400, "rotation": 90}]}
        value = {"page": 2, "bbox": [10, 20, 30, 40], "nested": [{"name_bbox": [10, 20, 30, 40]}],
                 "other": {"page": 1, "bbox": [1, 2, 3, 4]}, "y": 5}
        got = convert_boxes(value, display_boxes(document))
        self.assertEqual(got["bbox"], [560.0, 10.0, 580.0, 30.0])
        self.assertEqual(got["nested"][0]["name_bbox"], [560.0, 10.0, 580.0, 30.0])
        self.assertEqual(got["other"]["bbox"], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(got["y"], 5)
        self.assertEqual(value["bbox"], [10, 20, 30, 40])


if __name__ == "__main__":
    unittest.main()
