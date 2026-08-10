"""Regression test for a real-data pilot defect (Phase 2.5).

Found while running the Phase 2 export path against a real project PDF
with 235 label groups on a single dense page: ``write_group_export``
called ``render_page_svg`` once per group, and each render re-opened
the PDF and re-rendered the same multi-megabyte base page from scratch
-- on that real page this took the pipeline from a few seconds to a
5-minute timeout, and (separately) would have written ~5.6 GB of
near-duplicate SVG content for one page alone.

This fixture reproduces the *mechanism* (many groups sharing one page)
at a scale that runs in well under a second, without needing the real
(confidential) source file. It asserts the fix
(``review_export.render_page_svg`` is ``lru_cache``d) actually
eliminates the redundant renders, not just that export completes.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from services.ml_association.review_export import render_page_svg, write_group_export
from services.ml_association.schemas import (
    AssociationCandidateRow,
    GeometryEvidence,
    HeuristicEvidence,
    LabelEvidence,
    LabelGroup,
)

CREATED_AT = "2026-01-01T00:00:00Z"


def _make_many_groups_on_one_page(count: int) -> list:
    """count independent label groups, all on page 1, each with one
    real candidate -- simulates a real dense page with many labels
    without needing thousands of real geometry objects."""

    groups = []
    for i in range(count):
        label = LabelEvidence(
            raw_text=f"W{10 + i}X{20 + i}",
            text_bbox=[float(i), float(i), float(i) + 10, float(i) + 5],
            text_center=[float(i) + 5, float(i) + 2.5],
        )
        candidate = AssociationCandidateRow(
            project_id="pilot_perf",
            document_id="doc_perf",
            page_id="page_perf",
            page_number=1,
            text_entity_id=f"token_{i}",
            geometry_entity_id=f"geom_{i}",
            association_candidate_id=f"assoc_{i}",
            candidate_generator_version="v1",
            feature_generator_version="v1",
            created_at=CREATED_AT,
            label=label,
            geometry=GeometryEvidence(
                geometry_bbox=[float(i) + 20, float(i), float(i) + 30, float(i) + 5],
                geometry_center=[float(i) + 25, float(i) + 2.5],
            ),
            heuristic=HeuristicEvidence(current_heuristic_selected=True, current_heuristic_rank=1),
        )
        groups.append(
            LabelGroup(
                group_id=f"group_{i}",
                project_id="pilot_perf",
                document_id="doc_perf",
                page_id="page_perf",
                page_number=1,
                text_entity_id=f"token_{i}",
                label=label,
                candidates=[candidate],
                candidate_generator_version="v1",
                feature_generator_version="v1",
                created_at=CREATED_AT,
            )
        )
    return groups


class ExportPerformanceRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        render_page_svg.cache_clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf_path = Path(self.tmp.name) / "many_labels.pdf"
        doc = fitz.open()
        doc.new_page(width=2000, height=2000)
        doc.save(self.pdf_path)
        doc.close()

    def tearDown(self) -> None:
        render_page_svg.cache_clear()
        self.tmp.cleanup()

    def test_many_groups_on_one_page_reuse_a_single_cached_render(self) -> None:
        groups = _make_many_groups_on_one_page(150)
        out_dir = Path(self.tmp.name) / "export"
        for group in groups:
            write_group_export(group, pdf_path=str(self.pdf_path), output_dir=out_dir)

        info = render_page_svg.cache_info()
        self.assertEqual(
            info.misses,
            1,
            "150 groups on the same page must trigger exactly one real "
            "PyMuPDF render, not one per group",
        )
        self.assertEqual(info.hits, 149)

    def test_export_of_150_groups_completes_quickly(self) -> None:
        import time

        groups = _make_many_groups_on_one_page(150)
        out_dir = Path(self.tmp.name) / "export_timed"
        start = time.time()
        for group in groups:
            write_group_export(group, pdf_path=str(self.pdf_path), output_dir=out_dir)
        elapsed = time.time() - start
        # Generous bound (real hardware: well under 1s) -- this is a
        # regression guard against reintroducing the O(groups) render
        # cost, not a tight perf benchmark.
        self.assertLess(elapsed, 10.0)


if __name__ == "__main__":
    unittest.main()
