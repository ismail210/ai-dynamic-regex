"""Isolated tests for E5.1 ownership evidence audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "ownership_evidence_audit_e5_1.py"
E5_RESULTS = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "dimension_holdout_e5_results.jsonl"
)
RESULTS = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "ownership_evidence_e5_1_results.jsonl"
)
SUMMARY = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "ownership_evidence_e5_1_summary.json"
)
REPORT = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "GEOMETRY_OWNERSHIP_E5_1_REPORT.md"
)
GOLD = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_outcomes.jsonl"
)
EXTRACTOR = ROOT / "services" / "engineering" / "geometry_extractor.py"
E3_RESULTS = ROOT / "scripts" / "rd_geometry_integration" / "dimension_shadow_results.jsonl"
E4_RESULTS = ROOT / "scripts" / "rd_geometry_integration" / "dimension_control_results.jsonl"

EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
EXPECTED_E5_SHA = (
    "66d4d96f59014a7f0fd5e5f8483a504123203d76b2fc0d9d098bfae2d4fe7c15"
)


def _load():
    spec = importlib.util.spec_from_file_location("ownership_evidence_audit_e5_1", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows():
    return [json.loads(line) for line in RESULTS.read_text().splitlines() if line.strip()]


def test_artifacts_exist():
    assert SCRIPT.exists()
    assert RESULTS.exists()
    assert SUMMARY.exists()
    assert REPORT.exists()


def test_audits_exactly_e5_unestablished_token_ids(m):
    e5 = [
        json.loads(line)
        for line in E5_RESULTS.read_text().splitlines()
        if line.strip()
    ]
    expected = sorted(
        r["token_id"] for r in e5 if r.get("bucket") == "OWNERSHIP_UNESTABLISHED"
    )
    assert len(expected) == 33
    got = sorted(r["token_id"] for r in _rows())
    assert got == expected


def test_e5_artifacts_immutable():
    assert _sha(E5_RESULTS) == EXPECTED_E5_SHA
    summary = json.loads(SUMMARY.read_text())
    assert summary["regression"]["e5_results_sha"] == EXPECTED_E5_SHA


def test_no_proximity_only_ownership_proof(m):
    """BBox proximity alone must not mark machine ownership provable."""
    rows = _rows()
    for r in rows:
        if r.get("machine_ownership_provable"):
            # Must have same_text_span or (same_line + adjacent + containment)
            ev = r["evidence"]
            assert ev["same_text_span"]["positive"] or (
                ev["same_pdf_block_line"]["positive"]
                and ev["word_adjacency"]["positive"]
                and ev["bbox_containment"]["positive"]
            )


def test_category_partition_covers_all_33(m):
    rows = _rows()
    assert len(rows) == 33
    cats = {r["primary_category"] for r in rows}
    allowed = {
        m.CAT_PROVABLE,
        m.CAT_NOT_PROVABLE,
        m.CAT_UNRELATED,
        m.CAT_SPLIT,
        m.CAT_REP_GAP,
        m.CAT_OTHER,
    }
    assert cats <= allowed
    summary = json.loads(SUMMARY.read_text())
    assert sum(summary["category_counts"].values()) == 33


def test_unrelated_majority_and_zero_representation_gap(m):
    summary = json.loads(SUMMARY.read_text())
    assert summary["category_counts"].get(m.CAT_UNRELATED, 0) >= 25
    assert summary["category_counts"].get(m.CAT_REP_GAP, 0) == 0
    assert summary["metrics"]["visual_yes_machine_no_n"] == 0


def test_counterexamples_safe(m):
    cx = m.counterexample_shadow_tests()
    assert cx["w30x90_17k_not_stripped"] is True
    assert cx["genuine_7_8_preserved"] is True
    assert cx["mixed_23_10_preserved"] is True
    assert cx["own_label_w21x44_stripped"] is True


def test_ownership_gate_explicit():
    summary = json.loads(SUMMARY.read_text())
    gate = summary["ownership_gate"]["gate"]
    assert gate in {"READY_FOR_IMPLEMENTATION", "NOT_READY", "REPRESENTATION_GAP"}
    assert gate in REPORT.read_text()


def test_immutability_gold_extractor_e3_e4():
    summary = json.loads(SUMMARY.read_text())
    assert _sha(GOLD) == EXPECTED_GOLD_SHA
    # E3/E5 result artifacts remain frozen. geometry_extractor.py is allowed
    # to change after OWNERSHIP_GATE = READY_FOR_IMPLEMENTATION. E4 results may
    # be rewritten by E4's repeated-execution subprocess after that fix; pin E5.
    assert _sha(E3_RESULTS) == summary["regression"]["e3_sha"]
    assert E4_RESULTS.exists()
    assert summary["regression"]["e4_sha"]
    assert _sha(E5_RESULTS) == EXPECTED_E5_SHA


def test_contract_rejects_proximity_only(m):
    contract = m.ownership_contract()
    joined = " ".join(contract["explicit_non_signals"]).lower()
    assert "proximity" in joined or "nearest" in joined
    assert any("own" in x.lower() or "designation" in x.lower() for x in contract["OWNERSHIP_PROVEN_if"])
