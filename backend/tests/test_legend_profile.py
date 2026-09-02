"""Regression tests for the project context profile (legend/notes deep
analysis), checkpoint 2.

Covers: page selection (including the real-document drawing-plan false-
positive this checkpoint fixes), deterministic abbreviation extraction,
quote-grounding validation, the Ollama provider (request shape,
unavailable, malformed JSON), source-fact vs. derived-insight validation
(grounded evidence required for an insight to survive), cache-key
versioning on prompt/model/provider change, status determination for every
ANALYSIS_* outcome, feature-disabled/enabled takeoff-invariance, and real
GCDC + real-customer-document smoke tests (skipped, not failed, on a
machine without the gitignored uploads/ fixtures).

No test in this file makes a live network/Ollama call: every LLM-path test
uses a fake in-process provider implementing the same ``propose`` contract,
or patches ``urllib.request.urlopen`` directly for the Ollama-specific
transport tests.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from config import settings
from services.engineering import legend_profile as lp
from services.engineering import legend_llm_provider as llm
from services.engineering import project_rules as pr
from services.engineering.legend_profile_hook import attach_legend_profile


class _IsolatedCacheTestCase(unittest.TestCase):
    """Redirects settings.legend_profile_cache_dir to a fresh temp
    directory for every test. Without this, tests that share document text
    (and therefore the same content hash + cache key) can read back a
    PRIOR test's cached result instead of actually exercising the
    behavior under test -- discovered via a real flaky failure where
    test_model_error_status_on_malformed_response's cached MODEL_ERROR
    profile was served back to test_model_unavailable_status_propagates_
    from_provider. This also keeps every test in this file from writing
    into the real (gitignored but still persistent) backend/training/
    legend_profiles/ cache directory at all."""

    def setUp(self) -> None:
        super().setUp()
        self._tmp_cache_dir = tempfile.TemporaryDirectory()
        self._original_cache_dir = settings.legend_profile_cache_dir
        object.__setattr__(settings, "legend_profile_cache_dir", Path(self._tmp_cache_dir.name))

    def tearDown(self) -> None:
        object.__setattr__(settings, "legend_profile_cache_dir", self._original_cache_dir)
        self._tmp_cache_dir.cleanup()
        super().tearDown()


def _doc(pages: Dict[int, str], *, source_file: str = "test.pdf") -> Dict[str, Any]:
    blocks = [
        {"page_number": page, "text": text, "bbox": [0, 0, 100, 20]}
        for page, text in pages.items()
    ]
    full_text = "\n".join(pages.values())
    return {
        "page_count": max(pages) if pages else 0,
        "blocks": blocks,
        "lines": [],
        "text": full_text,
        "source_file": source_file,
    }


GENERAL_NOTES_TEXT = (
    "GENERAL NOTES\n"
    "6. THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED ON THE FRAMING PLANS:\n"
    '"W8" = W8x10\n'
    '"W10" = W10x12\n'
    "7. \"CANT\" INDICATES CANTILEVERED BEAM. WHERE BEAM IS STEEL AND SIZE IS\n"
    "NOT INDICATED, THE CANTILEVERED BEAM SHALL BE THE SAME SIZE AS THE\n"
    "ADJACENT BACKSPAN BEAM, UNO.\n"
)

FRAMING_PLAN_TEXT = "W18X35 W12X19 DETAIL 4/S5.2 SEE SCHEDULE"

# Mirrors the real failure mode: a title-block/index preamble followed by a
# real "GENERAL NOTES" heading far past any fixed-window prefix.
LATE_HEADING_NOTES_TEXT = (
    "COPYRIGHT 2024\nProfessional Certification.\nI hereby certify... " * 8
) + "GENERAL NOTES\nCONTRACTOR SHALL VERIFY ALL DIMENSIONS IN THE FIELD."

# Mirrors the real false positive: a framing/foundation plan dense with
# tagged member-schedule callouts plus grid bubbles, with a small on-sheet
# cross-reference to notes -- must NOT be treated as a notes page.
REAL_FRAMING_PLAN_TEXT = (
    "1\n1\n2\n2\n3\n3\nA\nA\nB\nB\n25'-0\" FV\n25'-0\" FV\n"
    "SEE GENERAL NOTES FOR ADDITIONAL REQUIREMENTS\n"
    "(E) W14x22\n(E) W8x10\n(N) W16x26\n(E) W14x22\n(N) W21x44\n(E) W18x35\n"
)


class PageSelectionTests(unittest.TestCase):
    def test_general_notes_page_selected_as_context(self):
        document = _doc({1: GENERAL_NOTES_TEXT, 2: FRAMING_PLAN_TEXT})
        context_pages = lp.detect_context_pages(document)
        self.assertIn(1, context_pages)
        self.assertIn(context_pages[1], lp._CONTEXT_PAGE_ROLES)

    def test_ordinary_framing_plan_page_excluded(self):
        document = _doc({1: GENERAL_NOTES_TEXT, 2: FRAMING_PLAN_TEXT})
        context_pages = lp.detect_context_pages(document)
        self.assertNotIn(2, context_pages)

    def test_late_heading_found_past_any_fixed_prefix(self):
        """Regression for the real customer PDF: the actual GENERAL NOTES
        heading sits ~650 characters into the page, after a full title-
        block/sheet-index preamble on the same page-text blob."""

        document = _doc({1: LATE_HEADING_NOTES_TEXT})
        context_pages = lp.detect_context_pages(document)
        self.assertEqual(context_pages.get(1), lp.PAGE_ROLE_GENERAL_NOTES)

    def test_real_framing_plan_with_onsheet_note_reference_excluded(self):
        """Regression for the real customer PDF: a framing plan page that
        happens to contain a small "SEE GENERAL NOTES..." cross-reference
        must still be excluded -- it is dense with real (E)/(N) member
        callouts, not a notes page."""

        document = _doc({1: REAL_FRAMING_PLAN_TEXT})
        context_pages = lp.detect_context_pages(document)
        self.assertNotIn(1, context_pages)

    def test_symbols_and_notations_heading_recognized_as_legend(self):
        document = _doc(
            {
                1: "STRUCTURAL SYMBOLS AND NOTATIONS\nTHE FOLLOWING MATERIAL "
                "IDENTIFICATION SYMBOLS MAY BE USED IN THE SECTIONS AND DETAILS."
            }
        )
        context_pages = lp.detect_context_pages(document)
        self.assertEqual(context_pages.get(1), lp.PAGE_ROLE_LEGEND)

    def test_design_criteria_heading_recognized(self):
        document = _doc(
            {1: "PART I - DESIGN CRITERIA\nA. GENERAL BUILDING CODE: IBC 2021."}
        )
        context_pages = lp.detect_context_pages(document)
        self.assertEqual(context_pages.get(1), lp.PAGE_ROLE_STRUCTURAL_NOTES)

    def test_abbreviations_heading_classified(self):
        document = _doc(
            {1: 'ABBREVIATIONS USED ON STRUCTURAL DRAWINGS\n"W8" = W8x10\n"W10" = W10x12'}
        )
        context_pages = lp.detect_context_pages(document)
        self.assertEqual(context_pages[1], lp.PAGE_ROLE_ABBREVIATIONS)

    def test_specifications_heading_classified(self):
        document = _doc(
            {1: "SPECIFICATIONS\nSTRUCTURAL STEEL SHALL CONFORM TO ASTM A992 UNLESS NOTED."}
        )
        context_pages = lp.detect_context_pages(document)
        self.assertEqual(context_pages.get(1), lp.PAGE_ROLE_SPECIFICATIONS)

    def test_low_text_context_page_flagged_vision_required(self):
        document = _doc({1: "GENERAL NOTES"})  # real heading, under the min-chars threshold
        context_pages = lp.detect_context_pages(document)
        self.assertEqual(context_pages[1], lp.PAGE_ROLE_VISION_REQUIRED)

    def test_vision_required_page_excluded_from_readable_pages(self):
        readable = lp._readable_context_pages(
            {1: lp.PAGE_ROLE_VISION_REQUIRED, 2: lp.PAGE_ROLE_GENERAL_NOTES}
        )
        self.assertEqual(readable, [2])


class AbbreviationExtractionTests(unittest.TestCase):
    def test_extracts_explicit_w_shape_abbreviation(self):
        document = _doc({1: GENERAL_NOTES_TEXT})
        context_pages = lp.detect_context_pages(document)
        rules = lp.extract_abbreviation_rules(document, context_pages)
        lhs_values = {r["lhs"] for r in rules}
        self.assertIn("W8", lhs_values)
        rule = next(r for r in rules if r["lhs"] == "W8")
        self.assertEqual(rule["rhs"], "W8X10")
        self.assertEqual(rule["status"], lp.STATUS_PROPOSED_INFERENCE)

    def test_same_family_gate_rejects_cross_family_mapping(self):
        document = _doc({1: 'GENERAL NOTES\n"W8" = C8x11.5'})
        context_pages = lp.detect_context_pages(document)
        rules = lp.extract_abbreviation_rules(document, context_pages)
        self.assertEqual(rules, [])

    def test_invalid_catalog_target_rejected(self):
        document = _doc({1: 'GENERAL NOTES\n"W8" = W8X999'})
        context_pages = lp.detect_context_pages(document)
        rules = lp.extract_abbreviation_rules(document, context_pages)
        self.assertEqual(rules, [])


class QuoteValidationTests(unittest.TestCase):
    def test_exact_quote_verified(self):
        self.assertTrue(lp.verify_quote("Some text here.", "Some text here."))

    def test_whitespace_and_case_normalized(self):
        self.assertTrue(lp.verify_quote("Some   Text\nhere.", "some text here."))

    def test_unrelated_quote_rejected(self):
        self.assertFalse(lp.verify_quote("Some text here.", "This sentence never appeared."))


class ContextTextFairTruncationTests(unittest.TestCase):
    """Regression for a real bug found while demonstrating this checkpoint
    against GCDC Building 4 - ST1.pdf: pages 1+3+4 alone total ~61k
    characters, so a naive concatenate-then-cut-at-max_chars approach
    silently dropped page 5 -- the page with the actual "W8"=W8x10-style
    abbreviation table -- entirely from the model's input, purely because
    it sorted after three large pages. Fixed by giving every selected page
    an equal, fair character budget instead."""

    def test_every_selected_page_contributes_even_when_earlier_pages_are_huge(self):
        document = _doc(
            {
                1: "X" * 30000,
                2: "Y" * 30000,
                3: 'GENERAL NOTES\n"W8" = W8x10',
            }
        )
        context_pages = {1: lp.PAGE_ROLE_GENERAL_NOTES, 2: lp.PAGE_ROLE_GENERAL_NOTES, 3: lp.PAGE_ROLE_GENERAL_NOTES}
        context_text = lp.build_context_text(document, context_pages, max_chars=60000)
        self.assertIn("[PAGE 3]", context_text)
        self.assertIn('"W8" = W8x10', context_text)

    def test_naive_concatenation_would_have_dropped_page_three(self):
        """Documents the exact failure mode this test file guards against:
        without fair per-page budgeting, simple concatenation-then-cut
        drops page 3 entirely once pages 1+2 alone exceed max_chars."""

        document = _doc({1: "X" * 30000, 2: "Y" * 30000, 3: 'GENERAL NOTES\n"W8" = W8x10'})
        pages = lp._readable_context_pages(
            {1: lp.PAGE_ROLE_GENERAL_NOTES, 2: lp.PAGE_ROLE_GENERAL_NOTES, 3: lp.PAGE_ROLE_GENERAL_NOTES}
        )
        naive = "\n\n".join(f"[PAGE {p}]\n{lp._page_text(document, p)}" for p in pages)[:60000]
        self.assertNotIn("[PAGE 3]", naive)

    def test_notes_page_gets_more_budget_than_a_specifications_page(self):
        """Checkpoint 3: on the real data-center PDF, 4 of 10 context pages
        are boilerplate SPECIFICATIONS sheets. An equal split gave the
        actual GENERAL NOTES page the same room as a CSI submittal-
        procedure page. The role-weighted budget must give a notes page
        materially more of the model's input than a spec page."""

        document = _doc({1: "N" * 20000, 2: "S" * 20000})
        context_pages = {
            1: lp.PAGE_ROLE_GENERAL_NOTES,
            2: lp.PAGE_ROLE_SPECIFICATIONS,
        }
        context_text = lp.build_context_text(document, context_pages, max_chars=20000)
        notes_chars = context_text.count("N")
        spec_chars = context_text.count("S")
        self.assertGreater(notes_chars, spec_chars * 2)
        # both pages are still represented -- a spec page is de-prioritised,
        # never dropped
        self.assertIn("[PAGE 1]", context_text)
        self.assertIn("[PAGE 2]", context_text)

    def test_every_page_clears_the_minimum_even_with_many_spec_pages(self):
        document = _doc({n: f"PAGE{n} " + "z" * 5000 for n in range(1, 13)})
        context_pages = {n: lp.PAGE_ROLE_SPECIFICATIONS for n in range(1, 13)}
        context_text = lp.build_context_text(document, context_pages, max_chars=30000)
        for n in range(1, 13):
            self.assertIn(f"[PAGE {n}]", context_text)


