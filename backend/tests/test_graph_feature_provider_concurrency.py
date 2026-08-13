"""
Regression test for the P1 GraphFeatureProvider cache race (accuracy sprint
Phase 2A).

``GraphFeatureProvider`` is a process-lifetime singleton (see
``orchestrator._graph_provider``). Its old implementation cached exactly one
graph's source-lookup index in a single mutable slot
(``self._lookup``/``self._lookup_fingerprint``), updated with a non-atomic
check-then-write. Two concurrent ``/analyze`` calls for two DIFFERENT
documents could interleave that check-then-write such that one document's
prediction silently resolved against the OTHER document's graph — attaching
the wrong ``source_node``/``node_kind``/``degree`` as evidence, with no error
raised.

This test drives many concurrent, interleaved ``extract()`` calls for two
distinct documents through one shared provider instance (mirroring the real
singleton) and asserts that every result for document A only ever contains
document A's node identity, and likewise for document B — never mixed. To
make the race window reliably observable rather than merely theoretical, the
underlying index build is patched to sleep briefly, which reproduces the
interleaving the bug depended on deterministically instead of by chance.
"""

from __future__ import annotations

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

from services.engineering.structural_graph import build_structural_graph
from services.multimodal.feature_providers import GraphFeatureProvider


def _document(prefix: str, text: str) -> dict:
    return {
        "engineering_tokens": [
            {
                "token_id": f"token_{prefix}_1",
                "text": text,
                "normalized_text": text,
                "page": 1,
                "bbox": [100, 100, 160, 112],
                "font_size": 9,
                "line": {"id": f"line_{prefix}"},
                "source_word_ids": [],
                "engineering_object_type": "beam",
            }
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
            }
        ]
    }


class GraphFeatureProviderConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc_a = _document("a", "W16X26")
        self.doc_b = _document("b", "HSS8X8X1/2")
        self.graph_a = build_structural_graph(self.doc_a, _geometry())
        self.graph_b = build_structural_graph(self.doc_b, _geometry())
        self.token_a = self.doc_a["engineering_tokens"][0]
        self.token_b = self.doc_b["engineering_tokens"][0]

        # Sanity: the two documents really do have distinct node identities,
        # otherwise this test couldn't detect cross-contamination at all.
        self.node_a = self.graph_a["source_features"]["token_a_1"]["source_node"]
        self.node_b = self.graph_b["source_features"]["token_b_1"]["source_node"]
        self.assertTrue(self.node_a)
        self.assertTrue(self.node_b)
        self.assertNotEqual(self.node_a, self.node_b)

    def test_concurrent_documents_never_share_graph_evidence(self):
        provider = GraphFeatureProvider()  # one shared instance, like the real singleton

        from services.engineering import structural_graph as structural_graph_module

        real_build_source_lookup = structural_graph_module.build_source_lookup

        def slow_build_source_lookup(graph):
            # Widen the interleaving window deterministically instead of
            # relying on OS scheduling luck to expose the race.
            time.sleep(0.02)
            return real_build_source_lookup(graph)

        results: list[tuple[str, dict]] = []
        results_lock = threading.Lock()

        def run_one(which: str) -> None:
            if which == "a":
                features = provider.extract({"token": self.token_a, "graph": self.graph_a})
            else:
                features = provider.extract({"token": self.token_b, "graph": self.graph_b})
            with results_lock:
                results.append((which, features))

        jobs = (["a", "b"] * 25)

        with patch.object(
            structural_graph_module, "build_source_lookup", side_effect=slow_build_source_lookup
        ), patch(
            "services.multimodal.feature_providers.build_source_lookup",
            side_effect=slow_build_source_lookup,
        ):
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(run_one, which) for which in jobs]
                for future in as_completed(futures):
                    future.result()  # re-raise any worker exception

        self.assertEqual(len(results), len(jobs))
        for which, features in results:
            expected_node = self.node_a if which == "a" else self.node_b
            wrong_node = self.node_b if which == "a" else self.node_a
            self.assertEqual(
                features["source_node"],
                expected_node,
                f"document {which} received the wrong document's graph node "
                f"(got {features['source_node']!r}, expected {expected_node!r}) "
                "— this is exactly the cross-document contamination the "
                "singleton cache race allowed",
            )
            self.assertNotEqual(features["source_node"], wrong_node)


if __name__ == "__main__":
    unittest.main()
