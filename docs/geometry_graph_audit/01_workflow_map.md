# 01 — End-to-End Workflow Map

Scope: `backend/` (FastAPI, Python) + `frontend/src/` (React/Vite). No SQL database exists — persistence is JSON files on disk, managed by `services/document_registry.py` and `services/artifact_store.py`. The AISC steel-shapes catalog is a single Excel file, `backend/database/aisc-shapes-database-v160-2.xlsx`, loaded once at process start.

> Anomaly noted up front: `git status` shows an **untracked nested directory `ai-dynamic-regex/`** at the repo root containing its own `.git` and a copy of `backend/`/`frontend/`. This audit covers only the tracked outer repository. See `09_open_questions.md`.

## Stage-by-stage call flow

| # | Stage | Entry point (file:line) | Data passed to next stage |
|---|-------|--------------------------|------------------------------|
| 1 | File upload | `routers/documents.py:40 upload_document()` → `services/upload_service.py:107 save_upload()` (streams to `backend/uploads/`, content-addressed `{stem}__{sha256[:12]}{suffix}`) → `services/document_registry.py:77 register_document()` (validates PDF, sha256, writes manifest) | Document manifest `{document_id, source_file, stored_file, sha256, page_count, stage:"uploaded", ...}` |
| 2 | PDF/CAD ingestion | `routers/documents.py:66 extract_document()` → `upload_service.py:214 run_analysis()` (threadpool, ~600s budget) → `services/staged_pipeline.py:71 run_extraction_stage()` → `services/extraction_engine.py:13 extract_engineering_document()` → `services/pdf_parser.py:360 extract_document_structure()` (PyMuPDF `fitz`) | `document` dict: `pages, words, lines, blocks, layers, text, object_counts`. Non-PDF suffixes are rejected at upload (`upload_service.PDF_SUFFIXES`); CAD adapters (`DeferredCadAdapter`, `geometry_adapters.py:144`) exist but are unreachable — always raise `NotImplementedError` |
| 3 | Text extraction | `pdf_parser.py:149 _extract_page_text_objects()` (per page) → `services/document_intelligence.py:419 enrich_document_structure()` (OCR repair, layout/table/schedule/title-block detection) → `services/token_extractor.py:114 extract_engineering_token_records()` → filtered by `services/engineering_object_filter.py:98 filter_engineering_objects()` | `document["engineering_tokens"]`, `tables/schedules/callouts/dimensions/title_blocks`; persisted as `document.json` |
| 4 | Geometry extraction | `services/multimodal/pipeline.py:80` → `services/engineering/geometry_adapters.py:201 extract_geometry_document()` → `adapter_for_path()` (:193) → `PdfGeometryAdapter.extract()` (:86) → `services/engineering/geometry_extractor.py:228 extract_geometry()` (raw PyMuPDF `page.get_drawings()`) | `geometry` dict `{geometry_count, objects[...], counts_by_kind}`; persisted as `geometry.json` |
| 5 | Entity creation | Per-token loop `multimodal/pipeline.py:101-118` → `multimodal/fusion_engine.py:36 WeightedFusionEngine.predict()` → `services/prediction/orchestrator.py:77 predict_from_context()`; entity/category via `resolve_entity()` (orchestrator.py:385), `allocate_component_id()` (orchestrator.py:413) | Per-token dict with `entity_type/category/category_label/component_id` |
| 6 | Label parsing/normalization | Extraction-time OCR repair (`document_intelligence.py:48`); prediction-time: `normalized_text` field, `services/wildcard_matcher.py:111 match_wildcard_mask()`, `services/exact_section_predictor.py:383 predict_exact_sections()`, `multimodal/correction_engine.py suggest_token_corrections()` | Normalized text + candidate/correction lists |
| 7 | Geometry-to-label association | `orchestrator.py:97-98`: `GeometryFeatureProvider.extract()` (nearest-object search, independent of the graph), `GraphFeatureProvider.extract()` (reads cached graph aggregates) | `geometry{available, similarity, object}`, `graph{degree, structural_links, min_distance, graph_consistency}` |
| 8 | Graph construction | `multimodal/pipeline.py:90 build_structural_graph(document, geometry)` → `engineering/structural_graph.py:72` (wraps `engineering/graph_builder.py:99 build_graph()`, then semantic node/edge enrichment); document-level rules via `engineering/rule_engine.py:266 evaluate_document_rules()` | `graph{nodes, edges, stats, source_features}`; persisted as `graph.json` |
| 9 | Candidate generation | `orchestrator.py:100-179`: wildcard-mask hits, `predict_exact_sections()`, `suggest_token_corrections()`, family-classifier fallback | `fusion_candidates: [{shape, evidence{text,geometry,graph,engineering_rules}}]` |
| 10 | Candidate ranking | `encoder_registry.encode_all()` → `multimodal/modular_fusion.py UnifiedMultimodalFusion.predict()` (orchestrator.py:228) → `services/prediction/ranking.py:77 build_ranking()` | Ranked, catalog-checked candidates + `near_tie` flag |
| 11 | Final prediction | `services/prediction/calibration.py:130 calibrate_score()` → `services/prediction/canonical_contract.py:244 build_canonical_prediction()` → `services/prediction/contract.py to_token_prediction()`; dedup via `multimodal/duplicate_detector.py:24 merge_duplicate_predictions()` | Canonical per-token prediction dict |
| 12 | Confidence/review decision | `services/prediction/review_policy.py:22 decide_review_status()`; pending items queued via `services/dataset_manager.py:72 enqueue_unknown()`; document-level QA via `multimodal/validation_engine.py:735 validate_multimodal_predictions()` | `review_status`, validation summary |
| 13 | API response | `staged_pipeline.py:110 run_analysis_stage()` writes `analysis/geometry/graph/predictions/validation.json` via `artifact_store.py:107 write_artifact()`, updates manifest `stage="analyzed"` | Full pipeline result JSON, HTTP body of `POST /api/documents/{id}/analyze` |
| 14 | Frontend rendering | `frontend/src/api/client.js:98 analyzeDocument()` reshapes → `AnalyzePage.jsx` stores via `AnalysisContext` → `ResultsPage.jsx` renders `StatsCards`/`Charts`/`TokensTable` directly from the stored object | Rendered UI, no further fetch |

