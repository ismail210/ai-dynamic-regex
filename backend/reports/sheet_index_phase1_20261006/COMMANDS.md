# Commands — Sheet Index Phase 0 + Phase 1 (2026-10-06)

All commands run from `backend/` unless stated. `./venv/bin/python` is the
project venv (needs PyMuPDF). `pdf_root/` mirrors the
`ESTIMA3D_TESTING_PROJECTS` layout with symlinks to the local PDFs (the PDFs
themselves are not moved, renamed or copied).

## Phase 0 — ground truth (values read from renders, not from the parser)

```bash
# Title-block crops of the 40 ground-truth pages (renders/tb_<project>_p<n>.png)
./venv/bin/python reports/sheet_index_phase1_20261006/render_title_blocks.py
# Holdout crops for manual validation, 2 pages per project, not in the fixture
./venv/bin/python reports/sheet_index_phase1_20261006/render_title_blocks.py --holdout
```

Fixture: `tests/fixtures/sheet_index/ground_truth.json`; flattened copy
`reports/sheet_index_phase1_20261006/GROUND_TRUTH.csv`.

## Phase 1 — tests

```bash
./venv/bin/python -m pytest tests/test_sheet_index.py -q                       # 16 synthetic cases
ESTIMA3D_TESTING_PROJECTS=reports/sheet_index_phase1_20261006/pdf_root \
  ./venv/bin/python -m pytest tests/test_sheet_index_reference_set.py -q      # 40 real pages via build_drawing_intelligence
./venv/bin/python -m pytest tests/test_drawing_intelligence.py tests/test_context_scope.py \
  tests/test_quantity_engine.py -q
ESTIMA3D_TESTING_PROJECTS=reports/sheet_index_phase1_20261006/pdf_root \
  ./venv/bin/python -m pytest tests/test_level_reference_set.py tests/test_column_schedule_reference_set.py -q
./venv/bin/python -m pytest -q                                                 # full backend suite
```

## Accuracy

```bash
cd reports/sheet_index_phase1_20261006
PYTHONPATH=../.. ../../venv/bin/python evaluate.py      # SHEET_INDEX_RESULTS.csv + evaluation_summary.json
PYTHONPATH=../..:. ../../venv/bin/python all_pages.py   # ALL_PAGES.csv, all 233 pages
```

## Quantity / prediction regression (production path, persist=False)

```bash
# BEFORE: run with drawing_intelligence.py not yet importing sheet_index
./venv/bin/python reports/sheet_index_phase1_20261006/quantity_regression.py before
# AFTER: with the additive profile key in place
./venv/bin/python reports/sheet_index_phase1_20261006/quantity_regression.py after
./venv/bin/python reports/sheet_index_phase1_20261006/quantity_regression.py diff
```

## Final safety

```bash
git diff --check
git status --short
git diff --stat
```
