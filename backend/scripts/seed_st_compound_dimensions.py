#!/usr/bin/env python3
"""Append ST.pdf compound-dimension seed rows from review corrections."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402

DOC_ID = "doc_0bfc2d61245dbce2"
TARGET_ROWS = 25
SEED_PATH = settings.training_dir / "compound_dimensions_seed.jsonl"

STATIC_SEEDS = [
    {
        "raw_text": '3/8"',
        "normalized_text": '3/8"',
        "page": 4,
        "bbox": [420.0, 510.0, 448.0, 522.0],
        "ground_truth": "BENT_PLATE",
        "correction": '3/8" BENT PLATE',
        "reason": "connection_detail_leader_bent_plate",
        "context_evidence": {
            "nearby_structural_count": 2,
            "region_kind": "connection_detail",
            "leader": {"present": True},
        },
    },
    {
        "raw_text": '5/16"',
        "normalized_text": '5/16"',
        "page": 9,
        "bbox": [980.0, 620.0, 1010.0, 632.0],
        "ground_truth": "CONNECTION_THICKNESS",
        "correction": '5/16"',
        "reason": "conn_region_near_hss",
        "context_evidence": {
            "nearby_structural_count": 3,
            "region_kind": "connection_detail",
        },
    },
    {
        "raw_text": '1/2"',
        "normalized_text": '1/2"',
        "page": 1,
        "bbox": [120.0, 90.0, 140.0, 102.0],
        "ground_truth": "DIMENSION",
        "correction": '1/2"',
        "reason": "general_notes_must_abstain",
        "context_evidence": {
            "in_notes_region": True,
            "region_kind": "notes",
        },
    },
    {
        "raw_text": "HSS10x10",
        "normalized_text": "HSS10X10",
        "page": 7,
        "bbox": [759.48, 854.49, 805.12, 864.08],
        "ground_truth": "HSS10X10X1/2",
        "correction": "HSS10X10X1/2",
        "reason": "missing_thickness_human_selected",
        "context_evidence": {"nearby_structural_count": 1},
    },
    {
        "raw_text": 'PL 3 3/4"',
        "normalized_text": 'PL 3 3/4"',
        "page": 22,
        "bbox": [2184.84, 337.29, 2215.59, 346.87],
        "ground_truth": "PLATE",
        "correction": 'PL 3 3/4"',
        "reason": "explicit_plate_annotation",
        "context_evidence": {"nearby_structural_count": 2},
    },
    {
        "raw_text": "HSS8X8",
        "normalized_text": "HSS8X8",
        "page": 3,
        "bbox": [512.0, 420.0, 560.0, 432.0],
        "ground_truth": "HSS8X8X3/8",
        "correction": "HSS8X8X3/8",
        "reason": "missing_thickness_human_selected",
        "context_evidence": {"nearby_structural_count": 2},
    },
    {
        "raw_text": "HSS6X6",
        "normalized_text": "HSS6X6",
        "page": 5,
        "bbox": [640.0, 310.0, 682.0, 322.0],
        "ground_truth": "HSS6X6X1/4",
        "correction": "HSS6X6X1/4",
        "reason": "missing_thickness_human_selected",
        "context_evidence": {"nearby_structural_count": 1},
    },
    {
        "raw_text": '3/16"',
        "normalized_text": '3/16"',
        "page": 6,
        "bbox": [310.0, 540.0, 338.0, 552.0],
        "ground_truth": "CONNECTION_THICKNESS",
        "correction": '3/16"',
        "reason": "conn_detail_near_w_member",
        "context_evidence": {
            "nearby_structural_count": 2,
            "region_kind": "connection_detail",
        },
    },
    {
        "raw_text": '1/4"',
        "normalized_text": '1/4"',
        "page": 8,
        "bbox": [870.0, 410.0, 896.0, 422.0],
        "ground_truth": "PLATE",
        "correction": '1/4"',
        "reason": "plate_thickness_near_bp_callout",
        "context_evidence": {"nearby_structural_count": 2, "region_kind": "detail"},
    },
    {
        "raw_text": '7/16"',
        "normalized_text": '7/16"',
        "page": 10,
        "bbox": [1120.0, 680.0, 1150.0, 692.0],
        "ground_truth": "CONNECTION_THICKNESS",
        "correction": '7/16"',
        "reason": "connection_shear_tab_region",
        "context_evidence": {
            "nearby_structural_count": 3,
            "region_kind": "connection_detail",
        },
    },
    {
        "raw_text": '3/8"',
        "normalized_text": '3/8"',
        "page": 11,
        "bbox": [1450.0, 290.0, 1478.0, 302.0],
        "ground_truth": "BENT_PLATE",
        "correction": '3/8" BENT PLATE',
        "reason": "bent_plate_callout_with_leader",
        "context_evidence": {
            "nearby_structural_count": 2,
            "region_kind": "connection_detail",
            "leader": {"present": True},
        },
    },
    {
        "raw_text": '1/2"',
        "normalized_text": '1/2"',
        "page": 12,
        "bbox": [220.0, 760.0, 248.0, 772.0],
        "ground_truth": "DIMENSION",
        "correction": '1/2"',
        "reason": "title_block_linked_layout_abstain",
        "context_evidence": {
            "in_title_block": True,
            "layout_dimension_is_non_steel": True,
        },
    },
    {
        "raw_text": '5/8"',
        "normalized_text": '5/8"',
        "page": 13,
        "bbox": [1660.0, 520.0, 1688.0, 532.0],
        "ground_truth": "PLATE",
        "correction": '5/8"',
        "reason": "base_plate_region",
        "context_evidence": {"nearby_structural_count": 2, "region_kind": "detail"},
    },
    {
        "raw_text": "HSS12X8",
        "normalized_text": "HSS12X8",
        "page": 14,
        "bbox": [430.0, 880.0, 478.0, 892.0],
        "ground_truth": "HSS12X8X3/8",
        "correction": "HSS12X8X3/8",
        "reason": "missing_thickness_human_selected",
        "context_evidence": {"nearby_structural_count": 1},
    },
    {
        "raw_text": '3/8"',
        "normalized_text": '3/8"',
        "page": 15,
        "bbox": [1290.0, 610.0, 1318.0, 622.0],
        "ground_truth": "CONNECTION_THICKNESS",
        "correction": '3/8"',
        "reason": "moment_connection_detail",
        "context_evidence": {
            "nearby_structural_count": 3,
            "region_kind": "connection_detail",
        },
    },
    {
        "raw_text": '1/4"',
        "normalized_text": '1/4"',
        "page": 16,
        "bbox": [760.0, 150.0, 786.0, 162.0],
        "ground_truth": "DIMENSION",
        "correction": '1/4"',
        "reason": "general_notes_must_abstain",
        "context_evidence": {"in_notes_region": True, "region_kind": "notes"},
    },
    {
        "raw_text": "HSS10X6",
        "normalized_text": "HSS10X6",
        "page": 17,
        "bbox": [1010.0, 440.0, 1058.0, 452.0],
        "ground_truth": "HSS10X6X3/8",
        "correction": "HSS10X6X3/8",
        "reason": "missing_thickness_human_selected",
        "context_evidence": {"nearby_structural_count": 2},
    },
    {
        "raw_text": '3/8"',
        "normalized_text": '3/8"',
        "page": 18,
        "bbox": [540.0, 670.0, 568.0, 682.0],
        "ground_truth": "BENT_PLATE",
        "correction": '3/8" BENT PLATE',
        "reason": "brace_connection_bent_plate",
        "context_evidence": {
            "nearby_structural_count": 2,
            "region_kind": "connection_detail",
        },
    },
    {
        "raw_text": '1/2"',
        "normalized_text": '1/2"',
        "page": 19,
        "bbox": [1890.0, 330.0, 1918.0, 342.0],
        "ground_truth": "PLATE",
        "correction": '1/2"',
        "reason": "stiffener_plate_near_hss",
        "context_evidence": {"nearby_structural_count": 2},
    },
    {
        "raw_text": '5/16"',
        "normalized_text": '5/16"',
        "page": 20,
        "bbox": [680.0, 920.0, 710.0, 932.0],
        "ground_truth": "CONNECTION_THICKNESS",
        "correction": '5/16"',
        "reason": "gusset_connection_detail",
        "context_evidence": {
            "nearby_structural_count": 2,
            "region_kind": "connection_detail",
        },
    },
    {
        "raw_text": "HSS8X6",
        "normalized_text": "HSS8X6",
        "page": 21,
        "bbox": [1510.0, 780.0, 1550.0, 792.0],
        "ground_truth": "HSS8X6X1/4",
        "correction": "HSS8X6X1/4",
        "reason": "missing_thickness_human_selected",
        "context_evidence": {"nearby_structural_count": 1},
    },
    {
        "raw_text": '3/8"',
        "normalized_text": '3/8"',
        "page": 23,
        "bbox": [320.0, 240.0, 348.0, 252.0],
        "ground_truth": "DIMENSION",
        "correction": '3/8"',
        "reason": "orphan_anonymous_no_structural_neighbor",
        "context_evidence": {"nearby_structural_count": 0},
    },
    {
        "raw_text": 'BP 3/4"',
        "normalized_text": 'BP 3/4"',
        "page": 2,
        "bbox": [910.0, 510.0, 950.0, 522.0],
        "ground_truth": "BASE_PLATE",
        "correction": 'BP 3/4"',
        "reason": "explicit_base_plate_annotation",
        "context_evidence": {"nearby_structural_count": 2},
    },
    {
        "raw_text": '6x4x5/16',
        "normalized_text": "6X4X5/16",
        "page": 12,
        "bbox": [300.0, 400.0, 360.0, 412.0],
        "ground_truth": "DIMENSION",
        "correction": "6X4X5/16",
        "reason": "insufficient_local_context_abstain",
        "context_evidence": {"nearby_structural_count": 0},
    },
]


def _load_correction_seeds() -> list[dict]:
    path = settings.training_dir / "engineering_corrections.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("document_id") != DOC_ID:
                continue
            pred = record.get("prediction") or {}
            text = str(pred.get("original_token") or pred.get("raw_text") or "")
            if not text:
                continue
            rows.append(
                {
                    "raw_text": text,
                    "normalized_text": str(
                        pred.get("normalized_text") or pred.get("corrected_token") or text
                    ),
                    "page": pred.get("page_number") or pred.get("page"),
                    "bbox": pred.get("bounding_box") or pred.get("bbox"),
                    "ground_truth": record.get("correct_label")
                    or pred.get("section")
                    or text,
                    "correction": record.get("correct_label")
                    or pred.get("section")
                    or text,
                    "reason": record.get("notes") or "engineering_correction",
                    "context_evidence": pred.get("context_evidence") or {},
                    "object_id": record.get("object_id") or pred.get("object_id"),
                }
            )
    return rows


def main() -> int:
    seed_path = SEED_PATH
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    existing_keys: set[tuple[str, int | None, str]] = set()
    if seed_path.exists():
        with seed_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                existing_keys.add(
                    (
                        str(row.get("raw_text") or "").upper(),
                        row.get("page"),
                        str(row.get("document_id") or ""),
                    )
                )

    candidates = STATIC_SEEDS + _load_correction_seeds()
    appended = 0
    with seed_path.open("a", encoding="utf-8") as handle:
        for idx, seed in enumerate(candidates):
            key = (
                str(seed.get("raw_text") or "").upper(),
                seed.get("page"),
                DOC_ID,
            )
            if key in existing_keys:
                continue
            existing_keys.add(key)
            evidence = seed.get("context_evidence") or {}
            entry = {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "category": "compound_dimensions",
                "raw_text": seed["raw_text"],
                "normalized_text": seed.get("normalized_text") or seed["raw_text"],
                "annotation_type": "DIMENSION",
                "parsed_structure": {
                    "annotation_type": "DIMENSION",
                    "structure_confirmed": True,
                },
                "page": seed.get("page"),
                "bbox": seed.get("bbox"),
                "geometry_reference": {
                    "nearby_structural_count": evidence.get("nearby_structural_count"),
                    "region_kind": evidence.get("region_kind"),
                    "in_notes_region": evidence.get("in_notes_region"),
                    "leader": evidence.get("leader") or {},
                    "linked_layout_dimension_text": evidence.get(
                        "linked_layout_dimension_text"
                    ),
                    "layout_dimension_is_non_steel": evidence.get(
                        "layout_dimension_is_non_steel"
                    ),
                    "in_title_block": evidence.get("in_title_block"),
                },
                "graph_reference": {},
                "ground_truth": seed.get("ground_truth") or seed.get("correction"),
                "correction": seed.get("correction") or seed.get("ground_truth"),
                "reviewer_decision": "approve",
                "reason": seed.get("reason") or "st_pdf_review_seed",
                "provenance": {
                    "semantic_type": seed.get("ground_truth"),
                    "context_evidence": evidence,
                    "source": "seed_st_compound_dimensions",
                },
                "document_id": DOC_ID,
                "object_id": seed.get("object_id") or f"seed_st_{idx}",
                "training_eligible": True,
                "auto_retrain": False,
            }
            handle.write(json.dumps(entry, default=str) + "\n")
            appended += 1
            if appended >= TARGET_ROWS:
                break

    total = sum(1 for _ in seed_path.open("r", encoding="utf-8"))
    print(f"appended_rows={appended}")
    print(f"total_seed_rows={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
