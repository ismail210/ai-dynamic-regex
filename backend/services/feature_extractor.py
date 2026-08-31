"""
Structural token feature extraction.

The production preprocessing pipeline imports this module through
``StructuralFeatureTransformer``.  Training and inference therefore execute
the exact same normalization and feature engineering code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from services.family_codes import MODERN_FAMILY_PREFIXES


FEATURE_COLUMNS = [
    "token",
    "prefix",
    "suffix",
    "token_length",
    "alpha_count",
    "digit_count",
    "special_char_count",
    "x_count",
    "contains_fraction",
    "contains_decimal",
    "contains_dash",
    "contains_slash",
    "contains_space",
    "starts_with_letter",
    "starts_with_digit",
    "ends_with_digit",
    "ends_with_letter",
    "numeric_groups",
    "alphabetic_groups",
    "shape_family",
    "material_hint",
    "company_prefix",
    "normalized_token",
    "regex_signature",
]

NUMERIC_FEATURE_COLUMNS = [
    "token_length",
    "alpha_count",
    "digit_count",
    "special_char_count",
    "x_count",
    "contains_fraction",
    "contains_decimal",
    "contains_dash",
    "contains_slash",
    "contains_space",
    "starts_with_letter",
    "starts_with_digit",
    "ends_with_digit",
    "ends_with_letter",
    "numeric_groups",
    "alphabetic_groups",
]

CATEGORICAL_FEATURE_COLUMNS = [
    "prefix",
    "suffix",
    "shape_family",
    "material_hint",
    "company_prefix",
    "regex_signature",
]

TEXT_FEATURE_COLUMN = "normalized_token"

_SPACE_RE = re.compile(r"\s+")
_ALPHA_RE = re.compile(r"[A-Z]+")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_FRACTION_RE = re.compile(r"\d+\s*/\s*\d+")
_MATERIAL_RE = re.compile(
    r"\b(?:ASTM\s*)?(A\d{2,4}|F\d{3,4})(?:\s*(?:GR(?:ADE)?\.?\s*)?([A-Z0-9.-]+))?\b",
    re.IGNORECASE,
)

_SHAPE_FAMILIES = MODERN_FAMILY_PREFIXES

_FAMILY_PATTERNS = {
    "HSS": re.compile(r"\b(?:HSS|TS|TUBE|SQUARE\s+HSS|RECTANGULAR\s+HSS)\s*[-_]?\s*\d", re.I),
    "PIPE": re.compile(r"\b(?:PIPE|STEEL\s+PIPE|STD\s+PIPE|P)\s*[-_]?\s*\d", re.I),
    "2L": re.compile(r"\b(?:2L|DOUBLE\s+ANGLE)\s*[-_]?\s*\d", re.I),
    "WT": re.compile(r"\b(?:WT|STRUCTURAL\s+TEE|WT\s+SHAPE)\s*[-_]?\s*\d", re.I),
    "MC": re.compile(r"\b(?:MC|MISC(?:ELLANEOUS)?\s+CHANNEL)\s*[-_]?\s*\d", re.I),
    "HP": re.compile(r"\b(?:HP|H[- ]?PILE|PILE)\s*[-_]?\s*\d", re.I),
    "MT": re.compile(r"\bMT\s*[-_]?\s*\d", re.I),
    "ST": re.compile(r"\bST\s*[-_]?\s*\d", re.I),
    "W": re.compile(
        r"\b(?:W|WF|WIDE\s*FLANGE|STEEL\s+BEAM|PRIMARY\s+BEAM|BEAM|COLUMN|W[- ]?SHAPE)"
        r"\s*[-_]?\s*\d",
        re.I,
    ),
    "M": re.compile(r"\b(?:M|MISCELLANEOUS\s+BEAM|M\s+SHAPE)\s*[-_]?\s*\d", re.I),
    "S": re.compile(r"\b(?:S|STANDARD\s+BEAM|I[- ]?BEAM|S\s+SHAPE)\s*[-_]?\s*\d", re.I),
    "C": re.compile(r"\b(?:C|CHANNEL|AMERICAN\s+STANDARD\s+CHANNEL)\s*[-_]?\s*\d", re.I),
    "L": re.compile(r"\b(?:L|ANGLE|ANGLE\s+IRON|SINGLE\s+ANGLE)\s*[-_]?\s*\d", re.I),
}

_COMPANY_PREFIXES = [
    "PRIMARY BEAM",
    "STEEL BEAM",
    "WIDE FLANGE",
    "WIDEFLANGE",
    "SQUARE HSS",
    "RECTANGULAR HSS",
    "STRUCTURAL TUBE",
    "DOUBLE ANGLE",
    "STANDARD BEAM",
    "MISCELLANEOUS BEAM",
    "MISC CHANNEL",
    "STEEL PIPE",
    "COLUMN",
    "BEAM",
    "TUBE",
    "ANGLE",
    "WF",
    "TS",
]


def normalize_token(token: object) -> str:
    """Return a stable uppercase representation while preserving word spaces."""

    return _SPACE_RE.sub(" ", str(token or "").strip().upper())


def _shape_family(normalized: str) -> str:
    for family, pattern in _FAMILY_PATTERNS.items():
        if pattern.search(normalized):
            return family

    compact = re.sub(r"[\s_-]+", "", normalized)
    for family in _SHAPE_FAMILIES:
        if compact.startswith(family) and re.search(r"\d", compact[len(family) :]):
            return family
    return "OTHER"


def _material_hint(normalized: str) -> str:
    match = _MATERIAL_RE.search(normalized)
    if not match:
        return "NONE"
    grade = match.group(1).upper()
    qualifier = (match.group(2) or "").upper()
    return f"{grade}:{qualifier}" if qualifier else grade


def _company_prefix(normalized: str) -> str:
    for prefix in _COMPANY_PREFIXES:
        if normalized.startswith(prefix):
            return prefix
    return "NONE"


def _regex_signature(normalized: str) -> str:
    """Encode structural runs without embedding literal numeric values."""

    parts: list[str] = []
    index = 0
    while index < len(normalized):
        char = normalized[index]
        if char.isalpha():
            end = index + 1
            while end < len(normalized) and normalized[end].isalpha():
                end += 1
            parts.append("A")
            index = end
        elif char.isdigit():
            end = index + 1
            while end < len(normalized) and normalized[end].isdigit():
                end += 1
            if (
                end < len(normalized)
                and normalized[end] == "."
                and end + 1 < len(normalized)
                and normalized[end + 1].isdigit()
            ):
                end += 1
                while end < len(normalized) and normalized[end].isdigit():
                    end += 1
                parts.append("D")
            else:
                parts.append("N")
            index = end
        elif char.isspace():
            parts.append("SPACE")
            index += 1
        else:
            parts.append(f"SEP:{char}")
            index += 1
    return "|".join(parts) if parts else "EMPTY"


def extract_structural_features(token: object) -> dict[str, object]:
    """Extract the full production feature row for one engineering token."""

    raw = str(token or "")
    normalized = normalize_token(raw)
    alpha_groups = _ALPHA_RE.findall(normalized)
    numeric_groups = _NUMBER_RE.findall(normalized)
    prefix = alpha_groups[0] if alpha_groups else "NONE"
    suffix_match = re.search(r"([A-Z]+)$", normalized)
    suffix = suffix_match.group(1) if suffix_match else "NONE"
    alpha_count = sum(char.isalpha() for char in normalized)
    digit_count = sum(char.isdigit() for char in normalized)
    special_count = sum(not char.isalnum() and not char.isspace() for char in normalized)

    return {
        "token": raw,
        "prefix": prefix,
        "suffix": suffix,
        "token_length": len(normalized),
        "alpha_count": alpha_count,
        "digit_count": digit_count,
        "special_char_count": special_count,
        "x_count": normalized.count("X"),
        "contains_fraction": int(bool(_FRACTION_RE.search(normalized))),
        "contains_decimal": int(bool(re.search(r"\d+\.\d+", normalized))),
        "contains_dash": int("-" in normalized),
        "contains_slash": int("/" in normalized),
        "contains_space": int(any(char.isspace() for char in raw)),
        "starts_with_letter": int(bool(normalized) and normalized[0].isalpha()),
        "starts_with_digit": int(bool(normalized) and normalized[0].isdigit()),
        "ends_with_digit": int(bool(normalized) and normalized[-1].isdigit()),
        "ends_with_letter": int(bool(normalized) and normalized[-1].isalpha()),
        "numeric_groups": len(numeric_groups),
        "alphabetic_groups": len(alpha_groups),
        "shape_family": _shape_family(normalized),
        "material_hint": _material_hint(normalized),
        "company_prefix": _company_prefix(normalized),
        "normalized_token": normalized,
        "regex_signature": _regex_signature(normalized),
    }


def extract_feature_frame(tokens: Iterable[object]) -> pd.DataFrame:
    """Create a deterministic DataFrame using ``FEATURE_COLUMNS`` order."""

    rows = [extract_structural_features(token) for token in tokens]
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS)


class StructuralFeatureTransformer(BaseEstimator, TransformerMixin):
    """Scikit-learn transformer that owns normalization and feature creation."""

    def fit(self, X: Sequence[object], y=None):
        return self

    def transform(self, X: Sequence[object]) -> pd.DataFrame:
        if isinstance(X, pd.DataFrame):
            if "token" not in X.columns:
                raise ValueError("Input DataFrame must contain a 'token' column")
            tokens = X["token"].tolist()
        elif isinstance(X, pd.Series):
            tokens = X.tolist()
        else:
            tokens = list(X)
        return extract_feature_frame(tokens)

    def get_feature_names_out(self, input_features=None):
        return FEATURE_COLUMNS
