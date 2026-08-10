"""Graph evidence must resolve for tokens that really have a graph node.

Regression guard for the "Graph evidence: Unavailable" UI bug: every
prediction reported degree 0 / min_distance 999 because the feature provider
used ``source_node`` as its found-sentinel while no producer ever set it, so
the loop always fell through to the last (word-id) candidate, which is not a
graph source id.
"""

from __future__ import annotations

import unittest

from services.engineering.graph_builder import _classify_text_node, section_family
from services.engineering.structural_graph import (
    build_structural_graph,
    graph_features_for_source,
    graph_matches_document,
)
from services.multimodal.feature_providers import GraphFeatureProvider


def _document() -> dict:
    return {
        "engineering_tokens": [
            {
                "token_id": "token_p1_1",
                "text": "W18X35",
                "normalized_text": "W18X35",
                "page": 1,
                "bbox": [100, 100, 160, 112],
                "font_size": 9,
                "line": {"id": "line_aaa"},
                "source_word_ids": ["word_zzz"],
                "engineering_object_type": "beam",
            },
            {
                "token_id": "token_p1_2",
                "text": "HSS6X6X1/4",
                "normalized_text": "HSS6X6X1/4",
                "page": 1,
                "bbox": [140, 130, 210, 142],
                "font_size": 9,
                "line": {"id": "line_bbb"},
                "source_word_ids": ["word_yyy"],
                "engineering_object_type": "column",
            },
        ]
    }


def _geometry() -> dict:
    return {
        "objects": [
            {
                "geometry_id": "geom_1",
                "kind": "line",
                "page_number": 1,
                "bbox": [100, 118, 220, 122],
                "center": [160, 120],
                "length": 120,
                "width": 4,
                "area": 480,
                "orientation": 0.0,
            },
            {
                "geometry_id": "geom_2",
                "kind": "line",
                "page_number": 1,
                "bbox": [150, 120, 154, 240],
                "center": [152, 180],
                "length": 120,
                "width": 4,
                "area": 480,
                "orientation": 90.0,
            },
        ]
    }


class GraphSourceFeatureIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = build_structural_graph(_document(), _geometry())

    def test_source_features_carry_node_identity(self) -> None:
        features = self.graph["source_features"]["token_p1_1"]
        self.assertTrue(features["source_node"])
        self.assertTrue(features["graph_available"])
        self.assertEqual(features["node_kind"], "beam")

    def test_unknown_source_is_reported_as_unavailable(self) -> None:
        features = graph_features_for_source(self.graph, "word_does_not_exist")
        self.assertFalse(features["graph_available"])
        self.assertIsNone(features["source_node"])
        self.assertEqual(features["degree"], 0.0)
        self.assertEqual(features["min_distance"], 999.0)

    def test_legacy_artifact_without_identity_is_backfilled(self) -> None:
        # Graphs persisted before identity fields existed are reused on
        # re-analysis; they must not report a spurious miss.
        legacy = dict(self.graph)
        legacy["source_features"] = {
            key: {
                name: value
                for name, value in value_map.items()
                if name not in ("source_node", "node_kind", "graph_available")
            }
            for key, value_map in self.graph["source_features"].items()
        }
        features = graph_features_for_source(legacy, "token_p1_1")
        self.assertTrue(features["graph_available"])
        self.assertTrue(features["source_node"])


class GraphFeatureProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = build_structural_graph(_document(), _geometry())
        self.provider = GraphFeatureProvider()

    def test_token_id_wins_over_unmatched_word_ids(self) -> None:
        token = _document()["engineering_tokens"][0]
        self.assertNotIn("word_zzz", self.graph["source_features"])

        features = self.provider.extract({"token": token, "graph": self.graph})

        self.assertTrue(features["graph_available"])
        self.assertEqual(
            features["source_node"],
            self.graph["source_features"]["token_p1_1"]["source_node"],
        )
        self.assertGreater(float(features["degree"]), 0.0)

    def test_every_engineering_token_resolves_its_node(self) -> None:
        for token in _document()["engineering_tokens"]:
            features = self.provider.extract(
                {"token": token, "graph": self.graph}
            )
            self.assertTrue(
                features["graph_available"],
                f"{token['token_id']} lost its graph neighborhood",
            )

    def test_missing_graph_stays_unavailable(self) -> None:
        features = self.provider.extract(
            {
                "token": _document()["engineering_tokens"][0],
                "graph": {"nodes": [], "edges": []},
            }
        )
        self.assertFalse(features["graph_available"])


