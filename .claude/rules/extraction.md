---
paths:
  - "backend/services/engineering/**/*.py"
  - "backend/services/annotation/**/*.py"
  - "backend/services/takeoff/**/*.py"
  - "backend/services/pdf_parser.py"
  - "backend/services/pdf_pages.py"
  - "backend/services/structural_parser.py"
  - "backend/services/token_extractor.py"
  - "backend/services/extraction_engine.py"
  - "backend/services/document_intelligence.py"
  - "backend/services/normalization.py"
  - "backend/services/preprocessing_pipeline.py"
  - "backend/services/staged_pipeline.py"
  - "backend/services/stage_runner.py"
---

# Extraction / engineering / annotation rules

See `docs/SERVICES.md` and `docs/ENGINEERING_VALIDATION.md` first.

- Extraction and analysis are explicit stages — never start implicitly. The staged flow is
  `POST /api/documents` → `.../extract` → `.../analyze`; upload only stores bytes.
- Geometry access goes through `engineering/geometry_adapters.py` (normalized providers); build
  the structural graph via `engineering/structural_graph.py`; compatibility findings come from
  `engineering/rule_engine.py`. Do not re-derive geometry inline.
- Parsing is consolidated: use `structural_parser.py`, `annotation/parser.py`,
  `annotation/plate_grammar.py`, `annotation/fragment_grouper.py`. Do not add a parallel
  regex/grammar for something these cover — extend the shared one.
- Durable engineer decisions live in `engineering/correction_dataset.py`; keep that the single
  writer.
- Excel handling: `takeoff/ground_truth_excel.py` output role is always `ground_truth`; it must
  never feed prediction. `engineering/excel_loader.py` normalizes AISC/flexible workbooks.
- Keep noise filters (`extraction_noise_filter.py`, `feet_inch_filter.py`,
  `engineering_object_filter.py`) conservative — prefer routing uncertain tokens to review over
  silently dropping them.
- Verify with the focused suites: `test_engineering_pipeline`, `test_structural_*`,
  `test_plate_grammar`, `test_anonymous_dimension_*`, `test_feet_inch_filter`,
  `test_extraction_noise_filter`, `test_pdf_rotation_coordinates`.
