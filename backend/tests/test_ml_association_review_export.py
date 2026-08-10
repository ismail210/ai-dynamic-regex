"""Categories 5, 22, 23: reviewer export determinism, rotated pages, dense pages."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.geometry_extractor import extract_geometry
from services.pdf_parser import extract_document_structure
from services.ml_association.candidate_dataset import build_label_groups
from services.ml_association.review_export import write_group_export

CREATED_AT = "2026-01-01T00:00:00Z"


def _build_groups_for_pdf(pdf_path: Path):
    document_structure = extract_document_structure(str(pdf_path))
    geometry = extract_geometry(str(pdf_path), document_structure)
    return build_label_groups(
        document_structure, geometry, project_id="p1", document_id="d1", created_at=CREATED_AT
    )


class ExportReproducibilityTests(unittest.TestCase):
    def test_export_is_byte_identical_across_two_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sample.pdf"
            doc = fitz.open()
            page = doc.new_page(width=600, height=800)
            page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
            page.draw_rect(fitz.Rect(80, 90, 120, 110), color=(0, 0, 0), width=1)
            doc.save(pdf_path)
            doc.close()

            groups = _build_groups_for_pdf(pdf_path)
            out_a = Path(tmp) / "export_a"
            out_b = Path(tmp) / "export_b"
            payload_a = write_group_export(groups[0], pdf_path=str(pdf_path), output_dir=out_a)
            payload_b = write_group_export(groups[0], pdf_path=str(pdf_path), output_dir=out_b)

            svg_a = (out_a / payload_a.svg_relative_path).read_bytes()
            svg_b = (out_b / payload_b.svg_relative_path).read_bytes()
            self.assertEqual(svg_a, svg_b)
            self.assertEqual(payload_a.model_dump(), payload_b.model_dump())

    def test_re_exporting_the_same_group_overwrites_with_identical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sample.pdf"
            doc = fitz.open()
            page = doc.new_page(width=600, height=800)
            page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
            page.draw_rect(fitz.Rect(80, 90, 120, 110), color=(0, 0, 0), width=1)
            doc.save(pdf_path)
            doc.close()

            groups = _build_groups_for_pdf(pdf_path)
            out_dir = Path(tmp) / "export"
            first = write_group_export(groups[0], pdf_path=str(pdf_path), output_dir=out_dir)
            first_bytes = (out_dir / first.svg_relative_path).read_bytes()
            second = write_group_export(groups[0], pdf_path=str(pdf_path), output_dir=out_dir)
            second_bytes = (out_dir / second.svg_relative_path).read_bytes()
            self.assertEqual(first.svg_relative_path, second.svg_relative_path)
            self.assertEqual(first_bytes, second_bytes)


class RotatedPageExportTests(unittest.TestCase):
    def test_export_succeeds_on_a_90_degree_rotated_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "rotated.pdf"
            doc = fitz.open()
            page = doc.new_page(width=600, height=800)
            page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
            page.draw_rect(fitz.Rect(80, 90, 120, 110), color=(0, 0, 0), width=1)
            page.set_rotation(90)
            doc.save(pdf_path)
            doc.close()

            groups = _build_groups_for_pdf(pdf_path)
            self.assertTrue(groups)
            out_dir = Path(tmp) / "export"
            payload = write_group_export(groups[0], pdf_path=str(pdf_path), output_dir=out_dir)
            svg_text = (out_dir / payload.svg_relative_path).read_text(encoding="utf-8")
            self.assertIn("<svg", svg_text)
            self.assertIn("ml_association_overlay", svg_text)

    def test_export_succeeds_for_every_cardinal_rotation(self) -> None:
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                with tempfile.TemporaryDirectory() as tmp:
                    pdf_path = Path(tmp) / f"rot_{rotation}.pdf"
                    doc = fitz.open()
                    page = doc.new_page(width=600, height=800)
                    page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
                    page.draw_rect(fitz.Rect(80, 90, 120, 110), color=(0, 0, 0), width=1)
                    page.set_rotation(rotation)
                    doc.save(pdf_path)
                    doc.close()

                    groups = _build_groups_for_pdf(pdf_path)
                    out_dir = Path(tmp) / "export"
                    payload = write_group_export(
                        groups[0], pdf_path=str(pdf_path), output_dir=out_dir
                    )
                    self.assertTrue((out_dir / payload.svg_relative_path).exists())


class DensePageExportTests(unittest.TestCase):
    def test_export_succeeds_on_a_dense_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "dense.pdf"
            doc = fitz.open()
            page = doc.new_page(width=2200, height=1700)
            page.insert_text((60, 60), "W18X35 BEAM", fontsize=14)
            # 80 lines is enough to exercise multi-candidate export
            # without the runtime cost of the full 300-line Phase 1
            # dense-page fixture (already covered by
            # test_dense_page_geometry_cap.py) -- this test is about the
            # export path succeeding, not re-proving the cap defect.
            for i in range(80):
                y = 100 + i * 15
                page.draw_line(
                    fitz.Point(60, y), fitz.Point(360, y), color=(0, 0, 0), width=1
                )
            doc.save(pdf_path)
            doc.close()

            groups = _build_groups_for_pdf(pdf_path)
            self.assertTrue(groups)
            out_dir = Path(tmp) / "export"
            payload = write_group_export(
                groups[0], pdf_path=str(pdf_path), output_dir=out_dir, nearby_label_bboxes={}
            )
            svg_text = (out_dir / payload.svg_relative_path).read_text(encoding="utf-8")
            self.assertIn("ml_association_overlay", svg_text)
            # Multiple numbered candidates should appear given top_k>1
            # geometry objects are genuinely nearby.
            real_candidates = [
                c for c in groups[0].candidates if not c.is_no_match_placeholder
            ]
            self.assertGreater(len(real_candidates), 1)


class ExportMetadataContentTests(unittest.TestCase):
    def test_json_metadata_exposes_no_valid_target_and_multi_target_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sample.pdf"
            doc = fitz.open()
            page = doc.new_page(width=600, height=800)
            page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
            page.draw_rect(fitz.Rect(80, 90, 120, 110), color=(0, 0, 0), width=1)
            doc.save(pdf_path)
            doc.close()

            groups = _build_groups_for_pdf(pdf_path)
            out_dir = Path(tmp) / "export"
            payload = write_group_export(groups[0], pdf_path=str(pdf_path), output_dir=out_dir)
            metadata = json.loads((out_dir / f"{groups[0].group_id}.json").read_text())
            self.assertIn("no_valid_target_option", metadata)
            self.assertTrue(metadata["multi_target_supported"])
            self.assertIn("annotation_notes_field", metadata)
            self.assertIn("heuristic_selection_candidate_id", metadata)


if __name__ == "__main__":
    unittest.main()
