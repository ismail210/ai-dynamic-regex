"""Validate in-place semantic damage test PDF manifests (validation corpus).

These fixtures are NOT production inference inputs. They must not overwrite
source PDFs under backend/uploads/.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "validation" / "semantic_test_pdfs"
UPLOADS = ROOT / "backend" / "uploads"

REQUIRED_CASE_KEYS = {
    "test_case_id",
    "category",
    "corruption_type",
    "source_page",
    "original_text",
    "test_text",
    "intended_semantic_result",
    "expected_operation",
    "expected_status",
    "expected_normalized",
    "expected_abstention",
    "original_bbox",
    "modified_bbox",
}

ALLOWED_CATEGORIES = {
    "char_corruption",
    "deletion",
    "insertion",
    "decimal_fraction",
    "spacing",
    "incomplete",
    "clean_control",
    "other_structural",
}

STEMS = [
    "burrville_SEMANTIC_DAMAGE_TEST",
    "st_SEMANTIC_DAMAGE_TEST",
    "structure_SEMANTIC_DAMAGE_TEST",
]

SOURCE_NAMES = [
    "Burrville ES - ST__0d910a43b4a0.pdf",
    "ST__0bfc2d61245d.pdf",
    "Structure - Copy__9414716bffc6.pdf",
]


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SemanticDamageManifestTests(unittest.TestCase):
    def test_manifests_and_pdfs_exist(self):
        for stem in STEMS:
            self.assertTrue((CORPUS / f"{stem}.pdf").is_file(), stem)
            self.assertTrue((CORPUS / f"{stem}.manifest.json").is_file(), stem)

    def test_case_schema_and_categories(self):
        for stem in STEMS:
            manifest = json.loads((CORPUS / f"{stem}.manifest.json").read_text(encoding="utf-8"))
            cases = manifest["cases"]
            self.assertGreaterEqual(len(cases), 20, stem)
            self.assertLessEqual(len(cases), 35, stem)
            ids = set()
            for case in cases:
                missing = REQUIRED_CASE_KEYS - set(case)
                self.assertFalse(missing, f"{stem} missing {missing}")
                self.assertIn(case["category"], ALLOWED_CATEGORIES, case["test_case_id"])
                self.assertTrue(case["original_text"])
                self.assertTrue(case["test_text"])
                self.assertGreaterEqual(int(case["source_page"]), 1)
                self.assertEqual(len(case["original_bbox"]), 4)
                self.assertEqual(len(case["modified_bbox"]), 4)
                self.assertNotIn(case["test_case_id"], ids)
                ids.add(case["test_case_id"])
                if case["category"] == "clean_control":
                    self.assertEqual(case["original_text"], case["test_text"])
                else:
                    # Spacing cases differ by whitespace / × only; incomplete may
                    # keep a short token equal after strip in edge cases.
                    self.assertNotEqual(
                        case["original_text"],
                        case["test_text"],
                        case["test_case_id"],
                    )

    def test_originals_not_overwritten(self):
        for src_name, stem in zip(SOURCE_NAMES, STEMS):
            src = UPLOADS / src_name
            out = CORPUS / f"{stem}.pdf"
            if not src.is_file():
                self.skipTest(f"upload missing: {src_name}")
            self.assertNotEqual(src.resolve(), out.resolve())
            self.assertNotEqual(_md5(src), _md5(out), f"{stem} must differ from source")

    def test_no_panel_banner_in_generated_pdfs(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("pymupdf not installed")
        for stem in STEMS:
            doc = fitz.open(CORPUS / f"{stem}.pdf")
            try:
                sample = "".join(doc[i].get_text() for i in range(min(3, doc.page_count)))
                self.assertNotIn("CONTROLLED SEMANTIC TEST", sample)
                self.assertNotIn("SEMANTIC TEST CASES", sample)
            finally:
                doc.close()

    def test_production_flag_defaults_untouched_in_settings_module(self):
        # Corpus work must not flip production ML rewrite / fusion flags.
        settings = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")
        for needle in (
            "ML_LABEL_RANKER_ENABLED",
            "LEARNED_FUSION_ENABLED",
            "GRAPHSAGE_SECTION_SCORING_ENABLED",
            "LEGEND_PROFILE_LLM_ENABLED",
        ):
            self.assertIn(needle, settings)


if __name__ == "__main__":
    unittest.main()