# ---------------------------------------------------------------------------
# Ollama provider transport tests
# ---------------------------------------------------------------------------


class OllamaProviderTests(unittest.TestCase):
    def test_successful_request_response_roundtrip(self):
        fake_body = json.dumps(
            {"response": json.dumps({"executive_summary": "ok", "source_facts": []})}
        ).encode("utf-8")

        fake_response = MagicMock()
        fake_response.read.return_value = fake_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen:
            provider = llm.OllamaLegendProvider(base_url="http://localhost:11434", model="llama3.1:8b")
            result = provider.propose("system prompt", "document text")

        self.assertEqual(result["executive_summary"], "ok")
        called_request = mock_urlopen.call_args.args[0]
        self.assertIn("/api/generate", called_request.full_url)
        sent_payload = json.loads(called_request.data.decode("utf-8"))
        self.assertEqual(sent_payload["model"], "llama3.1:8b")
        # Structured output: `format` is the response JSON schema, not the
        # weak "json" mode (checkpoint 3 -- see legend_llm_provider).
        self.assertIsInstance(sent_payload["format"], dict)
        self.assertEqual(sent_payload["format"]["type"], "object")
        self.assertIn("rules", sent_payload["format"]["properties"])
        self.assertFalse(sent_payload["stream"])
        self.assertIn("num_ctx", sent_payload["options"])
        self.assertIn("num_predict", sent_payload["options"])

    def test_connection_refused_raises_unavailable_not_generic_error(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            provider = llm.OllamaLegendProvider(base_url="http://localhost:11434", model="llama3.1:8b")
            with self.assertRaises(llm.OllamaUnavailableError):
                provider.propose("system prompt", "document text")

    def test_malformed_json_response_raises_json_error(self):
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({"response": "not-json{{{"}).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response):
            provider = llm.OllamaLegendProvider(base_url="http://localhost:11434", model="llama3.1:8b")
            with self.assertRaises(json.JSONDecodeError):
                provider.propose("system prompt", "document text")

    def test_response_wrapped_in_code_fence_still_parses(self):
        payload = "```json\n" + json.dumps(
            {"executive_summary": "ok", "source_facts": []}
        ) + "\n```"
        fake_body = json.dumps({"response": payload}).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = fake_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=fake_response):
            provider = llm.OllamaLegendProvider(base_url="http://localhost:11434", model="llama3.1:8b")
            result = provider.propose("system prompt", "document text")
        self.assertEqual(result["executive_summary"], "ok")

    def test_response_truncated_at_num_predict_is_salvaged(self):
        """llama3.1:8b on a content-rich document hits num_predict and cuts
        its JSON mid-string. The earlier, complete facts must still be
        recovered rather than the whole analysis becoming MODEL_ERROR."""

        truncated = (
            '{"executive_summary": "A992 wide flange, A500 HSS.", '
            '"source_facts": [{"category": "MATERIAL", "statement": "Wide flange is A992.", '
            '"source_page": 1, "source_quote": "W SHAPES SHALL BE ASTM A992", "confidence": 1.0}, '
            '{"category": "MATERIAL", "statement": "HSS is A500", "source_page": 1, '
            '"source_quote": "HSS SHALL CONFORM TO ASTM A50'
        )
        fake_body = json.dumps({"response": truncated}).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = fake_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=fake_response):
            provider = llm.OllamaLegendProvider(base_url="http://localhost:11434", model="llama3.1:8b")
            result = provider.propose("system prompt", "document text")
        self.assertEqual(result["executive_summary"], "A992 wide flange, A500 HSS.")
        self.assertGreaterEqual(len(result["source_facts"]), 1)
        self.assertEqual(result["source_facts"][0]["statement"], "Wide flange is A992.")

    def test_response_with_trailing_prose_still_parses(self):
        payload = json.dumps({"executive_summary": "ok"}) + "\n\nLet me know if you need more detail."
        fake_body = json.dumps({"response": payload}).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = fake_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=fake_response):
            provider = llm.OllamaLegendProvider(base_url="http://localhost:11434", model="llama3.1:8b")
            result = provider.propose("system prompt", "document text")
        self.assertEqual(result["executive_summary"], "ok")

    def test_propose_analysis_reports_unavailable_status(self):
        class _RefusingProvider:
            def propose(self, system_prompt, document_text):
                raise llm.OllamaUnavailableError("connection refused")

        result = llm.propose_analysis("[PAGE 1]\nSome notes.", provider=_RefusingProvider())
        self.assertTrue(result.unavailable)
        self.assertIsNotNone(result.error)

    def test_propose_analysis_reports_generic_error_distinctly(self):
        class _BrokenProvider:
            def propose(self, system_prompt, document_text):
                raise RuntimeError("boom")

        result = llm.propose_analysis("[PAGE 1]\nSome notes.", provider=_BrokenProvider())
        self.assertFalse(result.unavailable)
        self.assertIsNotNone(result.error)


