"""Phase E -- deterministic, seeded, family-aware structural corruption engine
(Section 12-14).

Every function here is pure: given a clean seed record and a
``random.Random`` instance, it returns a corruption result or ``None`` when
the category doesn't apply to that label's family/grammar. Nothing here
mutates global state, so the same seed always reproduces the same corpus.

CRITICAL DISTINCTIONS preserved throughout (Section 9/13):
  - Equivalent notation (spacing/separator/fraction-typography) is
    ``NORMALIZATION_VARIANT``, never ``REPAIR``.
  - Actual character/field corruption is ``REPAIR``.
  - Missing-information tests are ``COMPLETION_TEST``, evaluated separately.
  - Round HSS / Pipe decimal fields are NEVER fraction-converted -- the
    generator has no code path that does this at all.

The character-confusion weights below are NOT empirical (Section 11's raster
OCR experiment was not run this session -- see reports/ocr_confusion_matrix.md
for why). They encode the same qualitative assumptions the rest of this
project already uses (1<->I<->l, 0<->O, 5<->S, 8<->B, 2<->Z, 6<->G) with equal
weight per pair. This is explicitly flagged in the manifest as
``confusion_source: "assumed_not_empirical"``.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Optional

CONFUSION_SOURCE = "assumed_not_empirical"

# Symmetric confusion pairs -- digit/letter shapes that are visually similar.
# Applied ONLY inside numeric/typed field positions, never on the family
# prefix letters (Section 13: changing W -> Q is not a realistic error).
_CONFUSION_PAIRS: dict[str, list[str]] = {
    "1": ["I", "l"], "I": ["1", "l"], "l": ["1", "I"],
    "0": ["O"], "O": ["0"],
    "5": ["S"], "S": ["5"],
    "8": ["B"], "B": ["8"],
    "2": ["Z"], "Z": ["2"],
    "6": ["G"], "G": ["6"],
}


@dataclass
class CorruptionStep:
    type: str
    detail: dict = field(default_factory=dict)


@dataclass
class CorruptionExample:
    clean_text: str
    corrupted_text: str
    target_operation: str  # NORMALIZATION_VARIANT | REPAIR | COMPLETION_TEST
    category: str
    difficulty: int
    corruptions: list[CorruptionStep]
    seed: int
    fragments: Optional[list[dict]] = None  # for grouping/span examples


def _rng_for(base_seed: int, *parts: Any) -> random.Random:
    """Deterministic per-example RNG derived from a base seed + identifying
    parts, so re-running generation for the same seed always reproduces the
    exact same corpus without needing a single shared mutable RNG."""
    key = f"{base_seed}:{':'.join(str(p) for p in parts)}"
    return random.Random(key)


# ---------------------------------------------------------------------------
# Character-level corruptions (REPAIR)
# ---------------------------------------------------------------------------

def corrupt_character_confusion(text: str, family_start: int, rng: random.Random) -> Optional[CorruptionExample]:
    """Swap exactly one confusable character within the label's numeric
    field region (after the family prefix), never in the family letters."""
    candidates = [i for i in range(family_start, len(text)) if text[i] in _CONFUSION_PAIRS]
    if not candidates:
        return None
    pos = rng.choice(candidates)
    replacement = rng.choice(_CONFUSION_PAIRS[text[pos]])
    corrupted = text[:pos] + replacement + text[pos + 1:]
    return CorruptionExample(
        clean_text=text, corrupted_text=corrupted, target_operation="REPAIR",
        category="character_confusion", difficulty=1,
        corruptions=[CorruptionStep("character_confusion", {"position": pos, "from": text[pos], "to": replacement})],
        seed=rng.randint(0, 2**31),
    )


def corrupt_character_deletion(text: str, family_start: int, rng: random.Random) -> Optional[CorruptionExample]:
    digit_positions = [i for i in range(family_start, len(text)) if text[i].isdigit()]
    if not digit_positions:
        return None
    pos = rng.choice(digit_positions)
    corrupted = text[:pos] + text[pos + 1:]
    return CorruptionExample(
        clean_text=text, corrupted_text=corrupted, target_operation="REPAIR",
        category="character_deletion", difficulty=1,
        corruptions=[CorruptionStep("character_deletion", {"position": pos, "deleted": text[pos]})],
        seed=rng.randint(0, 2**31),
    )


def corrupt_character_insertion(text: str, family_start: int, rng: random.Random) -> Optional[CorruptionExample]:
    digit_positions = [i for i in range(family_start, len(text)) if text[i].isdigit()]
    if not digit_positions:
        return None
    pos = rng.choice(digit_positions)
    corrupted = text[:pos] + text[pos] + text[pos:]  # duplicate the digit
    return CorruptionExample(
        clean_text=text, corrupted_text=corrupted, target_operation="REPAIR",
        category="character_insertion", difficulty=1,
        corruptions=[CorruptionStep("character_insertion", {"position": pos, "inserted": text[pos]})],
        seed=rng.randint(0, 2**31),
    )


# ---------------------------------------------------------------------------
# Notation-equivalent variants (NORMALIZATION_VARIANT)
# ---------------------------------------------------------------------------

def corrupt_spacing(text: str, family: str, rng: random.Random) -> Optional[CorruptionExample]:
    if not text.startswith(family):
        return None
    rest = text[len(family):]
    # Insert a space either right after the family letters, or around the
    # first separator character (X/x), whichever is present -- both are
    # real drafting variants this system's own normalize_label_text already
    # collapses back to canonical.
    variants = [f"{family} {rest}"]
    sep_match = re.search(r"[Xx]", rest)
    if sep_match:
        i = sep_match.start()
        variants.append(f"{family}{rest[:i]} {rest[i]} {rest[i+1:]}")
        variants.append(f"{family}{rest[:i]}{rest[i]} {rest[i+1:]}")
        variants.append(f"{family}{rest[:i]} {rest[i]}{rest[i+1:]}")
    corrupted = rng.choice(variants)
    return CorruptionExample(
        clean_text=text, corrupted_text=corrupted, target_operation="NORMALIZATION_VARIANT",
        category="spacing_variation", difficulty=0,
        corruptions=[CorruptionStep("spacing_variation", {})],
        seed=rng.randint(0, 2**31),
    )


def corrupt_separator(text: str, rng: random.Random) -> Optional[CorruptionExample]:
    if "X" not in text:
        return None
    replacement = rng.choice(["x", "×"])  # lowercase x, multiplication sign
    idx = text.index("X")
    corrupted = text[:idx] + replacement + text[idx + 1:]
    return CorruptionExample(
        clean_text=text, corrupted_text=corrupted, target_operation="NORMALIZATION_VARIANT",
        category="separator_variation", difficulty=0,
        corruptions=[CorruptionStep("separator_variation", {"replacement": replacement})],
        seed=rng.randint(0, 2**31),
    )


def corrupt_fraction_typography(text: str, rng: random.Random) -> Optional[CorruptionExample]:
    """Genuinely equivalent fraction typography -- NOT a corruption."""
    m = re.search(r"(\d)/(\d)", text)
    if not m:
        return None
    variants = [
        f"{m.group(1)} / {m.group(2)}",
        f"{m.group(1)}⁄{m.group(2)}",  # fraction slash
    ]
    corrupted = text[:m.start()] + rng.choice(variants) + text[m.end():]
    return CorruptionExample(
        clean_text=text, corrupted_text=corrupted, target_operation="NORMALIZATION_VARIANT",
        category="fraction_typography", difficulty=0,
        corruptions=[CorruptionStep("fraction_typography", {})],
        seed=rng.randint(0, 2**31),
    )


# ---------------------------------------------------------------------------
# Decimal / fraction corruption (REPAIR) -- family-aware (Section 13)
# ---------------------------------------------------------------------------

def corrupt_decimal(text: str, rng: random.Random) -> Optional[CorruptionExample]:
    """Digit-level noise on a decimal field. Applies uniformly regardless of
    whether the family is rect/round HSS -- this never *converts* decimal to
    fraction (that would be the forbidden round-HSS-fractionization case), it
    only damages the decimal's own digits/characters, which is a repair
    problem for either grammar."""
    m = re.search(r"(\d*)\.(\d+)", text)
    if not m:
        return None
    choice = rng.choice(["drop_point", "drop_leading_zero", "zero_to_O"])
    if choice == "drop_point":
        corrupted = text[:m.start()] + m.group(1) + m.group(2) + text[m.end():]
    elif choice == "drop_leading_zero" and m.group(1) == "0":
        corrupted = text[:m.start()] + "." + m.group(2) + text[m.end():]
    else:
        leading = m.group(1).replace("0", "O", 1) if "0" in m.group(1) else m.group(1)
        if leading == m.group(1):
            return None
        corrupted = text[:m.start()] + leading + "." + m.group(2) + text[m.end():]
    if corrupted == text:
        return None
    return CorruptionExample(
        clean_text=text, corrupted_text=corrupted, target_operation="REPAIR",
        category="decimal_error", difficulty=1,
        corruptions=[CorruptionStep("decimal_error", {"variant": choice})],
        seed=rng.randint(0, 2**31),
    )


def corrupt_fraction_repair(text: str, rng: random.Random) -> Optional[CorruptionExample]:
    m = re.search(r"(\d)/(\d)", text)
    if not m:
        return None
    choice = rng.choice(["drop_slash", "space_for_slash", "letter_for_denominator"])
    if choice == "drop_slash":
        corrupted = text[:m.start()] + m.group(1) + m.group(2) + text[m.end():]
    elif choice == "space_for_slash":
        corrupted = text[:m.start()] + m.group(1) + " " + m.group(2) + text[m.end():]
    else:
        confusions = _CONFUSION_PAIRS.get(m.group(2))
        if not confusions:
            return None
        corrupted = text[:m.start()] + m.group(1) + "/" + rng.choice(confusions) + text[m.end():]
    return CorruptionExample(
        clean_text=text, corrupted_text=corrupted, target_operation="REPAIR",
        category="fraction_repair", difficulty=1,
        corruptions=[CorruptionStep("fraction_repair", {"variant": choice})],
        seed=rng.randint(0, 2**31),
    )


# ---------------------------------------------------------------------------
# Completion test (Section 12 "missing information") -- SEPARATE dataset
# ---------------------------------------------------------------------------

def corrupt_missing_information(text: str, family: str, fields: dict, rng: random.Random) -> Optional[CorruptionExample]:
    """Depth-only shorthand, e.g. W8X10 -> W8. Evaluated as COMPLETION_TEST,
    never mixed into the repair benchmark (Section 9/27)."""
    depth = fields.get("depth")
    if not depth:
        return None
    shorthand = f"{family}{depth}"
    if shorthand == text:
        return None
    return CorruptionExample(
        clean_text=text, corrupted_text=shorthand, target_operation="COMPLETION_TEST",
        category="missing_information", difficulty=1,
        corruptions=[CorruptionStep("missing_information", {"kept": "family+depth"})],
        seed=rng.randint(0, 2**31),
    )


# ---------------------------------------------------------------------------
# Composition: multi-step corruption (Level 2)
# ---------------------------------------------------------------------------

_REPAIR_FUNCS = [corrupt_character_confusion, corrupt_character_deletion, corrupt_character_insertion]


def corrupt_multi_step(text: str, family_start: int, rng: random.Random, steps: int = 2) -> Optional[CorruptionExample]:
    current = text
    applied: list[CorruptionStep] = []
    for _ in range(steps):
        fn = rng.choice(_REPAIR_FUNCS)
        result = fn(current, family_start, rng)
        if result is None:
            continue
        current = result.corrupted_text
        applied.extend(result.corruptions)
    if current == text or not applied:
        return None
    return CorruptionExample(
        clean_text=text, corrupted_text=current, target_operation="REPAIR",
        category="multi_step", difficulty=2,
        corruptions=applied, seed=rng.randint(0, 2**31),
    )


def family_prefix_length(family: str) -> int:
    return len(family)


# ---------------------------------------------------------------------------
# Fragmentation / tokenization variants (GROUPING, Section 14/D) -- these are
# NOT string corruptions, they simulate a native-PDF extractor emitting the
# same label as multiple separate text spans. Never mixed into the repair
# benchmark; evaluated as a grouping/reconstruction task instead.
# ---------------------------------------------------------------------------

def corrupt_fragmentation(text: str, family: str, rng: random.Random) -> Optional[CorruptionExample]:
    """Split one clean label into 2-3 fragments the way PyMuPDF sometimes
    emits separate words/spans for one visual label (Section 14/Case D)."""
    if not text.startswith(family) or len(text) <= len(family) + 1:
        return None
    rest = text[len(family):]
    sep_match = re.search(r"[Xx]", rest)
    schemes: list[list[str]] = [[family, rest]]  # ["W18", "X40"] style baseline
    if sep_match:
        i = sep_match.start()
        schemes.append([family + rest[:i], rest[i], rest[i + 1:]])  # ["W18","X","40"]
        schemes.append([family, rest[:i] + rest[i] + rest[i + 1:]])  # ["W", "18X40"]
        schemes.append([family + rest[:i] + rest[i], rest[i + 1:]])  # ["W18X", "40"]
    schemes = [s for s in schemes if all(part for part in s)]
    if not schemes:
        return None
    fragments_text = rng.choice(schemes)
    fragments = [{"text": part, "order": idx} for idx, part in enumerate(fragments_text)]
    return CorruptionExample(
        clean_text=text, corrupted_text="".join(fragments_text), target_operation="GROUPING",
        category="fragmentation", difficulty=1,
        corruptions=[CorruptionStep("fragmentation", {"scheme": fragments_text})],
        seed=rng.randint(0, 2**31),
        fragments=fragments,
    )
