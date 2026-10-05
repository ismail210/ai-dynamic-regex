"""Isolated tests for G9 association shadow experiment (R&D only)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "association_shadow_g9.py"
GOLD = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_outcomes.jsonl"
)
G8 = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "representation_repair_g8_results.jsonl"
)
EXTRACTOR = ROOT / "services" / "engineering" / "geometry_extractor.py"
RETRIEVAL = ROOT / "scripts" / "rd_geometry_integration" / "retrieval.py"
RETRIEVAL_V2 = ROOT / "scripts" / "rd_geometry_integration" / "retrieval_v2.py"
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)


def _load_mod():
    spec = importlib.util.spec_from_file_location("association_shadow_g9", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load_mod()


def _cand(**kwargs):
    base = {
        "candidate_id": kwargs.get("candidate_id", "rnd_x"),
        "candidate_kind": kwargs.get("candidate_kind", "LINE_MEMBER_CANDIDATE"),
        "bbox": kwargs.get("bbox", [100.0, 100.0, 200.0, 104.0]),
        "length": kwargs.get("length", 100.0),
        "orientation": kwargs.get("orientation", 0.0),
        "derivation": kwargs.get("derivation", "cap_restore"),
        "source_type": kwargs.get("source_type", "raw_drawing"),
        "confidence_basis": kwargs.get("confidence_basis", "role=member_like"),
        "provenance": kwargs.get(
            "provenance",
            {
                "source_page": 8,
                "source_raw_id": "raw_1",
                "source_geometry_id": kwargs.get("source_geometry_id"),
                "derivation_type": "cap_restore",
                "original_bbox": kwargs.get("bbox", [100.0, 100.0, 200.0, 104.0]),
                "derived_bbox": kwargs.get("bbox", [100.0, 100.0, 200.0, 104.0]),
            },
        ),
    }
    return base


def test_gold_sha_frozen():
    assert hashlib.sha256(GOLD.read_bytes()).hexdigest() == EXPECTED_GOLD_SHA


def test_g8_results_exist_with_75():
    assert G8.exists()
    rows = [json.loads(l) for l in G8.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 75


def test_giant_excluded(m):
    ok, reason = m.hard_eligible(
        _cand(bbox=[0, 0, 900, 20], length=900, candidate_id="giant")
    )
    assert ok is False
    assert reason == "giant"


def test_non_member_excluded(m):
    ok, reason = m.hard_eligible(_cand(candidate_kind="NON_MEMBER"))
    assert ok is False
    assert reason == "excluded_kind"


def test_large_segment_excluded(m):
    ok, reason = m.hard_eligible(
        _cand(
            candidate_kind="SEGMENT_MEMBER_CANDIDATE",
            bbox=[0, 0, 450, 10],
            length=450,
            candidate_id="seg",
        )
    )
    assert ok is False
    assert reason == "large_segment"


def test_leader_tip_non_member_no_valid(m):
    ranked = m.rank_candidates(
        label_bbox=[100, 100, 140, 120],
        candidates=[_cand(bbox=[200, 200, 300, 204], length=100)],
        association_mode="leader",
        leader_tip=[210, 202],
    )
    d = m.decide(
        ranked,
        association_mode="leader",
        schedule=False,
        leader_status="TARGET_PRESENT_NON_MEMBER",
    )
    assert d["decision"] == "NO_VALID_MEMBER"
    assert "leader_tip_non_member" in d["reason_codes"]


def test_schedule_no_valid(m):
    d = m.decide([], association_mode="direct", schedule=True, leader_status=None)
    assert d["decision"] == "NO_VALID_MEMBER"


def test_ambiguous_when_margin_small(m):
    label = [100, 100, 140, 120]
    c1 = _cand(candidate_id="a", bbox=[100, 98, 180, 102], length=80, orientation=0)
    c2 = _cand(candidate_id="b", bbox=[102, 99, 182, 103], length=80, orientation=0)
    ranked = m.rank_candidates(
        label_bbox=label, candidates=[c1, c2], association_mode="direct", leader_tip=None
    )
    # Force near-tie
    if len(ranked) >= 2:
        ranked[0]["total_score"] = 0.70
        ranked[1]["total_score"] = 0.69
    d = m.decide(ranked, association_mode="direct", schedule=False, leader_status=None)
    assert d["decision"] == "AMBIGUOUS"


def test_weak_evidence_abstains(m):
    ranked = [
        {
            "candidate_id": "far",
            "total_score": 0.30,
            "distance_score": 0.1,
            "orientation_score": 0.5,
            "length_score": 0.5,
            "candidate_kind": "LINE_MEMBER_CANDIDATE",
        }
    ]
    d = m.decide(ranked, association_mode="direct", schedule=False, leader_status=None)
    assert d["decision"] == "ABSTAIN"


def test_score_components_deterministic(m):
    label = [100, 100, 140, 120]
    cand = _cand(bbox=[100, 98, 200, 102], length=100, orientation=0)
    a = m.score_components(
        label_bbox=label, cand=cand, association_mode="direct", leader_tip=None
    )
    b = m.score_components(
        label_bbox=label, cand=cand, association_mode="direct", leader_tip=None
    )
    assert a == b
    assert set(a.keys()) >= {
        "distance_score",
        "bbox_score",
        "orientation_score",
        "length_score",
        "candidate_kind_score",
        "leader_score",
        "provenance_score",
        "penalty",
        "total_score",
    }


def test_compound_segment_provenance_id(m):
    cand = _cand(
        candidate_id="raw_p8_1_abc#seg0",
        candidate_kind="SEGMENT_MEMBER_CANDIDATE",
        bbox=[100, 100, 160, 104],
        length=60,
        derivation="vertex_split",
        provenance={
            "source_page": 8,
            "source_raw_id": "raw_p8_1_abc",
            "source_geometry_id": None,
            "derivation_type": "vertex_split",
            "original_bbox": [50, 50, 400, 300],
            "derived_bbox": [100, 100, 160, 104],
            "segment_index": 0,
        },
    )
    ok, _ = m.hard_eligible(cand)
    assert ok is True
    assert "#seg" in cand["candidate_id"]


def test_matches_gold_mirror(m):
    cand = _cand(
        candidate_id="rnd_gold_geom_095898d74240",
        source_geometry_id="geom_095898d74240",
    )
    assert m.matches_gold(cand, "geom_095898d74240") is True


def test_no_semantic_identity_in_decision_payload(m):
    label = [100, 100, 140, 120]
    cand = _cand(bbox=[100, 98, 200, 102], length=100)
    ranked = m.rank_candidates(
        label_bbox=label, candidates=[cand], association_mode="direct", leader_tip=None
    )
    d = m.decide(ranked, association_mode="direct", schedule=False, leader_status=None)
    blob = json.dumps(d) + json.dumps(ranked)
    assert "W21X44" not in blob
    assert "beam" not in blob.lower()
    assert "column" not in blob.lower()


def test_multi_signal_prefers_aligned_near_candidate(m):
    """Nearest far-oriented wrong candidate loses to better-aligned nearby stroke."""
    label = [100, 100, 150, 118]
    wrong = _cand(
        candidate_id="wrong_near",
        bbox=[148, 90, 156, 200],  # close corner but vertical
        length=110,
        orientation=90.0,
        derivation="neighborhood",
    )
    right = _cand(
        candidate_id="right_member",
        bbox=[90, 96, 210, 100],  # along label
        length=120,
        orientation=0.0,
        derivation="reclass_restore",
        source_geometry_id="geom_right",
    )
    ranked = m.rank_candidates(
        label_bbox=label,
        candidates=[wrong, right],
        association_mode="direct",
        leader_tip=None,
    )
    assert ranked[0]["candidate_id"] == "right_member"


def test_production_files_untouched_by_import():
    before_ex = EXTRACTOR.read_bytes()
    before_gold = GOLD.read_bytes()
    before_r = RETRIEVAL.read_bytes() if RETRIEVAL.exists() else None
    before_r2 = RETRIEVAL_V2.read_bytes() if RETRIEVAL_V2.exists() else None
    _load_mod()
    assert EXTRACTOR.read_bytes() == before_ex
    assert GOLD.read_bytes() == before_gold
    if before_r is not None:
        assert RETRIEVAL.read_bytes() == before_r
    if before_r2 is not None:
        assert RETRIEVAL_V2.read_bytes() == before_r2


def test_gate_blocks_on_false_nvm(m):
    summary = {
        "metrics": {
            "giant_selected": 0,
            "non_member_selected": 0,
            "schedule_false_association": 0,
            "associated_gold_exact_match": 8,
            "recall_at_1": 1.0,
            "false_association_no_valid_member": 20,
            "leader_false_association": 0,
            "ambiguous_forced_association": 0,
        }
    }
    assert m.decide_gate(summary) == "ASSOCIATION_STILL_NOT_READY"