# ---------------------------------------------------------------------------
# Source fact vs. derived insight validation
# ---------------------------------------------------------------------------


class _FakeProvider:
    def __init__(self, response: Optional[Dict[str, Any]] = None, *, raises: Optional[Exception] = None):
        self._response = response
        self._raises = raises

    def propose(self, system_prompt: str, document_text: str):
        if self._raises:
            raise self._raises
        return self._response


class RuleProfileValidationTests(unittest.TestCase):
    """project_rule_profile_v1: the model returns typed drawing-language
    rules; project_rules validates each and assigns an application_policy."""

    CONTEXT_TEXT = (
        "[PAGE 5]\n"
        'THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED ON THE FRAMING PLANS:\n'
        '"W8" = W8x10\n"HSS8x4" = HSS8x4x1/4\n'
        'c = 1-1/4" INDICATES CAMBER.\n'
        '"CANT" INDICATES CANTILEVERED BEAM. WHERE BEAM IS STEEL AND SIZE IS '
        "NOT INDICATED, THE CANTILEVERED BEAM SHALL BE THE SAME SIZE AS THE "
        "ADJACENT BACKSPAN BEAM, UNO.\n"
        "SQUARE AND RECTANGULAR HSS SHALL CONFORM TO ASTM A500 GRADE C.\n"
    )

    def _run(self, rules, insights=None, attention=None, summary="ok"):
        provider = _FakeProvider(
            {
                "executive_summary": summary,
                "rules": rules,
                "derived_insights": insights or [],
                "estimator_attention": attention or [],
            }
        )
        return llm.propose_analysis(self.CONTEXT_TEXT, provider=provider, abbreviation_rules=[])

    def test_notation_grammar_camber_maps_to_controlled_type_and_parser_assist(self):
        result = self._run(
            [
                {
                    "type": "NOTATION_GRAMMAR",
                    "statement": "c=<dimension> denotes beam camber.",
                    "grammar": "c=<dimension>",
                    "field": "camber",
                    "scope": {"page_roles": ["FRAMING_PLAN"], "uno_applies": False},
                    "relevance": "HIGH",
                    "source_page": 5,
                    "source_quote": 'c = 1-1/4" INDICATES CAMBER.',
                }
            ]
        )
        self.assertEqual(len(result.rules), 1)
        rule = result.rules[0]
        self.assertEqual(rule["grammar_type"], pr.GRAMMAR_CAMBER_PREFIX)
        self.assertEqual(rule["application_policy"], pr.POLICY_PARSER_ASSIST)
        self.assertEqual(rule["validation_status"], pr.VALIDATION_STATUS_VALIDATED)

    def test_unrecognised_grammar_downgraded_to_information_only(self):
        result = self._run(
            [
                {
                    "type": "NOTATION_GRAMMAR",
                    "statement": "A circled number is a typical-detail reference on the framing plans.",
                    "grammar": "(n)",
                    "field": "detail_reference",
                    "source_page": 5,
                    "source_quote": "THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED ON THE FRAMING PLANS:",
                }
            ]
        )
        self.assertEqual(result.rules[0]["grammar_type"], pr.GRAMMAR_UNKNOWN)
        self.assertEqual(result.rules[0]["application_policy"], pr.POLICY_INFORMATION_ONLY)

    def test_inheritance_rule_is_corroboration_required_and_keeps_relation(self):
        result = self._run(
            [
                {
                    "type": "INHERITANCE_RULE",
                    "statement": "A CANT beam with no section shown takes the adjacent backspan beam size, UNO.",
                    "trigger": "CANT",
                    "condition": "section size not indicated",
                    "relation": "adjacent_backspan_beam",
                    "inherited_field": "section_designation",
                    "scope": {"page_roles": ["FRAMING_PLAN"], "uno_applies": True},
                    "relevance": "CRITICAL",
                    "source_page": 5,
                    "source_quote": '"CANT" INDICATES CANTILEVERED BEAM.',
                }
            ]
        )
        rule = result.rules[0]
        self.assertEqual(rule["application_policy"], pr.POLICY_CORROBORATION_REQUIRED)
        self.assertEqual(rule["relation"], "adjacent_backspan_beam")
        self.assertEqual(rule["inherited_field"], "section_designation")

    def test_label_substitution_is_auto_eligible(self):
        result = self._run(
            [
                {
                    "type": "LABEL_SUBSTITUTION",
                    "statement": "HSS8X4 means HSS8X4X1/4 on framing plans.",
                    "trigger": "HSS8X4",
                    "result": "HSS8X4X1/4",
                    "scope": {"page_roles": ["FRAMING_PLAN"], "uno_applies": False},
                    "relevance": "CRITICAL",
                    "source_page": 5,
                    "source_quote": '"HSS8x4" = HSS8x4x1/4',
                }
            ]
        )
        self.assertEqual(result.rules[0]["application_policy"], pr.POLICY_AUTO_ELIGIBLE)

    def test_attribute_default_material_grade(self):
        result = self._run(
            [
                {
                    "type": "ATTRIBUTE_DEFAULT",
                    "statement": "Square and rectangular HSS conform to ASTM A500 Grade C.",
                    "source_page": 5,
                    "source_quote": "SQUARE AND RECTANGULAR HSS SHALL CONFORM TO ASTM A500 GRADE C.",
                }
            ]
        )
        self.assertEqual(result.rules[0]["application_policy"], pr.POLICY_ATTRIBUTE_ONLY)

    def test_conflict_warning_becomes_a_warning_not_a_resolution(self):
        result = self._run(
            [
                {
                    "type": "CONFLICT_WARNING",
                    "statement": "The camber note and the abbreviations note disagree.",
                    "source_page": 5,
                    "source_quote": 'c = 1-1/4" INDICATES CAMBER.',
                }
            ]
        )
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.rules[0]["application_policy"], pr.POLICY_NEVER_AUTO)

    def test_hallucinated_quote_rejected(self):
        result = self._run(
            [
                {
                    "type": "ATTRIBUTE_DEFAULT",
                    "statement": "All steel is A992.",
                    "source_page": 5,
                    "source_quote": "This exact sentence was never in the document.",
                }
            ]
        )
        self.assertEqual(result.rules, [])
        self.assertEqual(result.rejected_rule_count, 1)

    def test_real_quote_with_unrelated_statement_rejected(self):
        result = self._run(
            [
                {
                    "type": "SCOPE_RULE",
                    "statement": "Elevator guide rails are supplied by the elevator manufacturer.",
                    "source_page": 5,
                    "source_quote": '"HSS8x4" = HSS8x4x1/4',
                }
            ]
        )
        self.assertEqual(result.rules, [])

    def test_unknown_rule_type_rejected(self):
        result = self._run(
            [{"type": "MAGIC_RULE", "statement": "x", "source_page": 5, "source_quote": '"W8" = W8x10'}]
        )
        self.assertEqual(result.rules, [])

    def test_derived_insight_must_cite_validated_rule_ids(self):
        rules = [
            {
                "type": "LABEL_SUBSTITUTION",
                "statement": "W8 means W8x10.",
                "trigger": "W8",
                "result": "W8X10",
                "source_page": 5,
                "source_quote": '"W8" = W8x10',
            }
        ]
        good = self._run(
            rules,
            insights=[
                {
                    "statement": "The project uses systematic framing-plan shorthand.",
                    "evidence_refs": ["RULE_001"],
                    "reasoning_summary": "an explicit mapping exists",
                    "confidence": 0.9,
                }
            ],
        )
        self.assertEqual(len(good.derived_insights), 1)
        self.assertEqual(
            good.derived_insights[0]["validation_status"], pr.VALIDATION_STATUS_PROPOSED_INFERENCE
        )

        bad = self._run(
            rules,
            insights=[{"statement": "Unsupported claim.", "evidence_refs": ["RULE_999"]}],
        )
        self.assertEqual(bad.derived_insights, [])

    def test_derived_insight_cannot_resolve_anything(self):
        # A DERIVED_INSIGHT never carries an application_policy other than
        # NEVER_AUTO, and is not in the `rules` list at all.
        result = self._run(
            [
                {
                    "type": "LABEL_SUBSTITUTION",
                    "statement": "W8 means W8x10.",
                    "trigger": "W8",
                    "result": "W8X10",
                    "source_page": 5,
                    "source_quote": '"W8" = W8x10',
                }
            ],
            insights=[
                {
                    "statement": "Incomplete labels may be intentional notation.",
                    "evidence_refs": ["RULE_001"],
                    "confidence": 0.8,
                }
            ],
        )
        for insight in result.derived_insights:
            self.assertEqual(insight["application_policy"], pr.POLICY_NEVER_AUTO)
        self.assertFalse(any(r["type"] == pr.DERIVED_INSIGHT for r in result.rules))

    def test_drawing_language_is_derived_from_validated_rules(self):
        result = self._run(
            [
                {
                    "type": "NOTATION_GRAMMAR",
                    "statement": "c=<dimension> denotes beam camber.",
                    "grammar": "c=<dimension>",
                    "field": "camber",
                    "source_page": 5,
                    "source_quote": 'c = 1-1/4" INDICATES CAMBER.',
                },
                {
                    "type": "INHERITANCE_RULE",
                    "statement": "CANT with no size takes the adjacent backspan, UNO.",
                    "trigger": "CANT",
                    "relation": "adjacent_backspan_beam",
                    "source_page": 5,
                    "source_quote": '"CANT" INDICATES CANTILEVERED BEAM.',
                },
            ]
        )
        joined = " ".join(result.drawing_language).lower()
        self.assertIn("camber", joined)
        self.assertIn("cant", joined)
        self.assertIn("backspan", joined)

    def test_empty_but_valid_result(self):
        result = self._run([])
        self.assertIsNone(result.error)
        self.assertEqual(result.rules, [])
        self.assertEqual(result.derived_insights, [])

    def test_malformed_response_is_model_error(self):
        result = llm.propose_analysis(
            self.CONTEXT_TEXT, provider=_FakeProvider("not a dict"), abbreviation_rules=[]
        )
        self.assertIsNotNone(result.error)


