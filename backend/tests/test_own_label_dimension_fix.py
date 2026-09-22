"""Production regression: own-label digit contamination fix for dimension predicate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering import geometry_extractor as GX
from services.engineering.geometry_extractor import extract_geometry
from services.engineering.models import GeometryKind


def _classify_production(
    *,
    kind: GeometryKind,
    length: float,
    bbox: list,
    nearby_text: str,
    nearby_line: dict | None,
    document_structure: dict,
    page_number: int = 8,
) -> GeometryKind:
    """Mirror the production leader/dimension branch in extract_geometry."""
    nearby_for_dim = GX._nearby_text_for_dimension(
        nearby_text=nearby_text,
        nearby_line=nearby_line,
        page_number=page_number,
        document_structure=document_structure,
    )
    out = kind
    if GX._looks_like_leader(out, length, bbox):
        return GeometryKind.LEADER
    if GX._looks_like_dimension(out, length, nearby_for_dim):
        return GeometryKind.DIMENSION
    return out


class OwnLabelDimensionFixTests(unittest.TestCase):
    def test_own_label_w21x44_30_does_not_trigger_dimension(self):
        line = {
            "page_number": 8,
            "text": "W21X44  [30]",
            "bbox": [2058.46, 1219.17, 2122.46, 1247.56],
            "center": [2090.0, 1233.0],
        }
        doc = {"lines": [line]}
        kind = _classify_production(
            kind=GeometryKind.LINE,
            length=241.5,
            bbox=[1982.64, 1209.0, 2215.92, 1271.52],
            nearby_text="W21X44  [30]",
            nearby_line=line,
            document_structure=doc,
        )
        self.assertEqual(kind, GeometryKind.LINE)
        self.assertFalse(
            GX._looks_like_dimension(
                GeometryKind.LINE,
                241.5,
                GX._nearby_text_for_dimension(
                    nearby_text="W21X44  [30]",
                    nearby_line=line,
                    page_number=8,
                    document_structure=doc,
                ),
            )
        )

    def test_e3_positive_fixtures_recover_member(self):
        fixtures = [
            ("W14X22  [25]", "W14X22"),
            ("W21X44  [30]", "W21X44"),
            ("W18X35  [35]", "W18X35"),
            ("W18X35  [28]", "W18X35"),
        ]
        for nearby, _token in fixtures:
            with self.subTest(nearby=nearby):
                line = {
                    "page_number": 8,
                    "text": nearby,
                    "bbox": [100.0, 100.0, 180.0, 130.0],
                    "center": [140.0, 115.0],
                }
                doc = {"lines": [line]}
                kind = _classify_production(
                    kind=GeometryKind.LINE,
                    length=100.0,
                    bbox=[0.0, 0.0, 100.0, 2.0],
                    nearby_text=nearby,
                    nearby_line=line,
                    document_structure=doc,
                )
                self.assertEqual(kind, GeometryKind.LINE)

    def test_unrelated_17k_near_w30x90_still_dimension(self):
        own = {
            "page_number": 8,
            "text": 'W30X90  [42]  c = 3/4"',
            "bbox": [1427.21, 1171.46, 1522.85, 1234.01],
            "center": [1475.0, 1202.0],
        }
        load = {
            "page_number": 8,
            "text": "17K",
            "bbox": [1496.18, 1238.11, 1512.99, 1257.6],
            "center": [1504.59, 1247.86],
        }
        doc = {"lines": [own, load]}
        kind = _classify_production(
            kind=GeometryKind.LINE,
            length=323.0,
            bbox=[1359.6, 1146.48, 1640.16, 1308.48],
            nearby_text="17K",
            nearby_line=load,
            document_structure=doc,
        )
        self.assertEqual(kind, GeometryKind.DIMENSION)

    def test_genuine_fraction_and_length_remain_dimension(self):
        cases = [
            ("7/8", [1550.16, 211.2, 1567.64, 223.88]),
            ("23' - 10\"", [1306.35, 1614.95, 1336.47, 1654.19]),
        ]
        for text, bbox in cases:
            with self.subTest(text=text):
                line = {
                    "page_number": 8,
                    "text": text,
                    "bbox": bbox,
                    "center": [
                        (bbox[0] + bbox[2]) / 2,
                        (bbox[1] + bbox[3]) / 2,
                    ],
                }
                # Member also present but ownership must not transfer to dim text
                member = {
                    "page_number": 8,
                    "text": "W14X22  [23]",
                    "bbox": [100.0, 100.0, 160.0, 120.0],
                    "center": [130.0, 110.0],
                }
                doc = {"lines": [member, line]}
                kind = _classify_production(
                    kind=GeometryKind.LINE,
                    length=120.0,
                    bbox=[bbox[0] - 20, bbox[1] - 20, bbox[2] + 20, bbox[3] + 20],
                    nearby_text=text,
                    nearby_line=line,
                    document_structure=doc,
                )
                self.assertEqual(kind, GeometryKind.DIMENSION)

    def test_e5_1_unrelated_marks_not_stripped(self):
        marks = [
            "H24",
            "H12",
            "R=22K",
            "BP3",
            "S-311",
            "(4*)",
            "L4X3-1/2X3/8",
            "-0'-2 1/2\"",
            "WIDTH 'W' > 2'-0\"",
        ]
        member = {
            "page_number": 7,
            "text": "W18X40",
            "bbox": [100.0, 100.0, 160.0, 120.0],
            "center": [130.0, 110.0],
        }
        for text in marks:
            with self.subTest(text=text):
                line = {
                    "page_number": 7,
                    "text": text,
                    "bbox": [200.0, 200.0, 260.0, 220.0],
                    "center": [230.0, 210.0],
                }
                doc = {"lines": [member, line]}
                filtered = GX._nearby_text_for_dimension(
                    nearby_text=text,
                    nearby_line=line,
                    page_number=7,
                    document_structure=doc,
                )
                self.assertEqual(filtered, text)
                if GX._DIGIT_RE.search(text):
                    kind = _classify_production(
                        kind=GeometryKind.LINE,
                        length=100.0,
                        bbox=[180.0, 180.0, 280.0, 240.0],
                        nearby_text=text,
                        nearby_line=line,
                        document_structure=doc,
                        page_number=7,
                    )
                    self.assertEqual(kind, GeometryKind.DIMENSION)

    def test_incomplete_l4x4_not_treated_as_own_label_token(self):
        self.assertEqual(GX._member_designation_token("L4X4"), "")
        self.assertEqual(GX._member_designation_token("2L4X4"), "")
        # Complete angle with thickness may be a designation token; incomplete must not.
        self.assertEqual(GX._member_designation_token("L4X4X1/4"), "L4X4X1/4")

    def test_raw_nearby_text_unchanged_when_ownership_unproven(self):
        line = {
            "page_number": 8,
            "text": "5",
            "bbox": [200.0, 200.0, 210.0, 210.0],
            "center": [205.0, 205.0],
        }
        member = {
            "page_number": 8,
            "text": "W18X40",
            "bbox": [100.0, 100.0, 160.0, 120.0],
            "center": [130.0, 110.0],
        }
        doc = {"lines": [member, line]}
        self.assertEqual(
            GX._nearby_text_for_dimension(
                nearby_text="5",
                nearby_line=line,
                page_number=8,
                document_structure=doc,
            ),
            "5",
        )

    def test_extract_geometry_integration_own_label_vs_unrelated(self):
        """End-to-end: extract_geometry classification uses the ownership filter."""
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "own_label_dim.pdf"
            doc = fitz.open()
            page = doc.new_page(width=800, height=600)
            # Long horizontal member-scale stroke
            page.draw_line(fitz.Point(50, 200), fitz.Point(400, 200), color=(0, 0, 0), width=1)
            doc.save(pdf_path)
            doc.close()

            # Case A: nearest text is own-label designation with digits
            structure_own = {
                "lines": [
                    {
                        "page_number": 1,
                        "text": "W21X44  [30]",
                        "bbox": [180.0, 190.0, 280.0, 210.0],
                        "center": [230.0, 200.0],
                    }
                ]
            }
            geo_own = extract_geometry(str(pdf_path), document_structure=structure_own)
            objs_own = [
                o
                for o in geo_own["objects"]
                if o.get("page_number") == 1 and float(o.get("length") or 0) >= 12
            ]
            self.assertTrue(objs_own)
            # The long line must not be classified dimension solely due to own-label digits
            long_own = max(objs_own, key=lambda o: float(o.get("length") or 0))
            self.assertEqual(long_own.get("nearby_text"), "W21X44  [30]")
            self.assertNotEqual(long_own.get("kind"), "dimension")

            # Case B: nearest text is unrelated 17K → still dimension
            structure_load = {
                "lines": [
                    {
                        "page_number": 1,
                        "text": "17K",
                        "bbox": [200.0, 195.0, 230.0, 210.0],
                        "center": [215.0, 202.0],
                    }
                ]
            }
            geo_load = extract_geometry(str(pdf_path), document_structure=structure_load)
            objs_load = [
                o
                for o in geo_load["objects"]
                if o.get("page_number") == 1 and float(o.get("length") or 0) >= 12
            ]
            long_load = max(objs_load, key=lambda o: float(o.get("length") or 0))
            self.assertEqual(long_load.get("nearby_text"), "17K")
            self.assertEqual(long_load.get("kind"), "dimension")


class OwnLabelBeforeAfterComparisonTests(unittest.TestCase):
    """Compact V0 (raw predicate) vs V1 (ownership-filtered) safety matrix."""

    CASES = [
        ("own_w21", "W21X44  [30]", True, False),  # recover
        ("own_w14", "W14X22  [25]", True, False),
        ("own_w18a", "W18X35  [35]", True, False),
        ("own_w18b", "W18X35  [28]", True, False),
        ("unrelated_17k", "17K", True, True),
        ("genuine_7_8", "7/8", True, True),
        ("genuine_23_10", "23' - 10\"", True, True),
        ("mark_h24", "H24", True, True),
        ("mark_r22k", "R=22K", True, True),
        ("mark_bp3", "BP3", True, True),
    ]

    def test_before_after_matrix_zero_false_flips(self):
        false_flips = 0
        recovered = 0
        preserved_dim = 0
        for name, text, v0_expect_dim, v1_expect_dim in self.CASES:
            with self.subTest(name=name):
                line = {
                    "page_number": 8,
                    "text": text,
                    "bbox": [100.0, 100.0, 180.0, 120.0],
                    "center": [140.0, 110.0],
                }
                doc = {"lines": [line]}
                v0 = GX._looks_like_dimension(GeometryKind.LINE, 100.0, text)
                v1_text = GX._nearby_text_for_dimension(
                    nearby_text=text,
                    nearby_line=line,
                    page_number=8,
                    document_structure=doc,
                )
                v1 = GX._looks_like_dimension(GeometryKind.LINE, 100.0, v1_text)
                self.assertEqual(v0, v0_expect_dim)
                self.assertEqual(v1, v1_expect_dim)
                if v0 and not v1 and name.startswith("own_"):
                    recovered += 1
                if v0 and v1:
                    preserved_dim += 1
                # False flip: non-own genuine/unrelated became non-dimension
                if v0 and not v1 and not name.startswith("own_"):
                    false_flips += 1
        self.assertEqual(false_flips, 0)
        self.assertGreaterEqual(recovered, 4)
        self.assertGreaterEqual(preserved_dim, 4)


if __name__ == "__main__":
    unittest.main()
