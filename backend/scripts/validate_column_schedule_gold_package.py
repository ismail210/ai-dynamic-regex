"""Validate the two-stage column-schedule reviewer package.

Schema validity and reviewer approval are separate results. Pending or unsure
records are valid annotations, but they do not unlock the matrix parser. The
parser gate depends only on extraction approval for development pages;
physical review may remain ``UNSURE``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.build_column_schedule_gold_package import FIELDS, REVIEW_STATES

APPROVED_STATES = frozenset({"APPROVED", "CORRECTED"})
REQUIRED_EXTRACTION_FIELDS = frozenset(
    {
        "record_id",
        "project_id",
        "document_id",
        "page_number",
        "schedule_id",
        "schedule_class",
        "region_bbox",
        "location_or_grid_raw",
        "level_raw",
        "raw_cell_text",
        "catalog_valid",
        "lifecycle_status",
        "source_cell_bbox",
        "proposal_method",
        "extraction_review_status",
        "physical_review_status",
    }
)
REQUIRED_PHYSICAL_FIELDS = frozenset(
    {
        "physical_semantics",
        "member_extent",
        "continuation_inheritance",
        "physical_segment_count",
        "plan_corroboration_status",
    }
)


def validate_record(record: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    record_id = str(record.get("record_id") or "<missing-record-id>")
    missing = sorted((REQUIRED_EXTRACTION_FIELDS | REQUIRED_PHYSICAL_FIELDS) - set(record))
    if missing:
        errors.append(f"{record_id}: missing fields {missing}")
    if "reviewer_status" in record:
        errors.append(f"{record_id}: legacy reviewer_status must be migrated")
    for field in ("extraction_review_status", "physical_review_status"):
        state = record.get(field)
        if state not in REVIEW_STATES:
            errors.append(f"{record_id}: invalid {field}={state!r}")
    if record.get("catalog_valid") is True and not record.get("canonical_section"):
        errors.append(f"{record_id}: catalog_valid requires canonical_section")
    count = record.get("physical_segment_count")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 0):
        errors.append(f"{record_id}: physical_segment_count must be a non-negative integer or null")
    return errors


def summarize(records: Iterable[Dict[str, Any]], development_pages: set[Tuple[str, int]]) -> Dict[str, Any]:
    rows = list(records)
    extraction = Counter(str(row.get("extraction_review_status")) for row in rows)
    physical = Counter(str(row.get("physical_review_status")) for row in rows)
    development = [
        row
        for row in rows
        if (str(row.get("document_id") or ""), int(row.get("page_number") or 0))
        in development_pages
    ]
    return {
        "records": len(rows),
        "extraction": dict(sorted(extraction.items())),
        "physical": dict(sorted(physical.items())),
        "development_records": len(development),
        "matrix_parser_unblocked": bool(development)
        and all(row.get("extraction_review_status") in APPROVED_STATES for row in development),
    }


def validate_package(package_dir: Path) -> Dict[str, Any]:
    manifest_path = package_dir / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: List[str] = []
    records: List[Dict[str, Any]] = []
    development_pages: set[Tuple[str, int]] = set()
    for page in manifest.get("pages") or []:
        document_id = str(page.get("document_id") or "")
        page_number = int(page.get("page") or 0)
        if page.get("role") == "development":
            development_pages.add((document_id, page_number))
        path = package_dir / str(page.get("prefill_file") or "")
        page_records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if len(page_records) != int(page.get("records") or 0):
            errors.append(
                f"{path.name}: manifest says {page.get('records')} records, found {len(page_records)}"
            )
        records.extend(page_records)
    ids = [str(row.get("record_id") or "") for row in records]
    duplicates = sorted(record_id for record_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate record ids: {duplicates}")
    for record in records:
        errors.extend(validate_record(record))
        unexpected = sorted(set(record) - set(FIELDS))
        if unexpected:
            errors.append(f"{record.get('record_id')}: unexpected fields {unexpected}")
    return {
        "valid": not errors,
        "errors": errors,
        "summary": summarize(records, development_pages),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate column-schedule reviewer annotations.")
    parser.add_argument("package_dir", type=Path)
    args = parser.parse_args()
    result = validate_package(args.package_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