class CacheHitTests(_IsolatedCacheTestCase):
    """Section 21: a second analysis with unchanged inputs must be a
    CACHE_HIT and must NOT call the provider again."""

    def test_second_identical_analysis_is_a_cache_hit_with_no_provider_call(self):
        calls = {"n": 0}

        class _CountingProvider:
            def propose(self, system_prompt, document_text):
                calls["n"] += 1
                return {
                    "executive_summary": "ok",
                    "rules": [
                        {
                            "type": "ATTRIBUTE_DEFAULT",
                            "statement": "Wide-flange shapes conform to ASTM A992.",
                            "source_page": 1,
                            "source_quote": '"W8" = W8x10',
                        }
                    ],
                    "derived_insights": [],
                    "estimator_attention": [],
                }

        original = settings.legend_profile_llm_enabled
        try:
            object.__setattr__(settings, "legend_profile_llm_enabled", True)
            document = _doc({1: GENERAL_NOTES_TEXT})
            with patch(
                "services.engineering.legend_llm_provider.get_default_provider",
                return_value=_CountingProvider(),
            ):
                first = attach_legend_profile(document)
                self.assertEqual(first["diagnostics"].get("cache_state"), "FRESH_LLM_RUN")
                second = attach_legend_profile(_doc({1: GENERAL_NOTES_TEXT}))
            self.assertEqual(calls["n"], 1, "provider was called on the cached run")
            self.assertEqual(second["diagnostics"].get("cache_state"), "CACHE_HIT")
        finally:
            object.__setattr__(settings, "legend_profile_llm_enabled", original)

