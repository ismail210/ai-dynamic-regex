# Dependency and Entrypoint Map

Audited baseline: `main` @ `5261ee1f1c4ccc428e28ce6c739dc145fd080b8a`. Read-only audit; no application code changed.

## Backend entrypoints

- **Process entrypoint**: `backend/app.py` (`uvicorn app:app`). Creates the FastAPI app and registers 7 routers:
  `upload`, `documents`, `analysis`, `learning`, `engineering`, `semantic`, `takeoff` (see `backend/routers/*.py`).
- **Sole production inference entrypoint**: `backend/services/prediction/orchestrator.py` (2068 LOC). Confirmed via
  grep across all 204 backend-runtime-core files that no second per-token prediction entrypoint exists. Every
  router chain that returns predictions (`analysis`, `engineering`, `dynamic_regex_service`, `retrain_service`,
  `self_learning_engine`, etc.) depends on `orchestrator.py`'s `predict_token` / `predict_from_context` output
  contract. This matches CLAUDE.md's stated invariant exactly — verified, not assumed.
- **CLI / maintenance scripts**: `backend/scripts/*.py` (64 files). ~29 are actively referenced from
  `.claude/rules|skills|agents`, `docs/**/*.md`, or imported directly by `backend/tests/test_*.py`. The remaining
  ~33 have no doc/test reference but are not stale — `git log` shows every one last touched between
  2026-08-10 and 2026-09-16, inside the active ML-audit sprint, and several (`phase_d1_orientation_forensics.py`,
  `phase_d2_merge_forensics.py`) directly correspond to the untracked `docs/validation/phase_d1_*`/`phase_d2_*`
  outputs visible in the current `git status` — i.e. they were just run. Classified `operational/manual script`,
  not dead.
- **Runtime model/data loading**: `backend/config.py`'s `Settings` dataclass holds every `*_path` field the
  running app reads from disk (model binaries, registries, continuous-learning CSV/JSON/JSONL files under
  `backend/training/`). All flat top-level `backend/training/{best_model.pkl, exact_section_model.joblib,
  label_encoder.pkl, vectorizer.pkl, preprocessing_pipeline.pkl, feature_names.json, model_metadata.json,
  dynamic_regex.json, graphsage_model.pt, multimodal_fusion.pt, geometry_embedding_index.joblib}` and the
  runtime-updated CSV/JSON/JSONL continuous-learning files were traced to a `settings.*_path` and a consumer
  service — genuinely `actively used at runtime`, matching CLAUDE.md's note that these are normal to edit.
- **Reflection / registry patterns**: `services/label_reconstruction/*` and `services/ml_association/*` are
  guard-tested to **never** be imported from the production module list
  (`services.multimodal.pipeline`, `services.prediction.orchestrator`,
  `services.multimodal.fusion_engine`/`modular_fusion`, `services.prediction.ranking`/`canonical_contract`,
  `services.staged_pipeline`, `app`, `routers.documents`/`analysis`/`engineering`). The guard tests
  (`test_label_reconstruction_not_wired_into_production.py`, `test_ml_association_not_wired_into_production.py`)
  work by `importlib.import_module` + `inspect.getsource` scanning that hardcoded module list and asserting the
  shadow package names never appear in their source — this is an active, enforced architectural boundary, not
  dead code.
- A third, similarly self-guarded experiment module was found: `services/engineering/graph_v2_scorer.py`
  (576 LOC, docstring: "MUST NOT be imported by the production prediction pipeline"). Unlike
  label_reconstruction/ml_association it has **no dedicated isolation guard test** — recommend adding one
  (tracked in the roadmap, not done here).

## Frontend entrypoints

- **Process entrypoint**: `frontend/src/main.jsx` → `frontend/src/App.jsx`.
- **Router**: `App.jsx` defines `BrowserRouter`, lazy-loaded routes, legacy redirects, and wraps everything in
  `AnalysisProvider`. Route map (from the frontend inventory pass): the workflow sidebar exposes routes for
  upload/extract, analysis/results, drawing review, semantic review, validation, dataset, training, model,
  history, settings, dashboard, plus off-nav routes (takeoff, unknown-review, model detail).
