"""Read-only benchmark for project-rule / schedule-mark resolution.

Runs the *current* schedule-grid path (``baseline``) over a versioned gold
manifest, then scores discovery, row/cell relationships, mark->section
resolution, components, abstention, provenance and safety gates.

Never mutates predictions, review decisions, training files, or artifacts:
it only calls pure functions plus ``predict_from_context`` with an injected
adversarial fusion decoy (the semantic-lock stress test).

Usage (from ``backend/``)::

    python scripts/evaluate_project_rules.py MANIFEST.json --out DIR

Real PDFs are referenced through ``source.root_env`` (an environment
variable naming a local directory) so private drawings never enter git.
A document without ``gold`` is scored for discovery only and emitted to the
annotation queue.
"""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_BACKEND = _Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import argparse
import csv
import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import patch

from services.engineering import schedule_grid
from services.engineering.graph_builder import _intersects, section_family
from services.exact_section_predictor import catalog_valid_exact_section

MANIFEST_SCHEMA_VERSION = "1.0"
HARNESS_VERSION = "1.0"

# Statuses under which a prediction is auto-accepted with no review.
_AUTO_STATUSES = {"exact_match", "normalized_match", "project_rule_resolved"}


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def load_manifest(path: Path) -> Dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    version = str(manifest.get("schema_version") or "")
    if version != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"manifest schema_version {version!r} != {MANIFEST_SCHEMA_VERSION}")
    return manifest


