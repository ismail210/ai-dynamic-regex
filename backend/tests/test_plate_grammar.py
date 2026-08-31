"""Regression tests for CAP PL, CONN PL, and thickness-first non-bent plates."""

from __future__ import annotations

import unittest

from services.annotation.parser import interpret_annotation
from services.annotation.taxonomy import AnnotationType


class CapConnPlateParserTests(unittest.TestCase):
    def test_cap_pl_is_plate_not_bent(self) -> None:
        parsed = interpret_annotation(raw_text="CAP PL")
        self.assertEqual(parsed.raw_text, "CAP PL")
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.subtype, "cap_plate")
        self.assertEqual(parsed.plate_type, "cap_plate")
        self.assertTrue(parsed.structure_confirmed)
        self.assertNotEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)

    def test_cap_plate_words(self) -> None:
        parsed = interpret_annotation(raw_text="CAP PLATE")
        self.assertEqual(parsed.raw_text, "CAP PLATE")
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.plate_type, "cap_plate")
        self.assertTrue(parsed.structure_confirmed)

    def test_compact_cappl_and_connpl(self) -> None:
        cap = interpret_annotation(raw_text="CAPPL")
        self.assertEqual(cap.raw_text, "CAPPL")
        self.assertEqual(cap.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(cap.plate_type, "cap_plate")

        conn = interpret_annotation(raw_text="CONNPL")
        self.assertEqual(conn.raw_text, "CONNPL")
        self.assertEqual(conn.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(conn.plate_type, "connection_plate")

    def test_conn_pl_is_connection_plate_not_bent(self) -> None:
        parsed = interpret_annotation(raw_text="CONN PL")
        self.assertEqual(parsed.raw_text, "CONN PL")
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.subtype, "connection_plate")
        self.assertEqual(parsed.plate_type, "connection_plate")
        self.assertTrue(parsed.structure_confirmed)
        self.assertNotEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)

    def test_connection_plate_words(self) -> None:
        parsed = interpret_annotation(raw_text="CONNECTION PLATE")
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.plate_type, "connection_plate")
        self.assertTrue(parsed.structure_confirmed)


class ThicknessFirstNonBentPlateTests(unittest.TestCase):
    def test_three_eighths_pl(self) -> None:
        parsed = interpret_annotation(raw_text='3/8" PL')
        self.assertEqual(parsed.raw_text, '3/8" PL')
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.plate_type, "flat_plate")
        self.assertEqual(parsed.thickness, "3/8")
        self.assertTrue(parsed.structure_confirmed)
        self.assertNotEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)

    def test_three_eighths_conn_pl(self) -> None:
        parsed = interpret_annotation(raw_text='3/8" CONN PL')
        self.assertEqual(parsed.raw_text, '3/8" CONN PL')
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.plate_type, "connection_plate")
        self.assertEqual(parsed.thickness, "3/8")
        self.assertTrue(parsed.structure_confirmed)

    def test_three_eighths_cap_pl(self) -> None:
        parsed = interpret_annotation(raw_text='3/8" CAP PL')
        self.assertEqual(parsed.raw_text, '3/8" CAP PL')
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.plate_type, "cap_plate")
        self.assertEqual(parsed.thickness, "3/8")
        self.assertTrue(parsed.structure_confirmed)

    def test_thickness_first_does_not_steal_bent_pl(self) -> None:
        parsed = interpret_annotation(raw_text='3/8" BENT PL')
        self.assertEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)
        self.assertEqual(parsed.plate_type, "bent_plate")
        self.assertEqual(parsed.thickness, "3/8")
        self.assertEqual(parsed.raw_text, '3/8" BENT PL')


class ExistingPlateGrammarPreservedTests(unittest.TestCase):
    def test_pl_compound_still_flat_plate(self) -> None:
        parsed = interpret_annotation(raw_text="PL 1x9x1'-9")
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.plate_type, "flat_plate")
        self.assertTrue(parsed.structure_confirmed)

    def test_plate_word_and_bp_are_unchanged(self) -> None:
        plate = interpret_annotation(raw_text="PLATE")
        self.assertEqual(plate.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(plate.plate_type, "flat_plate")
        self.assertEqual(plate.raw_text, "PLATE")

        bp = interpret_annotation(raw_text="BP 6x4x3/8")
        self.assertEqual(bp.annotation_type, AnnotationType.BENT_PLATE.value)
        self.assertEqual(bp.plate_type, "bent_plate")
        self.assertEqual(bp.raw_text, "BP 6x4x3/8")

        bent_plate = interpret_annotation(raw_text="BENT PLATE")
        self.assertEqual(bent_plate.annotation_type, AnnotationType.BENT_PLATE.value)
        self.assertEqual(bent_plate.plate_type, "bent_plate")

    def test_legend_cap_pl_does_not_retype_flat_pl(self) -> None:
        parsed = interpret_annotation(
            raw_text="PL 1x9x1'-9",
            page_context='CAP PL 3/4" | CONN PL | LEGEND_CONFIRMS_PLATES',
        )
        self.assertEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertEqual(parsed.plate_type, "flat_plate")

    def test_bare_fraction_is_not_a_plate(self) -> None:
        parsed = interpret_annotation(raw_text='3/8"')
        self.assertNotEqual(parsed.annotation_type, AnnotationType.PLATE.value)
        self.assertNotEqual(parsed.annotation_type, AnnotationType.BENT_PLATE.value)


if __name__ == "__main__":
    unittest.main()
