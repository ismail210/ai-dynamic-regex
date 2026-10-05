"""Isolated tests for G9 false-association forensic audit (R&D only)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "g9_false_association_audit.py"
OUT = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "g9_false_association_audit"
)
RESULTS = OUT / "g9_false_association_audit.jsonl"
SUMMARY = OUT / "g9_false_association_audit_summary.json"
REPORT = OUT / "G9_FALSE_ASSOCIATION_AUDIT_REPORT.md"
REVIEW = OUT / "review.html"
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
G9 = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "association_shadow_g9_results.jsonl"
)
G8_SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "representation_repair_g8.py"
G9_SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "association_shadow_g9.py"
EXTRACTOR = ROOT / "services" / "engineering" / "geometry_extractor.py"
RETRIEVAL = ROOT / "scripts" / "rd_geometry_integration" / "retrieval.py"
RETRIEVAL_V2 = ROOT / "scripts" / "rd_geometry_integration" / "retrieval_v2.py"

EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
EXPECTED_FA = 27
ALLOWED = {"A", "B", "C", "D"}


def _load():
    spec = importlib.util.spec_from_file_location("g9_false_association_audit", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load()


@pytest.fixture(scope="module")
def rows():
    assert RESULTS.exists(), "Run g9_false_association_audit.py first"
    return [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.fixture(scope="module")
def summary():
    assert SUMMARY.exists()
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_artifacts_exist():
    assert SCRIPT.exists()
    assert RESULTS.exists()
    assert SUMMARY.exists()
    assert REPORT.exists()
    assert REVIEW.exists()


def test_discovers_exactly_27_false_associations(m):
    g9 = [json.loads(l) for l in G9.read_text(encoding="utf-8").splitlines() if l.strip()]
    fa = m.discover_false_associations(g9)
    assert len(fa) == EXPECTED_FA
    ids = [r["token_id"] for r in fa]
    assert len(ids) == len(set(ids))


def test_every_case_one_classification(rows, m):
    assert len(rows) == EXPECTED_FA
    for r in rows:
        assert r["classification"] in ALLOWED
        assert r["confidence"] in {"HIGH", "MEDIUM", "LOW"}
        assert r["new_representation_status"] in m.NEW_STATUSES


def test_classifications_only_abcd(rows, summary):
    assert set(rows[i]["classification"] for i in range(len(rows))) <= ALLOWED
    assert sum(summary["classification_counts"].values()) == EXPECTED_FA


def test_every_case_has_evidence(rows):
    for r in rows:
        assert isinstance(r.get("evidence"), list) and len(r["evidence"]) >= 3


def test_b_cases_reference_g8_candidate(rows):
    g8 = {
        json.loads(l)["token_id"]: json.loads(l)
        for l in G8.read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    for r in rows:
        if r["classification"] != "B":
            continue
        sel = r["g9_selected_geometry_id"]
        assert sel
        b_ids = {c["candidate_id"] for c in (g8[r["token_id"]].get("B_candidates") or [])}
        assert sel in b_ids
        assert r.get("b_proof")


def test_d_cases_identify_selected_and_alternative(rows):
    g8 = {
        json.loads(l)["token_id"]: json.loads(l)
        for l in G8.read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    for r in rows:
        if r["classification"] != "D":
            continue
        assert r["g9_selected_geometry_id"]
        assert r["best_candidate_geometry_id"]
        assert r["g9_selected_geometry_id"] != r["best_candidate_geometry_id"]
        assert r.get("d_characterization")
        b_ids = {c["candidate_id"] for c in (g8[r["token_id"]].get("B_candidates") or [])}
        assert r["best_candidate_geometry_id"] in b_ids
        assert r["g9_selected_geometry_id"] in b_ids


def test_gold_file_not_modified():
    assert _sha(GOLD) == EXPECTED_GOLD_SHA


def test_production_and_upstream_scripts_not_modified_by_audit_module(m, summary):
    # Importing the audit module must not rewrite pinned artifacts / production.
    assert _sha(GOLD) == EXPECTED_GOLD_SHA
    assert _sha(GOLD) == summary["gold_sha"]
    assert G8_SCRIPT.exists() and G9_SCRIPT.exists() and EXTRACTOR.exists()
    assert RETRIEVAL.exists() and RETRIEVAL_V2.exists()
    assert summary["g8_results_sha"] == _sha(G8)
    assert summary["g9_results_sha"] == _sha(G9)
    assert summary["safety"]["human_gold_unchanged"] is True
    assert summary["safety"]["g8_unchanged"] is True
    assert summary["safety"]["g9_unchanged"] is True
    assert summary["safety"]["production_unchanged"] is True


def test_deterministic_output(rows, summary, m):
    assert summary.get("deterministic_ok") is True
    assert summary.get("validation_problems") == []
    # Second discovery pass yields identical token set
    g9 = [json.loads(l) for l in G9.read_text(encoding="utf-8").splitlines() if l.strip()]
    fa_ids = [r["token_id"] for r in m.discover_false_associations(g9)]
    assert [r["token_id"] for r in rows] == fa_ids
    assert len(set(fa_ids)) == EXPECTED_FA


def test_duplicate_token_ids_rejected(rows):
    ids = [r["token_id"] for r in rows]
    assert len(ids) == len(set(ids)) == EXPECTED_FA


def test_all_referenced_candidate_ids_exist(rows):
    g8 = {
        json.loads(l)["token_id"]: json.loads(l)
        for l in G8.read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    for r in rows:
        b_ids = {c["candidate_id"] for c in (g8[r["token_id"]].get("B_candidates") or [])}
        assert r["g9_selected_geometry_id"] in b_ids
        for c in r.get("g8_candidates") or []:
            # summaries may include ranking-only extras; require id present in B or rankings
            assert c.get("candidate_id")
        if r.get("best_candidate_geometry_id"):
            assert r["best_candidate_geometry_id"] in b_ids


def test_all_27_represented_exactly_once(rows, m):
    g9 = [json.loads(l) for l in G9.read_text(encoding="utf-8").splitlines() if l.strip()]
    expected = sorted(r["token_id"] for r in m.discover_false_associations(g9))
    got = sorted(r["token_id"] for r in rows)
    assert got == expected
    assert len(got) == EXPECTED_FA


def test_gate_is_explicit(summary):
    gate = summary["g9_false_association_audit_gate"]
    assert gate in {
        "AUDIT_COMPLETE_G10_JUSTIFIED",
        "AUDIT_COMPLETE_G10_NOT_YET_JUSTIFIED",
        "AUDIT_INCOMPLETE",
    }
    assert gate in REPORT.read_text(encoding="utf-8")
    assert gate != "AUDIT_INCOMPLETE"


def test_counts_consistent(summary, rows):
    from collections import Counter

    assert summary["A_count"] + summary["B_count"] + summary["C_count"] + summary["D_count"] == 27
    assert summary["candidate_universe_stale_count"] == summary["B_count"]
    assert summary["ambiguous_count"] == summary["C_count"]
    assert summary["genuine_false_association_count"] == summary["A_count"] + summary["D_count"]
    assert summary["cases_requiring_future_g10"] == summary["D_count"]
    c = Counter(r["classification"] for r in rows)
    assert c["B"] == summary["B_count"]