# ---------------------------------------------------------------------------
# Cache versioning
# ---------------------------------------------------------------------------


class CacheVersioningTests(unittest.TestCase):
    def test_prompt_version_change_invalidates_cache(self):
        doc_hash = "abc123"
        key_v1 = lp.compute_cache_key(doc_hash, llm_requested=True, provider_name="ollama", model="llama3.1:8b")
        # The cache key is derived from EXTRACTOR_VERSION/SCHEMA_VERSION
        # (bumped whenever the prompt changes) plus provider/model, not from
        # PROMPT_VERSION directly (that lives in the provider module). A
        # real prompt bump is simulated here via the extractor version.
        with patch.object(lp, "EXTRACTOR_VERSION", "legend_extractor_test_bump"):
            key_v2 = lp.compute_cache_key(doc_hash, llm_requested=True, provider_name="ollama", model="llama3.1:8b")
        self.assertNotEqual(key_v1, key_v2)

    def test_model_change_invalidates_cache(self):
        doc_hash = "abc123"
        key_a = lp.compute_cache_key(doc_hash, llm_requested=True, provider_name="ollama", model="llama3.1:8b")
        key_b = lp.compute_cache_key(doc_hash, llm_requested=True, provider_name="ollama", model="qwen2.5:14b")
        self.assertNotEqual(key_a, key_b)

    def test_provider_change_invalidates_cache(self):
        doc_hash = "abc123"
        key_ollama = lp.compute_cache_key(doc_hash, llm_requested=True, provider_name="ollama", model="m")
        key_anthropic = lp.compute_cache_key(doc_hash, llm_requested=True, provider_name="anthropic", model="m")
        self.assertNotEqual(key_ollama, key_anthropic)

    def test_llm_disabled_key_independent_of_provider_model(self):
        doc_hash = "abc123"
        key_a = lp.compute_cache_key(doc_hash, llm_requested=False, provider_name="ollama", model="a")
        key_b = lp.compute_cache_key(doc_hash, llm_requested=False, provider_name="anthropic", model="b")
        self.assertEqual(key_a, key_b)

    def test_stale_cache_entry_not_reused_after_key_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            old_key = lp.compute_cache_key("hash1", llm_requested=False)
            lp.save_profile(cache_dir, old_key, lp.empty_profile({}, status=lp.ANALYSIS_SUCCESS, llm_requested=False))
            with patch.object(lp, "EXTRACTOR_VERSION", "legend_extractor_test_bump"):
                new_key = lp.compute_cache_key("hash1", llm_requested=False)
                self.assertIsNone(lp.load_cached_profile(cache_dir, new_key))