def _synthetic_words(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    words = []
    for page in pages:
        for y, items in page.get("lines") or []:
            for x, text in items:
                words.append(
                    {
                        "text": text,
                        "bbox": [float(x), float(y), float(x) + 6.0 * len(text), float(y) + 8.0],
                        "page_number": int(page["page_number"]),
                    }
                )
    return words


def load_document(entry: Dict[str, Any]) -> Dict[str, Any]:
    """``{"words", "pages": {page: meta}, "source_type", "document"}``."""

    source = entry.get("source") or {}
    kind = source.get("kind")
    if kind == "synthetic_words":
        pages = source.get("pages") or []
        return {
            "words": _synthetic_words(pages),
            "pages": {
                int(p["page_number"]): {
                    "page_role": p.get("page_role", "UNKNOWN"),
                    "text_layer": p.get("text_layer", "vector"),
                }
                for p in pages
            },
            "source_type": "synthetic",
            "document": None,
        }
    if kind == "pdf":
        root = os.environ.get(str(source.get("root_env") or ""), "")
        path = Path(root) / str(source.get("path") or "")
        if not root or not path.is_file():
            raise FileNotFoundError(f"{entry.get('document_id')}: PDF not available ({path})")
        from services.engineering import legend_profile
        from services.pdf_parser import extract_document_structure

        document = extract_document_structure(str(path))
        roles = legend_profile.detect_context_pages(document)
        return {
            "words": document.get("words") or [],
            "pages": {
                page: {"page_role": roles.get(page, "DRAWING"), "text_layer": "vector"}
                for page in range(1, int(document.get("page_count") or 0) + 1)
            },
            "source_type": "real_pdf",
            "document": document,
        }
    raise ValueError(f"unknown source kind {kind!r}")


# --------------------------------------------------------------------------
# Pipelines under test. Each returns the same normalized shape.
# --------------------------------------------------------------------------


def _row(page, mark, size_text, section, roles, components, bbox, status, countable) -> Dict[str, Any]:
    return {
        "page": page,
        "mark": schedule_grid._compact_mark(mark),
        "size_text": size_text or "",
        "section": section or None,
        "role_tags": list(roles),
        "component_text": list(components),
        "bbox": bbox,
        "status": status,
        "countable_occurrence": countable,
    }


def run_baseline(words: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The production path, unchanged: ``build_schedule_grids`` + legacy map."""

    grids = schedule_grid.build_schedule_grids(words)
    rows = []
    for grid in grids:
        for row in grid["rows"]:
            roles = [grid["kind"]] if grid["kind"] != "schedule" else []
            roles += list(row.get("member_plate_roles") or [])
            if row.get("plate_role"):
                roles.append(row["plate_role"])
            rows.append(
                _row(
                    grid["page"],
                    row["mark"],
                    row.get("size_text"),
                    row.get("section"),
                    roles,
                    [row["plate_text"]] if row.get("plate_text") else [],
                    None,  # the baseline carries no row bbox
                    "resolved" if row.get("catalog_valid") else "rejected",
                    None,  # countability is not represented by the baseline
                )
            )
    return {
        "regions": [{"page": g["page"], "kind": g["kind"], "bbox": None} for g in grids],
        "rows": rows,
        "mark_map": schedule_grid.schedule_mark_map(grids),
        "conflicts": [],
        "rejections": [],
    }


PIPELINES: Dict[str, Callable[[List[Dict[str, Any]]], Dict[str, Any]]] = {
    "baseline": run_baseline,
}


# --------------------------------------------------------------------------
# Scoring helpers
# --------------------------------------------------------------------------


def _overlaps(a: Optional[List[float]], b: Optional[List[float]]) -> bool:
    return bool(a) and bool(b) and _intersects(a, b, pad=0.0)


def _compact(text: str) -> str:
    return re.sub(r"[^A-Z0-9/.]", "", str(text or "").upper())


def _ratio(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def _wilson(num: int, den: int, z: float = 1.96) -> Optional[List[float]]:
    if not den:
        return None
    p = num / den
    centre = p + z * z / (2 * den)
    margin = z * ((p * (1 - p) + z * z / (4 * den)) / den) ** 0.5
    scale = 1 + z * z / den
    return [round(max(0.0, (centre - margin) / scale), 4), round(min(1.0, (centre + margin) / scale), 4)]


def _classify(passed: bool, baseline_expectation: str, pipeline: str) -> str:
    if passed:
        return "pass"
    if baseline_expectation in {"unsupported", "known_defect"}:
        return f"expected_{baseline_expectation}"
    return "regression" if pipeline == "baseline" else "fail"


# --------------------------------------------------------------------------
# Document scoring
# --------------------------------------------------------------------------


def score_document(entry: Dict[str, Any], loaded: Dict[str, Any], pipeline: str, output: Dict[str, Any]) -> Dict[str, Any]:
    gold = entry.get("gold")
    doc_meta = {
        "document_id": entry["document_id"],
        "project_id": entry.get("project_id"),
        "template_family": entry.get("template_family"),
        "source_type": loaded["source_type"],
        "pipeline": pipeline,
    }
    pred_rows = output["rows"]
    counters: Dict[str, int] = defaultdict(int)
    for row in pred_rows:
        if row["status"] == "resolved":
            counters["resolved_rows"] += 1
            if row["page"] and row["size_text"] and row["bbox"]:
                counters["resolved_rows_with_provenance"] += 1
        if row["countable_occurrence"] is True:
            counters["false_occurrence_rows"] += 1
    for mark, section in output["mark_map"].items():
        counters["map_entries"] += 1
        if catalog_valid_exact_section(section):
            counters["map_catalog_valid"] += 1
        else:
            counters["invalid_catalog_auto_accept"] += 1
    vision_pages = {p for p, m in loaded["pages"].items() if m["page_role"] == "VISION_REQUIRED"}
    counters["fabricated_rows_on_vision_pages"] = sum(1 for r in pred_rows if r["page"] in vision_pages)

    row_results: List[Dict[str, Any]] = []
    region_results: List[Dict[str, Any]] = []
    if gold is None:
        discovered = [
            {k: row[k] for k in ("page", "mark", "size_text", "section", "status", "role_tags", "component_text", "bbox")}
            for row in pred_rows
        ]
        return {
            **doc_meta,
            "labelled": False,
            "counters": dict(counters),
            "regions": region_results,
            "rows": row_results,
            "discovered_regions": output["regions"],
            "discovered_rows": discovered,
            "rejections": output["rejections"],
            "conflicts": output["conflicts"],
        }

    for region in gold.get("regions") or []:
        if not region.get("rule_bearing", True):
            continue
        page_found = any(r["page"] == region["page"] for r in output["regions"])
        found = any(
            r["page"] == region["page"]
            and (
                _overlaps(r["bbox"], region.get("bbox"))
                if r["bbox"] and region.get("bbox")
                else r["kind"] == region.get("kind")
            )
            for r in output["regions"]
        )
        expectation = region.get("baseline", "supported")
        region_results.append(
            {
                **doc_meta,
                "region_id": region["region_id"],
                "page": region["page"],
                "kind": region.get("kind"),
                "page_found": page_found,
                "region_found": found,
                "outcome": _classify(found, expectation, pipeline),
                "note": region.get("note", ""),
            }
        )

    by_mark: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in pred_rows:
        by_mark[row["mark"]].append(row)
    for grow in gold.get("rows") or []:
        mark = schedule_grid._compact_mark(grow["mark"])
        expected_status = grow["expected_status"]
        expected_section = grow.get("primary_section")
        candidates = [r for r in by_mark.get(mark, []) if r["page"] == grow["page"]]
        row = candidates[0] if candidates else None
        mapped = output["mark_map"].get(mark)
        if expected_status == "resolved":
            status_ok = mapped == expected_section
        elif expected_status == "review":
            status_ok = mapped is None and mark in output["conflicts"]
        else:
            status_ok = mapped is None
        cell_ok = bool(row) and (row["section"] == expected_section) and (
            _compact(grow.get("size_text_raw", "")) in _compact(row["size_text"])
        )
        roles_ok = bool(row) and set(grow.get("role_tags") or []) <= set(row["role_tags"])
        comp_expected = [_compact(c) for c in grow.get("component_text") or []]
        comp_ok = bool(row) and all(any(c in _compact(t) for t in row["component_text"]) for c in comp_expected)
        qty_expected = grow.get("quantity_per_assembly")
        # No pipeline emits quantity-per-assembly yet: any gold quantity is a miss.
        qty_ok = qty_expected is None
        prov_ok = bool(row) and bool(row["bbox"]) and bool(row["size_text"]) and bool(row["page"])
        expectation = grow.get("baseline", "supported")
        row_results.append(
            {
                **doc_meta,
                "row_id": grow["row_id"],
                "page": grow["page"],
                "mark": mark,
                "family": section_family(expected_section or "") or "NONE",
                "expected_status": expected_status,
                "expected_section": expected_section,
                "predicted_section": mapped,
                "row_found": bool(row),
                "status_ok": status_ok,
                "cell_ok": cell_ok,
                "roles_ok": roles_ok,
                "has_components": bool(comp_expected),
                "components_ok": comp_ok,
                "has_quantity": qty_expected is not None,
                "quantity_ok": qty_ok,
                "provenance_ok": prov_ok,
                "outcome": _classify(status_ok, expectation, pipeline),
                "note": grow.get("note", ""),
            }
        )
    return {**doc_meta, "labelled": True, "counters": dict(counters), "regions": region_results, "rows": row_results}


# --------------------------------------------------------------------------
# Token cases: semantic lock / terminology under adversarial fusion context
# --------------------------------------------------------------------------


def _decoy_fusion(section: str):
    from services.multimodal.encoder_contracts import AttentionResult, FusedFeatures, UnifiedFusionResult

    return UnifiedFusionResult(
        section=section,
        confidence=0.95,
        contributions={"text": 0.2, "geometry": 0.4, "graph": 0.4},
        attention=AttentionResult(weights={"text": 0.2, "geometry": 0.4, "graph": 0.4}, logits={}),
        fused_features=FusedFeatures(vector=[], modality_slices={}, availability={}, encoders={}),
        candidate_scores=[{"shape": section, "score": 0.95}],
        reasons=["adversarial decoy"],
    )


def run_token_case(case: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
    from services.prediction.orchestrator import predict_from_context

    text = case["text"]
    context = {
        "token": {"text": text, "normalized_text": text, "raw_text": text, "confidence": 0.5},
        "document": document,
        "geometry": {"objects": []},
        "graph": {"nodes": [], "edges": []},
    }
    started = time.perf_counter()
    with patch(
        "services.prediction.orchestrator.unified_multimodal_fusion.predict",
        return_value=_decoy_fusion(case["decoy_section"]),
    ):
        result = predict_from_context(context)
    latency_ms = (time.perf_counter() - started) * 1000.0
    status = str((result.get("comparison") or {}).get("match_status") or "")
    section = str(result.get("section") or "")
    confidence = float(((result.get("confidence") or {}).get("overall")) or 0.0)
    auto = status in _AUTO_STATUSES and not result.get("needs_review")
    expect = case["expect"]
    expected_section = case.get("expected_section")
    if expect == "locked":
        passed = auto and section == expected_section and confidence >= 1.0
    elif expect == "rule_resolved":
        passed = auto and status == "project_rule_resolved" and section == expected_section
    elif expect == "not_auto_accepted":
        passed = not auto
    elif expect == "component_not_rolled":
        passed = bool(result.get("plate_annotation_type")) and not section
    else:
        raise ValueError(f"unknown expect {expect!r}")
    return {
        "case_id": case["case_id"],
        "text": text,
        "expect": expect,
        "expected_section": expected_section,
        "decoy_section": case["decoy_section"],
        "section": section,
        "match_status": status,
        "confidence": confidence,
        "needs_review": bool(result.get("needs_review")),
        "takeoff_eligible": result.get("takeoff_eligible"),
        "auto_accepted": auto,
        # Context overrode the exact label (decoy won), or the correct label
        # was demoted (review / reduced confidence).
        "semantic_lock_violation": expect == "locked"
        and not passed
        and section in {case["decoy_section"], expected_section},
        "wrong_auto_accept": auto and expect != "component_not_rolled" and section != expected_section,
        "latency_ms": round(latency_ms, 2),
        "passed": passed,
        "outcome": _classify(passed, case.get("baseline", "supported"), "baseline"),
        "note": case.get("note", ""),
    }


def _region_token_exposure(loaded: Dict[str, Any], output: Dict[str, Any]) -> Dict[str, Any]:
    """Engineering tokens inside discovered schedule regions whose page is not
    a context page: an upper bound on definition text that ``context_scope``
    leaves ``takeoff_eligible`` (its detail-sheet demotion is not modelled)."""

    tokens = loaded["document"].get("engineering_tokens") or []
    context_pages = {p for p, m in loaded["pages"].items() if m["page_role"] != "DRAWING"}
    inside = eligible = 0
    for token in tokens:
        page = int(token.get("page_number", token.get("page", 0)) or 0)
        bbox = token.get("bbox") or []
        if len(bbox) < 4:
            continue
        if any(r["page"] == page and _overlaps(r["bbox"], bbox) for r in output["regions"] if r["bbox"]):
            inside += 1
            eligible += page not in context_pages
    keyword_pages = {
        int(w.get("page_number", 0))
        for w in loaded["words"]
        if "SCHEDULE" in str(w.get("text") or "").upper()
    }
    covered = {r["page"] for r in output["regions"]}
    return {
        "tokens_in_regions": inside,
        "tokens_in_regions_on_drawing_pages": eligible,
        "schedule_keyword_pages": len(keyword_pages),
        "schedule_keyword_pages_uncovered": sorted(keyword_pages - covered),
    }


def annotation_queue(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every discovered row of every unlabelled document, for a reviewer."""

    queue = []
    for name, pipeline in report["pipelines"].items():
        for doc in pipeline["documents"]:
            if doc["labelled"]:
                continue
            for row in doc.get("discovered_rows") or []:
                queue.append({"pipeline": name, "document_id": doc["document_id"], "project_id": doc["project_id"], **row})
    return queue


def cross_document_leaks(mark_maps: Dict[str, Dict[str, str]], projects: Dict[str, str]) -> List[Dict[str, str]]:
    """Resolve every mark in its own document (warming any cache the resolver
    might grow), then against every other project's document: a hit there
    that B's own map does not define is a leak."""

    for map_a in mark_maps.values():
        for mark in map_a:
            schedule_grid.resolve_schedule_mark(mark, {"schedule_mark_map": map_a})
    leaks = []
    for doc_a, map_a in mark_maps.items():
        for doc_b, map_b in mark_maps.items():
            if projects[doc_a] == projects[doc_b]:
                continue
            for mark in map_a:
                if mark in map_b:
                    continue
                if schedule_grid.resolve_schedule_mark(mark, {"schedule_mark_map": map_b}):
                    leaks.append({"mark": mark, "from": doc_a, "into": doc_b})
    return leaks


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def _row_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    resolved = [r for r in rows if r["expected_status"] == "resolved"]
    abstain = [r for r in rows if r["expected_status"] in {"abstain", "review"}]
    predicted = [r for r in rows if r["predicted_section"]]
    correct = [r for r in resolved if r["status_ok"]]
    comps = [r for r in rows if r["has_components"]]
    qty = [r for r in rows if r["has_quantity"]]
    return {
        "gold_rows": len(rows),
        "row_found_rate": _ratio(sum(r["row_found"] for r in rows), len(rows)),
        "cell_relationship_accuracy": _ratio(sum(r["cell_ok"] for r in resolved), len(resolved)),
        "mark_to_section_precision": _ratio(
            sum(1 for r in predicted if r["predicted_section"] == r["expected_section"] and r["expected_status"] == "resolved"),
            len(predicted),
        ),
        "mark_to_section_recall": _ratio(len(correct), len(resolved)),
        "mark_to_section_recall_ci95": _wilson(len(correct), len(resolved)),
        "correct_abstention_rate": _ratio(sum(r["status_ok"] for r in abstain), len(abstain)),
        "component_role_accuracy": _ratio(sum(r["roles_ok"] for r in rows), len(rows)),
        "component_dimension_accuracy": _ratio(sum(r["components_ok"] for r in comps), len(comps)),
        "quantity_per_assembly_accuracy": _ratio(sum(r["quantity_ok"] for r in qty), len(qty)),
        "provenance_completeness": _ratio(sum(r["provenance_ok"] for r in correct), len(correct)),
    }


def _group(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(key))].append(row)
    return {name: _row_metrics(items) for name, items in sorted(buckets.items())}


def evaluate(manifest: Dict[str, Any], pipelines: Optional[List[str]] = None) -> Dict[str, Any]:
    names = pipelines or list(PIPELINES)
    loaded_docs: Dict[str, Dict[str, Any]] = {}
    skipped: List[Dict[str, str]] = []
    for entry in manifest.get("documents") or []:
        try:
            loaded_docs[entry["document_id"]] = load_document(entry)
        except FileNotFoundError as exc:
            skipped.append({"document_id": entry["document_id"], "reason": str(exc)})

    # Warm the lazily loaded AISC catalog so the first pipeline timed does not
    # pay for it.
    schedule_grid._catalog_spelling("W8X21")
    results: Dict[str, Any] = {}
    outputs: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for name in names:
        docs = []
        outputs[name] = {}
        for entry in manifest.get("documents") or []:
            loaded = loaded_docs.get(entry["document_id"])
            if loaded is None:
                continue
            started = time.perf_counter()
            output = PIPELINES[name](loaded["words"])
            elapsed = (time.perf_counter() - started) * 1000.0
            outputs[name][entry["document_id"]] = output
            scored = score_document(entry, loaded, name, output)
            scored["latency_ms"] = round(elapsed, 2)
            if loaded["document"] is not None:
                scored["schedule_region_tokens"] = _region_token_exposure(loaded, output)
            docs.append(scored)
        rows = [r for d in docs for r in d["rows"]]
        regions = [r for d in docs for r in d["regions"]]
        counters: Dict[str, int] = defaultdict(int)
        for d in docs:
            for k, v in d["counters"].items():
                counters[k] += v
        gold_pages = {(r["document_id"], r["page"]) for r in regions}
        found_pages = {(r["document_id"], r["page"]) for r in regions if r["page_found"]}
        projects = {e["document_id"]: str(e.get("project_id")) for e in manifest.get("documents") or []}
        leaks = cross_document_leaks(
            {doc_id: out["mark_map"] for doc_id, out in outputs[name].items()},
            projects,
        )
        results[name] = {
            "documents": docs,
            "metrics": {
                "rule_bearing_page_recall": _ratio(len(found_pages), len(gold_pages)),
                "rule_bearing_region_recall": _ratio(sum(r["region_found"] for r in regions), len(regions)),
                "rule_bearing_region_recall_ci95": _wilson(sum(r["region_found"] for r in regions), len(regions)),
                **_row_metrics(rows),
                "catalog_valid_output_rate": _ratio(counters["map_catalog_valid"], counters["map_entries"]),
                "latency_ms_total": round(sum(d["latency_ms"] for d in docs), 2),
            },
            "by_project": _group(rows, "project_id"),
            "by_template_family": _group(rows, "template_family"),
            "by_source_type": _group(rows, "source_type"),
            "by_family": _group(rows, "family"),
            "safety": {
                "invalid_catalog_auto_accept": counters["invalid_catalog_auto_accept"],
                "schedule_rows_marked_countable": counters["false_occurrence_rows"],
                "resolved_rows_missing_provenance": counters["resolved_rows"] - counters["resolved_rows_with_provenance"],
                "fabricated_rows_on_vision_pages": counters["fabricated_rows_on_vision_pages"],
                "cross_project_leaks": len(leaks),
            },
            "leaks": leaks,
            "outcomes": {
                "rows": _count(r["outcome"] for r in rows),
                "regions": _count(r["outcome"] for r in regions),
            },
        }

    # Token cases always exercise the production orchestrator; the document
    # context is the *baseline* mark map (production behavior).
    token_results = []
    for case in manifest.get("token_cases") or []:
        ref = case.get("document_ref")
        document = {}
        if ref and ref in outputs.get("baseline", {}):
            document = {"schedule_mark_map": outputs["baseline"][ref]["mark_map"]}
        token_results.append(run_token_case(case, document))
    return {
        "harness_version": HARNESS_VERSION,
        "manifest_id": manifest.get("manifest_id"),
        "manifest_schema_version": manifest.get("schema_version"),
        "versions": _versions(),
        "skipped_documents": skipped,
        "pipelines": results,
        "token_cases": token_results,
        "token_safety": {
            "semantic_lock_violations": sum(t["semantic_lock_violation"] for t in token_results),
            "wrong_auto_accepts": sum(t["wrong_auto_accept"] for t in token_results),
            "outcomes": _count(t["outcome"] for t in token_results),
            "latency_ms_total": round(sum(t["latency_ms"] for t in token_results), 2),
        },
    }


def _count(values) -> Dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _versions() -> Dict[str, Any]:
    from config import settings
    from services.extraction_engine import EXTRACTION_VERSION

    return {
        "extraction_version": EXTRACTION_VERSION,
        "schedule_grid_enabled": settings.schedule_grid_enabled,
        "schedule_mark_map_enabled": settings.schedule_mark_map_enabled,
        "legend_profile_llm_enabled": settings.legend_profile_llm_enabled,
    }


# --------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------


def write_outputs(report: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "project_rule_benchmark.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    rows = [r for p in report["pipelines"].values() for d in p["documents"] for r in d["rows"]]
    _write_csv(out_dir / "project_rule_rows.csv", rows)
    _write_csv(out_dir / "project_rule_token_cases.csv", report["token_cases"])
    _write_csv(out_dir / "annotation_queue.csv", annotation_queue(report))
    (out_dir / "project_rule_benchmark.md").write_text(render_markdown(report), encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# Project-rule benchmark — {report.get('manifest_id')}",
        "",
        f"Harness {report['harness_version']} · versions `{json.dumps(report['versions'])}`",
        "",
    ]
    names = list(report["pipelines"])
    metric_keys = list(next(iter(report["pipelines"].values()))["metrics"]) if names else []
    lines += ["| metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key in metric_keys:
        lines.append(f"| {key} | " + " | ".join(str(report["pipelines"][n]["metrics"][key]) for n in names) + " |")
    lines += ["", "## Safety gates", "", "| gate | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key in next(iter(report["pipelines"].values()))["safety"] if names else []:
        lines.append(f"| {key} | " + " | ".join(str(report["pipelines"][n]["safety"][key]) for n in names) + " |")
    lines += ["", f"Token cases: `{json.dumps(report['token_safety'])}`", "", "## Row outcomes", ""]
    for name in names:
        lines.append(f"- **{name}** rows `{report['pipelines'][name]['outcomes']['rows']}` regions `{report['pipelines'][name]['outcomes']['regions']}`")
    lines += ["", "## Non-passing rows", "", "| pipeline | row | expected | predicted | outcome | note |", "|---|---|---|---|---|---|"]
    for name in names:
        for doc in report["pipelines"][name]["documents"]:
            for row in doc["rows"]:
                if row["outcome"] != "pass":
                    lines.append(
                        f"| {name} | {row['row_id']} | {row['expected_status']}:{row['expected_section']} "
                        f"| {row['predicted_section']} | {row['outcome']} | {row['note']} |"
                    )
    lines += ["", "## Token cases", "", "| case | text | expect | section | status | review | outcome |", "|---|---|---|---|---|---|---|"]
    for t in report["token_cases"]:
        lines.append(
            f"| {t['case_id']} | `{t['text']}` | {t['expect']}:{t['expected_section']} | {t['section']} "
            f"| {t['match_status']} | {t['needs_review']} | {t['outcome']} |"
        )
    unlabelled = [
        (name, doc)
        for name, pipeline in report["pipelines"].items()
        for doc in pipeline["documents"]
        if not doc["labelled"]
    ]
    if unlabelled:
        lines += [
            "",
            "## Unlabelled discovery (no gold; not an accuracy claim)",
            "",
            "| pipeline | document | regions | rows | resolved | conflicts | rejections | region tokens on drawing pages | ms |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for name, doc in unlabelled:
            rows = doc["discovered_rows"]
            exposure = doc.get("schedule_region_tokens") or {}
            lines.append(
                f"| {name} | {doc['document_id']} | {len(doc['discovered_regions'])} | {len(rows)} "
                f"| {sum(r['status'] == 'resolved' for r in rows)} | {len(doc['conflicts'])} "
                f"| {len(doc['rejections'])} | {exposure.get('tokens_in_regions_on_drawing_pages', '-')} | {doc['latency_ms']} |"
            )
        lines += ["", "| pipeline | document | page | mark | size text | section | status |", "|---|---|---|---|---|---|---|"]
        for name, doc in unlabelled:
            for row in doc["discovered_rows"]:
                lines.append(
                    f"| {name} | {doc['document_id']} | {row['page']} | {row['mark']} | {row['size_text'][:40]} "
                    f"| {row['section']} | {row['status']} |"
                )
    if report["skipped_documents"]:
        lines += ["", "Skipped (input unavailable): " + ", ".join(s["document_id"] for s in report["skipped_documents"])]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only project-rule benchmark.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pipelines", nargs="*", default=None, choices=sorted(PIPELINES))
    args = parser.parse_args(argv)
    report = evaluate(load_manifest(args.manifest), args.pipelines)
    write_outputs(report, args.out)
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
