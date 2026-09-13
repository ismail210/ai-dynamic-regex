"""Tests for scripts/corpus/corruption_engine.py -- Section 50's required
guards: round-HSS protection, category-truncation regression, and basic
determinism of the corruption generator.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.corpus import corruption_engine as ce


def test_round_hss_never_fractionized():
    """HSS5.563X0.258 is a round HSS with decimal fields -- no corruption
    function may introduce a '/' into it (that would be the forbidden
    round-HSS-fractionization case)."""
    text = "HSS5.563X0.258"
    rng = random.Random(1)
    for fn_name in ("corrupt_character_confusion", "corrupt_character_deletion",
                     "corrupt_character_insertion", "corrupt_decimal"):
        fn = getattr(ce, fn_name)
        if fn_name == "corrupt_decimal":
            result = fn(text, random.Random(1))
        else:
            result = fn(text, ce.family_prefix_length("HSS"), random.Random(1))
        if result is not None:
            assert "/" not in result.corrupted_text, f"{fn_name} introduced a fraction into round HSS"

    # corrupt_fraction_repair and corrupt_fraction_typography require an
    # existing "/" to apply at all -- they must no-op on round HSS.
    assert ce.corrupt_fraction_repair(text, random.Random(1)) is None
    assert ce.corrupt_fraction_typography(text, random.Random(1)) is None


def test_rectangular_hss_normalizes_to_fraction_not_corrupted_by_decimal_fns():
    text = "HSS8X8X0.375"
    # decimal corruption may apply (it damages digits, doesn't convert grammar)
    result = ce.corrupt_decimal(text, random.Random(2))
    if result is not None:
        assert result.target_operation == "REPAIR"


def test_every_repair_category_produces_examples_over_a_label_sample():
    """Regression guard for the truncation bug: every applicable category
    must be reachable, not silently dropped by fixed list-order truncation."""
    labels = [
        {"canonical_text": "W18X40", "family": "W", "fields": {"depth": "18", "rest": "40"}},
        {"canonical_text": "W10X33", "family": "W", "fields": {"depth": "10", "rest": "33"}},
        {"canonical_text": "HSS8X8X3/8", "family": "HSS", "fields": {"a": "8", "b": "8", "t": "3/8"}},
        {"canonical_text": "HSS6X6X0.375", "family": "HSS", "fields": {"a": "6", "b": "6", "t": "0.375"}},
        {"canonical_text": "C8X11.5", "family": "C", "fields": {"depth": "8", "rest": "11.5"}},
    ]
    seen_categories: set[str] = set()
    for i, label in enumerate(labels):
        family_start = ce.family_prefix_length(label["family"])
        text = label["canonical_text"]
        for name, fn in [
            ("confusion", lambda t, fs, r: ce.corrupt_character_confusion(t, fs, r)),
            ("deletion", lambda t, fs, r: ce.corrupt_character_deletion(t, fs, r)),
            ("insertion", lambda t, fs, r: ce.corrupt_character_insertion(t, fs, r)),
            ("multi", lambda t, fs, r: ce.corrupt_multi_step(t, fs, r, steps=2)),
            ("decimal", lambda t, fs, r: ce.corrupt_decimal(t, r)),
            ("fracrepair", lambda t, fs, r: ce.corrupt_fraction_repair(t, r)),
        ]:
            result = fn(text, family_start, ce._rng_for(42, text, name, i))
            if result is not None:
                seen_categories.add(result.category)
    expected = {"character_confusion", "character_deletion", "character_insertion", "multi_step", "fraction_repair"}
    missing = expected - seen_categories
    assert not missing, f"corruption categories never produced an example across the sample: {missing}"


def test_deletion_and_insertion_change_string_length():
    text = "W18X40"
    rng = random.Random(3)
    deletion = ce.corrupt_character_deletion(text, ce.family_prefix_length("W"), rng)
    assert deletion is not None
    assert len(deletion.corrupted_text) == len(text) - 1

    insertion = ce.corrupt_character_insertion(text, ce.family_prefix_length("W"), random.Random(4))
    assert insertion is not None
    assert len(insertion.corrupted_text) == len(text) + 1


def test_confusion_pairs_cover_required_set():
    required = {"1", "I", "l", "0", "O", "5", "S", "8", "B", "2", "Z", "6", "G"}
    assert required.issubset(ce._CONFUSION_PAIRS.keys())


def test_normalization_variants_never_labeled_repair():
    text = "HSS8X8X3/8"
    for fn_name, args in [
        ("corrupt_spacing", (text, "HSS", random.Random(5))),
        ("corrupt_separator", (text, random.Random(6))),
        ("corrupt_fraction_typography", (text, random.Random(7))),
    ]:
        fn = getattr(ce, fn_name)
        result = fn(*args)
        if result is not None:
            assert result.target_operation == "NORMALIZATION_VARIANT"


def test_completion_test_never_labeled_repair():
    result = ce.corrupt_missing_information("W8X10", "W", {"depth": "8", "rest": "10"}, random.Random(8))
    assert result is not None
    assert result.target_operation == "COMPLETION_TEST"
    assert result.corrupted_text == "W8"


def test_fragmentation_is_grouping_not_repair():
    result = ce.corrupt_fragmentation("W18X40", "W", random.Random(9))
    assert result is not None
    assert result.target_operation == "GROUPING"
    assert result.fragments is not None
    assert "".join(f["text"] for f in result.fragments) == "W18X40"


def test_determinism_same_seed_same_output():
    text = "W18X40"
    a = ce.corrupt_character_confusion(text, ce.family_prefix_length("W"), ce._rng_for(42, "seed_a", "confusion"))
    b = ce.corrupt_character_confusion(text, ce.family_prefix_length("W"), ce._rng_for(42, "seed_a", "confusion"))
    assert a is not None and b is not None
    assert a.corrupted_text == b.corrupted_text
    assert a.seed == b.seed
