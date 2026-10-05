"""Isolated tests for E5 multi-document own-label digit-stripping holdout."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "multi_document_dimension_holdout.py"
E3_RESULTS = ROOT / "scripts" / "rd_geometry_integration" / "dimension_shadow_results.jsonl"
E4_RESULTS = ROOT / "scripts" / "rd_geometry_integration" / "dimension_control_results.jsonl"
GOLD = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_outcomes.jsonl"
)
EXTRACTOR = ROOT / "services" / "engineering" / "geometry_extractor.py"
RESULTS = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "dimension_holdout_e5_results.jsonl"
)
SUMMARY = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "dimension_holdout_e5_summary.json"
)
REPORT = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "GEOMETRY_DIMENSION_HOLDOUT_E5_REPORT.md"
)
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
EXPECTED_EXTRACTOR_SHA = (
    "6c6f73d7090a427705599a24cba4bad167a531a70cc5ff6879ccd0ca809ec940"
)
EXPECTED_E3_SHA = (
    "bc633040e9c5624d3147d937e93d536be3a5ee510ed95bf85d0c6af8a3020568"
)


def _load():
    spec = importlib.util.spec_from_file_location("multi_document_dimension_holdout", SCRIPT)
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
    return [json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_artifacts_exist():
    assert SCRIPT.exists()
    assert RESULTS.exists()
    assert SUMMARY.exists()
    assert REPORT.exists()


def test_holdout_documents_independent_of_burrville(m):
    assert len(m.HOLDOUT_DOCS) >= 3
    for d in m.HOLDOUT_DOCS:
        assert d["independent_of_burrville"] is True
        assert "burrville" not in d["doc_key"].lower()
        assert d["pdf"].parent.name == "uploads"
        assert len(d["pages"]) >= 1


def test_holdout_pdfs_present_for_a_rerun(m):
    # The holdout inputs are client drawing sets in the git-ignored uploads/
    # folder, not repository fixtures; re-running E5 needs them locally.
    missing = [d["pdf"].name for d in m.HOLDOUT_DOCS if not d["pdf"].exists()]
    if missing:
        pytest.skip(f"E5 holdout PDFs not in backend/uploads on this machine: {', '.join(missing)}")
    assert not missing


def test_v1_only_strips_when_ownership_established(m):
    e3 = m._load_e3()
    from services.engineering.models import GeometryKind

    own = [
        {
            "page_number": 7,
            "text": "W16X36  [22]",
            "bbox": [100.0, 100.0, 180.0, 130.0],
            "center": [140.0, 115.0],
        }
    ]
    # Owned nearby → strip
    v1 = e3.classify_shadow_ignore_own_numbers(
        base_kind=GeometryKind.LINE,
        length=100.0,
        bbox=[0.0, 0.0, 100.0, 2.0],
        nearby_text="W16X36  [22]",
        nearby_line=own[0],
        own_label_lines=own,
    )
    assert v1["removed_trigger_text"] == "W16X36  [22]"
    assert v1["member_eligible"] is True
    # Unrelated load → no strip
    load = {
        "page_number": 7,
        "text": "17K",
        "bbox": [200.0, 200.0, 220.0, 220.0],
        "center": [210.0, 210.0],
    }
    v1b = e3.classify_shadow_ignore_own_numbers(
        base_kind=GeometryKind.LINE,
        length=100.0,
        bbox=[0.0, 0.0, 100.0, 2.0],
        nearby_text="17K",
        nearby_line=load,
        own_label_lines=own,
    )
    assert v1b["removed_trigger_text"] is None
    assert v1b["is_dimension"] is True


def test_genuine_dimension_not_stripped_when_not_own_label(m):
    e3 = m._load_e3()
    from services.engineering.models import GeometryKind

    own = [
        {
            "page_number": 8,
            "text": "W14X22  [23]",
            "bbox": [100.0, 100.0, 180.0, 130.0],
            "center": [140.0, 115.0],
        }
    ]
    dim = {
        "page_number": 8,
        "text": "23' - 10\"",
        "bbox": [200.0, 200.0, 260.0, 220.0],
        "center": [230.0, 210.0],
    }
    v1 = e3.classify_shadow_ignore_own_numbers(
        base_kind=GeometryKind.LINE,
        length=120.0,
        bbox=[180.0, 180.0, 280.0, 240.0],
        nearby_text="23' - 10\"",
        nearby_line=dim,
        own_label_lines=own,
    )
    assert v1["removed_trigger_text"] is None
    assert v1["is_dimension"] is True


def test_e5_results_have_zero_dangerous_false_flips():
    rows = _rows()
    assert rows
    dangerous = [r for r in rows if r.get("dangerous")]
    assert dangerous == []
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["metrics"]["false_flip_n"] == 0


def test_e5_recovers_own_label_across_multiple_docs():
    rows = _rows()
    own = [r for r in rows if r["bucket"] == "OWN_LABEL_CONTAMINATION"]
    recovered = [r for r in own if r["outcome"] == "MEMBER_RECOVERED"]
    assert len(own) >= 6
    assert len(recovered) >= 6
    docs = {r["doc_key"] for r in recovered}
    assert len(docs) >= 2


def test_e5_preserves_genuine_and_unrelated_controls():
    rows = _rows()
    genuine = [r for r in rows if r["bucket"] in {"GENUINE_DIMENSION", "MIXED_MEMBER_DIMENSION"}]
    assert len(genuine) >= 5
    assert all(r.get("v1_is_dimension") for r in genuine if r.get("baseline_is_dimension"))
    unr = [r for r in rows if r["bucket"] == "UNRELATED_NUMERIC"]
    assert len(unr) >= 1
    assert all(r.get("removed_by_v1") is None for r in unr)


def test_e3_e4_regression_and_immutability(m):
    reg = m.verify_e3_e4_regression()
    # Artifact + behavioral regression must pass; extractor may differ after
    # the approved production own-label digit fix landed post-E5.1.
    assert reg["gold_sha_ok"] is True
    assert reg["e3_results_sha_ok"] is True
    assert reg["e3_own_label_recovery_ok"] is True
    assert reg["e3_unrelated_17k_ok"] is True
    assert reg["e3_genuine_7_8_ok"] is True
    assert reg["e4_preserved_ok"] is True
    assert _sha(GOLD) == EXPECTED_GOLD_SHA
    assert _sha(E3_RESULTS) == EXPECTED_E3_SHA
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    # E4 results jsonl may be rewritten by E4's own repeated-execution test when
    # the suite re-runs dimension_control_expansion after the production own-label
    # fix; behavioral preservation above is the gate, not the frozen SHA pin.
    assert E4_RESULTS.exists()
    assert _sha(GOLD) == summary["regression"]["gold_sha"]
    assert summary["regression"]["e4_results_sha"]

def test_implementation_gate_is_explicit():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    gate = summary["implementation_gate"]["gate"]
    assert gate in {"IMPLEMENT", "DO_NOT_IMPLEMENT", "NEED_MORE_EVIDENCE"}
    report = REPORT.read_text(encoding="utf-8")
    assert gate in report
    assert "Executive Verdict" in report or "# Executive Verdict" in report


def test_decide_gate_false_flip_blocks_implement(m):
    metrics = {
        "total_documents": 3,
        "own_label_contamination_n": 20,
        "genuine_dimension_n": 12,
        "mixed_n": 5,
        "false_flip_n": 1,
        "member_recovery_n": 18,
        "genuine_preserved_n": 12,
        "ownership_unestablished_n": 2,
        "own_label_recovery_rate": 0.9,
        "genuine_preservation_rate": 1.0,
    }
    reg = {"pass": True}
    gate = m.decide_gate(metrics, reg)
    assert gate["gate"] == "DO_NOT_IMPLEMENT"


def test_decide_gate_high_unestablished_needs_more_evidence(m):
    metrics = {
        "total_documents": 3,
        "own_label_contamination_n": 20,
        "genuine_dimension_n": 12,
        "mixed_n": 5,
        "false_flip_n": 0,
        "member_recovery_n": 18,
        "genuine_preserved_n": 17,
        "ownership_unestablished_n": 40,
        "own_label_recovery_rate": 0.9,
        "genuine_preservation_rate": 1.0,
    }
    gate = m.decide_gate(metrics, {"pass": True})
    assert gate["gate"] == "NEED_MORE_EVIDENCE"


def test_changed_cases_have_renders_when_present():
    rows = _rows()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    if summary.get("renders_written", 0) == 0:
        pytest.skip("renders not generated in this artifact set")
    changed = [r for r in rows if r.get("changed")]
    assert changed
    for r in changed:
        assert r.get("render_file"), f"missing render for changed case {r['token_id']}"
