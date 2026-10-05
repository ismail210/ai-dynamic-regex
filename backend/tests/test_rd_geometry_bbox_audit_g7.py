"""Isolated tests for G7 geometry/bbox representation audit (R&D only)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "geometry_bbox_audit_g7.py"
GOLD = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_outcomes.jsonl"
)
EXTRACTOR = ROOT / "services" / "engineering" / "geometry_extractor.py"
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)


def _load_mod():
    spec = importlib.util.spec_from_file_location("geometry_bbox_audit_g7", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load_mod()


def test_gold_sha_frozen():
    assert hashlib.sha256(GOLD.read_bytes()).hexdigest() == EXPECTED_GOLD_SHA


def test_gold_has_75_cases():
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 75


def test_classify_local_bbox(m):
    q = m.classify_bbox_quality([100, 100, 250, 140], length=155.0, point_count=2)
    assert q == "LOCAL_BBOX"


def test_classify_giant_bbox(m):
    q = m.classify_bbox_quality([0, 0, 900, 700], length=1200.0, point_count=6)
    assert q == "GIANT_BBOX"


def test_classify_degenerate_bbox(m):
    q = m.classify_bbox_quality([10, 10, 10.2, 10.3], length=0.1, point_count=2)
    assert q == "DEGENERATE_BBOX"


def test_classify_compound_bbox(m):
    # Mid-size extent but winding path (length >> diagonal).
    q = m.classify_bbox_quality(
        [100, 100, 300, 250], length=900.0, point_count=12, page_width=3000, page_height=2200
    )
    assert q == "COMPOUND_BBOX"


def test_label_class_helpers(m):
    assert m.label_class("W10X15") == "short_W"
    assert m.label_class("W21X44") == "girder_W"
    assert m.label_class("L4X4X3/8") == "L_clip_angle"
    assert m.label_class("WT7X19") == "WT"
    assert m.label_class('PL 3/8"') == "plate"


def test_feature_table_shape(m):
    table = m.feature_readiness_table()
    assert len(table) >= 10
    assert {r["feature"] for r in table} >= {"geometry bbox", "path length", "leader endpoint"}


def test_gate_not_ready_when_retention_low(m):
    summary = {
        "metrics": {
            "missing_candidate_visible_member_n": 58,
            "visible_miss_with_usable_local_geometry": 10,
            "current_retention_rate_among_raw_present": 0.3,
            "gold_geometry_coverage_among_associated": 1.0,
            "bbox_usable_rate": 0.5,
        },
        "dominant_blockers": {
            "GEOMETRY_POPULATION_GAP": 30,
            "LEADER_TARGET_GAP": 12,
            "SEGMENTATION_GAP": 5,
        },
    }
    assert m.decide_gate(summary) == "REPRESENTATION_NOT_READY"


def test_script_does_not_modify_extractor_bytes():
    # Guard: G7 must not rewrite production extractor.
    before = EXTRACTOR.read_bytes()
    # Loading the module must not touch the file.
    _load_mod()
    assert EXTRACTOR.read_bytes() == before