class RenumberedTokenIdTests(unittest.TestCase):
    """Token ids are positional, so re-extraction renumbers them.

    A graph built from an earlier pass then shares no ids with the current
    document, which is what made graph evidence read "Unavailable" for an
    arbitrary subset of labels (HSS, L, C, W alike).
    """

    def setUp(self) -> None:
        self.graph = build_structural_graph(_document(), _geometry())
        self.provider = GraphFeatureProvider()

    def _renumbered(self) -> list:
        tokens = _document()["engineering_tokens"]
        for offset, token in enumerate(tokens):
            token["token_id"] = f"token_p1_{90 + offset}"
            token["source_word_ids"] = [f"word_new_{offset}"]
            token["line"] = {"id": f"line_new_{offset}"}
        return tokens

    def test_renumbered_tokens_resolve_by_page_bbox_and_text(self) -> None:
        for token in self._renumbered():
            features = self.provider.extract(
                {"token": token, "graph": self.graph}
            )
            self.assertTrue(features["graph_available"], token["token_id"])
            self.assertEqual(features["source_match"], "page_bbox_text")

    def test_same_place_but_different_text_is_not_accepted(self) -> None:
        token = self._renumbered()[0]
        token["text"] = "HSS12X12X1/2"
        token["normalized_text"] = "HSS12X12X1/2"

        features = self.provider.extract({"token": token, "graph": self.graph})

        self.assertFalse(features["graph_available"])
        self.assertEqual(features["source_match"], "unresolved")

    def test_stale_graph_is_detected(self) -> None:
        document = _document()
        self.assertTrue(graph_matches_document(self.graph, document))
        document["engineering_tokens"] = self._renumbered()
        self.assertFalse(graph_matches_document(self.graph, document))


class ShapeFamilyNodeKindTests(unittest.TestCase):
    """A shape family constrains the section, not always the member role."""

    def test_channels_angles_and_tees_are_not_called_beams(self) -> None:
        for label in ("C8X11.5", "MC12X31", "L3X3X1/4", "2L3X3X1/4", "WT7X19"):
            kind = _classify_text_node(label).value
            self.assertNotEqual(kind, "beam", f"{label} classified as {kind}")
            self.assertEqual(kind, "steel_section", label)

    def test_wide_flange_and_plate_keep_their_roles(self) -> None:
        self.assertEqual(_classify_text_node("W18X35").value, "beam")
        self.assertEqual(_classify_text_node("HP12X53").value, "column")
        self.assertEqual(_classify_text_node("PL 1x9x1").value, "plate")

    def test_explicit_role_word_outranks_the_family(self) -> None:
        self.assertEqual(_classify_text_node("W12X40 COLUMN").value, "column")
        self.assertEqual(_classify_text_node("HSS6X6 BRACE").value, "brace")

    def test_families_are_matched_longest_first(self) -> None:
        self.assertEqual(section_family("WT7X19"), "WT")
        self.assertEqual(section_family("MC12X31"), "MC")
        self.assertEqual(section_family("ST12X50"), "ST")
        self.assertEqual(section_family("HSS8X8"), "HSS")
        self.assertEqual(section_family("12X4"), "")

    def test_upstream_detected_role_is_preserved(self) -> None:
        graph = build_structural_graph(_document(), _geometry())
        kinds = {
            node["text"]: node["kind"]
            for node in graph["nodes"]
            if str(node["node_id"]).startswith("txt_")
        }
        # engineering_object_type said "column" for the HSS token.
        self.assertEqual(kinds["HSS6X6X1/4"], "column")

    def test_shape_family_does_not_override_a_resolved_kind(self) -> None:
        # The semantic pass used to relabel every HSS a brace and every
        # W-shape a beam, discarding upstream detection.
        document = _document()
        document["engineering_tokens"][1]["engineering_object_type"] = "column"
        document["engineering_tokens"][1]["text"] = "HSS8X8"
        graph = build_structural_graph(document, _geometry())
        kinds = {
            node["text"]: node["kind"]
            for node in graph["nodes"]
            if str(node["node_id"]).startswith("txt_")
        }
        self.assertEqual(kinds["HSS8X8"], "column")


if __name__ == "__main__":
    unittest.main()
