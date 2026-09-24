"""Arbitrary-corpus validation of production extraction + shadow schedule quarantine.

Measurement only. Production flags stay at their committed defaults; the
shadow quarantine is called directly on a copy-safe side path and never
enabled. Absolute paths live only in the local manifest (``--local``);
everything written by ``report`` is sanitized.

Subcommands:
  inventory  hash/dedup PDFs from source roots, inventory workbooks, pair GT
  run        one full pass over the unique PDFs (subprocess per PDF)
  worker     internal: analyze one PDF, write one JSON
  report     compare two runs and write the sanitized report bundle
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import types
from collections import Counter, defaultdict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

PDF_EXT = ".pdf"
SHEET_EXT = (".xlsx", ".xls", ".xlsm", ".csv")
# Filenames that name a structural drawing set (whole-word, case-insensitive).
_STRUCTURAL_NAME = re.compile(r"(?<![A-Z])(ST\d*|STR|STRUCT|STRUCTURAL\d*|STRUCTURE)(?![A-Z])", re.I)
# Estimator copies / superseded sets: never primary, but still competing candidates.
_MARKUP_NAME = re.compile(r"MARK[\s_-]*UP|MARKEDUP|MARKED|HIGHLIGHT", re.I)
_OLD_DIR = re.compile(r"(^|/)(old)(/|$)", re.I)
_GT_DIR = re.compile(r"manual (markups|takeoff)", re.I)
# pdf_parser._new_id: f"{prefix}_{uuid4().hex[:12]}" -- the only random ids.
_RANDOM_ID = re.compile(r"_([0-9a-f]{12})\b")
# Runtime/timestamp fields only. ``built_at`` and ``summary_llm_latency_ms``
# are written by a cold legend-profile build (legend_profile_hook).
TIMING_KEYS = frozenset(
    {
        "parse_ms", "region_ms", "prediction_ms", "head_parse_ms", "wall_ms",
        "region_runtime_ms", "built_at", "summary_llm_latency_ms",
    }
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def dedup_pdfs(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One entry per SHA-256, keeping every source reference, stable order."""

    unique: Dict[str, Dict[str, Any]] = {}
    for record in records:
        entry = unique.setdefault(
            record["sha256"], {**record, "references": []}
        )
        entry["references"].append(
            {"source": record["source"], "relative_path": record["relative_path"]}
        )
    for entry in unique.values():
        entry["references"].sort(key=lambda ref: (ref["source"], ref["relative_path"]))
        first = entry["references"][0]
        entry["source"], entry["relative_path"] = first["source"], first["relative_path"]
        entry["filename"] = PurePosixPath(first["relative_path"]).name
    return sorted(unique.values(), key=lambda entry: (entry["source"], entry["relative_path"]))


def project_key(relative_path: str) -> Optional[str]:
    """``Testing Projects/NN - Name/...`` -> ``NN - Name``; None outside a project."""

    parts = PurePosixPath(relative_path).parts
    return parts[1] if len(parts) >= 3 and parts[0].lower() == "testing projects" else None


def _candidate_kind(relative_path: str) -> str:
    name = PurePosixPath(relative_path).name
    if _MARKUP_NAME.search(name):
        return "markup_copy"
    if _OLD_DIR.search(relative_path):
        return "superseded_old"
    if _STRUCTURAL_NAME.search(PurePosixPath(name).stem):
        return "structural"
    return "non_structural"


