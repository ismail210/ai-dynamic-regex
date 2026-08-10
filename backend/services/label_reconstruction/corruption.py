"""Generate realistic corruptions of canonical AISC labels.

Every function here takes a clean, normalized AISC manual label (e.g.
``W18X35``) and returns a *plausible* damaged version that could appear on a
scanned/OCR'd structural drawing, plus tags identifying which corruption(s)
were applied. This is deliberately not random character noise: each family
below mirrors a real failure mode (a torn corner, a smudge, a smashed OCR
glyph, a truncated leader label, ...).

Severity is the count of distinct corruption operations applied (1 for a
single-family corruption, 2-3 for combinations).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# OCR confusion table (bidirectional, single characters only). Deliberately
# conservative: only pairs that are genuinely easy to confuse at typical scan
# resolution on architectural/structural drawings.
# ---------------------------------------------------------------------------
OCR_CONFUSION = {
    "0": "O",
    "O": "0",
    "1": "I",
    "I": "1",
    "L": "1",
    "5": "S",
    "S": "5",
    "8": "B",
    "B": "8",
    "2": "Z",
    "Z": "2",
    "6": "G",
    "G": "6",
}

WILDCARD_TOKENS = ("*", "?")

_FAMILY_PREFIXES = sorted(
    {"W", "WT", "HSS", "L", "2L", "C", "MC", "PIPE", "MT", "ST", "HP", "M", "S"},
    key=len,
    reverse=True,
)


@dataclass
class Corruption:
    text: str
    corruption_types: List[str] = field(default_factory=list)


def family_of(label: str) -> str:
    for prefix in _FAMILY_PREFIXES:
        if label.startswith(prefix):
            return prefix
    return "".join(ch for ch in label if ch.isalpha())[:3] or "OTHER"


# ---------------------------------------------------------------------------
# Individual corruption families. Each returns None when it cannot apply
# (e.g. deleting a character from a 1-character remainder).
# ---------------------------------------------------------------------------


def corrupt_char_deletion(label: str, rng: random.Random) -> Optional[Corruption]:
    """Drop 1-2 trailing or interior characters (torn/cut-off label)."""

    if len(label) < 3:
        return None
    mode = rng.choice(["trailing", "interior"])
    if mode == "trailing":
        drop = rng.choice([1, 1, 2])
        drop = min(drop, len(label) - 2)
        return Corruption(label[: len(label) - drop], ["char_deletion_trailing"])
    index = rng.randrange(1, len(label) - 1)
    return Corruption(label[:index] + label[index + 1 :], ["char_deletion_interior"])


def corrupt_unknown_char(label: str, rng: random.Random) -> Optional[Corruption]:
    """Replace 1-3 characters with a wildcard marker (smudge/illegible)."""

    if len(label) < 2:
        return None
    marker = rng.choice(WILDCARD_TOKENS)
    count = rng.choice([1, 1, 2, 3])
    # Never mask the whole string and prefer masking away from the family
    # prefix so at least the family is usually still legible.
    fam = family_of(label)
    start = len(fam) if len(fam) < len(label) else 0
    positions = list(range(start, len(label)))
    if not positions:
        return None
    count = min(count, len(positions))
    chosen = set(rng.sample(positions, count))
    chars = [marker if i in chosen else ch for i, ch in enumerate(label)]
    tag = "unknown_char_single" if count == 1 else "unknown_char_multi"
    return Corruption("".join(chars), [tag])


def corrupt_ocr_substitution(label: str, rng: random.Random) -> Optional[Corruption]:
    """Swap 1-2 characters for their OCR-confusable twin."""

    candidates = [i for i, ch in enumerate(label) if ch in OCR_CONFUSION]
    if not candidates:
        return None
    count = min(rng.choice([1, 1, 2]), len(candidates))
    chosen = rng.sample(candidates, count)
    chars = list(label)
    tags = []
    for i in chosen:
        original = chars[i]
        replacement = OCR_CONFUSION[original]
        chars[i] = replacement
        tags.append(f"{original}_to_{replacement}")
    return Corruption("".join(chars), tags)


def corrupt_separator(label: str, rng: random.Random) -> Optional[Corruption]:
    """Corrupt the depth/weight separator ('X')."""

    if "X" not in label:
        return None
    style = rng.choice(["space", "multiply_sign", "dash", "space_after"])
    if style == "space":
        text = label.replace("X", " ", 1)
        tag = "separator_space"
    elif style == "multiply_sign":
        text = label.replace("X", "×", 1)
        tag = "separator_multiply_sign"
    elif style == "dash":
        text = label.replace("X", "-X", 1)
        tag = "separator_dash"
    else:
        text = label.replace("X", "X ", 1)
        tag = "separator_space_after"
    return Corruption(text, [tag])


def corrupt_added_noise(label: str, rng: random.Random) -> Optional[Corruption]:
    """Add stray characters from nearby drawing text (leader lines, revision
    markers, parentheses) that OCR merges into the token."""

    style = rng.choice(["prefix_letter", "suffix_letter", "parens"])
    if style == "prefix_letter":
        text = rng.choice("BFW") + label
        tag = "added_prefix_letter"
    elif style == "suffix_letter":
        text = label + rng.choice("AB")
        tag = "added_suffix_letter"
    else:
        text = f"({label})"
        tag = "added_parens"
    return Corruption(text, [tag])


def corrupt_missing_prefix(label: str, rng: random.Random) -> Optional[Corruption]:
    """Drop the family letter prefix entirely (leader points at the number
    only) or keep only the family with nothing else."""

    fam = family_of(label)
    if not fam or len(fam) >= len(label):
        return None
    mode = rng.choice(["drop_family", "family_only"])
    if mode == "drop_family":
        return Corruption(label[len(fam) :], ["missing_family_prefix"])
    return Corruption(fam, ["family_only_partial"])


CORRUPTION_FAMILIES: List[Tuple[str, Callable[[str, random.Random], Optional[Corruption]]]] = [
    ("char_deletion", corrupt_char_deletion),
    ("unknown_char", corrupt_unknown_char),
    ("ocr_substitution", corrupt_ocr_substitution),
    ("separator", corrupt_separator),
    ("added_noise", corrupt_added_noise),
    ("missing_prefix", corrupt_missing_prefix),
]


def generate_single_corruption(
    label: str, rng: random.Random, family_name: Optional[str] = None
) -> Optional[Corruption]:
    """Apply one named corruption family, or a random applicable one."""

    families = CORRUPTION_FAMILIES
    if family_name is not None:
        families = [(name, fn) for name, fn in families if name == family_name]
        if not families:
            raise ValueError(f"Unknown corruption family: {family_name}")
    rng.shuffle(families := list(families))
    for _, fn in families:
        result = fn(label, rng)
        if result is not None and result.text != label:
            return result
    return None


def generate_multi_corruption(
    label: str, rng: random.Random, severity: int
) -> Optional[Corruption]:
    """Chain 2-3 independent corruption operations onto the same label."""

    current = label
    all_tags: List[str] = []
    families = [name for name, _ in CORRUPTION_FAMILIES]
    rng.shuffle(families)
    applied = 0
    for family_name in families:
        if applied >= severity:
            break
        result = generate_single_corruption(current, rng, family_name=family_name)
        if result is None:
            continue
        current = result.text
        all_tags.extend(result.corruption_types)
        applied += 1
    if applied == 0 or current == label:
        return None
    return Corruption(current, all_tags)