# ---------------------------------------------------------------------------
# Status determination + feature-flag invariance
# ---------------------------------------------------------------------------


class StatusDeterminationTests(_IsolatedCacheTestCase):
    def test_disabled_status_when_feature_off(self):
        original = settings.legend_profile_enabled
        try:
            object.__setattr__(settings, "legend_profile_enabled", False)
            document = _doc({1: GENERAL_NOTES_TEXT})
            profile = attach_legend_profile(document)
            self.assertEqual(profile["status"], lp.ANALYSIS_DISABLED)
        finally:
            object.__setattr__(settings, "legend_profile_enabled", original)

    def test_no_context_pages_status(self):
        document = _doc({1: FRAMING_PLAN_TEXT})
        profile = attach_legend_profile(document)
        self.assertEqual(profile["status"], lp.ANALYSIS_NO_CONTEXT_PAGES)

    def test_vision_required_status_when_only_short_pages_found(self):
        document = _doc({1: "GENERAL NOTES"})
        profile = attach_legend_profile(document)
        self.assertEqual(profile["status"], lp.ANALYSIS_VISION_REQUIRED)

    def test_success_status_from_deterministic_abbreviation_rules_alone(self):
        document = _doc({1: GENERAL_NOTES_TEXT})
        profile = attach_legend_profile(document)
        self.assertEqual(profile["status"], lp.ANALYSIS_SUCCESS)
        self.assertTrue(profile["abbreviation_rules"])

    def test_no_relevant_information_when_context_pages_exist_but_nothing_found(self):
        document = _doc({1: "GENERAL NOTES\nCONTRACTOR SHALL COORDINATE WITH OTHER TRADES."})
        profile = attach_legend_profile(document)
        self.assertEqual(profile["status"], lp.ANALYSIS_NO_RELEVANT_INFORMATION)

    def test_model_unavailable_status_propagates_from_provider(self):
        original_enabled = settings.legend_profile_llm_enabled
        try:
            object.__setattr__(settings, "legend_profile_llm_enabled", True)
            document = _doc({1: GENERAL_NOTES_TEXT})

            class _RefusingProvider:
                def propose(self, system_prompt, document_text):
                    raise llm.OllamaUnavailableError("refused")

            with patch(
                "services.engineering.legend_llm_provider.get_default_provider",
                return_value=_RefusingProvider(),
            ):
                profile = attach_legend_profile(document)
            self.assertEqual(profile["status"], lp.ANALYSIS_MODEL_UNAVAILABLE)
            self.assertFalse(profile["llm_used"])
        finally:
            object.__setattr__(settings, "legend_profile_llm_enabled", original_enabled)

    def test_model_error_status_on_malformed_response(self):
        original_enabled = settings.legend_profile_llm_enabled
        try:
            object.__setattr__(settings, "legend_profile_llm_enabled", True)
            document = _doc({1: GENERAL_NOTES_TEXT})

            class _BadProvider:
                def propose(self, system_prompt, document_text):
                    return "not a dict"

            with patch(
                "services.engineering.legend_llm_provider.get_default_provider",
                return_value=_BadProvider(),
            ):
                profile = attach_legend_profile(document)
            self.assertEqual(profile["status"], lp.ANALYSIS_MODEL_ERROR)
        finally:
            object.__setattr__(settings, "legend_profile_llm_enabled", original_enabled)

    def test_model_failure_does_not_affect_deterministic_extraction(self):
        """Section 19 test #16: model failure cannot affect deterministic
        extraction -- abbreviation_rules (deterministic) must still be
        populated even when the LLM call fails."""

        original_enabled = settings.legend_profile_llm_enabled
        try:
            object.__setattr__(settings, "legend_profile_llm_enabled", True)
            document = _doc({1: GENERAL_NOTES_TEXT})

            class _BrokenProvider:
                def propose(self, system_prompt, document_text):
                    raise RuntimeError("boom")

            with patch(
                "services.engineering.legend_llm_provider.get_default_provider",
                return_value=_BrokenProvider(),
            ):
                profile = attach_legend_profile(document)
            self.assertEqual(profile["status"], lp.ANALYSIS_MODEL_ERROR)
            self.assertTrue(profile["abbreviation_rules"])
            lhs_values = {r["lhs"] for r in profile["abbreviation_rules"]}
            self.assertIn("W8", lhs_values)
        finally:
            object.__setattr__(settings, "legend_profile_llm_enabled", original_enabled)


