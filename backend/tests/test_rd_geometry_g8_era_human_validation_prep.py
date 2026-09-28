"""Isolated tests for G8-era human validation PREPARATION (R&D only)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "g8_era_human_validation_prep.py"
PREP = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "g8_era_human_validation"
)
MANIFEST = PREP / "g8_era_human_validation_manifest.jsonl"
SCHEMA = PREP / "g8_era_human_validation_schema.json"
SUMMARY = PREP / "g8_era_human_validation_summary.json"
PLAN = PREP / "G8_ERA_HUMAN_VALIDATION_PLAN.md"
REVIEW = PREP / "review.html"
GOLD = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_outcomes.jsonl"
)
GOLD_METRICS = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_metrics.json"
)
G8 = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "representation_repair_g8_results.jsonl"
)
G9 = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "association_shadow_g9_results.jsonl"
)
AUDIT = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "g9_false_association_audit"
    / "g9_false_association_audit.jsonl"
)

EXPECTED_GOLD = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
EXPECTED_G8 = (
    "1931707165664d9e8e6ea198171624b9f9d8bb25dda2edd40d86619126ed3c44"
)
EXPECTED_G9 = (
    "b459522eb097c285a359bd01a2be61c389daeded6415f236b6a0c47323cb4814"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load():
    spec = importlib.util.spec_from_file_location("g8_era_human_validation_prep", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load()


@pytest.fixture(scope="module")
def rows():
    assert MANIFEST.exists(), "Run g8_era_human_validation_prep.py first"
    return [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]


@pytest.fixture(scope="module")
def summary():
    return json.loads(SUMMARY.read_text())


def test_artifacts_exist():
    assert SCRIPT.exists()
    assert MANIFEST.exists()
    assert SCHEMA.exists()
    assert SUMMARY.exists()
    assert PLAN.exists()
    assert REVIEW.exists()


def test_exactly_27_cases(rows, summary):
    assert len(rows) == 27
    assert summary["counts"]["total"] == 27


def test_b_c_d_counts_exact(rows, summary):
    c = Counter(r["audit_classification"] for r in rows)
    assert c["B"] == 21
    assert c["C"] == 5
    assert c["D"] == 1
    assert summary["counts"]["B"] == 21
    assert summary["counts"]["C"] == 5
    assert summary["counts"]["D"] == 1


def test_no_duplicate_token_ids(rows):
    ids = [r["token_id"] for r in rows]
    assert len(ids) == len(set(ids)) == 27


def test_matches_audit_bcd_set(rows):
    audit = [json.loads(l) for l in AUDIT.read_text().splitlines() if l.strip()]
    expected = sorted(
        r["token_id"] for r in audit if r.get("classification") in {"B", "C", "D"}
    )
    assert sorted(r["token_id"] for r in rows) == expected


def test_all_g8_candidate_ids_exist(rows):
    g8 = {
        json.loads(l)["token_id"]: json.loads(l)
        for l in G8.read_text().splitlines()
        if l.strip()
    }
    for r in rows:
        b_ids = {
            c["candidate_id"]
            for c in (g8[r["token_id"]].get("B_candidates") or [])
            if c.get("candidate_id")
        }
        assert set(r["g8_candidate_ids"]) <= b_ids
        assert r["g9_selected_candidate_id"] in b_ids


def test_c_cases_list_competitors(rows):
    for r in rows:
        if r["audit_classification"] != "C":
            continue
        assert r["review_priority"] == "HIGH"
        assert len(r.get("competing_candidates") or []) >= 2


def test_d_case_reference(rows):
    d = [r for r in rows if r["audit_classification"] == "D"]
    assert len(d) == 1
    assert d[0]["token_id"] == "token_p24_1359"
    assert d[0]["review_priority"] == "HIGH"
    ref = d[0]["d_case_reference"]
    assert ref["g9_selected_id"] == "rnd_raw_p24_480_d0c0ca5e54d7"
    assert ref["audit_best_candidate_id"] == "raw_p24_10_9d8fbf0dfe5b#seg1"


def test_decisions_still_pending(rows):
    for r in rows:
        assert r["review_status"] == "PENDING"
        assert r["reviewer_decision"] is None
        assert r["owned_candidate_ids"] == []


def test_historical_gold_and_frozen_inputs_unchanged(summary):
    assert _sha(GOLD) == EXPECTED_GOLD
    assert _sha(G8) == EXPECTED_G8
    assert _sha(G9) == EXPECTED_G9
    assert summary["frozen_inputs"]["gold_sha"] == EXPECTED_GOLD
    assert summary["frozen_inputs"]["g8_sha"] == EXPECTED_G8
    assert summary["frozen_inputs"]["g9_sha"] == EXPECTED_G9
    assert summary["frozen_inputs"]["audit_sha"] == _sha(AUDIT)
    if GOLD_METRICS.exists():
        assert summary["frozen_inputs"]["gold_metrics_sha"] == _sha(GOLD_METRICS)


def test_no_new_gold_file_created():
    # Preparation must not create a fake production gold in this folder
    assert not (PREP / "gold_outcomes.jsonl").exists()
    assert not (PREP / "gold_metrics.json").exists()


def test_schema_has_required_decisions():
    schema = json.loads(SCHEMA.read_text())
    vocab = schema["decision_vocabulary"]
    assert set(vocab) >= {"VALID_MEMBER", "NO_VALID_MEMBER", "AMBIGUOUS", "NEEDS_REVIEW"}
    assert schema["not_production_gold"] is True
    assert schema["historical_gold_immutable"] is True
    assert "distance_alone" in schema["explicit_non_signals"]


def test_priority_rules(rows, m):
    for r in rows:
        assert r["review_priority"] == m.review_priority(
            r["audit_classification"], r["audit_confidence"]
        )


def test_gate_complete(summary):
    assert summary["g8_era_human_validation_preparation"] == "COMPLETE"
    assert summary["validation"]["ok"] is True
    assert summary["safety"]["no_new_gold_created"] is True
    assert "COMPLETE" in PLAN.read_text()


def test_deterministic_manifest_order(rows, m):
    # Recompute priorities; order must be HIGH→MEDIUM→NORMAL then page/token
    priorities = [r["review_priority"] for r in rows]
    ranks = [m.priority_rank(p) for p in priorities]
    assert ranks == sorted(ranks)
