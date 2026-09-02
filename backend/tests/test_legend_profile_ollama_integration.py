"""Real-Ollama integration smoke test for the project context profile.

This is the ONE test in the suite that makes a live HTTP call to a running
Ollama service with a real local model. It is SKIPPED by default so the
normal suite never depends on Ollama (every other LLM-path test in
``test_legend_profile.py`` uses an in-process fake provider).

Run it explicitly, with Ollama running and the model pulled:

    RUN_OLLAMA_INTEGRATION=1 python -m pytest \
        tests/test_legend_profile_ollama_integration.py -q -s

Optional overrides: ``LEGEND_LLM_MODEL`` (default llama3.1:8b),
``OLLAMA_BASE_URL`` (default http://localhost:11434).

What it proves, end to end, against a real document:
  * the request reaches Ollama and the configured local model runs;
  * a schema-valid JSON object comes back and parses;
  * deterministic quote-grounding + grounded-evidence validation run;
  * the deterministic takeoff path (engineering_tokens) is byte-identical
    with the feature on vs. off -- the LLM never touches prediction.
"""

from __future__ import annotations

import json
import os
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from config import settings
from services.engineering import legend_llm_provider as llm
from services.engineering import legend_profile as lp
from services.engineering import project_rules as pr

_ENABLED = os.getenv("RUN_OLLAMA_INTEGRATION", "").strip().lower() in ("1", "true", "yes", "on")
_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_MODEL = os.getenv("LEGEND_LLM_MODEL", "llama3.1:8b")

_SMALL_NOTES = """[PAGE 1]
GENERAL STRUCTURAL NOTES
1. STRUCTURAL STEEL WIDE-FLANGE SHAPES SHALL CONFORM TO ASTM A992.
2. HSS SHALL CONFORM TO ASTM A500 GRADE C. PLATES AND ANGLES TO ASTM A36.
3. CONNECTION DESIGN IS DELEGATED TO THE STEEL FABRICATOR'S ENGINEER.
4. THE FABRICATOR SHALL PROVIDE ALL BASE PLATES, ANCHOR RODS, AND LEVELING NUTS.
   GROUT IS BY OTHERS.
5. ALL NEW STEEL SHALL BE HOT-DIP GALVANIZED AFTER FABRICATION.
"""


def _ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{_BASE_URL}/api/tags", timeout=3) as resp:
            tags = json.loads(resp.read())
        return any(_MODEL in (m.get("name") or "") for m in tags.get("models") or [])
    except (urllib.error.URLError, OSError, ValueError):
        return False


@unittest.skipUnless(_ENABLED, "set RUN_OLLAMA_INTEGRATION=1 to run the live Ollama smoke test")
class OllamaLiveSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not _ollama_reachable():
            raise unittest.SkipTest(f"Ollama not reachable at {_BASE_URL} or model {_MODEL} not pulled")

    def test_small_notes_roundtrip_through_our_provider(self):
        provider = llm.OllamaLegendProvider(base_url=_BASE_URL, model=_MODEL)
        started = time.monotonic()
        result = llm.propose_analysis(_SMALL_NOTES, provider=provider, abbreviation_rules=[])
        elapsed_ms = round((time.monotonic() - started) * 1000)

        self.assertIsNone(result.error, f"provider error: {result.error}")
        self.assertFalse(result.unavailable)
        # A real model on this input should compile at least a couple of
        # typed rules (each quote-verified) from the material / connection /
        # notation statements.
        self.assertGreaterEqual(len(result.rules), 2)
        for rule in result.rules:
            self.assertIn(rule["type"], pr.RULE_TYPES)
            if rule.get("source_quote"):
                self.assertTrue(lp.verify_quote(_SMALL_NOTES, rule["source_quote"]))
            self.assertIn(rule["application_policy"], {
                pr.POLICY_AUTO_ELIGIBLE, pr.POLICY_CORROBORATION_REQUIRED,
                pr.POLICY_PARSER_ASSIST, pr.POLICY_ATTRIBUTE_ONLY,
                pr.POLICY_INFORMATION_ONLY, pr.POLICY_NEVER_AUTO,
            })
        for insight in result.derived_insights:
            self.assertTrue(insight["evidence_refs"])
        print(
            f"\n[ollama smoke] model={_MODEL} latency={elapsed_ms}ms "
            f"rules={len(result.rules)}/{result.raw_rule_count} {result.rules_by_type()} "
            f"insights={len(result.derived_insights)}/{result.raw_insight_count}"
        )
        print(f"[ollama smoke] summary: {result.executive_summary[:400]}")

    def test_real_pdf_takeoff_is_identical_with_llm_on_and_off(self):
        pdf = settings.uploads_dir / "GCDC Building 4 - ST1__47dc7ef27f6e.pdf"
        if not pdf.exists():
            self.skipTest("GCDC fixture PDF not present (gitignored uploads/)")

        from services.extraction_engine import extract_engineering_document

        original = settings.legend_profile_llm_enabled
        try:
            object.__setattr__(settings, "legend_profile_llm_enabled", True)
            doc_on = extract_engineering_document(str(pdf), document_id="ollama_smoke_llm_on")
            object.__setattr__(settings, "legend_profile_llm_enabled", False)
            doc_off = extract_engineering_document(str(pdf), document_id="ollama_smoke_llm_off")
        finally:
            object.__setattr__(settings, "legend_profile_llm_enabled", original)

        def _content_only(tokens):
            out = []
            for token in tokens:
                t = dict(token)
                for volatile in ("line", "block", "source_word_ids", "layout_dimension_id", "token_id"):
                    t.pop(volatile, None)
                out.append(t)
            return out

        self.assertEqual(
            _content_only(doc_on["engineering_tokens"]),
            _content_only(doc_off["engineering_tokens"]),
        )
        # And the LLM genuinely ran on the on-path.
        self.assertIn(
            doc_on["legend_profile"]["status"],
            {lp.ANALYSIS_SUCCESS, lp.ANALYSIS_NO_RELEVANT_INFORMATION},
        )


if __name__ == "__main__":
    unittest.main()
