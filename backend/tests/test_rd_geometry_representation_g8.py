"""Isolated tests for G8 representation repair experiment (R&D only)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "representation_repair_g8.py"
GOLD = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_outcomes.jsonl"
)
EXTRACTOR = ROOT / "services" / "engineering" / "geometry_extractor.py"
RETRIEVAL = ROOT / "scripts" / "rd_geometry_integration" / "retrieval.py"
RETRIEVAL_V2 = ROOT / "scripts" / "rd_geometry_integration" / "retrieval_v2.py"
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)


def _load_mod():
    spec = importlib.util.spec_from_file_location("representation_repair_g8", SCRIPT)
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
    rows = [json.loads(l) for l in GOLD.read_text().splitlines() if l.strip()]
    assert len(rows) == 75
    assert sum(1 for r in rows if r["decision"] == "associated") == 8


def test_raw_drawing_index_stable(m):
    drawing = {"rect": type("R", (), {"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0})(), "items": []}
    a = m.raw_drawing_index(8, drawing, 12)
    b = m.raw_drawing_index(8, drawing, 12)
    assert a == b
    assert a.startswith("raw_p8_12_")


def test_classify_simple_long_vs_compound(m):
    simple = m.classify_giant(
        [0, 0, 900, 10], length=900.0, point_count=2, page_w=3000, page_h=2200
    )
    assert simple == "SIMPLE_LONG_STROKE"
    compound = m.classify_giant(
        [100, 100, 400, 300], length=1200.0, point_count=8, page_w=3000, page_h=2200
    )
    assert compound == "COMPOUND_POLYLINE"


def test_page_frame_detection(m):
    assert m.is_page_frame_bbox([0, 0, 2900, 2100], 3000, 2200) is True
    assert m.is_page_frame_bbox([100, 100, 200, 150], 3000, 2200) is False


def test_candidate_schema_kinds(m):
    c = m.make_candidate(
        candidate_id="rnd_x",
        source_raw_id="raw_1",
        source_type="raw_drawing",
        page=8,
        bbox=[0, 0, 10, 2],
        length=10.0,
        orientation=0.0,
        point_count=2,
        candidate_kind="LINE_MEMBER_CANDIDATE",
        derivation="cap_restore",
        confidence_basis="test",
        provenance={
            "source_page": 8,
            "source_raw_id": "raw_1",
            "source_geometry_id": None,
            "derivation_type": "cap_restore",
            "original_bbox": [0, 0, 10, 2],
            "derived_bbox": [0, 0, 10, 2],
            "original_point_count": 2,
            "derived_point_count": 2,
        },
    )
    assert set(c.keys()) >= {
        "candidate_id",
        "source_raw_id",
        "candidate_kind",
        "derivation",
        "provenance",
    }
    assert c["candidate_kind"] in m.CANDIDATE_KINDS


def test_gate_blocks_without_recovery(m):
    summary = {
        "metrics": {
            "associated_gold_preserved": 8,
            "rnd_recovered_among_visible_miss": 2,
            "short_stroke_recovered": 1,
            "giant_member_candidates_after_total": 0,
            "giant_nearby_before_total": 5,
        },
        "leader_metrics": {
            "leader_required_n": 18,
            "target_memberlike_or_recoverable": 2,
        },
        "provenance_complete": True,
    }
    assert m.decide_gate(summary) == "REPRESENTATION_STILL_NOT_READY"


def test_gate_ready_when_thresholds_met(m):
    summary = {
        "metrics": {
            "associated_gold_preserved": 8,
            "rnd_recovered_among_visible_miss": 25,
            "short_stroke_recovered": 10,
            "giant_member_candidates_after_total": 3,
            "giant_nearby_before_total": 10,
        },
        "leader_metrics": {
            "leader_required_n": 18,
            "target_memberlike_or_recoverable": 9,
        },
        "provenance_complete": True,
    }
    assert m.decide_gate(summary) == "REPRESENTATION_READY_FOR_ASSOCIATION"


def test_script_does_not_modify_production_files():
    before_ex = EXTRACTOR.read_bytes()
    before_r = RETRIEVAL.read_bytes() if RETRIEVAL.exists() else None
    before_r2 = RETRIEVAL_V2.read_bytes() if RETRIEVAL_V2.exists() else None
    before_gold = GOLD.read_bytes()
    _load_mod()
    assert EXTRACTOR.read_bytes() == before_ex
    assert GOLD.read_bytes() == before_gold
    if before_r is not None:
        assert RETRIEVAL.read_bytes() == before_r
    if before_r2 is not None:
        assert RETRIEVAL_V2.read_bytes() == before_r2


def test_loss_classes_defined(m):
    assert "CAP_DROPPED" in m.LOSS_CLASSES
    assert "RECLASSIFIED_DIMENSION" in m.LOSS_CLASSES
    assert "RETAINED_MEMBER" in m.LOSS_CLASSES
