#!/usr/bin/env python3
"""Measure member-geometry retention and text→stroke proximity (OCR QA).

Read-only against persisted Analyze artifacts. Does not change predictions.

Usage (from backend/):

  python scripts/evaluate_member_geometry.py --document-id doc_0d910a43b4a021e3
  python scripts/evaluate_member_geometry.py --document-id doc_... --pages 10-16
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.artifact_store import read_artifact  # noqa: E402
from services.engineering.member_geometry import (  # noqa: E402
    STRUCT_KINDS,
    build_member_candidates,
    distance_point_to_geometry,
    unresolved_member_geometry,
)

_STRUCT_PREFIXES = ("W", "HSS", "C", "L", "2L", "WT", "MC")


def _parse_pages(spec: Optional[str]) -> Optional[set[int]]:
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return pages


def _center(bbox: Sequence[float]) -> Tuple[float, float]:
    return ((float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0)


def _is_structural_label(text: str) -> bool:
    up = str(text or "").upper().replace(" ", "")
    return any(up.startswith(p) for p in _STRUCT_PREFIXES)


def _load_geometry(document_id: str) -> Dict[str, Any]:
    return read_artifact(document_id, "geometry.json") or {}


def _load_predictions(document_id: str) -> List[dict]:
    view = read_artifact(document_id, "predictions_view.json") or {}
    preds = view.get("predictions") if isinstance(view, dict) else None
    if preds:
        return list(preds)
    raw = read_artifact(document_id, "predictions.json") or {}
    if isinstance(raw, dict):
        return list(raw.get("predictions") or [])
    return []


def summarize(
    document_id: str,
    *,
    pages: Optional[set[int]] = None,
    proximity_pt: float = 50.0,
) -> Dict[str, Any]:
    geometry = _load_geometry(document_id)
    objects = list(geometry.get("objects") or [])
    by_page: Dict[int, List[dict]] = defaultdict(list)
    kind_counts = Counter()
    for obj in objects:
        page = int(obj.get("page_number") or obj.get("page") or 0)
        by_page[page].append(obj)
        kind_counts[str(obj.get("kind") or "?")] += 1

    page_summaries = geometry.get("page_summaries") or (
        (geometry.get("metadata") or {}).get("page_summaries") or []
    )
    retention_rows = []
    for summary in page_summaries:
        page = int(summary.get("page_number") or 0)
        if pages is not None and page not in pages:
            continue
        retention_rows.append(
            {
                "page": page,
                "raw_drawing_count": summary.get("raw_drawing_count")
                or summary.get("drawing_count"),
                "retained": summary.get("retained_drawing_count")
                or summary.get("geometry_count")
                or summary.get("processed_drawing_count"),
                "dropped_by_cap": summary.get("drawings_dropped_by_cap"),
                "cap_applied": summary.get("drawing_cap_applied"),
                "kinds": dict(
                    Counter(str(o.get("kind") or "?") for o in by_page.get(page, []))
                ),
            }
        )

    candidates = build_member_candidates(geometry)
    cand_by_page: Dict[int, List[dict]] = defaultdict(list)
    for cand in candidates:
        cand_by_page[int(cand.get("page_number") or 0)].append(cand)

    preds = _load_predictions(document_id)
    label_rows = []
    hits = 0
    collisions: Counter = Counter()
    preview_kinds = Counter()
    member_available = 0
    for pred in preds:
        page = int(pred.get("page_number") or pred.get("page") or 0)
        if pages is not None and page not in pages:
            continue
        raw = str(pred.get("raw_text") or pred.get("original_token") or "")
        if not _is_structural_label(raw):
            continue
        bbox = pred.get("bounding_box") or pred.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        gp = pred.get("geometry_preview") or {}
        preview_kinds[str(gp.get("kind") or "none")] += 1
        mg = pred.get("member_geometry")
        if isinstance(mg, dict) and mg.get("available"):
            member_available += 1
        center = _center(bbox)
        best_d = None
        best_id = None
        near_ids = []
        for cand in cand_by_page.get(page, []):
            d = distance_point_to_geometry(center, cand)
            if best_d is None or d < best_d:
                best_d = d
                best_id = cand.get("geometry_id")
            if d <= proximity_pt:
                near_ids.append(str(cand.get("geometry_id") or ""))
        if best_d is not None and best_d <= proximity_pt:
            hits += 1
            if best_id:
                collisions[str(best_id)] += 1
        label_rows.append(
            {
                "page": page,
                "raw_text": raw[:48],
                "preview_kind": gp.get("kind"),
                "nearest_member_distance": None if best_d is None else round(best_d, 2),
                "near_member_count": len(near_ids),
                "member_geometry_available": bool(
                    isinstance(mg, dict) and mg.get("available")
                ),
            }
        )

    n_labels = len(label_rows)
    shared = {gid: n for gid, n in collisions.items() if n >= 2}
    return {
        "document_id": document_id,
        "role": "member_geometry_ocr_qa",
        "pages_filter": sorted(pages) if pages else None,
        "proximity_pt": proximity_pt,
        "geometry_object_count": len(objects),
        "geometry_kind_counts": dict(kind_counts),
        "member_candidate_count": len(candidates),
        "page_retention": retention_rows,
        "structural_labels": n_labels,
        "struct_stroke_within_proximity": hits,
        "struct_stroke_coverage": round(hits / n_labels, 4) if n_labels else 0.0,
        "preview_kind_counts": dict(preview_kinds),
        "member_geometry_available_count": member_available,
        "member_geometry_available_rate": (
            round(member_available / n_labels, 4) if n_labels else 0.0
        ),
        "primitives_claimed_by_multiple_labels": len(shared),
        "max_labels_per_stroke": max(shared.values()) if shared else 0,
        "sample_labels": label_rows[:25],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--pages", default=None, help="e.g. 10-16 or 10,12,13")
    parser.add_argument("--proximity-pt", type=float, default=50.0)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = summarize(
        args.document_id,
        pages=_parse_pages(args.pages),
        proximity_pt=args.proximity_pt,
    )
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
