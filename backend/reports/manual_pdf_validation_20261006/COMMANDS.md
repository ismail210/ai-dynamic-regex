# Commands

Audit date: 2026-10-06. No application code, tests, caches, golden files, or training data were modified. Nothing was committed or pushed.

## Git state at start

- Branch `main`, HEAD `9522744` (`feat(trace): per-view scale evidence, offset placement and continuation notes`), even with `origin/main`.
- Uncommitted work was already present (schedule parsers, extraction version, geometry fixtures, training files, and others). It was left in place.
- This audit ran the **working tree**, so the extraction version constant was `3.25-level-bands-locations`, not the committed `3.24-level-bands`.

## What was safe to run

`extract_document_structure()` writes a file only when `persist_json` is set. It was called without that argument. `attach_schedule_grid()` updates the in-memory document only. Outputs were written only under this directory.

## Commands

From `backend/`, interpreter `backend/venv/bin/python`.

1. Page-count unique PDFs under `backend/uploads`, `backend/Testing Projects`, `backend/tests/fixtures`, `backend/training/eval_cache_backups`, and the Cursor attachments folder. Result: `inventory_raw.json` (58 unique paths).
2. `page.search_for` for `COLUMN SCHEDULE`, `BASE PLATE`, and `COLUMN LOCATIONS` on the priority sets. Result: `priority_hits.json`.
3. A second full-text scan of non-damage uploads. Result: `schedule_page_hits.json` (31 paths, including duplicates).
4. In-memory production path for five PDFs: `extract_document_structure` then `attach_schedule_grid`. No `persist_json`. Results: `extract_brandywine.json`, `extract_burrville.json`, `extract_springhill.json`, `extract_struct.json`, `extract_structure_copy.json`.
5. Rendered schedule pages with PyMuPDF into `renders/` (new files only).
6. Word-level check of Springhill page 26 (`get_text("words")`) after a full-page image description disagreed with the extractor. A high-zoom crop then confirmed `W10X45` is printed.

Not run:

- The level-reference unittest (`tests/test_level_reference_set.py`). Its default PDF root is a Windows path that is not on this machine, and several named PDFs are absent. Running it would only skip.
- Any command that rewrites golden answers, training CSV/JSON, or the extraction cache.
- Live column-trace calls (`trace_column`). No OSSE or Yellow Spring PDF is present, and Brandywine traces were not executed in this pass.
- The historical Struct.pdf 383/414 evaluation. `schedule_mark_map` on this 24-page file has 12 entries, which is a different count, and the old evaluation was not rerun.