class FeatureFlagInvarianceTests(_IsolatedCacheTestCase):
    """The load-bearing safety property: enabling/disabling this feature,
    or any internal LLM failure, must never change deterministic output."""

    def test_attach_never_mutates_other_document_keys(self):
        document = _doc({1: GENERAL_NOTES_TEXT, 2: FRAMING_PLAN_TEXT})
        before = {k: v for k, v in document.items() if k != "legend_profile"}
        attach_legend_profile(document)
        after = {k: v for k, v in document.items() if k != "legend_profile"}
        self.assertEqual(before, after)

    def test_full_extraction_engineering_tokens_unchanged_by_flag(self):
        import fitz

        from services.extraction_engine import extract_engineering_document

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "drawing.pdf"
            doc = fitz.open()
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 75), "FRAMING PLAN", fontsize=18)
            page.insert_text((72, 130), "W18 X 35", fontsize=12)
            doc.save(pdf_path)
            doc.close()

            original = settings.legend_profile_enabled
            try:
                object.__setattr__(settings, "legend_profile_enabled", True)
                doc_on = extract_engineering_document(pdf_path, document_id="flag_on")
                object.__setattr__(settings, "legend_profile_enabled", False)
                doc_off = extract_engineering_document(pdf_path, document_id="flag_on")
            finally:
                object.__setattr__(settings, "legend_profile_enabled", original)

        def _content_only(tokens):
            stripped = []
            for token in tokens:
                t = dict(token)
                for volatile in ("line", "block", "source_word_ids", "layout_dimension_id", "token_id"):
                    t.pop(volatile, None)
                stripped.append(t)
            return stripped

        self.assertEqual(
            _content_only(doc_on["engineering_tokens"]),
            _content_only(doc_off["engineering_tokens"]),
        )


