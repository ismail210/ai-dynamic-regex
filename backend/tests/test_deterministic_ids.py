"""Reproducibility tests for geometry/graph identifiers.

Phase 1 of the ML-association roadmap (docs/ml_association_phase/) requires
that repeated extraction of the same document produce byte-identical
geometry and graph artifacts, so that diagnostics, regression fixtures, and
future reviewer tooling can diff runs meaningfully. Previously
``geometry_extractor._gid`` and ``graph_builder._nid`` used
``uuid.uuid4()``, so every run produced different IDs even for an
unchanged input file. See docs/geometry_graph_audit/04_graph_audit.md §7.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fitz

from services.engineering.geometry_extractor import extract_geometry
from services.engineering.graph_builder import build_graph
from services.pdf_parser import extract_document_structure


def _make_sample_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((72, 72), "W18X35 BEAM", fontsize=14)
    page.insert_text((72, 120), "HSS8X8X1/2 COLUMN", fontsize=12)
    page.insert_text((72, 168), "See S-101", fontsize=10)
    page.draw_rect(fitz.Rect(200, 200, 400, 260), color=(0, 0, 0), width=1)
    page.draw_line(fitz.Point(50, 300), fitz.Point(250, 300), color=(0, 0, 0), width=1)
    page.draw_circle(fitz.Point(450, 400), 30, color=(0, 0, 0), width=1)
    doc.save(path)
    doc.close()


class DeterministicIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "sample.pdf"
        _make_sample_pdf(self.pdf)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _extract_all(self):
        document = extract_document_structure(str(self.pdf))
        geometry = extract_geometry(str(self.pdf), document)
        graph = build_graph(document, geometry)
        return document, geometry, graph

    def test_geometry_ids_are_reproducible(self) -> None:
        _, geometry_a, _ = self._extract_all()
        _, geometry_b, _ = self._extract_all()
        ids_a = sorted(obj["geometry_id"] for obj in geometry_a["objects"])
        ids_b = sorted(obj["geometry_id"] for obj in geometry_b["objects"])
        self.assertTrue(ids_a, "fixture must produce at least one geometry object")
        self.assertEqual(ids_a, ids_b)

    def test_graph_node_and_edge_ids_are_reproducible(self) -> None:
        _, _, graph_a = self._extract_all()
        _, _, graph_b = self._extract_all()
        node_ids_a = sorted(n["node_id"] for n in graph_a["nodes"])
        node_ids_b = sorted(n["node_id"] for n in graph_b["nodes"])
        edge_ids_a = sorted(e["edge_id"] for e in graph_a["edges"])
        edge_ids_b = sorted(e["edge_id"] for e in graph_b["edges"])
        self.assertTrue(node_ids_a, "fixture must produce at least one node")
        self.assertEqual(node_ids_a, node_ids_b)
        self.assertEqual(edge_ids_a, edge_ids_b)

    def test_full_graph_artifact_is_byte_identical_across_runs(self) -> None:
        _, _, graph_a = self._extract_all()
        _, _, graph_b = self._extract_all()
        self.assertEqual(
            json.dumps(graph_a, sort_keys=True),
            json.dumps(graph_b, sort_keys=True),
        )

    def test_node_ids_still_carry_the_txt_geo_prefix_convention(self) -> None:
        # graph_builder.py relies on the "txt_"/"geo_" string prefix (not a
        # separate type field) to distinguish text nodes from geometry nodes
        # in several places (see build_graph's semantic_kinds filtering).
        # Deterministic IDs must preserve this convention.
        _, _, graph = self._extract_all()
        for node in graph["nodes"]:
            self.assertTrue(
                node["node_id"].startswith("txt_") or node["node_id"].startswith("geo_"),
                f"unexpected node_id prefix: {node['node_id']}",
            )

    def test_edge_ids_do_not_collide_when_same_pair_and_relation_repeats(self) -> None:
        # add_edge's occurrence counter must keep edge_id unique even if the
        # same (source, target, relation) triple is ever emitted more than
        # once within a single build.
        _, _, graph = self._extract_all()
        edge_ids = [e["edge_id"] for e in graph["edges"]]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))


if __name__ == "__main__":
    unittest.main()
