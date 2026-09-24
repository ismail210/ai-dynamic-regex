"""Shadow-only schedule-region quarantine safety contract."""

from __future__ import annotations

import json
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from config import Settings
from services.engineering.schedule_region_quarantine import (
    detect_schedule_regions,
    quarantine_tokens,
)


@contextmanager
def _setting(name: str, value):
    from config import settings

    original = getattr(settings, name)
    try:
        object.__setattr__(settings, name, value)
        yield
    finally:
        object.__setattr__(settings, name, original)


def _token(
    text: str = "W8X21",
    *,
    bbox=None,
    page: int = 1,
    document_id: str = "doc-a",
    **extra,
) -> dict:
    return {
        "object_id": extra.pop("object_id", text),
        "document_id": document_id,
        "text": text,
        "raw_text": text,
        "normalized_text": text,
        "section": text,
        "page_number": page,
        "bbox": bbox or [20, 20, 40, 30],
        "takeoff_eligible": True,
        "object_scope": "takeoff",
        "comparison": {"match_status": "exact_match"},
        **extra,
    }


def _region(region_id="r1", *, bbox=None, document_id="doc-a", status="confident") -> dict:
    return {
        "region_id": region_id,
        "page_number": 1,
        "region_bbox": bbox or [10, 10, 100, 100],
        "source_document_id": document_id,
        "boundary_status": status,
        "region_source": "test",
    }


class ScheduleRegionQuarantineTests(unittest.TestCase):
    def test_flag_is_default_off(self) -> None:
        self.assertFalse(Settings().schedule_region_quarantine_enabled)

    def test_exact_section_inside_region_becomes_evidence_only(self) -> None:
        original = _token()
        result = quarantine_tokens([original], [_region()], document_id="doc-a")
        quarantined = result["tokens"][0]
        self.assertEqual(quarantined["section"], "W8X21")
        self.assertEqual(quarantined["raw_text"], "W8X21")
        self.assertEqual(quarantined["occurrence_scope"], "schedule_definition")
        self.assertFalse(quarantined["countable_occurrence"])
        self.assertFalse(quarantined["takeoff_eligible"])
        self.assertEqual(result["quarantined_count"], 1)
        self.assertTrue(original["takeoff_eligible"], "input must not be mutated")

    def test_section_immediately_outside_region_is_unchanged_on_mixed_sheet(self) -> None:
        inside = _token(object_id="inside")
        outside = _token(bbox=[101, 20, 120, 30], object_id="outside")
        result = quarantine_tokens([inside, outside], [_region()], document_id="doc-a")
        self.assertFalse(result["tokens"][0]["takeoff_eligible"])
        self.assertTrue(result["tokens"][1]["takeoff_eligible"])
        self.assertNotIn("occurrence_scope", result["tokens"][1])

    def test_page_with_no_schedule_region_is_unchanged(self) -> None:
        token = _token()
        result = quarantine_tokens([token], [], document_id="doc-a")
        self.assertEqual(result["tokens"], [token])

    def test_boundary_straddle_abstains(self) -> None:
        token = _token(bbox=[95, 20, 105, 30])
        result = quarantine_tokens([token], [_region()], document_id="doc-a")
        self.assertTrue(result["tokens"][0]["takeoff_eligible"])
        self.assertEqual(result["ambiguous_count"], 1)

    def test_overlapping_regions_choose_smallest_then_id_deterministically(self) -> None:
        large = _region("z-large", bbox=[0, 0, 200, 200])
        small_b = _region("b-small", bbox=[10, 10, 80, 80])
        small_a = _region("a-small", bbox=[10, 10, 80, 80])
        forward = quarantine_tokens([_token()], [large, small_b, small_a], document_id="doc-a")
        reverse = quarantine_tokens([_token()], [small_a, small_b, large], document_id="doc-a")
        self.assertEqual(forward, reverse)
        provenance = forward["tokens"][0]["schedule_region_provenance"]
        self.assertEqual(provenance["region_id"], "a-small")
        self.assertEqual(
            provenance["overlapping_region_ids"], ["a-small", "b-small", "z-large"]
        )

    def test_context_definition_scope_has_precedence(self) -> None:
        context = _token(
            object_scope="context_definition",
            takeoff_eligible=False,
            countable_occurrence=False,
        )
        result = quarantine_tokens([context], [_region()], document_id="doc-a")
        self.assertEqual(result["tokens"][0]["object_scope"], "context_definition")
        self.assertEqual(result["decisions"][0]["action"], "unchanged_context_definition")

    def test_semantic_lock_is_preserved(self) -> None:
        token = _token()
        before = json.dumps(token["comparison"], sort_keys=True)
        result = quarantine_tokens([token], [_region()], document_id="doc-a")
        after = result["tokens"][0]
        self.assertEqual(after["section"], "W8X21")
        self.assertEqual(json.dumps(after["comparison"], sort_keys=True), before)

    def test_invalid_catalog_text_is_never_auto_accepted(self) -> None:
        invalid = _token("W99X999")
        result = quarantine_tokens([invalid], [_region()], document_id="doc-a")
        self.assertTrue(result["tokens"][0]["takeoff_eligible"])
        self.assertEqual(result["decisions"][0]["reason"], "invalid_or_incomplete_catalog_text")

    def test_cross_document_region_is_rejected(self) -> None:
        result = quarantine_tokens(
            [_token(document_id="doc-b")], [_region(document_id="doc-a")], document_id="doc-b"
        )
        self.assertTrue(result["tokens"][0]["takeoff_eligible"])
        self.assertEqual(result["decisions"][0]["reason"], "cross_document_region")

    def test_output_is_byte_deterministic(self) -> None:
        args = ([_token(), _token("W10X33", bbox=[45, 20, 65, 30])], [_region()])
        first = json.dumps(quarantine_tokens(*args, document_id="doc-a"), sort_keys=True)
        second = json.dumps(quarantine_tokens(*args, document_id="doc-a"), sort_keys=True)
        self.assertEqual(first, second)


