"""Isolated tests for E3 dimension-shadow experiment helpers."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rd_geometry_integration" / "dimension_shadow_experiment.py"
GOLD = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "review_kit"
    / "gold_outcomes.jsonl"
)
E1 = (
    ROOT.parent
    / "docs"
    / "validation"
    / "rd_geometry_integration"
    / "cap_cost_results.jsonl"
)
EXTRACTOR = ROOT / "services" / "engineering" / "geometry_extractor.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("dimension_shadow_experiment", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load_mod()


def test_own_label_numeric_text_identified(m):
    label_bbox = [100.0, 100.0, 150.0, 120.0]
    lines = [
        {
            "page_number": 8,
            "text": "W21X44  [30]",
            "bbox": [100.0, 100.0, 180.0, 130.0],
            "center": [140.0, 115.0],
        },
        {
            "page_number": 8,
            "text": "17K",
            "bbox": [200.0, 200.0, 220.0, 220.0],
            "center": [210.0, 210.0],
        },
    ]
    own = m.identify_own_label_lines(
        lines, label_bbox=label_bbox, label_text="W21X44", page_number=8
    )
    texts = [o["text"] for o in own]
    assert "W21X44  [30]" in texts
    assert "17K" not in texts


def test_unrelated_nearby_numeric_not_own_label(m):
    label_bbox = [1427.21, 1171.46, 1468.02, 1202.41]
    lines = [
        {
            "page_number": 8,
            "text": "W30X90  [42]  c = 3/4\"",
            "bbox": [1427.21, 1171.46, 1522.85, 1234.01],
            "center": [1475.0, 1202.0],
        },
        {
            "page_number": 8,
            "text": "17K",
            "bbox": [1496.18, 1238.11, 1512.99, 1257.6],
            "center": [1504.59, 1247.86],
        },
    ]
    own = m.identify_own_label_lines(
        lines, label_bbox=label_bbox, label_text="W30X90", page_number=8
    )
    texts = [o["text"] for o in own]
    assert any("W30X90" in t for t in texts)
    assert "17K" not in texts


def test_genuine_nearby_dimension_remains_visible(m):
    from services.engineering.models import GeometryKind

    base = GeometryKind.LINE
    length = 100.0
    bbox = [0.0, 0.0, 100.0, 2.0]
    own = [
        {
            "page_number": 8,
            "text": "W10X33",
            "bbox": [0.0, 50.0, 40.0, 60.0],
            "center": [20.0, 55.0],
        }
    ]
    ranked = [
        (10.0, {"text": "7/8", "bbox": [80.0, 0.0, 95.0, 10.0], "center": [87.0, 5.0]}),
        (40.0, own[0]),
    ]
    # V1: production nearby is 7/8 (not own) → still dimension
    v1 = m.classify_shadow_ignore_own_numbers(
        base_kind=base,
        length=length,
        bbox=bbox,
        nearby_text="7/8",
        nearby_line=ranked[0][1],
        own_label_lines=own,
    )
    assert v1["is_dimension"] is True
    assert v1["member_eligible"] is False
    # V2: excludes own label, keeps 7/8
    v2 = m.classify_shadow_ignore_own_label(
        base_kind=base, length=length, bbox=bbox, nearby_ranked=ranked, own_label_lines=own
    )
    assert v2["is_dimension"] is True


def test_w30x90_17k_behavior(m):
    from services.engineering.models import GeometryKind

    own = [
        {
            "text": "W30X90  [42]  c = 3/4\"",
            "bbox": [1427.21, 1171.46, 1522.85, 1234.01],
            "center": [1475.0, 1202.0],
            "page_number": 8,
        }
    ]
    trigger = {
        "text": "17K",
        "bbox": [1496.18, 1238.11, 1512.99, 1257.6],
        "center": [1504.59, 1247.86],
        "page_number": 8,
    }
    base = GeometryKind.LINE
    length = 323.97
    bbox = [1359.6, 1146.48, 1640.16, 1308.48]
    v0 = m.classify_baseline(
        base_kind=base, length=length, bbox=bbox, nearby_text="17K"
    )
    assert v0["is_dimension"] is True
    v1 = m.classify_shadow_ignore_own_numbers(
        base_kind=base,
        length=length,
        bbox=bbox,
        nearby_text="17K",
        nearby_line=trigger,
        own_label_lines=own,
    )
    # 17K is NOT own-label → V1 does not recover
    assert v1["is_dimension"] is True
    assert v1["trigger_source"] == "unchanged_non_own_or_empty"
    ranked = [(20.9, trigger), (5.0, own[0])]
    v2 = m.classify_shadow_ignore_own_label(
        base_kind=base, length=length, bbox=bbox, nearby_ranked=ranked, own_label_lines=own
    )
    # nearest is 17K (non-own) even after excluding own → still dimension
    assert v2["is_dimension"] is True


def test_own_label_w21x44_case(m):
    from services.engineering.models import GeometryKind

    own_line = {
        "text": "W21X44  [30]",
        "bbox": [2050.0, 1220.0, 2120.0, 1260.0],
        "center": [2085.0, 1240.0],
        "page_number": 8,
    }
    base = GeometryKind.LINE
    length = 241.51
    bbox = [1982.0, 1209.0, 2215.0, 1271.0]
    v0 = m.classify_baseline(
        base_kind=base, length=length, bbox=bbox, nearby_text="W21X44  [30]"
    )
    assert v0["is_dimension"] is True
    v1 = m.classify_shadow_ignore_own_numbers(
        base_kind=base,
        length=length,
        bbox=bbox,
        nearby_text="W21X44  [30]",
        nearby_line=own_line,
        own_label_lines=[own_line],
    )
    assert v1["is_dimension"] is False
    assert v1["member_eligible"] is True
    assert v1["removed_trigger_text"] == "W21X44  [30]"


def test_no_mutation_of_production_extractor():
    before = hashlib.sha256(EXTRACTOR.read_bytes()).hexdigest()
    _load_mod()
    after = hashlib.sha256(EXTRACTOR.read_bytes()).hexdigest()
    assert before == after


def test_gold_immutable_sha():
    sha = hashlib.sha256(GOLD.read_bytes()).hexdigest()
    assert sha.startswith("0fad4291")
    assert sha == "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"


def test_audited_population_is_21_from_e1():
    tokens = {
        __import__("json").loads(line)["token_id"]
        for line in E1.read_text(encoding="utf-8").splitlines()
        if line.strip()
        and __import__("json").loads(line).get("population") == "audited_21"
    }
    assert len(tokens) == 21


def test_deterministic_strip_and_change(m):
    from services.engineering.models import GeometryKind

    own = [{"text": "W18X35  [35]", "bbox": [0, 0, 10, 10], "center": [5, 5], "page_number": 8}]
    a = m.classify_shadow_ignore_own_numbers(
        base_kind=GeometryKind.LINE,
        length=50.0,
        bbox=[0, 0, 50, 2],
        nearby_text="W18X35  [35]",
        nearby_line=own[0],
        own_label_lines=own,
    )
    b = m.classify_shadow_ignore_own_numbers(
        base_kind=GeometryKind.LINE,
        length=50.0,
        bbox=[0, 0, 50, 2],
        nearby_text="W18X35  [35]",
        nearby_line=own[0],
        own_label_lines=own,
    )
    assert a == b
    assert m.strip_digits("W21X44  [30]") == m.strip_digits("W21X44  [30]")
