"""Categories 4, 19, 20, 21: candidate-dataset construction behavior.

Uses hand-built ``document_structure``/``geometry`` dicts (the same
shape ``pdf_parser.extract_document_structure`` /
``geometry_extractor.extract_geometry`` produce) for tightly controlled
scenarios, plus one real-PDF integration case.
"""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.geometry_extractor import extract_geometry
from services.pdf_parser import extract_document_structure
from services.ml_association.candidate_dataset import build_label_groups

CREATED_AT = "2026-01-01T00:00:00Z"


def _token(token_id: str, text: str, page: int, x: float, y: float, w: float = 20, h: float = 10):
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


def _document(tokens):
    return {
        "engineering_tokens": tokens,
        "pages": [{"page_number": 1, "width": 1000, "height": 1000, "rotation": 0}],
        "lines": [],
    }


def _geometry(objects):
    return {"objects": objects, "page_summaries": []}


class DeterministicOrderingTests(unittest.TestCase):
    def test_group_order_is_stable_regardless_of_input_token_order(self) -> None:
        tokens_a = [
            _token("token_p1_2", "W12X26", 1, 300, 300),
            _token("token_p1_0", "W18X35", 1, 0, 0),
            _token("token_p1_1", "HSS8X8", 1, 150, 150),
        ]
        tokens_b = list(reversed(tokens_a))
        document_a = _document(tokens_a)
        document_b = _document(tokens_b)
        geometry = _geometry([_geom("geom_1", 1, 5, 5)])

        groups_a = build_label_groups(
            document_a, geometry, project_id="p1", document_id="d1", created_at=CREATED_AT
        )
        groups_b = build_label_groups(
            document_b, geometry, project_id="p1", document_id="d1", created_at=CREATED_AT
        )
        self.assertEqual(
            [g.text_entity_id for g in groups_a], [g.text_entity_id for g in groups_b]
        )
        self.assertEqual([g.model_dump() for g in groups_a], [g.model_dump() for g in groups_b])

    def test_repeated_calls_are_byte_identical(self) -> None:
        document = _document([_token("token_p1_0", "W18X35", 1, 0, 0)])
        geometry = _geometry([_geom("geom_1", 1, 5, 5)])
        groups_1 = build_label_groups(
            document, geometry, project_id="p1", document_id="d1", created_at=CREATED_AT
        )
        groups_2 = build_label_groups(
            copy.deepcopy(document),
            copy.deepcopy(geometry),
            project_id="p1",
            document_id="d1",
            created_at=CREATED_AT,
        )
        self.assertEqual([g.model_dump() for g in groups_1], [g.model_dump() for g in groups_2])


class OneLabelSeveralGeometriesTests(unittest.TestCase):
    def test_one_label_with_several_valid_geometries_are_all_candidates(self) -> None:
        document = _document([_token("token_p1_0", "W18X35", 1, 0, 0)])
        geometry = _geometry(
            [
                _geom("geom_near", 1, 15, 0),
                _geom("geom_mid", 1, 45, 0),
                _geom("geom_far", 1, 75, 0),
            ]
        )
        groups = build_label_groups(
            document, geometry, project_id="p1", document_id="d1", created_at=CREATED_AT, top_k=5
        )
        self.assertEqual(len(groups), 1)
        real_ids = [c.geometry_entity_id for c in groups[0].candidates if not c.is_no_match_placeholder]
        self.assertEqual(real_ids, ["geom_near", "geom_mid", "geom_far"])
        # A no-valid-target option must always be present alongside real candidates.
        self.assertTrue(any(c.is_no_match_placeholder for c in groups[0].candidates))


class TwoLabelsCompetingTests(unittest.TestCase):
    def test_two_labels_competing_for_one_geometry_both_reference_it(self) -> None:
        document = _document(
            [
                _token("token_p1_0", "W18X35", 1, 0, 0),
                _token("token_p1_1", "W12X26", 1, 10, 0),
            ]
        )
        geometry = _geometry([_geom("geom_shared", 1, 5, 0, w=2, h=2)])
        groups = build_label_groups(
            document, geometry, project_id="p1", document_id="d1", created_at=CREATED_AT
        )
        self.assertEqual(len(groups), 2)
        for group in groups:
            real_ids = [
                c.geometry_entity_id for c in group.candidates if not c.is_no_match_placeholder
            ]
            self.assertIn(
                "geom_shared",
                real_ids,
                "candidate generation must not artificially enforce exclusivity "
                "-- that is a future global-resolution concern (roadmap P1.6), "
                "not this layer's job",
            )


class TwoSimilarDetailsTests(unittest.TestCase):
    def test_two_visually_identical_geometries_in_different_page_areas_stay_distinct(self) -> None:
        # This repository has no detail-/region-detection layer yet
        # (docs/geometry_graph_audit/08_prioritized_roadmap.md P1.4 is
        # still open), so "two identical detail regions" is approximated
        # here as two geometrically-identical shapes placed far apart on
        # one page. What Phase 2 CAN and does guarantee without a region
        # layer: distance-based candidate generation does not confuse
        # them, each keeps its own stable ID, and region_id is left
        # explicitly None (not fabricated) on every row/group.
        document = _document(
            [
                _token("token_p1_0", "W18X35", 1, 0, 0),
                _token("token_p1_1", "W18X35", 1, 500, 500),
            ]
        )
        geometry = _geometry(
            [
                _geom("geom_detail_a", 1, 15, 15, w=10, h=10),
                _geom("geom_detail_b", 1, 515, 515, w=10, h=10),  # identical shape, far away
            ]
        )
        groups = build_label_groups(
            document, geometry, project_id="p1", document_id="d1", created_at=CREATED_AT
        )
        by_label = {g.text_entity_id: g for g in groups}
        first_real = [
            c.geometry_entity_id
            for c in by_label["token_p1_0"].candidates
            if not c.is_no_match_placeholder
        ]
        second_real = [
            c.geometry_entity_id
            for c in by_label["token_p1_1"].candidates
            if not c.is_no_match_placeholder
        ]
        self.assertEqual(first_real, ["geom_detail_a"])
        self.assertEqual(second_real, ["geom_detail_b"])
        for group in groups:
            self.assertIsNone(
                group.region_id, "region_id must stay explicitly None, not a fabricated value"
            )
            for candidate in group.candidates:
                self.assertFalse(candidate.relationship.region_available)


class RealPdfIntegrationTests(unittest.TestCase):
    def test_build_label_groups_on_a_real_extracted_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sample.pdf"
            doc = fitz.open()
            page = doc.new_page(width=600, height=800)
            page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
            page.draw_rect(fitz.Rect(80, 90, 120, 110), color=(0, 0, 0), width=1)
            doc.save(pdf_path)
            doc.close()

            document_structure = extract_document_structure(str(pdf_path))
            geometry = extract_geometry(str(pdf_path), document_structure)
            groups = build_label_groups(
                document_structure,
                geometry,
                project_id="p1",
                document_id="d1",
                created_at=CREATED_AT,
            )
            self.assertTrue(groups)
            for group in groups:
                self.assertTrue(group.candidates)
                self.assertTrue(any(c.is_no_match_placeholder for c in group.candidates))


if __name__ == "__main__":
    unittest.main()