class ScheduleRegionDetectionTests(unittest.TestCase):
    @staticmethod
    def _word(text, x0, y0, x1, y1, *, rotation=0):
        return {
            "text": text,
            "bbox": [x0, y0, x1, y1],
            "page_number": 1,
            "rotation": rotation,
        }

    def _matrix_document(self, *, with_title=True):
        words = []
        if with_title:
            words += [self._word("COLUMN", 10, 5, 30, 10), self._word("SCHEDULE", 32, 5, 60, 10)]
        words += [
            self._word("0' - 0\"", 10, 30, 45, 35),
            self._word("14' - 0\"", 10, 60, 45, 65),
            self._word("W8X21", 90, 35, 100, 50, rotation=90),
            self._word("W10X33", 130, 35, 140, 52, rotation=90),
            self._word("W12X40", 170, 35, 180, 52, rotation=90),
            self._word("COLUMN", 10, 100, 35, 108),
            self._word("LOCATIONS", 37, 100, 75, 108),
        ]
        return {"document_id": "doc-a", "words": words, "engineering_tokens": []}

    def test_strong_title_grid_levels_and_labels_produce_confident_region(self) -> None:
        lines = {1: [(80, 0, 120), (120, 0, 120), (160, 0, 120), (200, 0, 120)]}
        result = detect_schedule_regions(
            self._matrix_document(), vector_lines_by_page=lines
        )
        self.assertEqual(len(result["regions"]), 1)
        self.assertEqual(result["regions"][0]["boundary_status"], "confident")
        self.assertEqual(result["ambiguous_regions"], [])

    def test_ambiguous_grid_boundary_abstains_even_with_other_evidence(self) -> None:
        lines = {1: [(80, 0, 120), (120, 0, 120), (160, 0, 120)]}
        result = detect_schedule_regions(
            self._matrix_document(with_title=False), vector_lines_by_page=lines
        )
        self.assertEqual(result["regions"], [])
        self.assertEqual(len(result["ambiguous_regions"]), 1)

    _GRID = {1: [(80, 0, 120), (120, 0, 120), (160, 0, 120), (200, 0, 120)]}

    def test_missing_title_is_confident_only_when_all_local_signals_agree(self) -> None:
        result = detect_schedule_regions(
            self._matrix_document(with_title=False), vector_lines_by_page=self._GRID
        )
        self.assertEqual(len(result["regions"]), 1)
        self.assertNotIn("schedule_title", result["regions"][0]["evidence"])

    def test_missing_any_required_signal_abstains(self) -> None:
        drops = {
            "level_datum_axis": lambda w: "'" not in w["text"],
            "catalog_label_density": lambda w: w["text"] != "W12X40",
        }
        for signal, keep in drops.items():
            with self.subTest(signal=signal):
                document = self._matrix_document(with_title=False)
                document["words"] = [word for word in document["words"] if keep(word)]
                result = detect_schedule_regions(document, vector_lines_by_page=self._GRID)
                self.assertEqual(result["regions"], [])
                self.assertNotIn(signal, result["ambiguous_regions"][0]["evidence"])
        with self.subTest(signal="column_locations_header"):
            document = self._matrix_document(with_title=False)
            document["words"] = [w for w in document["words"] if w["text"] != "LOCATIONS"]
            result = detect_schedule_regions(document, vector_lines_by_page=self._GRID)
            self.assertEqual((result["regions"], result["ambiguous_regions"]), ([], []))

    def test_region_is_clipped_so_adjacent_plan_labels_stay_unchanged(self) -> None:
        document = self._matrix_document(with_title=False)
        document["words"] += [
            self._word("W14X90", 210, 35, 220, 52, rotation=90),
            self._word("W16X31", 100, 140, 130, 148),
        ]
        regions = detect_schedule_regions(document, vector_lines_by_page=self._GRID)["regions"]
        tokens = [
            _token("W10X33", bbox=[130, 35, 140, 52], object_id="schedule"),
            _token("W14X90", bbox=[210, 35, 220, 52], object_id="plan-right"),
            _token("W16X31", bbox=[100, 140, 130, 148], object_id="plan-below"),
        ]
        result = quarantine_tokens(tokens, regions, document_id="doc-a")
        actions = {d["token_id"]: d["action"] for d in result["decisions"]}
        self.assertEqual(
            actions,
            {"schedule": "quarantined", "plan-right": "unchanged", "plan-below": "unchanged"},
        )
        self.assertEqual(result["tokens"][1:], tokens[1:])