def pair_ground_truth(
    pdfs: List[Dict[str, Any]], workbooks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Conservative PDF<->workbook pairing, one decision per project with GT.

    Confident only when, inside one project folder: exactly one distinct
    workbook (by SHA-256) sits in a Manual Markups/Takeoff folder, exactly one
    distinct clean structural PDF exists, no superseded (``old``) structural
    set competes, and every markup copy has the clean set's page count.
    Anything else is ambiguous and excluded from accuracy scoring.
    """

    pdfs_by_project: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for pdf in pdfs:
        for ref in pdf["references"]:
            key = project_key(ref["relative_path"])
            if key:
                pdfs_by_project[key].setdefault(pdf["sha256"], {**pdf, "_ref": ref["relative_path"]})
    books_by_project: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for book in workbooks:
        key = project_key(book["relative_path"])
        if key and _GT_DIR.search(book["relative_path"]):
            books_by_project[key].setdefault(book["sha256"], book)

    decisions: List[Dict[str, Any]] = []
    for project in sorted(books_by_project):
        books = sorted(books_by_project[project].values(), key=lambda b: b["relative_path"])
        kinds: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for pdf in sorted(pdfs_by_project.get(project, {}).values(), key=lambda p: p["_ref"]):
            kinds[_candidate_kind(pdf["_ref"])].append(pdf)
        structural = kinds["structural"]
        evidence = [
            "workbook in project manual-takeoff folder",
            f"{len(books)} distinct workbook(s)",
            f"{len(structural)} clean structural PDF(s)",
            f"{len(kinds['superseded_old'])} superseded/old PDF(s)",
            f"{len(kinds['markup_copy'])} markup cop(ies)",
        ]
        reasons = []
        if len(books) != 1:
            reasons.append("multiple_distinct_workbooks")
        if len(structural) != 1:
            reasons.append("no_clean_structural_pdf" if not structural else "multiple_structural_pdfs")
        if any(_STRUCTURAL_NAME.search(PurePosixPath(p["_ref"]).stem) for p in kinds["superseded_old"]):
            reasons.append("superseded_structural_set_present")
        if structural and any(
            m.get("page_count") != structural[0].get("page_count") for m in kinds["markup_copy"]
        ):
            reasons.append("markup_copy_page_count_differs")
        decisions.append(
            {
                "project": project,
                "status": "confident" if not reasons else "ambiguous",
                "reasons": reasons,
                "evidence": evidence,
                "workbooks": [b["relative_path"] for b in books],
                "workbook_sha256": [b["sha256"] for b in books],
                "pdf_sha256": structural[0]["sha256"] if len(structural) == 1 else None,
                "pdf_relative_path": structural[0]["_ref"] if len(structural) == 1 else None,
                "candidates": sorted(p["_ref"] for group in kinds.values() for p in group),
            }
        )
    return decisions


def canonicalize_random_ids(payload: Any) -> Any:
    """Replace pdf_parser uuid4 hex ids by first-appearance indices.

    Serialization is key-sorted and lists keep document order (words and
    tokens are page/reading ordered), so identical documents canonicalize
    identically. Only the 12-hex id body is rewritten; semantic text is not.
    """

    raw = json.dumps(payload, sort_keys=True, default=str)
    seen: Dict[str, int] = {}
    return json.loads(
        _RANDOM_ID.sub(lambda m: "_#%d" % seen.setdefault(m.group(1), len(seen)), raw)
    )


def digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(canonicalize_random_ids(strip_timings(payload)), sort_keys=True).encode("utf-8")
    ).hexdigest()


# Free-form Drawing Summary LLM prose (DRAWING_SUMMARY_LLM_ENABLED, default
# on) differs between identical extractions. Only these two leaves of
# legend_profile.drawing_intelligence are left out of the structural digest;
# every other field counts.
NARRATIVE_KEYS = ("narrative", "overview")


def structural_digest(document: Dict[str, Any]) -> str:
    """``digest`` without the LLM narrative leaves; ``document`` is not mutated."""

    profile = document.get("legend_profile")
    intelligence = profile.get("drawing_intelligence") if isinstance(profile, dict) else None
    if isinstance(intelligence, dict):
        kept = {k: v for k, v in intelligence.items() if k not in NARRATIVE_KEYS}
        document = {**document, "legend_profile": {**profile, "drawing_intelligence": kept}}
    return digest(document)


def recorded_flags(settings: Any) -> Dict[str, Any]:
    return {
        "schedule_region_quarantine_enabled": settings.schedule_region_quarantine_enabled,
        "schedule_evidence_shadow_enabled": getattr(settings, "schedule_evidence_shadow_enabled", None),
        "schedule_evidence_shadow_widened": getattr(settings, "schedule_evidence_shadow_widened", None),
        "legend_profile_llm_enabled": settings.legend_profile_llm_enabled,
        "drawing_summary_llm_enabled": getattr(settings, "drawing_summary_llm_enabled", None),
    }


def strip_timings(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: strip_timings(v) for k, v in payload.items() if k not in TIMING_KEYS}
    if isinstance(payload, list):
        return [strip_timings(v) for v in payload]
    return payload


def semantic_differences(first: Any, second: Any, path: str = "") -> List[str]:
    """Every differing path after timings are removed (no other normalization)."""

    a, b = strip_timings(first), strip_timings(second)
    if type(a) is not type(b):
        return [path or "$"]
    if isinstance(a, dict):
        out: List[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}.{key}")
            else:
                out.extend(semantic_differences(a[key], b[key], f"{path}.{key}"))
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}[len {len(a)}!={len(b)}]"]
        out = []
        for index, (x, y) in enumerate(zip(a, b)):
            out.extend(semantic_differences(x, y, f"{path}[{index}]"))
        return out
    return [] if a == b else [path or "$"]


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pdf_facts(path: Path) -> Dict[str, Any]:
    import fitz

    facts: Dict[str, Any] = {"page_count": None, "encrypted": None, "issue": None}
    try:
        with fitz.open(str(path)) as pdf:
            facts["encrypted"] = bool(pdf.needs_pass or pdf.is_encrypted)
            facts["page_count"] = pdf.page_count
            text_pages = textless = textless_with_images = 0
            for page in pdf:
                if page.get_text("text").strip():
                    text_pages += 1
                else:
                    textless += 1
                    textless_with_images += int(bool(page.get_images(full=False)))
            facts.update(
                vector_text_pages=text_pages,
                textless_pages=textless,
                textless_image_pages=textless_with_images,
                has_vector_text=text_pages > 0,
            )
    except Exception as exc:  # corrupted / unsupported
        facts["issue"] = f"{type(exc).__name__}: {exc}"[:300]
    return facts


def build_inventory(sources: Dict[str, Tuple[Path, Optional[Path]]]) -> Dict[str, Any]:
    """``sources[name] = (root, mapping_json_or_None)``.

    A mapping file (from the flat ZIP extraction) maps local files back to the
    original archive-relative path; without one, paths are relative to root.
    """

    files: List[Dict[str, Any]] = []
    for name, (root, mapping) in sources.items():
        if mapping is not None:
            entries = [
                (root / item["local_file"], item["relative_path"])
                for item in json.loads(mapping.read_text(encoding="utf-8"))
            ]
        else:
            entries = [
                (p, p.relative_to(root).as_posix())
                for p in sorted(root.rglob("*"))
                if p.is_file()
            ]
        for local, relative in entries:
            suffix = local.suffix.lower()
            if suffix != PDF_EXT and suffix not in SHEET_EXT:
                continue
            record = {
                "source": name,
                "relative_path": relative,
                "local_path": str(local),
                "sha256": _sha256(local),
                "size_bytes": local.stat().st_size,
                "kind": "pdf" if suffix == PDF_EXT else "workbook",
            }
            if record["kind"] == "pdf":
                record.update(_pdf_facts(local))
            files.append(record)
    pdf_refs = [f for f in files if f["kind"] == "pdf"]
    unique = dedup_pdfs(pdf_refs)
    for index, entry in enumerate(unique, start=1):
        entry["doc_id"] = f"DOC-{index:03d}"
    workbooks = [f for f in files if f["kind"] == "workbook"]
    return {
        "pdf_references": pdf_refs,
        "unique_pdfs": unique,
        "workbooks": workbooks,
        "pairing": pair_ground_truth(unique, workbooks),
    }


# ---------------------------------------------------------------------------
# Worker: one PDF
# ---------------------------------------------------------------------------


def _load_reference_extraction(ref: str):
    """Extraction engine source at ``ref`` (pre-quarantine) as a module."""

    from services import extraction_engine as current

    source = subprocess.check_output(
        ["git", "show", f"{ref}:backend/services/extraction_engine.py"],
        cwd=_BACKEND, text=True, encoding="utf-8",
    )
    module = types.ModuleType("extraction_engine_reference")
    module.__file__ = current.__file__
    exec(compile(source, f"{ref}:extraction_engine.py", "exec"), module.__dict__)
    return module


@contextmanager
def _cold_legend_cache(settings):
    """Every extraction starts from an empty legend-profile cache.

    A cache hit only changes ``legend_profile.diagnostics.cache_state``
    (FRESH_* vs CACHE_HIT), which would otherwise make the first and later
    extractions of a PDF differ; it also keeps benchmark writes out of
    ``backend/training/legend_profiles``.
    """

    original = settings.legend_profile_cache_dir
    with tempfile.TemporaryDirectory(prefix="e3d_legend_cache_") as tmp:
        object.__setattr__(settings, "legend_profile_cache_dir", Path(tmp))
        try:
            yield
        finally:
            object.__setattr__(settings, "legend_profile_cache_dir", original)


def _count(values: Iterable[str]) -> Dict[str, int]:
    return dict(sorted(Counter(values).items()))


def analyze_pdf(
    pdf: Path,
    doc_id: str,
    *,
    reference_ref: Optional[str],
    with_predictions: bool,
    ground_truth_xlsx: Optional[Path] = None,
) -> Dict[str, Any]:
    from config import settings
    from services.database_loader import catalog_form
    from services.engineering import legend_profile, schedule_grid
    from services.engineering.graph_builder import section_family
    from services.engineering.schedule_region_quarantine import (
        _bbox,
        _exact_section,
        _page,
        _relation,
        build_schedule_region_quarantine,
    )
    from services.extraction_engine import extract_engineering_document

    flags = recorded_flags(settings)
    started = time.perf_counter()
    with _cold_legend_cache(settings):
        document = extract_engineering_document(pdf, document_id=doc_id)
    parse_ms = (time.perf_counter() - started) * 1000.0
    tokens: List[Dict[str, Any]] = document.get("engineering_tokens") or []
    production_digest = digest(document)
    production_structural = structural_digest(document)

    reference: Dict[str, Any] = {"ref": reference_ref, "equal": None, "structural_equal": None}
    if reference_ref:
        started = time.perf_counter()
        with _cold_legend_cache(settings):
            ref_doc = _load_reference_extraction(reference_ref).extract_engineering_document(
                pdf, document_id=doc_id
            )
        reference.update(
            equal=digest(ref_doc) == production_digest,
            structural_equal=structural_digest(ref_doc) == production_structural,
            head_parse_ms=round((time.perf_counter() - started) * 1000.0, 1),
        )
        del ref_doc

    pages_meta = {int(p.get("page_number") or 0): p for p in document.get("pages") or []}
    roles = legend_profile.detect_context_pages(document)
    exact = [_exact_section(t) for t in tokens]
    eligible = [
        (t, s) for t, s in zip(tokens, exact) if s and t.get("takeoff_eligible") is not False
    ]
    evidence = schedule_grid.build_schedule_evidence(document.get("words") or [], discovery="widened")
    context_defs = [t for t in tokens if t.get("object_scope") == "context_definition"]

    before = digest(tokens)
    shadow = build_schedule_region_quarantine(document, source_path=pdf)
    live_mutation = int(digest(tokens) != before)

    confident = {r["region_id"]: r for r in shadow["regions"]}
    ambiguous = {r["region_id"]: r for r in shadow["ambiguous_regions"]}
    gates = Counter()
    quarantined: List[Dict[str, Any]] = []
    region_tokens: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for index, (original, classified, decision) in enumerate(
        zip(tokens, shadow["tokens"], shadow["decisions"])
    ):
        section = exact[index]
        if section != _exact_section(classified):
            gates["semantic_lock_overrides"] += 1
        if decision["action"] != "quarantined":
            changed = classified != original
            gates["unquarantined_token_changes"] += int(changed)
            if decision.get("reason") == "no_confident_schedule_region":
                gates["plan_labels_outside_regions_changed"] += int(changed)
            continue
        region_id = decision["region_id"]
        region = confident.get(region_id) or ambiguous.get(region_id) or {}
        gates["invalid_catalog_auto_accepts"] += int(not catalog_form(str(decision.get("section") or "")))
        gates["ambiguous_regions_auto_quarantined"] += int(region_id not in confident)
        gates["definition_rows_counted_in_shadow"] += int(
            classified.get("takeoff_eligible") is not False
            or classified.get("countable_occurrence") is not False
        )
        gates["cross_document_leaks"] += int(
            str(region.get("source_document_id") or "") not in ("", doc_id)
        )
        record = {
            "token_id": decision["token_id"],
            "page": _page(original),
            "raw_text": str(original.get("raw_text") or original.get("text") or ""),
            "section": section,
            "family": section_family(section or ""),
            "bbox": _bbox(original),
            "region_id": region_id,
            "baseline_eligible": original.get("takeoff_eligible") is not False,
        }
        quarantined.append(record)
        region_tokens[region_id].append(record)

    gates["context_definitions_counted"] = sum(
        1 for t in context_defs
        if t.get("takeoff_eligible") is not False or t.get("countable_occurrence") is True
    )
    gates["schedule_evidence_as_quantity"] = sum(
        1 for r in evidence.get("records") or [] if r.get("quantity") or r.get("countable") is True
    ) + int("schedule_evidence_shadow" in document)
    gates["default_off_production_differences"] = int(
        "schedule_region_quarantine_shadow" in document
    ) + int(reference["structural_equal"] is False)
    gates["live_token_mutations"] = live_mutation

    regions_out = []
    for region in [*shadow["regions"], *shadow["ambiguous_regions"]]:
        page = region["page_number"]
        box = region["region_bbox"]
        meta = pages_meta.get(page) or {}
        area = float(meta.get("width") or 0) * float(meta.get("height") or 0)
        inside_exact, boundary, nearby, nearby_changed = [], 0, 0, 0
        for original, classified, section in zip(tokens, shadow["tokens"], exact):
            box_t = _bbox(original)
            if _page(original) != page or not box_t:
                continue
            relation = _relation(box_t, box)
            if relation == "inside" and section:
                inside_exact.append(section)
            elif relation == "boundary":
                boundary += 1
            elif section and _near(box_t, box, 72.0):
                nearby += 1
                nearby_changed += int(classified != original)
        q = region_tokens.get(region["region_id"], [])
        regions_out.append(
            {
                "region_id": region["region_id"],
                "page": page,
                "status": region.get("boundary_status"),
                "region_source": region.get("region_source"),
                "title": region.get("title") or region.get("schedule_type") or region.get("kind"),
                "bbox": box,
                "evidence": list(region.get("evidence") or []),
                "page_area_pct": round(100.0 * (box[2] - box[0]) * (box[3] - box[1]) / area, 2) if area else None,
                "exact_labels_inside": len(inside_exact),
                "quarantined": len(q),
                "quarantined_by_section": _count(r["section"] for r in q),
                "quarantined_by_family": _count(r["family"] for r in q),
                "boundary_tokens": boundary,
                "nearby_exact_labels_outside": nearby,
                "nearby_labels_changed": nearby_changed,
            }
        )

    baseline_sections = _count(s for _, s in eligible)
    q_eligible = [r for r in quarantined if r["baseline_eligible"]]
    projected = Counter(baseline_sections)
    projected.subtract(Counter(r["section"] for r in q_eligible))

    result: Dict[str, Any] = {
        "doc_id": doc_id,
        "flags": flags,
        "parse_ms": round(parse_ms, 1),
        "region_ms": shadow.get("region_runtime_ms"),
        "production": {
            "digest": production_digest,
            "structural_digest": production_structural,
            "reference_check": reference,
            "page_count": document.get("page_count"),
            "skipped_page_count": document.get("skipped_page_count"),
            "rich_page_limit_applied": document.get("rich_page_limit_applied"),
            "unreadable_pages": sum(1 for p in pages_meta.values() if p.get("unreadable")),
            "engineering_tokens": len(tokens),
            "exact_catalog_tokens": sum(1 for s in exact if s),
            "eligible_exact_tokens": len(eligible),
            "eligible_by_section": baseline_sections,
            "eligible_by_family": _count(section_family(s) for _, s in eligible),
            "eligible_by_page": _count(str(_page(t)) for t, _ in eligible),
            "page_roles": _count(roles.get(p, "DRAWING") for p in sorted(pages_meta)),
            "schedule_mark_map": len(document.get("schedule_mark_map") or {}),
            "legend_abbreviation_rules": len((document.get("legend_profile") or {}).get("abbreviation_rules") or []),
            "context_definitions": len(context_defs),
            "schedule_evidence": {
                "regions": len(evidence.get("regions") or []),
                "records": len(evidence.get("records") or []),
                "definitions": len(evidence.get("definitions") or []),
                "conflicts": len(evidence.get("conflicts") or []),
                "rejections": len(evidence.get("rejections") or []),
            },
        },
        "shadow": {
            "regions": regions_out,
            "confident_regions": len(confident),
            "ambiguous_regions": len(ambiguous),
            "quarantined": quarantined,
            "quarantined_eligible": len(q_eligible),
            "decision_reasons": _count(d["reason"] for d in shadow["decisions"]),
        },
        "projection": {
            "baseline_eligible": len(eligible),
            "projected_eligible": len(eligible) - len(q_eligible),
            "projected_by_section": {k: v for k, v in sorted(projected.items()) if v},
        },
        "gates": dict(sorted(gates.items())),
    }
    if with_predictions:
        result["predictions"] = _prediction_projection(
            pdf, doc_id, document, {r["token_id"] for r in quarantined}, ground_truth_xlsx
        )
    return result


def _near(inner: List[float], outer: List[float], margin: float) -> bool:
    return not (
        inner[2] < outer[0] - margin or inner[0] > outer[2] + margin
        or inner[3] < outer[1] - margin or inner[1] > outer[3] + margin
    )


def _prediction_projection(
    pdf: Path,
    doc_id: str,
    document: Dict[str, Any],
    quarantined_ids: set,
    ground_truth_xlsx: Optional[Path],
) -> Dict[str, Any]:
    """Production served predictions (persist=False) vs the same minus quarantined tokens."""

    from services.multimodal.pipeline import run_multimodal_pipeline
    from services.staged_pipeline import _apply_project_rule_resolution, analysis_response
    from services.takeoff.canonical_takeoff_eval import (
        aggregate_predictions,
        evaluate,
        parse_workbook_ground_truth,
    )

    started = time.perf_counter()
    result = run_multimodal_pipeline(
        pdf, persist=False, document_structure=copy.deepcopy(document), document_id=doc_id
    )
    served = analysis_response(result).get("predictions") or []
    served, _ = _apply_project_rule_resolution(
        served, document.get("legend_profile"), set(), document_id=doc_id
    )
    projected = [p for p in served if str(p.get("object_id")) not in quarantined_ids]
    out: Dict[str, Any] = {
        "prediction_ms": round((time.perf_counter() - started) * 1000.0, 1),
        "served_predictions": len(served),
        "removed_by_quarantine": len(served) - len(projected),
        "baseline_counts": aggregate_predictions(served)["counts"],
        "projected_counts": aggregate_predictions(projected)["counts"],
    }
    if ground_truth_xlsx is not None:
        gt = parse_workbook_ground_truth(ground_truth_xlsx)
        out["ground_truth"] = {
            "parser": gt.get("parser"),
            "scope_quantity": gt.get("scope_quantity"),
            "sheets_used": gt.get("sheets_used"),
            "evaluable": bool(gt.get("total_quantity")),
        }
        # A workbook the repository parser cannot read yields zero ground
        # truth; scoring against it would report a fake 0% precision.
        for name, preds in (("baseline", served), ("projected", projected)) if gt.get("total_quantity") else ():
            report = evaluate(preds, gt)
            out[f"eval_{name}"] = {
                k: report[k]
                for k in (
                    "ground_truth_total", "predicted_total", "caught",
                    "section_precision_pct", "section_recall_pct", "excess_quantity",
                )
            }
            out[f"rows_{name}"] = [
                {k: row[k] for k in ("section", "ground_truth", "predicted", "caught")}
                for row in report.get("rows") or []
            ]
    return out


# ---------------------------------------------------------------------------
# Run driver
# ---------------------------------------------------------------------------


def run_pass(local_manifest: Path, out_dir: Path, *, workers: int, timeout: int,
             reference_ref: Optional[str], large_bytes: int, min_free_gb: float) -> Optional[str]:
    manifest = json.loads(local_manifest.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    gt_by_sha = {
        d["pdf_sha256"]: d for d in manifest["pairing"] if d["status"] == "confident"
    }
    xlsx_by_book = manifest.get("xlsx_by_workbook_sha") or {}
    jobs = []
    for entry in manifest["unique_pdfs"]:
        if entry.get("issue") or entry.get("encrypted"):
            continue
        cmd = [
            sys.executable, str(Path(__file__).resolve()), "worker",
            "--pdf", entry["local_path"], "--doc-id", entry["doc_id"],
            "--out", str(out_dir / f"{entry['doc_id']}.json"),
        ]
        if reference_ref:
            cmd += ["--reference-ref", reference_ref]
        pairing = gt_by_sha.get(entry["sha256"])
        if pairing:
            cmd += ["--with-predictions"]
            xlsx = xlsx_by_book.get(pairing["workbook_sha256"][0])
            if xlsx:
                cmd += ["--ground-truth", xlsx]
        jobs.append((entry["size_bytes"], entry["doc_id"], cmd))
    small = sorted((j for j in jobs if j[0] < large_bytes), key=lambda j: j[0])
    large = sorted((j for j in jobs if j[0] >= large_bytes), key=lambda j: j[0])

    stop = {"reason": None}

    def launch(job):
        _, doc_id, cmd = job
        target = out_dir / f"{doc_id}.json"
        if target.exists() or stop["reason"]:
            return
        free_gb = _free_memory_gb()
        if free_gb is not None and free_gb < min_free_gb:
            # Checkpoints are per PDF, so stopping here loses nothing.
            stop["reason"] = f"free memory {free_gb:.1f} GB < {min_free_gb} GB before {doc_id}"
            print(f"STOPPING: {stop['reason']}", flush=True)
            return
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd, cwd=_BACKEND, capture_output=True, text=True, timeout=timeout,
                stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
            )
            written = target.exists()
            status = "ok" if proc.returncode == 0 and written else "failed"
            detail = (proc.stderr or "")[-1500:] if status != "ok" else ""
            if status != "ok" and ("MemoryError" in detail or proc.returncode in (-9, 3221225477, 3221226505)):
                status = "resource_gap"
        except subprocess.TimeoutExpired:
            status, detail = "resource_gap", f"timeout: exceeded {timeout}s"
        if status != "ok" and not (target.exists() and status == "failed"):
            target.write_text(json.dumps({"doc_id": doc_id, "status": status, "error": detail}), encoding="utf-8")
        print(f"{doc_id} {status} {round(time.perf_counter() - started, 1)}s", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(launch, small))
    for job in large:  # each alone, after everything else
        launch(job)
    if stop["reason"]:
        print(f"STOPPED EARLY: {stop['reason']}", flush=True)
    return stop["reason"]


def _free_memory_gb() -> Optional[float]:
    """Available physical memory (Windows GlobalMemoryStatusEx); None elsewhere."""

    if sys.platform != "win32":
        return None
    import ctypes

    class _Status(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = _Status()
    status.dwLength = ctypes.sizeof(_Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullAvailPhys / 1e9


def worker_main(args: argparse.Namespace) -> int:
    import logging

    warnings: List[str] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                warnings.append(f"{record.name}: {record.getMessage()}"[:200])

    logging.getLogger().addHandler(_Collect())
    wall = time.perf_counter()
    try:
        result = analyze_pdf(
            Path(args.pdf), args.doc_id,
            reference_ref=args.reference_ref,
            with_predictions=args.with_predictions,
            ground_truth_xlsx=Path(args.ground_truth) if args.ground_truth else None,
        )
        result["status"] = "ok"
    except MemoryError as exc:
        result = {"doc_id": args.doc_id, "status": "resource_gap", "error": f"MemoryError: {exc}"[:500]}
    except Exception as exc:
        result = {"doc_id": args.doc_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]}
    result["warnings"] = sorted(set(warnings))[:50]
    result["wall_ms"] = round((time.perf_counter() - wall) * 1000.0, 1)
    Path(args.out).write_text(json.dumps(result, default=str), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _load_run(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(run_dir.glob("DOC-*.json"))}


_KNOWN_DEV_PROJECTS = ("burrvil", "gcdc", "springhill", "h5 herndon", "sidwell", "ketcham", "1200 k")
_QUEUE_LABELS_PER_REGION = 10


def _project_of(entry: Dict[str, Any]) -> str:
    key = project_key(entry["relative_path"])
    return key or f"({entry['source']})"


def _pct(part: float, whole: float) -> Optional[float]:
    return round(100.0 * part / whole, 2) if whole else None


def build_report(local_manifest: Path, run1_dir: Path, run2_dir: Path, out: Path) -> Dict[str, Any]:
    manifest = json.loads(local_manifest.read_text(encoding="utf-8"))
    run1, run2 = _load_run(run1_dir), _load_run(run2_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = {e["doc_id"]: e for e in manifest["unique_pdfs"]}
    confident = {d["pdf_sha256"]: d for d in manifest["pairing"] if d["status"] == "confident"}

    # --- determinism -------------------------------------------------------
    determinism = {"documents_compared": 0, "identical": 0, "differing": {}}
    for doc_id in sorted(set(run1) | set(run2)):
        a, b = run1.get(doc_id), run2.get(doc_id)
        if a is None or b is None:
            determinism["differing"][doc_id] = ["missing_in_one_run"]
            continue
        determinism["documents_compared"] += 1
        diffs = semantic_differences(
            {k: v for k, v in a.items() if k != "warnings"},
            {k: v for k, v in b.items() if k != "warnings"},
        )
        if diffs:
            determinism["differing"][doc_id] = diffs[:25]
        else:
            determinism["identical"] += 1
    determinism["normalized_fields"] = sorted(TIMING_KEYS) + [
        "pdf_parser uuid4 12-hex id bodies (first-appearance order)",
        "worker logging warnings list (diagnostic only)",
    ]

    # --- per-document tables ------------------------------------------------
    doc_rows, section_rows, gt_rows, queue, gate_hits = [], [], [], [], []
    gate_totals: Counter = Counter()
    summaries: Dict[str, List[Dict[str, Any]]] = {"run1": [], "run2": []}
    for doc_id, entry in sorted(entries.items()):
        project = _project_of(entry)
        result = run1.get(doc_id) or {"status": "not_run"}
        pairing = confident.get(entry["sha256"])
        base = {
            "doc_id": doc_id,
            "project": project,
            "source": entry["source"],
            "relative_path": entry["relative_path"],
            "duplicate_references": len(entry["references"]) - 1,
            "size_mb": round(entry["size_bytes"] / 1e6, 2),
            "pages": entry.get("page_count"),
            "vector_text_pages": entry.get("vector_text_pages"),
            "textless_pages": entry.get("textless_pages"),
            "status": result.get("status"),
            "error": (result.get("error") or "")[:160],
            "ground_truth_pairing": "confident" if pairing else "",
            "known_dev_project": any(k in entry["relative_path"].lower() for k in _KNOWN_DEV_PROJECTS),
        }
        for name, run in (("run1", run1), ("run2", run2)):
            r = run.get(doc_id)
            summaries[name].append(strip_timings({
                "doc_id": doc_id,
                "status": (r or {}).get("status", "not_run"),
                "production": (r or {}).get("production"),
                "gates": (r or {}).get("gates"),
                "shadow_regions": (r or {}).get("shadow", {}).get("regions"),
                "quarantined": [
                    {k: q[k] for k in ("token_id", "page", "section", "region_id", "baseline_eligible")}
                    for q in (r or {}).get("shadow", {}).get("quarantined") or []
                ],
                "projection": (r or {}).get("projection"),
            }))
        if result.get("status") != "ok":
            doc_rows.append(base)
            continue
        prod, shadow, proj = result["production"], result["shadow"], result["projection"]
        for gate, value in result["gates"].items():
            gate_totals[gate] += value
            if value:
                gate_hits.append({"doc_id": doc_id, "relative_path": entry["relative_path"], "gate": gate, "value": value})
        by_page = Counter(q["page"] for q in shadow["quarantined"] if q["baseline_eligible"])
        by_section = Counter(q["section"] for q in shadow["quarantined"] if q["baseline_eligible"])
        by_family = Counter(q["family"] for q in shadow["quarantined"] if q["baseline_eligible"])
        titleless = [r for r in shadow["regions"] if r["status"] == "confident" and "schedule_title" not in r["evidence"] and r["region_source"] == "column_matrix_geometry"]
        doc_rows.append({
            **base,
            "parse_s": round(result["parse_ms"] / 1000.0, 1),
            "region_s": round((result.get("region_ms") or 0) / 1000.0, 2),
            "reference_equal": prod["reference_check"]["equal"],
            "reference_structural_equal": prod["reference_check"].get("structural_equal"),
            "skipped_pages": prod.get("skipped_page_count"),
            "engineering_tokens": prod["engineering_tokens"],
            "exact_catalog_tokens": prod["exact_catalog_tokens"],
            "baseline_eligible": proj["baseline_eligible"],
            "shadow_quarantined": len(shadow["quarantined"]),
            "projected_eligible": proj["projected_eligible"],
            "reduction_pct": _pct(proj["baseline_eligible"] - proj["projected_eligible"], proj["baseline_eligible"]),
            "confident_regions": shadow["confident_regions"],
            "ambiguous_regions": shadow["ambiguous_regions"],
            "titleless_matrix_regions": len(titleless),
            "context_definitions": prod["context_definitions"],
            "page_roles": json.dumps(prod["page_roles"]),
            "schedule_mark_map": prod["schedule_mark_map"],
            "legend_abbreviation_rules": prod["legend_abbreviation_rules"],
            "schedule_evidence_regions": prod["schedule_evidence"]["regions"],
            "schedule_evidence_conflicts": prod["schedule_evidence"]["conflicts"],
            "schedule_evidence_rejections": prod["schedule_evidence"]["rejections"],
            "top_sections": json.dumps(dict(by_section.most_common(5))),
            "top_families": json.dumps(dict(by_family.most_common(5))),
            "top_pages": json.dumps({str(k): v for k, v in by_page.most_common(3)}),
            "warnings": len(result.get("warnings") or []),
        })
        for section in sorted(set(prod["eligible_by_section"]) | set(by_section)):
            baseline = prod["eligible_by_section"].get(section, 0)
            removed = by_section.get(section, 0)
            if removed or baseline:
                section_rows.append({
                    "doc_id": doc_id, "project": project, "section": section,
                    "baseline_eligible": baseline, "shadow_quarantined": removed,
                    "projected_eligible": baseline - removed,
                })
        if pairing:
            pred = result.get("predictions") or {}
            gt = pred.get("ground_truth") or {}
            gt_rows.append({
                "doc_id": doc_id, "project": project,
                "workbook": PurePosixPath(pairing["workbooks"][0]).name,
                "pairing_evidence": "; ".join(pairing["evidence"]),
                "gt_parser": gt.get("parser"),
                "gt_primary_framing_quantity": (gt.get("scope_quantity") or {}).get("primary_framing"),
                "ground_truth_evaluable": gt.get("evaluable"),
                "served_predictions": pred.get("served_predictions"),
                "removed_by_quarantine": pred.get("removed_by_quarantine"),
                "baseline_predicted_exact": sum((pred.get("baseline_counts") or {}).values()),
                "projected_predicted_exact": sum((pred.get("projected_counts") or {}).values()),
                **{f"baseline_{k}": v for k, v in (pred.get("eval_baseline") or {}).items()},
                **{f"projected_{k}": v for k, v in (pred.get("eval_projected") or {}).items()},
            })
        # --- reviewer queue ---------------------------------------------------
        reduction = _pct(proj["baseline_eligible"] - proj["projected_eligible"], proj["baseline_eligible"]) or 0.0
        for region in shadow["regions"]:
            reasons = []
            if region in titleless:
                reasons.append("titleless_matrix_region")
            if (region.get("page_area_pct") or 0) >= 25.0:
                reasons.append("region_covers_large_page_area")
            if region["nearby_exact_labels_outside"]:
                reasons.append("exact_labels_near_region_outside_bounds")
            if region["status"] != "confident":
                reasons.append("ambiguous_boundary_region")
            if region["boundary_tokens"]:
                reasons.append("tokens_straddle_region_boundary")
            if not base["known_dev_project"] and region["quarantined"]:
                reasons.append("new_project_template_unverified")
            if reduction >= 10.0 and not pairing:
                reasons.append("large_reduction_without_ground_truth")
            if not reasons:
                continue
            labels = [q for q in shadow["quarantined"] if q["region_id"] == region["region_id"]]
            samples = labels[:_QUEUE_LABELS_PER_REGION] or [None]
            for q in samples:
                queue.append({
                    "doc_id": doc_id, "project": project, "page": region["page"],
                    "region_id": region["region_id"], "region_status": region["status"],
                    "region_source": region["region_source"],
                    "region_bbox": json.dumps(region["bbox"]),
                    "region_evidence": "|".join(region["evidence"]),
                    "page_area_pct": region.get("page_area_pct"),
                    "region_quarantined": region["quarantined"],
                    "raw_text": q["raw_text"] if q else "",
                    "canonical_section": q["section"] if q else "",
                    "token_bbox": json.dumps(q["bbox"]) if q else "",
                    "review_reasons": "|".join(reasons),
                    "priority": len(reasons),
                    "reviewer_decision": "",
                })
        if prod["schedule_evidence"]["conflicts"]:
            queue.append({
                "doc_id": doc_id, "project": project, "page": "", "region_id": "",
                "region_status": "", "region_source": "structured_schedule_evidence",
                "region_bbox": "", "region_evidence": "", "page_area_pct": "",
                "region_quarantined": "", "raw_text": "", "canonical_section": "", "token_bbox": "",
                "review_reasons": f"schedule_evidence_conflicts={prod['schedule_evidence']['conflicts']}",
                "priority": 3, "reviewer_decision": "",
            })
    queue.sort(key=lambda r: (-int(r["priority"]), r["doc_id"], str(r["page"]), r["region_id"]))

    gates = {
        "evidence_class": "measured per document; nonzero hits listed individually",
        "totals": dict(sorted(gate_totals.items())),
        "nonzero": gate_hits,
    }
    _write_csv(out / "document_metrics.csv", doc_rows)
    _write_csv(out / "section_deltas.csv", section_rows)
    _write_csv(out / "ground_truth_comparison.csv", gt_rows)
    _write_csv(out / "review_queue.csv", queue)
    for name, payload in (
        ("hard_gates.json", gates),
        ("determinism_comparison.json", determinism),
        ("run1_summary.json", summaries["run1"]),
        ("run2_summary.json", summaries["run2"]),
    ):
        (out / name).write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    return {"docs": doc_rows, "sections": section_rows, "gt": gt_rows, "queue": queue,
            "gates": gates, "determinism": determinism, "run1": run1, "manifest": manifest}


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fields: List[str] = []
    for row in rows:
        fields.extend(k for k in row if k not in fields)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["empty"])
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory")
    inv.add_argument("--source", action="append", required=True,
                     help="NAME=ROOT[::MAPPING_JSON]")
    inv.add_argument("--local", type=Path, required=True, help="local-only manifest path")
    run = sub.add_parser("run")
    run.add_argument("--local", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--workers", type=int, default=3)
    run.add_argument("--timeout", type=int, default=2400)
    run.add_argument("--reference-ref", default=None)
    run.add_argument("--large-bytes", type=int, default=60_000_000)
    run.add_argument("--min-free-gb", type=float, default=1.5)
    wk = sub.add_parser("worker")
    wk.add_argument("--pdf", required=True)
    wk.add_argument("--doc-id", required=True)
    wk.add_argument("--out", required=True)
    wk.add_argument("--reference-ref", default=None)
    wk.add_argument("--with-predictions", action="store_true")
    wk.add_argument("--ground-truth", default=None)
    rep = sub.add_parser("report")
    rep.add_argument("--local", type=Path, required=True)
    rep.add_argument("--run1", type=Path, required=True)
    rep.add_argument("--run2", type=Path, required=True)
    rep.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "report":
        built = build_report(args.local, args.run1, args.run2, args.out)
        print(json.dumps({"docs": len(built["docs"]), "queue": len(built["queue"]),
                          "gates": built["gates"]["totals"],
                          "determinism_identical": built["determinism"]["identical"],
                          "determinism_differing": len(built["determinism"]["differing"])}))
        return 0

    if args.command == "inventory":
        sources = {}
        for spec in args.source:
            name, _, rest = spec.partition("=")
            root, _, mapping = rest.partition("::")
            sources[name] = (Path(root), Path(mapping) if mapping else None)
        inventory = build_inventory(sources)
        args.local.parent.mkdir(parents=True, exist_ok=True)
        args.local.write_text(json.dumps(inventory, indent=1), encoding="utf-8")
        print(json.dumps({
            "pdf_references": len(inventory["pdf_references"]),
            "unique_pdfs": len(inventory["unique_pdfs"]),
            "workbooks": len(inventory["workbooks"]),
            "pairing": Counter(d["status"] for d in inventory["pairing"]),
        }, default=str))
        return 0
    if args.command == "run":
        stopped = run_pass(args.local, args.out, workers=args.workers, timeout=args.timeout,
                           reference_ref=args.reference_ref, large_bytes=args.large_bytes,
                           min_free_gb=args.min_free_gb)
        return 2 if stopped else 0
    if args.command == "worker":
        return worker_main(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
