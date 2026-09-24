"""Full-corpus benchmark helpers: dedup, conservative GT pairing, stable comparison."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.benchmark_full_corpus_quarantine import (
    canonicalize_random_ids,
    dedup_pdfs,
    digest,
    pair_ground_truth,
    recorded_flags,
    semantic_differences,
    structural_digest,
)

_P = "Testing Projects/01 - Alpha"


def _pdf(path, sha, *, source="zip", pages=10):
    return {"source": source, "relative_path": path, "sha256": sha, "page_count": pages}


def _book(path, sha):
    return {"relative_path": path, "sha256": sha}


class DedupTests(unittest.TestCase):
    def test_duplicates_collapse_and_keep_every_reference(self) -> None:
        unique = dedup_pdfs(
            [
                _pdf("b/ST.pdf", "h1", source="zip"),
                _pdf("ST.pdf", "h1", source="attachments"),
                _pdf("c/Other.pdf", "h2"),
            ]
        )
        self.assertEqual([u["sha256"] for u in unique], ["h1", "h2"])
        self.assertEqual(
            unique[0]["references"],
            [
                {"source": "attachments", "relative_path": "ST.pdf"},
                {"source": "zip", "relative_path": "b/ST.pdf"},
            ],
        )
        self.assertEqual(unique[0]["filename"], "ST.pdf")

    def test_order_is_independent_of_input_order(self) -> None:
        records = [_pdf("x/A.pdf", "h1"), _pdf("y/B.pdf", "h2"), _pdf("z/A.pdf", "h1")]
        self.assertEqual(dedup_pdfs(records), dedup_pdfs(list(reversed(records))))


class PairingTests(unittest.TestCase):
    def _pair(self, pdfs, books):
        return pair_ground_truth(dedup_pdfs(pdfs), books)[0]

    def test_single_structural_pdf_and_workbook_is_confident(self) -> None:
        decision = self._pair(
            [_pdf(f"{_P}/ST.pdf", "s"), _pdf(f"{_P}/Arch.pdf", "a")],
            [_book(f"{_P}/Manual Markups - For Reference/QTO.x.xls", "w")],
        )
        self.assertEqual(decision["status"], "confident")
        self.assertEqual(decision["pdf_sha256"], "s")

    def test_two_distinct_workbooks_are_ambiguous(self) -> None:
        decision = self._pair(
            [_pdf(f"{_P}/ST.pdf", "s")],
            [
                _book(f"{_P}/Manual Markups - For Reference/QTO.a.xls", "w1"),
                _book(f"{_P}/Manual Markups - For Reference/QTO.b.xls", "w2"),
            ],
        )
        self.assertEqual(decision["status"], "ambiguous")
        self.assertIn("multiple_distinct_workbooks", decision["reasons"])

    def test_identical_workbook_copies_count_once(self) -> None:
        decision = self._pair(
            [_pdf(f"{_P}/ST.pdf", "s")],
            [
                _book(f"{_P}/Manual Markups - For Reference/QTO.a.xls", "w"),
                _book(f"{_P}/Manual Markups - For Reference/QTO.a - Copy.xls", "w"),
            ],
        )
        self.assertEqual(decision["status"], "confident")

    def test_superseded_or_competing_structural_sets_are_ambiguous(self) -> None:
        old = self._pair(
            [_pdf(f"{_P}/ST.pdf", "s"), _pdf(f"{_P}/OLD/Structure.pdf", "o")],
            [_book(f"{_P}/Manual Markups - For Reference/QTO.x.xls", "w")],
        )
        self.assertIn("superseded_structural_set_present", old["reasons"])
        two = self._pair(
            [_pdf(f"{_P}/ST.pdf", "s"), _pdf(f"{_P}/Structural.pdf", "t")],
            [_book(f"{_P}/Manual Markups - For Reference/QTO.x.xls", "w")],
        )
        self.assertIn("multiple_structural_pdfs", two["reasons"])

    def test_markup_copy_must_match_page_count(self) -> None:
        same = self._pair(
            [_pdf(f"{_P}/ST.pdf", "s", pages=12), _pdf(f"{_P}/Manual Markups - For Reference/ST - MARKUP.pdf", "m", pages=12)],
            [_book(f"{_P}/Manual Markups - For Reference/QTO.x.xls", "w")],
        )
        self.assertEqual(same["status"], "confident")
        differs = self._pair(
            [_pdf(f"{_P}/ST.pdf", "s", pages=12), _pdf(f"{_P}/Manual Markups - For Reference/ST - MARKUP.pdf", "m", pages=9)],
            [_book(f"{_P}/Manual Markups - For Reference/QTO.x.xls", "w")],
        )
        self.assertIn("markup_copy_page_count_differs", differs["reasons"])

    def test_workbook_outside_takeoff_folder_is_not_ground_truth(self) -> None:
        self.assertEqual(
            pair_ground_truth(dedup_pdfs([_pdf(f"{_P}/ST.pdf", "s")]), [_book(f"{_P}/budget.xls", "w")]),
            [],
        )


class StableComparisonTests(unittest.TestCase):
    def test_random_parser_ids_canonicalize_by_first_appearance(self) -> None:
        first = {"blocks": [{"object_id": "block_0123456789ab", "line_ids": ["line_aaaaaaaaaaaa"]}],
                 "callouts": [{"callout_id": "callout_line_aaaaaaaaaaaa"}]}
        second = {"blocks": [{"object_id": "block_ba9876543210", "line_ids": ["line_bbbbbbbbbbbb"]}],
                  "callouts": [{"callout_id": "callout_line_bbbbbbbbbbbb"}]}
        self.assertEqual(canonicalize_random_ids(first), canonicalize_random_ids(second))
        self.assertEqual(digest(first), digest(second))

    def test_id_normalization_keeps_structural_references(self) -> None:
        linked = {"a": "line_aaaaaaaaaaaa", "b": "line_aaaaaaaaaaaa"}
        unlinked = {"a": "line_aaaaaaaaaaaa", "b": "line_bbbbbbbbbbbb"}
        self.assertNotEqual(digest(linked), digest(unlinked))

    def test_timings_ignored_but_semantics_reported(self) -> None:
        a = {"parse_ms": 1.0, "legend_profile": {"built_at": 1}, "section": "W8X21"}
        b = {"parse_ms": 9.0, "legend_profile": {"built_at": 2}, "section": "W8X21"}
        self.assertEqual(semantic_differences(a, b), [])
        self.assertEqual(digest(a), digest(b))
        c = {**b, "section": "W8X24"}
        self.assertEqual(semantic_differences(a, c), [".section"])

    def test_non_hex_ids_and_positional_token_ids_are_not_normalized(self) -> None:
        self.assertNotEqual(digest({"token_id": "token_p7_313"}), digest({"token_id": "token_p7_314"}))


def _document(**overrides):
    document = {
        "engineering_tokens": [{"token_id": "t1", "text": "W14X90", "takeoff_eligible": True}],
        "predictions": [{"section": "W14X90", "quantity": 1}],
        "schedule_region_quarantine_shadow": {"regions": [{"region_id": "p3-matrix-1"}], "quarantined": []},
        "flags": {"schedule_region_quarantine_enabled": False},
        "legend_profile": {
            "drawing_intelligence": {
                "narrative": {"project_overview": "wide-flange beams"},
                "overview": "wide-flange beams",
                "page_groups": [{"category": "framing", "pages": [3]}],
                "summary_prompt_version": "v2",
            }
        },
    }
    document.update(overrides)
    return document


class StructuralDigestTests(unittest.TestCase):
    """Only the LLM narrative/overview leaves are outside the structural digest."""

    def test_narrative_or_overview_change_keeps_structural_but_not_raw_digest(self) -> None:
        base = _document()
        for key, value in (("narrative", {"project_overview": "wide-flange framing"}),
                           ("overview", "wide-flange framing")):
            with self.subTest(key=key):
                changed = _document()
                changed["legend_profile"]["drawing_intelligence"][key] = value
                self.assertEqual(structural_digest(base), structural_digest(changed))
                self.assertNotEqual(digest(base), digest(changed))

    def test_other_drawing_intelligence_fields_still_count(self) -> None:
        base = _document()
        for key, value in (("page_groups", []), ("summary_prompt_version", "v3"), ("new_field", 1)):
            with self.subTest(key=key):
                changed = _document()
                changed["legend_profile"]["drawing_intelligence"][key] = value
                self.assertNotEqual(structural_digest(base), structural_digest(changed))

    def test_structural_changes_change_the_structural_digest(self) -> None:
        base = structural_digest(_document())
        for name, changed in (
            ("tokens", _document(engineering_tokens=[{"token_id": "t1", "text": "W14X90", "takeoff_eligible": False}])),
            ("sections", _document(engineering_tokens=[{"token_id": "t1", "text": "W14X99", "takeoff_eligible": True}])),
            ("predictions", _document(predictions=[{"section": "W14X99", "quantity": 1}])),
            ("quantities", _document(predictions=[{"section": "W14X90", "quantity": 0}])),
            ("regions", _document(schedule_region_quarantine_shadow={"regions": [], "quarantined": []})),
            ("quarantine", _document(schedule_region_quarantine_shadow={
                "regions": [{"region_id": "p3-matrix-1"}], "quarantined": [{"token_id": "t1"}]})),
            ("flags", _document(flags={"schedule_region_quarantine_enabled": True})),
        ):
            with self.subTest(name=name):
                self.assertNotEqual(base, structural_digest(changed))

    def test_document_is_not_mutated(self) -> None:
        document = _document()
        structural_digest(document)
        self.assertIn("narrative", document["legend_profile"]["drawing_intelligence"])
        self.assertIn("overview", document["legend_profile"]["drawing_intelligence"])

    def test_missing_legend_profile_is_supported(self) -> None:
        self.assertEqual(structural_digest({"a": 1}), digest({"a": 1}))

    def test_drawing_summary_llm_flag_is_recorded(self) -> None:
        for value in (True, False):
            with self.subTest(value=value):
                flags = recorded_flags(SimpleNamespace(
                    schedule_region_quarantine_enabled=False,
                    schedule_evidence_shadow_enabled=False,
                    schedule_evidence_shadow_widened=False,
                    legend_profile_llm_enabled=False,
                    drawing_summary_llm_enabled=value,
                ))
                self.assertIs(flags["drawing_summary_llm_enabled"], value)
                self.assertIs(flags["schedule_region_quarantine_enabled"], False)


if __name__ == "__main__":
    unittest.main()
