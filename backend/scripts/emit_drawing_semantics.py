#!/usr/bin/env python3
"""Emit drawing_semantics.json for Phase 3 docs (Accuracy Track A8)."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_BACKEND = _Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import argparse
import json
from collections import defaultdict
from pathlib import Path

from services.prediction.drawing_semantics import (
    build_drawing_semantics,
    validate_drawing_semantics,
    write_drawing_semantics,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase3", default="june_phase3_results.json")
    parser.add_argument(
        "--out-dir",
        default="training/eval_cache_backups/accuracy_reports/drawing_semantics",
    )
    args = parser.parse_args()
    phase3 = json.loads(Path(args.phase3).read_text(encoding="utf-8"))
    by_doc = defaultdict(lambda: {"predictions": [], "context": [], "meta": {}})
    for row in phase3.get("records") or []:
        doc = row.get("document_id") or "unknown"
        bucket = row.get("bucket") or "predictions"
        pred = {
            "object_id": row.get("object_id"),
            "raw_text": row.get("raw_text"),
            "normalized_text": row.get("normalized_text"),
            "section": row.get("section"),
            "completion_status": row.get("completion_status"),
            "takeoff_eligible": row.get("takeoff_eligible"),
            "object_scope": row.get("object_scope"),
            "page_number": row.get("source_page"),
            "confidence": row.get("confidence"),
            "needs_review": row.get("needs_review"),
            "review_reason": row.get("review_reason"),
            "semantic_annotation": row.get("semantic_annotation"),
        }
        if bucket == "context_definitions":
            by_doc[doc]["context"].append(pred)
        else:
            by_doc[doc]["predictions"].append(pred)
        by_doc[doc]["meta"] = {
            "project": row.get("project"),
            "document_id": doc,
        }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for doc_id, payload_parts in by_doc.items():
        semantics = build_drawing_semantics(
            document_id=doc_id,
            source_file=str(payload_parts["meta"].get("project") or doc_id),
            predictions=payload_parts["predictions"],
            context_definitions=payload_parts["context"],
            pipeline_version="june_phase3_replay",
        )
        errors = validate_drawing_semantics(semantics)
        path = write_drawing_semantics(out_dir / f"{doc_id}_drawing_semantics.json", semantics)
        summary.append(
            {
                "document_id": doc_id,
                "path": str(path),
                "annotation_count": semantics["annotation_count"],
                "validation_errors": errors,
            }
        )

    summary_path = out_dir / "emit_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"documents": len(summary), "summary": summary_path.as_posix()}, indent=2))
    return 0 if all(not s["validation_errors"] for s in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
