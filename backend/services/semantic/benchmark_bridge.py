"""Dev/demo-only bridge from a registered document back to its PDF-attack-
benchmark oracle manifest (repair-trace sprint, Section 20/26).

This is intentionally isolated from the repair path: nothing in
``services.semantic.repair_shadow`` or ``services.label_reconstruction``
imports this module or anything under it (see
``test_semantic_repair_shadow.py::test_module_never_imports_the_attack_benchmark_package``).
It exists only so the Semantic Review UI can, AFTER a human review decision,
show whether that decision matched the known-clean answer key from
``scripts/pdf_attack`` -- never before, and never as a feature the repair
engine itself can see.

The benchmark lives outside the repo (see backend/scripts/pdf_attack), at a
fixed local path -- this is dev/demo tooling, not a production data source.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

BENCHMARK_ROOT = r"C:\Users\Bassam\Downloads\estima3d_pdf_attack_benchmark_v1"
_MANIFEST_DIR = os.path.join(BENCHMARK_ROOT, "attack_manifests")


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _load_all_manifests() -> List[Dict[str, Any]]:
    if not os.path.isdir(_MANIFEST_DIR):
        return []
    manifests = []
    for path in sorted(glob.glob(os.path.join(_MANIFEST_DIR, "*.manifest.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                manifests.append(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
    return manifests


def is_benchmark_available() -> bool:
    return os.path.isdir(_MANIFEST_DIR)


def find_manifest_for_document(document_source_path: str) -> Optional[Dict[str, Any]]:
    """Match a registered document back to its attack manifest by content
    hash of the actual PDF bytes -- never by filename (a copy into
    uploads/ may be renamed)."""
    if not os.path.isfile(document_source_path):
        return None
    sha = _sha256_file(document_source_path)
    for manifest in _load_all_manifests():
        if manifest.get("attacked_pdf_sha256") == sha:
            return manifest
    return None


def _bbox_center(bbox: List[float]) -> tuple:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _bbox_distance(a: List[float], b: List[float]) -> float:
    ax, ay = _bbox_center(a)
    bx, by = _bbox_center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


_MATCH_MAX_DISTANCE = 40.0  # PDF points


def oracle_for_annotation(manifest: Dict[str, Any], page: Optional[int], bbox: Optional[List[float]]) -> Optional[Dict[str, Any]]:
    """Best-effort match of one annotation to its oracle mutation or clean
    control record, by page + spatial proximity only (never by text --
    matching on text would make it trivial to accidentally leak the answer
    through the matching logic itself)."""
    if page is None or not bbox:
        return None
    if manifest.get("page") != page:
        return None

    best = None
    best_dist = None
    for mutation in manifest.get("mutations", []):
        if not mutation.get("verification", {}).get("verified", False):
            continue
        dist = _bbox_distance(mutation["mutated_bbox"], bbox)
        if dist <= _MATCH_MAX_DISTANCE and (best_dist is None or dist < best_dist):
            best, best_dist = {"kind": "mutation", "record": mutation}, dist
    for control in manifest.get("clean_controls", []):
        dist = _bbox_distance(control["bbox"], bbox)
        if dist <= _MATCH_MAX_DISTANCE and (best_dist is None or dist < best_dist):
            best, best_dist = {"kind": "clean_control", "record": control}, dist
    return best


def benchmark_summary(manifest: Dict[str, Any]) -> Dict[str, Any]:
    verified = [m for m in manifest.get("mutations", []) if m.get("verification", {}).get("verified")]
    return {
        "attack_set_id": manifest.get("attack_set_id"),
        "source_pdf": manifest.get("source_pdf"),
        "page": manifest.get("page"),
        "generation": manifest.get("generation"),
        "mutation_count": len(verified),
        "clean_control_count": len(manifest.get("clean_controls", [])),
    }