## API endpoints (all under `app.py`, no auth found anywhere)

- **`app.py`**: `GET /`, `/health`, `/health/live`, `/health/ready`
- **`routers/upload.py`** (`/upload`, `/upload/`): legacy upload-only endpoint, **not called by the frontend** — superseded by `/api/documents`, kept as documented backward compatibility
- **`routers/documents.py`** (`/api/documents...`): `POST /api/documents`, `GET /{id}`, `POST /{id}/extract`, `POST /{id}/analyze`, `GET /{id}/artifacts/{name}` — this is the live path the frontend uses
- **`routers/analysis.py`** (`/api`): `POST /analyze`, `POST /analyze/batch`, `GET /knowledge-base[/{cls}]`, `GET /stats`
- **`routers/engineering.py`** (`/api`): `multimodal/capabilities|analyze|extract`, `engineering/excel/parse|aisc-catalog|artifacts/{doc}/{name}|pdf/{filename}|corrections` — a **parallel entry point** into the same pipeline via `settings.engineering_uploads_dir`; no frontend caller found
- **`routers/takeoff.py`** (`/api/takeoff...`): `pairs`, `dataset/build|summary`, `evaluations[/{file}]`, `validate/{pair_id}`, `generate`, `exports/{file}`
- **`routers/learning.py`** (`/api`): unknown-tokens review/approve/reject/batch, retrain start/status, continuous-learning status/trigger, dataset/model versions, statistics, model rollback, reload-model

## Disk storage layout

