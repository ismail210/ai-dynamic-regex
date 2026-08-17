"""
Single place that knows every module-level cache in the label-reconstruction
stack that depends on the currently loaded catalog
(`services.database_loader`), for offline training/eval scripts that swap
catalogs mid-process (e.g. `reload_from_aisc_v16_catalog`).

The live prediction path never calls this -- it loads the catalog once at
import and never reloads, so it never goes stale. This exists only because
training/audit scripts do reload mid-process and must not silently keep
serving cached results built from the previous catalog.
"""

from __future__ import annotations

from services import wildcard_matcher
from services.label_reconstruction import candidates as candidates_module
from services.label_reconstruction import corruption
from services.label_reconstruction import features
from services.label_reconstruction import structural_parser


def refresh_all_dependent_caches() -> None:
    wildcard_matcher.refresh_family_prefixes()
    corruption.set_family_codes(set(wildcard_matcher._FAMILY_PREFIXES))
    candidates_module.refresh_catalog_cache()
    structural_parser.refresh_catalog_index()
    features.refresh_family_size_cache()
