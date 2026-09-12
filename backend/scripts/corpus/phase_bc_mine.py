"""Phase B (page-native-text health) + Phase C (structural annotation mining).

Combined into one pass per PDF so the (potentially expensive) native-text
extraction happens exactly once per document. Read-only against the source
corpus; every output goes under --output.

Reuses the real semantic_preprocessor pipeline -- extraction, grouping,
structural_parser, normalization -- rather than a second parser (Section 4).
Source-of-truth commit is recorded in the manifest by the caller.

Usage:
    python -m scripts.corpus.phase_bc_mine \
        --input "C:\\...\\Testing Projects" \
        --output "C:\\Users\\Bassam\\Downloads\\estima3d_structural_corpus_v1" \
        --projects-file scripts/corpus/pilot_projects.txt
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import (  # noqa: E402
    ResumableCache,
    sha256_of,
    write_json,
    write_jsonl,
)
from services.pdf_parser import extract_document_structure  # noqa: E402
from services.semantic_preprocessor.extraction import build_text_primitives  # noqa: E402
from services.semantic_preprocessor.grouping import group_primitives  # noqa: E402
from services.semantic_preprocessor.models import SCHEMA_VERSION  # noqa: E402
from services.semantic_preprocessor.normalization import canonicalize  # noqa: E402
from services.semantic_preprocessor.structural_parser import is_architectural_dimension  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("corpus.mine")

PIPELINE_VERSION = f"mine-v1-{SCHEMA_VERSION}"

_SINGLE_CHAR_LEN = 1


def page_health_features(page_stats: dict, words: list[dict]) -> dict:
    word_count = page_stats.get("word_count") or 0
    text_length = page_stats.get("text_length") or 0
    single_char = sum(1 for w in words if len(w.get("text", "").strip()) == _SINGLE_CHAR_LEN)
    lengths = [len(w.get("text", "")) for w in words if w.get("text")]
    avg_len = sum(lengths) / len(lengths) if lengths else 0.0
    sorted_lengths = sorted(lengths)
    median_len = sorted_lengths[len(sorted_lengths) // 2] if sorted_lengths else 0.0
    single_char_ratio = (single_char / word_count) if word_count else 0.0

    if page_stats.get("unreadable"):
        page_class = "NO_NATIVE_TEXT"
    elif word_count == 0 and text_length == 0:
        page_class = "IMAGE_DOMINANT"
    elif not page_stats.get("rich_extraction"):
        page_class = "NATIVE_TEXT_GARBLED"
    elif single_char_ratio > 0.35 and word_count > 20:
        page_class = "NATIVE_TEXT_FRAGMENTED"
    elif word_count > 0:
        page_class = "NATIVE_TEXT_HEALTHY"
    else:
        page_class = "UNKNOWN"

    return {
        "word_count": word_count,
        "char_count": text_length,
        "single_char_span_count": single_char,
        "single_char_span_ratio": round(single_char_ratio, 4),
        "avg_span_length": round(avg_len, 2),
        "median_span_length": median_len,
        "rich_extraction": bool(page_stats.get("rich_extraction")),
        "unreadable": bool(page_stats.get("unreadable")),
        "engineering_relevance_score": page_stats.get("engineering_relevance_score"),
        "page_class": page_class,
    }


def classify_annotation(annotation) -> str:
    parse = annotation.structural_parse
    correction = annotation.correction
    if parse is None or not parse.is_structural:
        return "NONSTRUCTURAL"
    if parse.grammar == "incomplete":
        return "INCOMPLETE_OR_SHORTHAND"
    if correction.operation == "repair":
        return "POTENTIAL_REPAIR"
    if correction.operation == "none" and not parse.catalog_exact_match:
        return "AMBIGUOUS"
    if correction.operation == "normalization":
        return "CLEAN_NONCANONICAL"
    if correction.operation == "none" and parse.catalog_exact_match:
        return "CLEAN_EXACT"
    return "AMBIGUOUS"


def process_pdf(pdf_path: Path, project_id: str, rel_path: str, cache: ResumableCache) -> dict | None:
    try:
        digest = sha256_of(pdf_path)
    except OSError as exc:
        logger.warning("[%s] could not hash %s: %s", project_id, rel_path, exc)
        return None

    cached = cache.get(digest, PIPELINE_VERSION)
    if cached is not None:
        logger.info("[%s] %s -- cache hit (%s)", project_id, rel_path, digest[:12])
        return cached

    logger.info("[%s] %s -- extracting (%s)", project_id, rel_path, digest[:12])
    try:
        structure = extract_document_structure(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 -- one bad PDF must not kill the corpus run
        logger.error("[%s] %s -- extraction failed: %s", project_id, rel_path, exc)
        return {
            "project_id": project_id,
            "relative_path": rel_path,
            "sha256": digest,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=5),
            "pages": [],
            "annotations": [],
        }

    primitives, _page_classes = build_text_primitives(structure)

    pages_out = []
    words_by_page: dict[int, list[dict]] = {}
    for w in structure.get("words", []):
        words_by_page.setdefault(w["page_number"], []).append(w)
    for page_stats in structure.get("pages", []):
        page_number = page_stats["page_number"]
        features = page_health_features(page_stats, words_by_page.get(page_number, []))
        pages_out.append({
            "project_id": project_id,
            "relative_path": rel_path,
            "sha256": digest,
            "page": page_number,
            "width": page_stats.get("width"),
            "height": page_stats.get("height"),
            **features,
        })

    annotations_out = []
    pages_with_words = sorted(words_by_page.keys())
    for page_number in pages_with_words:
        annotations = group_primitives(primitives, page_number)
        for ann in annotations:
            label = ann.primary_label or ""
            if is_architectural_dimension(label) or not label:
                continue
            result = canonicalize(label)
            ann.structural_parse = result.parse
            ann.correction = result.correction
            category = classify_annotation(ann)
            if category == "NONSTRUCTURAL":
                continue  # not a structural-label candidate at all; skip to keep output focused
            annotations_out.append({
                "project_id": project_id,
                "relative_path": rel_path,
                "document_sha256": digest,
                "page": page_number,
                "annotation_id": ann.annotation_id,
                "original_text": ann.original_text,
                "primary_label": ann.primary_label,
                "canonical_text": result.correction.canonical,
                "operation": result.correction.operation,
                "family": result.parse.family,
                "grammar": result.parse.grammar,
                "fields": result.parse.fields,
                "catalog_exact_match": result.parse.catalog_exact_match,
                "category": category,
                "semantic_bbox": ann.semantic_bbox,
                "original_anchor": ann.original_anchor,
                "original_axis": ann.original_axis,
                "modifiers": [m.to_dict() for m in ann.modifiers],
                "grouping_reasons": ann.grouping_reasons,
                "source_fragments": [f.to_dict() for f in ann.source_fragments],
            })

    payload = {
        "project_id": project_id,
        "relative_path": rel_path,
        "sha256": digest,
        "error": None,
        "pages": pages_out,
        "annotations": annotations_out,
    }
    cache.set(digest, PIPELINE_VERSION, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--projects-file", type=Path, default=None, help="Text file, one project folder name per line; default: all projects")
    args = parser.parse_args()

    root: Path = args.input
    out_dir: Path = args.output
    cache = ResumableCache(out_dir / "_cache" / "pdf_extraction")

    if args.projects_file:
        wanted = {line.strip() for line in args.projects_file.read_text(encoding="utf-8").splitlines() if line.strip()}
    else:
        wanted = None

    pages_rows: list[dict] = []
    annotations_rows: list[dict] = []
    errors: list[dict] = []

    started = time.time()
    project_count = 0
    pdf_count = 0
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        if wanted is not None and project_dir.name not in wanted:
            continue
        project_count += 1
        for pdf_path in sorted(project_dir.rglob("*.pdf")):
            pdf_count += 1
            rel = str(pdf_path.relative_to(root))
            result = process_pdf(pdf_path, project_dir.name, rel, cache)
            if result is None:
                continue
            if result.get("error"):
                errors.append({"project_id": project_dir.name, "relative_path": rel, "error": result["error"]})
                continue
            pages_rows.extend(result["pages"])
            annotations_rows.extend(result["annotations"])

    write_jsonl(out_dir / "inventory" / "pages.jsonl", pages_rows)
    write_jsonl(out_dir / "clean" / "mined_annotations.jsonl", annotations_rows)
    write_json(out_dir / "inventory" / "mine_errors.json", errors)

    category_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    page_class_counts: dict[str, int] = {}
    for a in annotations_rows:
        category_counts[a["category"]] = category_counts.get(a["category"], 0) + 1
        if a["family"]:
            family_counts[a["family"]] = family_counts.get(a["family"], 0) + 1
    for p in pages_rows:
        page_class_counts[p["page_class"]] = page_class_counts.get(p["page_class"], 0) + 1

    summary = {
        "projects_processed": project_count,
        "pdfs_processed": pdf_count,
        "pdf_errors": len(errors),
        "pages_total": len(pages_rows),
        "page_class_counts": page_class_counts,
        "annotations_total": len(annotations_rows),
        "annotation_category_counts": category_counts,
        "family_counts": family_counts,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    write_json(out_dir / "inventory" / "mine_summary.json", summary)
    import json
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
