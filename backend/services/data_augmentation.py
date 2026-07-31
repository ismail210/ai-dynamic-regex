"""
Realistic engineering-token data augmentation
=============================================

Generates company-style naming variants for AISC / approved tokens.
Used only for classifier training — never fed into regex learning.

Examples for W16X26:
  W16X26, w16x26, W 16X26, W16 X26, WF16X26,
  Wide Flange W16X26, Beam W16X26 ASTM A992, …
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

# Compact designation: PREFIX + body (digits / X / fractions / decimals)
_SHAPE_RE = re.compile(
    r"^(?P<prefix>2L|HSS|PIPE|WT|MC|HP|MT|ST|WF|W|M|S|C|L)"
    r"(?P<body>.+)$",
    re.IGNORECASE,
)

_PREFIX_LABELS = {
    "W": ["Wide Flange", "WideFlange", "WF", "Steel Beam", "Beam", "W-Shape"],
    "WF": ["Wide Flange", "WideFlange", "Steel Beam", "Beam"],
    "WT": ["Structural Tee", "Tee", "WT Shape"],
    "M": ["Miscellaneous Beam", "M Shape", "Beam"],
    "S": ["Standard Beam", "S Shape", "I-Beam", "Beam"],
    "HP": ["H-Pile", "HP Shape", "Pile"],
    "C": ["Channel", "C Shape", "American Standard Channel"],
    "MC": ["Misc Channel", "MC Shape", "Channel"],
    "L": ["Angle", "L Shape", "Angle Iron", "Single Angle"],
    "2L": ["Double Angle", "2L Shape", "LL Angle"],
    "HSS": ["HSS", "Tube", "Hollow Structural Section", "Structural Tube", "TS"],
    "PIPE": ["Pipe", "Steel Pipe", "STD Pipe"],
    "MT": ["MT Tee", "Structural Tee"],
    "ST": ["ST Tee", "Structural Tee"],
}

_MATERIAL_HINTS = {
    "W": ["ASTM A992", "A992", "Gr.50", "Grade 50"],
    "WT": ["ASTM A992", "A992"],
    "M": ["ASTM A36", "A36"],
    "S": ["ASTM A36", "A36"],
    "HP": ["ASTM A572", "A572"],
    "C": ["ASTM A36", "A36"],
    "MC": ["ASTM A36", "A36"],
    "L": ["ASTM A36", "A36"],
    "2L": ["ASTM A36", "A36"],
    "HSS": ["ASTM A500", "A500", "Gr.B"],
    "PIPE": ["ASTM A53", "A53"],
}


def _normalize_prefix(prefix: str) -> str:
    return prefix.upper()


def _space_variants(prefix: str, body: str) -> List[str]:
    """Spacing / case variants that still look like drawing callouts."""
    p = prefix.upper()
    b = body.upper()
    raw = f"{p}{b}"
    out = [
        raw,
        raw.lower(),
        f"{p} {b}",
        f"{p}{b}".replace("X", " X ", 1) if "X" in b.upper() else f"{p} {b}",
        f"{p} {b}".replace("X", " X "),
        f"{p}-{b}",
        f"{p}_{b}",
    ]
    # WF alias for W shapes
    if p == "W":
        out.extend([f"WF{b}", f"WF {b}", f"WF-{b}", f"wf{b.lower()}"])
    if p == "HSS":
        out.extend([f"TS{b}", f"TS {b}", f"HSS {b}"])
    if p == "PIPE":
        out.extend([f"PIPE {b}", f"Pipe{b}", f"P {b}"])
    return out


def _phrase_variants(prefix: str, body: str, token: str) -> List[str]:
    labels = _PREFIX_LABELS.get(prefix, [prefix])
    materials = _MATERIAL_HINTS.get(prefix, [])
    designation = f"{prefix}{body}".upper()
    out: List[str] = []
    for label in labels[:4]:
        out.append(f"{label} {designation}")
        out.append(f"{label}-{designation}")
        out.append(f"{designation} {label}")
    for mat in materials[:2]:
        out.append(f"{designation} {mat}")
        out.append(f"Beam {designation} {mat}" if prefix in {"W", "M", "S"} else f"{designation} {mat}")
        if labels:
            out.append(f"{labels[0]} {designation} {mat}")
    # Keep original casing mix often seen in OCR
    out.append(token)
    out.append(token.upper())
    out.append(token.lower())
    return out


def generate_variants_for_token(token: str, cls: Optional[str] = None) -> List[str]:
    """Return unique realistic variants for one engineering token."""
    token = str(token).strip()
    if not token:
        return []

    variants: Set[str] = {token, token.upper(), token.lower()}
    match = _SHAPE_RE.match(token.replace(" ", ""))
    if match:
        prefix = _normalize_prefix(match.group("prefix"))
        body = match.group("body")
        # Prefer explicit class when provided (e.g. WF labeled as W)
        if cls:
            cls_u = str(cls).strip().upper()
            if cls_u in _PREFIX_LABELS:
                prefix = cls_u
        for v in _space_variants(prefix, body):
            variants.add(v)
        for v in _phrase_variants(prefix, body, token):
            variants.add(v)
    else:
        # Non-shape / material / bolt style tokens
        t = token.upper()
        variants.update(
            {
                t,
                token.lower(),
                f"ASTM {t}",
                f"Grade {t}",
                f"Steel {t}",
                f"{t} Steel",
                f"Mat'l {t}",
                f"MATERIAL {t}",
            }
        )
        if cls:
            c = str(cls).strip().upper()
            variants.add(f"{c} {t}")
            variants.add(f"{t} ({c})")

    # Drop empties / pure whitespace
    return sorted({v.strip() for v in variants if v and v.strip()})


def augment_frame(
    frame: pd.DataFrame,
    *,
    max_variants_per_token: int = 14,
    include_original: bool = True,
) -> pd.DataFrame:
    """
    Expand a token/class[/category] frame with synthetic naming variants.

    Returns columns: token, class, category (if present), source
    """
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["token", "class", "category", "source"])

    has_category = "category" in frame.columns
    rows: List[dict] = []
    seen: Set[Tuple[str, str]] = set()

    for _, row in frame.iterrows():
        token = str(row.get("token", "")).strip()
        cls = str(row.get("class", "")).strip()
        if not token or not cls:
            continue
        category = str(row.get("category", "")).strip() if has_category else ""
        variants = generate_variants_for_token(token, cls)
        if not include_original:
            variants = [v for v in variants if v.upper().replace(" ", "") != token.upper().replace(" ", "")]
        # Prefer shorter / closer variants first
        variants = sorted(variants, key=lambda v: (len(v), v.lower()))[:max_variants_per_token]
        for v in variants:
            key = (v.upper(), cls.upper())
            if key in seen:
                continue
            seen.add(key)
            is_orig = v.upper().replace(" ", "") == token.upper().replace(" ", "")
            rows.append(
                {
                    "token": v,
                    "class": cls.upper(),
                    "category": category,
                    "source": "original" if is_orig else "augmented",
                }
            )

    return pd.DataFrame(rows)


def augment_dataset_stats(original_n: int, augmented_frame: pd.DataFrame) -> dict:
    synth = int((augmented_frame.get("source") == "augmented").sum()) if not augmented_frame.empty else 0
    return {
        "original_samples": int(original_n),
        "augmented_samples": synth,
        "training_samples_total": int(len(augmented_frame)),
        "classes": int(augmented_frame["class"].nunique()) if not augmented_frame.empty else 0,
    }
