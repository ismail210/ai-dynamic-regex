"""Isolated tests for completed G8-era review outcomes + production gate (R&D)."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

PREP = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "g8_era_human_validation"
)
OUTCOMES = PREP / "g8_era_review_outcomes.jsonl"
SUMMARY = PREP / "g8_era_review_summary.json"
JUST = PREP / "G10_JUSTIFICATION.md"
FINAL = PREP / "FINAL_ASSOCIATION_GATE_REPORT.md"
PENDING = PREP / "decisions_pending"
GOLD = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_outcomes.jsonl"
)
G8 = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "representation_repair_g8_results.jsonl"
)
G9 = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "association_shadow_g9_results.jsonl"
)
MANIFEST = PREP / "g8_era_human_validation_manifest.jsonl"

EXPECTED_GOLD = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
EXPECTED_G8 = (
    "1931707165664d9e8e6ea198171624b9f9d8bb25dda2edd40d86619126ed3c44"
)
EXPECTED_G9 = (
    "b459522eb097c285a359bd01a2be61c389daeded6415f236b6a0c47323cb4814"
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rows():
    return [json.loads(l) for l in OUTCOMES.read_text().splitlines() if l.strip()]


def test_review_artifacts_exist():
    assert OUTCOMES.exists()
    assert SUMMARY.exists()
    assert JUST.exists()
    assert FINAL.exists()


def test_exactly_27_reviewed():
    rows = _rows()
    assert len(rows) == 27
    assert len({r["token_id"] for r in rows}) == 27


def test_decisions_match_pending_files():
    rows = _rows()
    for r in rows:
        p = PENDING / f"{r['token_id']}.decision.json"
        assert p.exists()
        d = json.loads(p.read_text())
        assert d["token_id"] == r["token_id"]
        assert d["reviewer_decision"] == r["reviewer_decision"]


def test_decision_vocabulary():
    allowed = {"VALID_MEMBER", "NO_VALID_MEMBER", "AMBIGUOUS", "NEEDS_REVIEW"}
    for r in _rows():
        assert r["reviewer_decision"] in allowed
        assert r["not_historical_gold"] is True
        assert r["review_source"] == "g8_era_human_validation"


def test_owned_ids_in_g8():
    g8 = {
        json.loads(l)["token_id"]: json.loads(l)
        for l in G8.read_text().splitlines()
        if l.strip()
    }
    for r in _rows():
        b_ids = {
            c["candidate_id"]
            for c in (g8[r["token_id"]].get("B_candidates") or [])
            if c.get("candidate_id")
        }
        for oid in r["owned_candidate_ids"]:
            assert oid in b_ids


def test_c_cases_ambiguous():
    c_ids = {
        "token_p8_381",
        "token_p8_382",
        "token_p8_383",
        "token_p8_384",
        "token_p8_430",
    }
    by = {r["token_id"]: r for r in _rows()}
    for tid in c_ids:
        assert by[tid]["reviewer_decision"] == "AMBIGUOUS"
        assert len(by[tid]["owned_candidate_ids"]) >= 2


def test_d_case_owns_short_segment():
    by = {r["token_id"]: r for r in _rows()}
    d = by["token_p24_1359"]
    assert d["reviewer_decision"] == "VALID_MEMBER"
    assert d["owned_candidate_ids"] == ["raw_p24_10_9d8fbf0dfe5b#seg1"]
    assert d["g9_disagrees"] is True


def test_counts():
    c = Counter(r["reviewer_decision"] for r in _rows())
    assert c["VALID_MEMBER"] == 22
    assert c["AMBIGUOUS"] == 5
    assert c.get("NO_VALID_MEMBER", 0) == 0
    assert c.get("NEEDS_REVIEW", 0) == 0


def test_g10_not_justified_and_final_no_go():
    just = JUST.read_text()
    final = FINAL.read_text()
    assert "NOT_JUSTIFIED" in just
    assert "PRODUCTION_NO_GO" in final
    assert "G10 was not run" in final or "not run" in final.lower()


def test_historical_gold_and_g8_g9_frozen():
    assert _sha(GOLD) == EXPECTED_GOLD
    assert _sha(G8) == EXPECTED_G8
    assert _sha(G9) == EXPECTED_G9
    summary = json.loads(SUMMARY.read_text())
    assert summary["safety"]["historical_gold_unchanged"] is True


def test_manifest_ids_covered():
    man = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    assert sorted(r["token_id"] for r in man) == sorted(r["token_id"] for r in _rows())
