"""Completion audit (Section 42-43): scrutinize source-verified completion
behavior on real projects rather than trusting the raw count.

For each project in the pilot with at least one drawing-note abbreviation
rule, this reuses the SAME extractor the demo uses
(services.semantic_document_service.extract_abbreviation_note_rules) against
the real PDF, then reuses drawing_language_profile.resolve_completion to see
exactly which bare-shorthand annotations would be completed, by which rule,
on which page, and records scope explicitly.

Scope note (Section 43): the current implementation supports exactly two
scopes -- a specific page list, or "document-wide" (empty page list). It
does NOT support sheet-set/plan-family scoping. That is stated here
explicitly rather than implied to be finer-grained than it is.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import read_jsonl, write_json, write_jsonl  # noqa: E402
from services.pdf_parser import extract_document_structure  # noqa: E402
from services.semantic_document_service import extract_abbreviation_note_rules  # noqa: E402
from services.semantic_preprocessor.drawing_language_profile import resolve_completion  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    out_dir: Path = args.output
    mined = list(read_jsonl(out_dir / "clean" / "mined_annotations.jsonl"))
    incomplete = [a for a in mined if a["category"] == "INCOMPLETE_OR_SHORTHAND"]

    # Group incomplete (bare shorthand) annotations by document so we only
    # re-extract each PDF's notes once.
    by_doc: dict[str, list[dict]] = {}
    for a in incomplete:
        by_doc.setdefault(a["document_sha256"], []).append(a)

    # The corpus root to re-open PDFs from -- read from the Phase A summary
    # rather than hardcoding it a second time.
    import json
    inv_summary = json.loads((out_dir / "inventory" / "summary.json").read_text(encoding="utf-8"))
    project_root = Path(inv_summary["input_root"])

    audit_rows = []

    rules_cache: dict[str, list[dict]] = {}
    for sha, annotations in by_doc.items():
        rel_path = annotations[0]["relative_path"]
        pdf_path = project_root / rel_path
        if not pdf_path.exists():
            continue
        if sha not in rules_cache:
            try:
                structure = extract_document_structure(str(pdf_path))
            except Exception as exc:  # noqa: BLE001
                print(f"skip {rel_path}: {exc}")
                continue
            rules_cache[sha] = extract_abbreviation_note_rules(structure)
        rules = rules_cache[sha]
        if not rules:
            continue

        for a in annotations:
            trigger = a["primary_label"]
            resolution = resolve_completion(trigger, a["page"], rules)
            audit_rows.append({
                "project_id": a["project_id"],
                "document_sha256": sha,
                "trigger": trigger,
                "target_page": a["page"],
                "annotation_id": a["annotation_id"],
                "would_complete": resolution.allowed,
                "canonical_result": resolution.canonical,
                "resolution_reason": resolution.reason,
                "evidence_rule_ids": resolution.evidence_ids,
            })

    write_jsonl(out_dir / "inventory" / "completion_audit.jsonl", audit_rows)

    completed = [r for r in audit_rows if r["would_complete"]]
    by_trigger: dict[str, dict] = {}
    for r in completed:
        key = f"{r['project_id']}::{r['trigger']}"
        entry = by_trigger.setdefault(key, {
            "project_id": r["project_id"], "trigger": r["trigger"],
            "canonical_result": r["canonical_result"], "target_pages": set(), "count": 0,
        })
        entry["target_pages"].add(r["target_page"])
        entry["count"] += 1
    trigger_summary = [
        {**v, "target_pages": sorted(v["target_pages"])} for v in by_trigger.values()
    ]

    summary = {
        "incomplete_shorthand_total": len(incomplete),
        "documents_with_any_note_rules": sum(1 for v in rules_cache.values() if v),
        "documents_with_no_note_rules": sum(1 for v in rules_cache.values() if not v),
        "resolvable_total": len(audit_rows),
        "would_complete_total": len(completed),
        "would_complete_by_reason": _counts(audit_rows, "resolution_reason"),
        "distinct_trigger_project_pairs_completed": len(trigger_summary),
        "supported_scopes": ["document_wide (empty scope.pages)", "explicit page list"],
        "unsupported_scopes": ["sheet_set", "plan_family", "page_range (contiguous)"],
    }
    write_json(out_dir / "inventory" / "completion_audit_summary.json", {"summary": summary, "by_trigger": trigger_summary})
    print(json.dumps(summary, indent=2))


def _counts(rows, key):
    out: dict = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


if __name__ == "__main__":
    main()