class ShadowWiringTests(unittest.TestCase):
    def _extract(self, *, enabled: bool):
        from services import extraction_engine

        document = {
            "engineering_tokens": [_token()],
            "dimensions": [],
            "document_id": "doc-a",
        }
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    extraction_engine,
                    "extract_document_structure",
                    return_value=document,
                )
            )
            for name in ("attach_schedule_grid", "attach_document_prior", "attach_legend_profile"):
                stack.enter_context(patch.object(extraction_engine, name))
            stack.enter_context(
                patch.object(
                    extraction_engine,
                    "group_annotation_fragments",
                    side_effect=lambda tokens: tokens,
                )
            )
            stack.enter_context(
                patch.object(
                    extraction_engine,
                    "filter_engineering_objects",
                    side_effect=lambda tokens, **_kwargs: tokens,
                )
            )
            stack.enter_context(
                patch.object(extraction_engine, "annotate_takeoff_scope", return_value={})
            )
            stack.enter_context(
                patch.object(extraction_engine, "_rescope_diagnostics_to_engineering_objects")
            )
            stack.enter_context(_setting("schedule_region_quarantine_enabled", enabled))
            builder = stack.enter_context(
                patch(
                    "services.engineering.schedule_region_quarantine.build_schedule_region_quarantine",
                    return_value={"mode": "shadow_only"},
                )
            )
            result = extraction_engine.extract_engineering_document("fake.pdf", document_id="doc-a")
        return result, builder

    def test_default_off_is_byte_neutral_and_does_not_build_shadow(self) -> None:
        result, builder = self._extract(enabled=False)
        self.assertNotIn("schedule_region_quarantine_shadow", result)
        builder.assert_not_called()

    def test_flag_on_attaches_side_artifact_without_replacing_live_tokens(self) -> None:
        result, builder = self._extract(enabled=True)
        self.assertEqual(result["schedule_region_quarantine_shadow"], {"mode": "shadow_only"})
        self.assertEqual(result["engineering_tokens"], [_token()])
        builder.assert_called_once()


if __name__ == "__main__":
    unittest.main()
