"""Drawing Intelligence Profile -- grounding, TYP detection, schedule /
scope safety, and the deterministic narrative fallback."""

from __future__ import annotations

import unittest

from services.engineering.drawing_intelligence import (
    build_drawing_intelligence,
    evidence_packet,
)
from services.engineering.drawing_summary_llm import summarize


def _doc(pages: dict, *, page_count=None, tokens=None, schedules=None, title_blocks=None):
    blocks = []
    for page, text in pages.items():
        blocks.append({"page_number": page, "text": text})
    return {
        "page_count": page_count or (max(pages) if pages else 0),
        "text": "\n".join(pages.values()),
        "blocks": blocks,
        "pages": [
            {"page_number": p, "text_length": len(t), "engineering_relevance_score": 5}
            for p, t in pages.items()
        ],
        "engineering_tokens": tokens or [],
        "schedules": schedules or [],
        "title_blocks": title_blocks or [],
    }


def _tok(text, page=1):
    return {"text": text, "normalized_text": text, "page": page, "takeoff_eligible": True}


class GroundingTests(unittest.TestCase):
    def test_no_evidence_makes_no_claim(self):
        prof = build_drawing_intelligence(_doc({1: "STRUCTURAL FRAMING PLAN\n" + "x " * 40}))
        n = prof["narrative"]
        self.assertIn("no catalog-valid steel", n["project_overview"].lower())
        self.assertEqual(n["drawing_language"], "No project-specific shorthand substitutions were found.")
        self.assertIn("No TYP", n["typical_conditions"])
        self.assertIn("No structural schedules", n["schedules"])

    def test_only_supported_families_are_named(self):
        prof = build_drawing_intelligence(_doc(
            {1: "FRAMING PLAN"},
            tokens=[_tok("W14X22"), _tok("W16X26"), _tok("W16X26"), _tok("HSS6X6X1/4")],
        ))
        fams = {f["family"] for f in prof["steel_system"]["families"]}
        self.assertEqual(fams, {"W", "HSS"})
        self.assertNotIn("angle", prof["narrative"]["steel_system"].lower())
        self.assertIn("W16X26", prof["steel_system"]["representative_sections"])
        # label tokens counted once each -- never multiplied
        w = next(f for f in prof["steel_system"]["families"] if f["family"] == "W")
        self.assertEqual(w["explicit_occurrences"], 3)

    def test_representative_sections_not_a_dump(self):
        toks = [_tok(f"W{d}X22") for d in range(8, 40, 2)] * 3
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN"}, tokens=toks))
        for fam in prof["steel_system"]["families"]:
            self.assertLessEqual(len(fam["representative"]), 4)


class TypicalConditionTests(unittest.TestCase):
    def test_typ_evidence_produces_insight(self):
        prof = build_drawing_intelligence(_doc({
            1: "ROOF FRAMING PLAN\nW16X26 TYP.\nW14X22, TYP\nSEE DETAIL SIM.",
        }))
        active = [i for i in prof["typical_conditions"] if i["detail"].get("present")]
        self.assertTrue(active)
        kws = {i["detail"]["keyword"] for i in active}
        self.assertIn("TYP", kws)
        self.assertIn("repeated framing", prof["narrative"]["typical_conditions"])

    def test_no_typ_is_not_invented(self):
        prof = build_drawing_intelligence(_doc({1: "FLOOR FRAMING PLAN\nW16X26 at grid A."}))
        self.assertEqual(
            prof["narrative"]["typical_conditions"],
            "No TYP / U.N.O. / repeated-condition language detected.",
        )

    def test_near_section_context_captured(self):
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN\nW21X44 TYP AT BAYS 1-6"}))
        active = [i for i in prof["typical_conditions"] if i["detail"].get("present")]
        near = {s for i in active for s in i["detail"].get("near_sections", [])}
        self.assertIn("W21X44", near)


class ScheduleTests(unittest.TestCase):
    def test_column_schedule_matrix_flagged_not_counted(self):
        sched_text = (
            "COLUMN SCHEDULE\nFIRST FLOOR 0' - 0\"\nSECOND FLOOR 14' - 0\"\n"
            "ROOF 28' - 0\"\nW14X90 W14X90 W12X65"
        )
        prof = build_drawing_intelligence(_doc(
            {1: "S-500 COLUMN SCHEDULE"},
            schedules=[{"schedule_id": "s1", "page_number": 1, "text": sched_text}],
        ))
        sched = prof["schedule_insights"]
        self.assertTrue(sched)
        self.assertEqual(sched[0]["detail"]["kind"], "column_schedule")
        self.assertIn("not a simple member count", sched[0]["detail"]["note"])

    def test_unclear_table_becomes_uncertainty_not_quantity(self):
        prof = build_drawing_intelligence(_doc(
            {1: "PLAN"},
            schedules=[{
                "schedule_id": "s2", "page_number": 3,
                "text": "MARK SIZE W12X26 W14X22 W16X31 W18X35 W21X44 W24X55 W10X12",
            }],
        ))
        kinds = {s["detail"]["kind"] for s in prof["schedule_insights"]}
        self.assertIn("unclassified_steel_table", kinds)
        self.assertTrue(any(
            u["detail"].get("kind") == "schedule_semantics" for u in prof["uncertainties"]
        ))

    def test_non_steel_table_not_surfaced(self):
        prof = build_drawing_intelligence(_doc(
            {1: "PLAN"},
            schedules=[{"schedule_id": "s3", "page_number": 2,
                        "text": "DOOR SCHEDULE\nD1 3070 HM\nD2 3070 WD"}],
        ))
        self.assertEqual(prof["schedule_insights"], [])