- `backend/uploads/` (+ `/engineering/`) — raw uploaded files, content-addressed, staged via `.incoming__{uuid}` before commit
- `backend/training/documents/{document_id}.json` — document manifest
- `backend/training/engineering_artifacts/{document_id}/multimodal/{document,geometry,graph,predictions,validation,analysis,expected_excel}.json` — pipeline artifacts, retention-capped (keep=5) and free-space-gated (min 2 GiB)
- `backend/training/takeoff_exports/` — generated `.xlsx` takeoff workbooks + evaluation reports
- `backend/training/unknown_tokens.csv`, `approved_dataset.csv`, `history.csv`, `upload_log.csv` — human-review datasets
- `backend/training/dynamic_regex.json` — learned regex knowledge base
- `backend/database/aisc-shapes-database-v160-2.xlsx` — AISC catalog (read-only, verification only)

## Upload → result sequence (prose)

1. `FileUpload.jsx` → `POST /api/documents`. Manifest written, `stage="uploaded"`. Frontend caches only `{documentId, stage}` in `sessionStorage`, not the payload.
2. `POST /api/documents/{id}/extract` runs in a worker thread. PyMuPDF parsing → OCR repair/layout detection → token filtering. `document.json` written, `stage="extracted"`.
3. `POST /api/documents/{id}/analyze` (optionally with a ground-truth Excel attached) requires `document.json` to exist. Runs `run_multimodal_pipeline()`: geometry extraction → graph construction + document rules → per-token fusion prediction (candidates → ranking → calibration → canonical prediction) → duplicate merge → pending-review tokens queued → cross-validation against extraction diagnostics/Excel ground truth.
4. Artifacts written under `training/engineering_artifacts/{document_id}/multimodal/`; stale directories pruned; `upload_log.csv` row appended; manifest → `stage="analyzed"`; full result JSON returned.
5. Frontend reshapes predictions into `results` + confidence/class distributions, stores via `AnalysisContext`, routes to `/results` — no further fetch; `TakeoffPage` separately calls `POST /api/takeoff/generate`, which reads the persisted `predictions.json` rather than re-running analysis.
6. On reload, `AnalysisContext` replays `GET /api/documents/{id}` then re-calls extract/analyze with `force=false` to rehydrate from cached artifacts; a 404 (pruned source) surfaces a distinct "missing source, please re-upload" notice vs. a generic restore-failed notice.

**Background/async work**: extract/analyze are synchronous HTTP requests offloaded to a threadpool with a wall-clock timeout (`upload_service.py:214-277`) — a timeout returns 504 while the worker keeps running server-side. The one true background job is model retraining: `POST /api/retrain/start` spawns a daemon `threading.Thread` (`retrain_service.py:198-202`); `GET /api/retrain/status` polls a **process-local, in-memory** dict (`retrain_service.py:25`) — not persisted, not safe across multiple workers or restarts.

**Important branches/fallbacks**:
- Bad file type / corrupt or zero-page PDF → 400, uploaded file deleted (`upload_service.save_upload`, `document_registry.validate_pdf`)
- Disk full → proactive prune + 507 before write; artifact writes are best-effort (a full disk during persistence skips that file with a warning, doesn't fail the request)
- Extraction/analysis exception → manifest `stage="failed"`, re-raised, mapped to 507/504/500
- Analyze-before-extract → `RuntimeError` surfaces as an unclean 500, not 409 (`staged_pipeline.py:120-126`)
- Missing AISC catalog match → `database_verified=False`, `"database_unverified"` issue appended, but **never changes the predicted label** (catalog fusion weight is hard-fixed to `0.0` — see `04_graph_audit.md` / `06_research_findings.md`); only affects `review_status` and the takeoff export's "AISC Confirmed" flag

**Legacy/duplicated endpoints**: `POST /upload` duplicates `POST /api/documents` (both call `save_upload`+`register_document`); only the latter is used by the frontend. `services/engineering/takeoff_interface.py` is a self-documented placeholder, not imported by any router, exercised only by tests — the live exporter is `services/takeoff/takeoff_exporter.py`.

## Open items from this stage

See `09_open_questions.md` for: whether `POST /api/continuous-learning/trigger` runs in-request or spawns a thread; whether the deployment is guaranteed single-worker (given the process-local retrain-status dict); and whether the `engineering.py` "multimodal" parallel entry point is intentionally kept live or is legacy.
