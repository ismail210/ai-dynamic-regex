"""
AISC v16 (all-editions) canonical label catalog — loader and lookup.

Reads the derived ``aisc_v16_label_catalog.csv`` (built by
``scripts/prepare_aisc_v16_catalog.py`` from the raw AISC v16 shapes CSV,
which spans 12 historical manual editions) and exposes a validated
family/designation contract: fast exact lookup and family grouping, with
clear failures on malformed catalog data.

This module is additive and self-contained. It is not imported by the
production prediction pipeline yet — ``services.database_loader`` (backed
by the existing v16 XLSX) remains the catalog actually used for
predictions until a promoted cutover.
"""

from __future__ import annotations

import csv
import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from config import settings
from services.wildcard_matcher import _FAMILY_PREFIXES

REQUIRED_COLUMNS = ("family", "designation")

# Modern production families are exactly the family codes the current
# candidate generator/parser already recognize (services.wildcard_matcher).
# This is intentionally the verified-against-data, currently-supported set,
# not a guess: any Type code that is not literally one of these strings
# (e.g. "ST R", "ST S", "ST JR" are distinct declared Type codes, never
# collapsed into modern "ST") is historical/legacy scope.
MODERN_FAMILIES = frozenset(_FAMILY_PREFIXES)


def classify_catalog_scope(family: str) -> str:
    """``"modern"`` for the 13 current production families, else
    ``"historical"``. Never reinterprets or merges the family string."""

    return "modern" if family in MODERN_FAMILIES else "historical"

_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_PREFIX_RE = re.compile(r"^(\d*)([A-Za-z]+)")


def normalize_designation_text(text: object) -> str:
    """Conservative text cleanup: unify the multiplication sign, trim,
    collapse internal whitespace runs, uppercase.

    Never touches digits or the punctuation that carries dimensional
    meaning (``/``, ``.``, ``-``). This is formatting cleanup only, not OCR
    correction — it must never make a designation numerically different
    from the source.
    """

    value = "" if text is None else str(text)
    value = value.replace("×", "X").replace("✕", "X")
    value = value.strip()
    value = _WHITESPACE_RE.sub(" ", value)
    return value.upper()


def lookup_key(designation: object) -> str:
    """Key used for exact matching: normalized text with spaces removed,
    matching the convention already used by ``services.database_loader``
    (``is_catalog_label``/``catalog_form``)."""

    return normalize_designation_text(designation).replace(" ", "")


def infer_family_longest_prefix(
    designation: str, known_families: Set[str]
) -> Optional[str]:
    """Infer a family code from a designation's leading digit+letter run.

    Matches the *whole* leading letter-run (optionally preceded by a digit
    multiplier) against ``known_families`` first, falling back to the
    letter-run alone. This is longest-prefix/family-aware, not naive
    first-character parsing: ``2L12X12X1`` infers ``2L`` (never collapsing
    to ``L``), and ``WT12X51`` infers ``WT`` (never collapsing to ``W``).
    Returns ``None`` when no known family matches.
    """

    match = _LEADING_PREFIX_RE.match(designation or "")
    if not match:
        return None
    digits, letters = match.groups()
    candidates = [digits + letters, letters] if digits else [letters]
    for candidate in candidates:
        if candidate in known_families:
            return candidate
    return None


@dataclass(frozen=True)
class CatalogEntry:
    family: str
    designation: str
    source_row_id: str
    source_edition: str
    source_edition_count: int
    catalog_scope: str = ""  # resolved by classify_catalog_scope() if left blank


class CatalogValidationError(ValueError):
    """Raised when the on-disk catalog CSV fails structural validation."""


class AiscV16Catalog:
    """In-memory, validated view of the canonical label catalog."""

    def __init__(self, entries: List[CatalogEntry]):
        self._by_key: Dict[str, CatalogEntry] = {}
        self._by_family: Dict[str, List[CatalogEntry]] = {}
        for entry in entries:
            if not entry.catalog_scope:
                entry = dataclasses.replace(
                    entry, catalog_scope=classify_catalog_scope(entry.family)
                )
            key = lookup_key(entry.designation)
            if key in self._by_key:
                raise CatalogValidationError(
                    "duplicate canonical designation after normalization: "
                    f"{entry.designation!r}"
                )
            self._by_key[key] = entry
            self._by_family.setdefault(entry.family, []).append(entry)

    def __len__(self) -> int:
        return len(self._by_key)

    def lookup(self, token: object) -> Optional[CatalogEntry]:
        return self._by_key.get(lookup_key(token))

    def is_catalog_label(self, token: object) -> bool:
        return lookup_key(token) in self._by_key

    def families(self) -> List[str]:
        return sorted(self._by_family)

    def family_counts(self) -> Dict[str, int]:
        return {family: len(entries) for family, entries in self._by_family.items()}

    def entries_by_scope(self, scope: str) -> List[CatalogEntry]:
        return [entry for entry in self._by_key.values() if entry.catalog_scope == scope]

    def modern_entries(self) -> List[CatalogEntry]:
        return self.entries_by_scope("modern")

    def historical_entries(self) -> List[CatalogEntry]:
        return self.entries_by_scope("historical")

    def examples_for_family(
        self, family: str, limit: Optional[int] = None
    ) -> List[str]:
        designations = [entry.designation for entry in self._by_family.get(family, [])]
        return designations[:limit] if limit else designations

    def entries(self) -> List[CatalogEntry]:
        return list(self._by_key.values())


def default_catalog_path() -> Path:
    return settings.aisc_v16_label_catalog_path


def load_catalog(path: Optional[Path] = None) -> AiscV16Catalog:
    """Load and validate the canonical catalog CSV.

    Fails clearly (``CatalogValidationError``) on: missing required
    columns, blank family/designation, or duplicate ``(family,
    designation)`` pairs — malformed catalog data must never load silently.
    """

    csv_path = Path(path) if path is not None else default_catalog_path()
    if not csv_path.exists():
        raise CatalogValidationError(f"catalog file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
        if missing:
            raise CatalogValidationError(
                f"catalog is missing required columns: {missing}"
            )

        entries: List[CatalogEntry] = []
        seen_pairs: Set[tuple] = set()
        for line_number, row in enumerate(reader, start=2):
            family = (row.get("family") or "").strip()
            designation = (row.get("designation") or "").strip()
            if not designation:
                raise CatalogValidationError(
                    f"blank designation at catalog row {line_number}"
                )
            if not family:
                raise CatalogValidationError(
                    f"blank family at catalog row {line_number}"
                )
            pair = (family, designation)
            if pair in seen_pairs:
                raise CatalogValidationError(
                    f"duplicate (family, designation) pair: {pair}"
                )
            seen_pairs.add(pair)
            entries.append(
                CatalogEntry(
                    family=family,
                    designation=designation,
                    source_row_id=(row.get("source_row_id") or "").strip(),
                    source_edition=(row.get("source_edition") or "").strip(),
                    source_edition_count=int(row.get("source_edition_count") or 1),
                    catalog_scope=(row.get("catalog_scope") or "").strip(),
                )
            )

    if not entries:
        raise CatalogValidationError("catalog contains no rows")

    return AiscV16Catalog(entries)