class ScopeRevisionTests(unittest.TestCase):
    def test_phase_stamp_from_title_block_only(self):
        prof = build_drawing_intelligence(_doc(
            {1: "FRAMING PLAN\nThe design development phase established the grid."},
            title_blocks=[{"page_number": 1, "text": "ISSUED FOR PERMIT"}],
        ))
        active = [i for i in prof["scope_signals"] if i["detail"].get("present")]
        labels = {i["detail"]["label"] for i in active}
        self.assertIn("Permit set", labels)
        # a prose mention of "design development" must NOT become a phase claim
        self.assertNotIn("Design Development", labels)

    def test_multiple_phases_raise_a_scope_uncertainty(self):
        prof = build_drawing_intelligence(_doc(
            {1: "PLAN"},
            title_blocks=[
                {"page_number": 1, "text": "EARLY STEEL RELEASE PACKAGE"},
                {"page_number": 2, "text": "ISSUED FOR BID"},
            ],
        ))
        self.assertTrue(any(u["detail"].get("kind") == "scope" for u in prof["uncertainties"]))
        self.assertIn("multiple phases present", prof["narrative"]["scope_revision"].lower())

    def test_no_scope_stamp_is_stated_plainly(self):
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN\nW16X26"}))
        self.assertIn("No explicit issue", prof["narrative"]["scope_revision"])


class RenovationTests(unittest.TestCase):
    def test_existing_new_detected(self):
        text = "PLAN\n(E) W14X22\n(N) W16X26\n(E) W12X19\nDEMOLISH (E) W10X12"
        prof = build_drawing_intelligence(_doc({1: text}))
        self.assertTrue(prof["existing_new"]["is_renovation"])
        self.assertIn("existing and new", prof["narrative"]["project_overview"])

    def test_new_construction_not_flagged_renovation(self):
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN\nW16X26\nW14X22"}))
        self.assertFalse(prof["existing_new"]["is_renovation"])


class NarrativeAndPacketTests(unittest.TestCase):
    def test_narrative_has_every_core_section(self):
        prof = build_drawing_intelligence(_doc(
            {1: "ROOF FRAMING PLAN\nW16X26 TYP"}, tokens=[_tok("W16X26")],
        ))
        for key in ("project_overview", "structural_content", "steel_system",
                    "drawing_language", "typical_conditions", "schedules",
                    "scope_revision", "important_notes", "uncertainties"):
            self.assertIn(key, prof["narrative"])

    def test_evidence_packet_is_bounded_and_has_no_token_dump(self):
        toks = [_tok(f"W{d}X{w}") for d in range(8, 40, 2) for w in range(10, 90, 5)]
        prof = build_drawing_intelligence(_doc({1: "FRAMING PLAN"}, tokens=toks))
        packet = evidence_packet(prof, max_chars=6000)
        self.assertLessEqual(len(packet), 6000)
        self.assertIn("STEEL SYSTEM", packet)
        # a full section dump would be hundreds of lines; the packet caps it
        self.assertLess(packet.count("W"), 200)


class SummaryLlmGroundingTests(unittest.TestCase):
    def _profile(self):
        return build_drawing_intelligence(_doc(
            {1: "ROOF FRAMING PLAN\nW16X26 TYP"},
            tokens=[_tok("W16X26"), _tok("W14X22")],
        ))

    def test_invented_section_rejects_the_section(self):
        prof = self._profile()

        class P:
            def propose(self, *_a):
                return {
                    "project_overview": "Uses W40X600 girders throughout.",  # not in profile
                    "structural_content": "Two framing pages.",
                    "steel_system": "Wide-flange framing.",
                    "drawing_language": "None found.",
                    "typical_conditions": "TYP language present.",
                    "schedules": "None.",
                    "scope_revision": "None.",
                }

        res = summarize(prof, provider=P(), evidence_text=evidence_packet(prof))
        # project_overview names an invented section -> that section keeps the
        # deterministic text
        self.assertIn("project_overview", res.dropped_claims)
        self.assertEqual(
            res.narrative["project_overview"], prof["narrative"]["project_overview"]
        )

    def test_all_rejected_keeps_deterministic_narrative(self):
        prof = self._profile()

        class P:
            def propose(self, *_a):
                return "not a dict"

        res = summarize(prof, provider=P(), evidence_text=evidence_packet(prof))
        self.assertIsNone(res.narrative)
        self.assertEqual(res.method, "deterministic")

    def test_provider_exception_is_safe(self):
        prof = self._profile()

        class P:
            def propose(self, *_a):
                raise RuntimeError("boom")

        res = summarize(prof, provider=P(), evidence_text=evidence_packet(prof))
        self.assertIsNone(res.narrative)
        self.assertIn("boom", res.error)

    def test_grounded_rewrite_is_accepted(self):
        prof = self._profile()

        class P:
            def propose(self, *_a):
                return {
                    "project_overview": "A small roof-framing package using W16X26 and W14X22 wide-flange beams.",
                    "structural_content": "One roof framing plan.",
                    "steel_system": "Wide-flange members only; W16X26 and W14X22 appear.",
                    "drawing_language": "No project shorthand was found.",
                    "typical_conditions": "TYP markings appear near the beam labels.",
                    "schedules": "No structural schedules were identified.",
                    "scope_revision": "No issue phase stamp was found.",
                }

        res = summarize(prof, provider=P(), evidence_text=evidence_packet(prof))
        self.assertEqual(res.method, "llm_enhanced")
        self.assertIn("W16X26", res.narrative["project_overview"])


if __name__ == "__main__":
    unittest.main()
