"""Seven-PDF shadow discovery and impact benchmark for schedule quarantine.

No output is an accuracy claim: the corpus has no reviewer-approved gold.
The script never enables the production flag and never mutates extraction
tokens; it measures a side-artifact classification twice for determinism.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.database_loader import catalog_form
from services.engineering.schedule_region_quarantine import (
    _bbox,
    _document_id,
    _exact_section,
    _page,
    build_schedule_region_quarantine,
)
from services.extraction_engine import extract_engineering_document

ROOT_ENV = "ESTIMA3D_PROJECT_RULE_ROOT"
CORPUS = (
    {
        "project": "Burrville",
        "document_id": "REAL-Burrville",
        "path": "Burrville/Burrville ES - ST.pdf",
        "pages": {28: "development"},
    },
    {
        "project": "GCDC",
        "document_id": "REAL-GCDC",
        "path": "GCDC Building/GCDC Building 4 - ST1.pdf",
        "pages": {77: "development"},
    },
    {
        "project": "Springhill",
        "document_id": "REAL-Springhill",
        "path": "Springhill ES/ST - Springhill Lake.pdf",
        "pages": {26: "development"},
    },
    {
        "project": "Ketcham",
        "document_id": "REAL-Ketcham",
        "path": "Ketcham/Structure - Copy.pdf",
        "pages": {4: "held_out"},
    },
    {
        "project": "Sidwell",
        "document_id": "REAL-Sidwell",
        "path": "Sidwell/03 - SFSLS_251029_ISSUED FOR BID_2A_STRUCTURAL complied thru add 2.pdf",
        "pages": {43: "held_out"},
    },
    {
        "project": "H5 Herndon",
        "document_id": "REAL-H5",
        "path": "H5 Herndon/ST.pdf",
        "pages": {7: "existing_control", 8: "existing_control", 23: "reinforcing_control"},
    },
    {
        "project": "1200 K",
        "document_id": "REAL-1200K",
        "path": "1200 K/1200 K_Permit_Bid_Dwgs - Structural.pdf",
        "pages": {32: "fabricated_component_control"},
    },
)


def _stable(payload: Dict[str, Any]) -> str:
    without_time = json.loads(json.dumps(payload))
    for document in without_time.get("documents") or []:
        document.pop("parsing_runtime_ms", None)
        document.pop("region_runtime_ms", None)
    without_time.pop("total_parsing_runtime_ms", None)
    without_time.pop("total_region_runtime_ms", None)
    return json.dumps(without_time, sort_keys=True, separators=(",", ":"))


def _page_rows(
    entry: Dict[str, Any],
    document: Dict[str, Any],
    shadow: Dict[str, Any],
) -> List[Dict[str, Any]]:
    confident = {region["region_id"]: region for region in shadow["regions"]}
    rows: List[Dict[str, Any]] = []
    for page_number, role in sorted(entry["pages"].items()):
        counters: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for original, decision in zip(
            document.get("engineering_tokens") or [], shadow["decisions"]
        ):
            if _page(original) != page_number:
                continue
            section = _exact_section(original)
            if not section:
                continue
            bucket = counters[section]
            if original.get("takeoff_eligible") is not False:
                bucket["baseline_countable_section_tokens"] += 1
            if decision.get("region_id") in confident:
                bucket["tokens_inside_confident_schedule_regions"] += 1
            if decision.get("action") == "quarantined":
                bucket["shadow_quarantined_tokens"] += 1
                if original.get("takeoff_eligible") is not False:
                    bucket["eligible_token_delta"] -= 1
            if decision.get("reason") == "ambiguous_boundary":
                bucket["ambiguous_tokens_left_unchanged"] += 1
        for section in sorted(counters) or ["(none)"]:
            counts = counters[section]
            rows.append(
                {
                    "project": entry["project"],
                    "document_id": entry["document_id"],
                    "page": page_number,
                    "role": role,
                    "section": section,
                    "baseline_countable_section_tokens": counts[
                        "baseline_countable_section_tokens"
                    ],
                    "tokens_inside_confident_schedule_regions": counts[
                        "tokens_inside_confident_schedule_regions"
                    ],
                    "shadow_quarantined_tokens": counts["shadow_quarantined_tokens"],
                    "ambiguous_tokens_left_unchanged": counts[
                        "ambiguous_tokens_left_unchanged"
                    ],
                    "eligible_token_delta": counts["eligible_token_delta"],
                }
            )
    return rows


def _safety(document: Dict[str, Any], shadow: Dict[str, Any]) -> Dict[str, int]:
    semantic_lock_overrides = invalid_auto = counted_definitions = leaks = 0
    unquarantined_changes = 0
    regions = {region["region_id"]: region for region in shadow["regions"]}
    for original, classified, decision in zip(
        document.get("engineering_tokens") or [], shadow["tokens"], shadow["decisions"]
    ):
        if _exact_section(original) != _exact_section(classified):
            semantic_lock_overrides += 1
        if decision.get("action") != "quarantined":
            unquarantined_changes += int(classified != original)
        else:
            invalid_auto += int(not bool(catalog_form(str(decision.get("section") or ""))))
            counted_definitions += int(
                classified.get("takeoff_eligible") is not False
                or classified.get("countable_occurrence") is not False
            )
            region = regions.get(str(decision.get("region_id"))) or {}
            leaks += int(
                bool(_document_id(original, str(document.get("document_id") or "")))
                and bool(region.get("source_document_id"))
                and _document_id(original, str(document.get("document_id") or ""))
                != region.get("source_document_id")
            )
    return {
        "semantic_lock_overrides": semantic_lock_overrides,
        "invalid_catalog_auto_accepts": invalid_auto,
        "definition_rows_counted_in_shadow": counted_definitions,
        "cross_document_leaks": leaks,
        "unquarantined_token_changes": unquarantined_changes,
        "default_off_production_changes": int(
            "schedule_region_quarantine_shadow" in document
        ),
    }


def run(root: Path) -> Dict[str, Any]:
    documents: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    hard_gates: Dict[str, int] = defaultdict(int)
    for entry in CORPUS:
        path = root / entry["path"]
        started = time.perf_counter()
        document = extract_engineering_document(path, document_id=entry["document_id"])
        parsing_ms = (time.perf_counter() - started) * 1000.0
        before = json.dumps(document.get("engineering_tokens") or [], sort_keys=True, default=str)
        shadow = build_schedule_region_quarantine(document, source_path=path)
        after = json.dumps(document.get("engineering_tokens") or [], sort_keys=True, default=str)
        safety = _safety(document, shadow)
        safety["live_token_mutations"] = int(before != after)
        for key, value in safety.items():
            hard_gates[key] += value
        selected_regions = [
            region
            for region in shadow["regions"]
            if region["page_number"] in entry["pages"]
        ]
        selected_ambiguous = [
            region
            for region in shadow["ambiguous_regions"]
            if region["page_number"] in entry["pages"]
        ]
        page_rows = _page_rows(entry, document, shadow)
        rows.extend(page_rows)
        documents.append(
            {
                "project": entry["project"],
                "document_id": entry["document_id"],
                "pages": entry["pages"],
                "parsing_runtime_ms": round(parsing_ms, 3),
                "region_runtime_ms": shadow["region_runtime_ms"],
                "confident_regions": selected_regions,
                "ambiguous_regions": selected_ambiguous,
                "baseline_countable_section_tokens": sum(
                    row["baseline_countable_section_tokens"] for row in page_rows
                ),
                "shadow_quarantined_tokens": sum(
                    row["shadow_quarantined_tokens"] for row in page_rows
                ),
                "ambiguous_tokens_left_unchanged": sum(
                    row["ambiguous_tokens_left_unchanged"] for row in page_rows
                ),
                "eligible_token_delta": sum(row["eligible_token_delta"] for row in page_rows),
                "safety": safety,
            }
        )
    controls = [row for row in rows if row["role"].endswith("control")]
    return {
        "benchmark": "schedule_region_quarantine_shadow_discovery",
        "evidence_class": "unlabelled_real_corpus_discovery",
        "accuracy_claim": False,
        "reviewer_approved_gold": False,
        "documents": documents,
        "by_project_page_section": rows,
        "exclusion_control_quarantines": sum(
            row["shadow_quarantined_tokens"] for row in controls
        ),
        "hard_gates": dict(sorted(hard_gates.items())),
        "total_parsing_runtime_ms": round(
            sum(document["parsing_runtime_ms"] for document in documents), 3
        ),
        "total_region_runtime_ms": round(
            sum(document["region_runtime_ms"] for document in documents), 3
        ),
        "revit_ground_truth": "no_project_page_scoped_revit_ground_truth_identified_without_inference",
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Schedule-region quarantine — shadow discovery and impact",
        "",
        "This is unlabelled real-corpus discovery and impact measurement, not an accuracy result. Reviewer-approved gold is not available.",
        "",
        "| project | page | role | section | baseline eligible | inside confident region | quarantined | ambiguous unchanged | eligible delta |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["by_project_page_section"]:
        lines.append(
            f"| {row['project']} | {row['page']} | {row['role']} | {row['section']} "
            f"| {row['baseline_countable_section_tokens']} | {row['tokens_inside_confident_schedule_regions']} "
            f"| {row['shadow_quarantined_tokens']} | {row['ambiguous_tokens_left_unchanged']} "
            f"| {row['eligible_token_delta']} |"
        )
    lines += [
        "",
        "## Runtime and determinism",
        "",
        f"- Total PDF parsing runtime: {report['total_parsing_runtime_ms']} ms",
        f"- Total region runtime: {report['total_region_runtime_ms']} ms",
        f"- Run-to-run deterministic excluding timings: {report.get('run_to_run_deterministic')}",
        "",
        "## Hard safety gates",
        "",
    ]
    for gate, value in report["hard_gates"].items():
        lines.append(f"- `{gate}`: {value}")
    lines += [
        f"- Exclusion-control quarantines (unreviewed, not an error count): {report['exclusion_control_quarantines']}",
        "",
        f"Revit ground truth: `{report['revit_ground_truth']}`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark shadow schedule-region quarantine.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root_text = os.environ.get(ROOT_ENV, "")
    if not root_text:
        raise SystemExit(f"set {ROOT_ENV}")
    args.out.mkdir(parents=True, exist_ok=True)
    first = run(Path(root_text))
    second = run(Path(root_text))
    deterministic = _stable(first) == _stable(second)
    first["run_to_run_deterministic"] = deterministic
    second["run_to_run_deterministic"] = deterministic
    (args.out / "schedule_quarantine_run1.json").write_text(
        json.dumps(first, indent=2), encoding="utf-8"
    )
    (args.out / "schedule_quarantine_run2.json").write_text(
        json.dumps(second, indent=2), encoding="utf-8"
    )
    (args.out / "SCHEDULE_QUARANTINE_REPORT.md").write_text(
        render_markdown(first), encoding="utf-8"
    )
    print(render_markdown(first))
    return 0 if deterministic and not any(first["hard_gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
