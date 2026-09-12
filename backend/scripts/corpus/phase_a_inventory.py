"""Phase A -- corpus inventory (Section 5).

Read-only against the source project directory. Writes only under
--output. For every PDF: path, project, size, sha256, page count, page
dimensions. Detects exact duplicates by sha256 and flags likely duplicate
project copies (same PDF sha256 appearing under two different top-level
project folders).

Usage:
    python -m scripts.corpus.phase_a_inventory \
        --input "C:\\...\\Testing Projects" \
        --output "C:\\Users\\Bassam\\Downloads\\estima3d_structural_corpus_v1"
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import (  # noqa: E402
    classify_extension,
    iter_files,
    iter_project_dirs,
    sha256_of,
    write_json,
    write_jsonl,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("corpus.inventory")


def inspect_pdf(path: Path) -> dict:
    info: dict = {"page_count": None, "pages": [], "error": None, "producer": None, "creator": None}
    try:
        with fitz.open(str(path)) as doc:
            info["page_count"] = doc.page_count
            info["producer"] = (doc.metadata or {}).get("producer")
            info["creator"] = (doc.metadata or {}).get("creator")
            for page in doc:
                rect = page.rect
                info["pages"].append({
                    "width": round(rect.width, 1),
                    "height": round(rect.height, 1),
                    "rotation": page.rotation,
                })
    except Exception as exc:  # noqa: BLE001 - keep the corpus audit alive
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--skip-pdf-inspect", action="store_true", help="Inventory files only, skip page-level PDF opens (fast pass)")
    args = parser.parse_args()

    root: Path = args.input
    out_dir: Path = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    if not root.exists():
        raise SystemExit(f"Input corpus path not found: {root}")

    projects = list(iter_project_dirs(root))
    logger.info("Found %d top-level project folders", len(projects))

    file_rows = []
    pdf_rows = []
    ext_counts: dict[str, int] = defaultdict(int)
    sha_to_pdfs: dict[str, list[str]] = defaultdict(list)
    project_summaries = []

    started = time.time()
    for project_dir in projects:
        project_id = project_dir.name
        project_files = list(iter_files(project_dir))
        project_ext_counts: dict[str, int] = defaultdict(int)
        project_size = 0

        for path in project_files:
            rel = path.relative_to(root)
            kind = classify_extension(path)
            ext_counts[kind] += 1
            project_ext_counts[kind] += 1
            try:
                size = path.stat().st_size
            except OSError:
                size = None
            if size:
                project_size += size

            row = {
                "project_id": project_id,
                "relative_path": str(rel),
                "kind": kind,
                "extension": path.suffix.lower(),
                "size_bytes": size,
            }
            file_rows.append(row)

            if kind == "pdf" and not args.skip_pdf_inspect:
                try:
                    digest = sha256_of(path)
                except OSError as exc:
                    logger.warning("Could not hash %s: %s", rel, exc)
                    continue
                pdf_info = inspect_pdf(path)
                pdf_row = {
                    "project_id": project_id,
                    "relative_path": str(rel),
                    "size_bytes": size,
                    "sha256": digest,
                    "page_count": pdf_info["page_count"],
                    "page_dims": pdf_info["pages"][:3],  # sample first 3 pages' dims
                    "producer": pdf_info["producer"],
                    "creator": pdf_info["creator"],
                    "error": pdf_info["error"],
                }
                pdf_rows.append(pdf_row)
                sha_to_pdfs[digest].append(f"{project_id}/{rel.name}")

        project_summaries.append({
            "project_id": project_id,
            "file_count": len(project_files),
            "size_bytes": project_size,
            "extension_counts": dict(project_ext_counts),
        })
        logger.info("[%s] %d files, %.1f MB", project_id, len(project_files), project_size / 1e6)

    # Duplicate detection
    exact_duplicate_groups = {sha: paths for sha, paths in sha_to_pdfs.items() if len(paths) > 1}
    cross_project_duplicates = {}
    for sha, paths in exact_duplicate_groups.items():
        projects_involved = {p.split("/")[0] for p in paths}
        if len(projects_involved) > 1:
            cross_project_duplicates[sha] = {"paths": paths, "projects": sorted(projects_involved)}

    inventory_dir = out_dir / "inventory"
    write_jsonl(inventory_dir / "files.jsonl", file_rows)
    write_jsonl(inventory_dir / "pdfs.jsonl", pdf_rows)
    write_json(inventory_dir / "projects.json", project_summaries)
    write_json(inventory_dir / "duplicate_pdfs_exact.json", exact_duplicate_groups)
    write_json(inventory_dir / "duplicate_pdfs_cross_project.json", cross_project_duplicates)

    total_pages = sum(r["page_count"] or 0 for r in pdf_rows)
    summary = {
        "input_root": str(root),
        "project_count": len(projects),
        "total_files": len(file_rows),
        "extension_counts": dict(ext_counts),
        "pdf_count": len(pdf_rows),
        "pdf_total_pages": total_pages,
        "pdf_open_errors": sum(1 for r in pdf_rows if r["error"]),
        "exact_duplicate_pdf_groups": len(exact_duplicate_groups),
        "cross_project_duplicate_pdf_groups": len(cross_project_duplicates),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    write_json(out_dir / "inventory" / "summary.json", summary)
    logger.info("Inventory summary: %s", summary)

    # CSV for pdfs (human/spreadsheet friendly)
    import csv
    with (inventory_dir / "corpus_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["project_id", "relative_path", "size_bytes", "sha256", "page_count", "producer", "creator", "error"])
        for r in pdf_rows:
            writer.writerow([r["project_id"], r["relative_path"], r["size_bytes"], r["sha256"], r["page_count"], r["producer"], r["creator"], r["error"]])
    write_json(inventory_dir / "corpus_inventory.json", {"summary": summary, "pdfs": pdf_rows, "projects": project_summaries})

    import json
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