- **Layout**: `frontend/src/layout/AppLayout.jsx` (265 LOC) — the app shell (sidebar nav, top bar, theme toggle,
  "start new analysis"), wraps every routed page via `<Outlet/>`. Defines `WORKFLOW_ITEMS` (8 nav items),
  `SYSTEM_ITEMS` (Settings), and `OFF_NAV_TITLES` for 6 off-nav routes.
- **Shared state**: `frontend/src/context/AnalysisContext.jsx` (183 LOC) — global analysis/document state
  (stage, document, rehydration, `startNewAnalysis`); `useAnalysis()` consumed by 13+ files. Matches CLAUDE.md's
  "shared state is in `src/context/`" rule.
- **Sole HTTP boundary**: `frontend/src/api/client.js` (425 LOC) — the single Axios wrapper; imported by 13+
  pages/components. Confirmed via grep that no component makes ad-hoc Axios calls — the "all HTTP calls belong
  in `src/api/client.js`" rule in `.claude/rules/frontend.md` is honored in practice, not just documented.
- **Shared contracts**: `frontend/src/lib/predictionContract.js` (771 LOC) is the sole boundary for reading
  family/section/confidence/explanations off a prediction (the v2 canonical contract per CLAUDE.md) — imported
  by 8+ components/pages. `frontend/src/lib/semanticContract.js` (300 LOC) is the parallel, intentionally
  separate contract boundary for the Semantic Review domain (imported by 6+ semantic/* components).
  `frontend/src/lib/semanticDamageManifest.js` bridges the 4 fixture JSON files under
  `frontend/src/fixtures/semanticDamage/` into the Semantic Review UI (see also `validation/semantic_test_pdfs/`
  below).
- **Lazy-loaded / dynamic modules**: page components are lazy-loaded from `App.jsx` (`React.lazy`/`import()`) —
  the frontend auditor explicitly checked for this pattern rather than relying on static-import scanning alone.
- **Largest pages (god-page candidates)**: `UnknownReviewPage.jsx` (1046 LOC, off-nav yet the largest single
  file in `frontend/src`), `ValidationPage.jsx` (958 LOC, **no dedicated test file**), `SemanticReviewPage.jsx`
  (866 LOC, composes 6+ child components). See `refactor-opportunities.md` for split proposals.
- **Static assets**: `frontend/public/**` and `index.html` references (favicon, manifest) are consumed by URL,
  not JS import — correctly not flagged as unused despite zero inbound `import` statements.

## Cross-cutting fixture used by both backend tests and frontend

`validation/semantic_test_pdfs/` (root-level, 7 files: README + 3 manifest/PDF pairs) is **confirmed** an active
test fixture, not documentation — referenced by `backend/tests/test_semantic_damage_manifests.py`,
`backend/tests/test_semantic_precedence_task_regression.py`, and 2 scripts
(`build_semantic_damage_test_pdfs.py`, `validate_demo_correction_flow.py`), and mirrored into
`frontend/src/fixtures/semanticDamage/*.manifest.json` for the Semantic Review UI's damage-test flow. See
`proposed-repository-structure.md` for the conventional-location move proposal (and why it's a coordinated,
not a trivial, move).

## Build / CI / deployment files

- `backend/Dockerfile`, `backend/.dockerignore`, `backend/requirements.txt`, `backend/requirements-dev.txt` —
  deployment-critical, referenced by `docker-compose.yml`'s `backend.build.context: ./backend`.
- `frontend/Dockerfile`, `frontend/.dockerignore`, `frontend/nginx.conf`, `frontend/package.json`,
  `frontend/package-lock.json`, `frontend/vite.config.js` — deployment-critical, referenced by
  `docker-compose.yml`'s `frontend.build.context: ./frontend`.
- `docker-compose.yml` (root) — the only orchestration file; both services' env vars, healthchecks, and volumes
  traced and are internally consistent with `backend/config.py`'s `Settings` fields.
- **No `.github/` CI configuration exists in this repository** — confirmed absent; "CI-referenced" checks for
  scripts/docs came back empty everywhere, which is expected (not a coverage gap in the audit).
- `.claude/settings.json` wires exactly 4 `PreToolUse` hooks (`secret_file_guard.py`, `protect_paths.py`,
  `precommit_guard.py`, `git_destructive_guard.py`); all 4 referenced files exist in `.claude/hooks/`, and all 4
  files present in that directory are referenced — clean, no mismatch either direction.

## Database (`backend/database/`)

- `aisc-shapes-database-v160-2.xlsx` (17,199 rows) is the actively-used-at-runtime AISC v16.0 reference —
  **verifies only**, never a prediction input, per CLAUDE.md.
- `aisc_v16_label_catalog.csv`, `_master_catalog.csv`, `_conflicts.csv`, and 8 `reports/*.md` are explicitly
  commented in `config.py` as "Not wired into the production prediction pipeline yet" — consumed almost
  entirely by offline scripts under `backend/scripts/` and by tests. Two of the 8 reports
  (`aisc_v16_parser_fix_before_after.md`, `aisc_v16_training_scale_estimate.md`) have **zero inbound
  references anywhere in the tracked tree** — orphaned documentation, low-stakes archive candidates.

## Boundary violations checked and NOT found

- No second production inference entrypoint besides `orchestrator.py`.
- No router imports a domain service directly bypassing the service layer (routers → services only, as
  CLAUDE.md requires).
- No domain service imports a router (the CLAUDE.md-forbidden direction) — not found in the 204-file backend
  runtime-core scope.
- `label_reconstruction`/`ml_association` shadow boundary is actively enforced (guard tests import-scan the
  production module list, not just assert absence of a specific import).

## Duplicated / overlapping implementations found (see `refactor-opportunities.md` for full detail)

- Backend: `multimodal/fusion_engine.py` (thin adapter, per `.claude/rules/backend.md`) vs the real fusion logic
  in `multimodal/modular_fusion.py`; three explicit `DEPRECATED` shim modules
  (`prediction/semantic_contract.py`, `semantic_preprocessor/models.py`, `semantic_preprocessor/serialization.py`)
  superseded by `services/semantic/{models,serialization}.py` but **still actively imported** — do not delete
  without a migration pass; `services/dataset_builder.py` self-labeled "Legacy compatibility adapter... prefer
  `services.training_pipeline.dataset_builder`"; `services/model_versioning.py` self-labeled "Compatibility
  wrapper over the continuous-learning model registry".
- Backend training: two parallel training/promotion systems, **explicitly documented as disagreeing with each
  other** in `docs/ml_integration/partner_vs_local_comparison.md` (not an inference of this audit) —
  `backend/training/{train_model.py, build_dataset.py, build_augmented_dataset.py}` (pre-existing
  XGBoost/LightGBM path) vs `backend/training/train_neural_models.py` +
  `services/training_pipeline/neural_dataset.py` (newer geometry/graph/fusion path).
- Frontend: `components/StatsCards.jsx` overlaps with `components/ui/KpiCard.jsx` (both render a
  Card-with-caption-and-large-value in a grid; `StatsCards` computes 5 stats inline instead of composing
  `KpiCard`). Three independent badge/chip components with the same shape, different domains:
  `OperationBadge.jsx`, `ui/MatchStatusBadge.jsx`, `ui/EntityTypeChip.jsx`.

## God modules (LOC-only signal, not automatically a problem)

Backend: `orchestrator.py` 2068 (sole inference entrypoint — split target is *internal decomposition only*;
CLAUDE.md forbids adding a second inference entrypoint, so `predict_token`/`predict_from_context` must remain
the sole public surface), `multimodal/validation_engine.py` 1180, `engineering/drawing_intelligence.py` 1007,
`training_pipeline/neural_dataset.py` 938, `semantic_preprocessor/geometry_route_association.py` 913 (shadow),
`engineering/legend_profile.py` 836, `label_reconstruction/candidates.py` 804 (shadow),
`engineering/geometry_extractor.py` 796, `semantic/models.py` 773 (schema), `training_service.py` 750,
`exact_section_predictor.py` 689, `engineering/legend_llm_provider.py` 668, `staged_pipeline.py` 653,
`multimodal/pipeline.py` 642, `document_intelligence.py` 641.

Frontend: `pages/UnknownReviewPage.jsx` 1046, `pages/ValidationPage.jsx` 958, `pages/SemanticReviewPage.jsx` 866,
`lib/predictionContract.js` 771 (intentional single boundary, not a decomposition target),
`components/pdf/PdfDocumentViewer.jsx` 682.
