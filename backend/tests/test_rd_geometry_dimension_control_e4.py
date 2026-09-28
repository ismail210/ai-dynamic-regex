"""Isolated tests for E4 genuine-dimension control expansion + V1 false-flip diagnostic."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "dimension_control_expansion.py"
E3_SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "dimension_shadow_experiment.py"
CONTROL_SET = ROOT / "scripts" / "rd_geometry_integration" / "dimension_control_set.jsonl"
RESULTS = ROOT / "scripts" / "rd_geometry_integration" / "dimension_control_results.jsonl"
SUMMARY = ROOT / "scripts" / "rd_geometry_integration" / "dimension_control_summary.json"
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
E3_RESULTS = ROOT / "scripts" / "rd_geometry_integration" / "dimension_shadow_results.jsonl"
EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)

E3_OWN = ("token_p8_332", "token_p8_337", "token_p8_381", "token_p8_430")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def e4():
    return _load(SCRIPT, "dimension_control_expansion")


@pytest.fixture(scope="module")
def e3():
    return _load(E3_SCRIPT, "dimension_shadow_experiment")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_control_records_deterministic(e4):
    """nearby_text_evidence_kind is stable for known patterns."""
    assert e4.nearby_text_evidence_kind("7/8") == "fraction"
    assert e4.nearby_text_evidence_kind("23' - 10\"") == "length"
    assert e4.nearby_text_evidence_kind('1"') == "inch"
    assert e4.nearby_text_evidence_kind("17K") is None
    assert e4.nearby_text_evidence_kind("W14X22  [23]") is None
    assert e4.nearby_text_evidence_kind("L4X4X1/4 TYP") is None
    assert e4.nearby_text_evidence_kind("1/8\" = 1'-0\"") is None


def test_e3_own_label_cases_remain_recoverable():
    rows = {r.get("token_id"): r for r in _load_jsonl(RESULTS) if r.get("token_id")}
    for tid in E3_OWN:
        r = rows[tid]
        assert r["baseline_is_dimension"] is True
        assert r["v1_is_dimension"] is False
        assert r["v1_member_eligible"] is True
        assert r["change_type"] == "DIMENSION_TO_MEMBER"
        assert r["safety_attribution"] == "SAFE_OWN_LABEL_REMOVAL"


def test_w30x90_17k_remains_unrelated():
    rows = {r.get("token_id"): r for r in _load_jsonl(RESULTS) if r.get("token_id")}
    r = rows["token_p8_348"]
    assert r["control_status"] == "unrelated_numeric"
    assert r["trigger_text"] == "17K"
    assert r["baseline_is_dimension"] is True
    assert r["v1_is_dimension"] is True
    assert r["v1_member_eligible"] is False
    assert r.get("removed_by_v1") is None


def test_genuine_7_8_remains_dimension():
    rows = {r.get("token_id"): r for r in _load_jsonl(RESULTS) if r.get("token_id")}
    r = rows["token_p18_1143"]
    assert r["control_status"] == "genuine_dimension"
    assert r["trigger_text"] == "7/8"
    assert r["baseline_is_dimension"] is True
    assert r["v1_is_dimension"] is True


def test_own_label_numeric_excluded_by_v1(e3):
    from services.engineering.models import GeometryKind

    own = [
        {
            "page_number": 8,
            "text": "W21X44  [30]",
            "bbox": [100.0, 100.0, 180.0, 130.0],
            "center": [140.0, 115.0],
        }
    ]
    v1 = e3.classify_shadow_ignore_own_numbers(
        base_kind=GeometryKind.LINE,
        length=100.0,
        bbox=[0.0, 0.0, 100.0, 2.0],
        nearby_text="W21X44  [30]",
        nearby_line=own[0],
        own_label_lines=own,
    )
    assert v1["removed_trigger_text"] == "W21X44  [30]"
    assert v1["is_dimension"] is False
    assert v1["member_eligible"] is True


def test_genuine_dimension_text_not_excluded_merely_because_nearby(e3):
    from services.engineering.models import GeometryKind

    own = [
        {
            "page_number": 8,
            "text": "W14X22  [23]",
            "bbox": [100.0, 100.0, 180.0, 130.0],
            "center": [140.0, 115.0],
        }
    ]
    dim_line = {
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
        nearby_line=dim_line,
        own_label_lines=own,
    )
    assert v1["removed_trigger_text"] is None
    assert v1["is_dimension"] is True
    assert v1["member_eligible"] is False


def test_insufficient_evidence_not_counted_as_genuine():
    controls = _load_jsonl(CONTROL_SET)
    results = _load_jsonl(RESULTS)
    insuff = [c for c in controls if c["control_status"] == "insufficient_evidence"]
    genuine_ids = {
        r["control_id"] for r in results if r["control_status"] == "genuine_dimension"
    }
    # Insufficient rows are optional after post-own-label E4 re-runs; when present
    # they must never be counted as genuine.
    for c in insuff:
        assert c["control_id"] not in genuine_ids
    summary = json.loads(SUMMARY.read_text())
    assert summary["metrics"]["insufficient_n"] == len(
        [r for r in results if r["control_status"] == "insufficient_evidence"]
    )
    assert summary["metrics"]["genuine_dimension_n"] == len(genuine_ids)
    assert len(genuine_ids) >= 1


def test_no_production_files_modified_and_gold_immutable():
    assert _sha(GOLD) == EXPECTED_GOLD_SHA
    summary = json.loads(SUMMARY.read_text())
    assert summary["gold_sha"] == EXPECTED_GOLD_SHA
    # Retrieval / E3 artifacts remain frozen; geometry_extractor.py may change
    # after the approved post-E5.1 production own-label fix.
    assert _sha(RETRIEVAL) == summary["retrieval_sha"]
    assert _sha(RETRIEVAL_V2) == summary["retrieval_v2_sha"]
    assert _sha(E3_RESULTS) == summary["e3_results_sha"]
    assert EXTRACTOR.exists()
    assert "services/engineering/geometry_extractor.py" in str(EXTRACTOR)


def test_e4_control_set_does_not_mutate_human_gold():
    before = _sha(GOLD)
    controls = _load_jsonl(CONTROL_SET)
    assert controls, "control set must exist"
    assert before == EXPECTED_GOLD_SHA
    assert _sha(GOLD) == before
    for c in controls:
        assert "human_gold_rewrite" not in c
        assert c.get("source") != "human_gold_mutation"


@pytest.mark.skip(
    reason=(
        "Rewrites E4 control/results in-place via subprocess; exclude from default "
        "cross-phase suites. Run explicitly when regenerating E4 artifacts."
    )
)
def test_repeated_execution_identical_results():
    """Two consecutive runs produce identical control-set + results digests."""
    py = ROOT / "venv" / "bin" / "python"
    if not py.exists():
        py = Path(sys.executable)
    env_cmd = [str(py), str(SCRIPT)]
    r1 = subprocess.run(env_cmd, cwd=str(ROOT), capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    set1 = _sha(CONTROL_SET)
    res1 = _sha(RESULTS)
    sum1 = json.loads(SUMMARY.read_text())
    r2 = subprocess.run(env_cmd, cwd=str(ROOT), capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert _sha(CONTROL_SET) == set1
    assert _sha(RESULTS) == res1
    sum2 = json.loads(SUMMARY.read_text())
    assert sum2["metrics"] == sum1["metrics"]
    assert sum2["e3_regression"] == sum1["e3_regression"]
    assert _sha(GOLD) == EXPECTED_GOLD_SHA