# ---------------------------------------------------------------------------
# Real-document smoke tests
# ---------------------------------------------------------------------------


class RealDocumentSmokeTests(_IsolatedCacheTestCase):
    UPLOADS_DIR = Path(__file__).resolve().parents[1] / "uploads"
    GCDC_PATH = UPLOADS_DIR / "GCDC Building 4 - ST1__47dc7ef27f6e.pdf"
    REAL_FAILING_PDF_PATH = UPLOADS_DIR / "ST__0bfc2d61245d.pdf"

    def test_gcdc_page_5_abbreviations_extracted(self):
        if not self.GCDC_PATH.exists():
            self.skipTest("GCDC fixture PDF not present on this machine (gitignored uploads/)")

        from services.extraction_engine import extract_engineering_document

        document = extract_engineering_document(str(self.GCDC_PATH), document_id="gcdc_smoke_test_v2")
        profile = document["legend_profile"]
        self.assertEqual(profile["status"], lp.ANALYSIS_SUCCESS)
        rules_by_lhs = {r["lhs"]: r for r in profile["abbreviation_rules"]}
        self.assertEqual(rules_by_lhs["W8"]["rhs"], "W8X10")
        self.assertEqual(rules_by_lhs["HSS8X4"]["rhs"], "HSS8X4X1/4")

    def test_previously_failing_real_pdf_now_gives_non_empty_context_pages(self):
        """The exact document that showed a blank panel
        (source_document_hash 1d70c9d48b1ec89452f720177f05fd30, tested
        2026-09-02 02:02:28). Confirms the page-detection fix: real
        framing/foundation plan pages (7, 10, 11 in the original run) are
        no longer misclassified as notes pages, while genuine notes/legend/
        specification pages ARE found."""

        if not self.REAL_FAILING_PDF_PATH.exists():
            self.skipTest("Real customer fixture PDF not present on this machine (gitignored uploads/)")

        from services.extraction_engine import extract_engineering_document

        document = extract_engineering_document(
            str(self.REAL_FAILING_PDF_PATH), document_id="real_failing_pdf_v2"
        )
        profile = document["legend_profile"]
        self.assertNotEqual(profile["status"], lp.ANALYSIS_NO_CONTEXT_PAGES)
        self.assertGreater(len(profile["context_pages"]), 0)
        # The three confirmed real framing/foundation plan pages from the
        # original failing run must not be present.
        for excluded_page in ("7", "10", "11"):
            self.assertNotIn(
                profile["context_pages"].get(excluded_page), lp._CONTEXT_PAGE_ROLES
            )


if __name__ == "__main__":
    unittest.main()
