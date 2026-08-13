# Repository Evidence — Phase 0

Resolves (or narrows) the open questions raised by `docs/geometry_graph_audit/09_open_questions.md` and the ChatGPT deep-research report, using direct inspection of this checkout on 2026-08-05. Status terms follow the report's convention: **Verified** (directly observed), **Strongly inferred** (evidence points one way, intent unconfirmed), **Requires team confirmation** (needs a human with production/deployment access), **Still unanswered**.

## Which repository is authoritative

**Verified.** The outer repo (`C:\Users\Bassam\git\ai-dynamic-regex`) and the untracked nested `ai-dynamic-regex/` directory share the same GitHub origin: `https://github.com/ismail210/ai-dynamic-regex.git`. The outer repo is at commit `2911a8a` ("feat(backend): wire canonical prediction contract, wildcard matching, and calibration"), with `ef6f71b` and `b9a9268` behind it. The nested directory is at `b9a9268` ("Initial commit") only — it is a **stale, incomplete checkout of the same repository**, missing both later commits. It is not a divergent production copy, not a submodule with separate history, and not a hidden source of additional data. It can be safely ignored or deleted; it is not a blocker for any phase of this roadmap.

**Recommendation**: delete it once you confirm no uncommitted work lives inside it (a `git status` inside that directory showed a clean tree at the time of inspection).

## Current Git commit and environment

- Outer repo HEAD: `2911a8a`.
- Python: 3.11.9 (local dev environment). Docker image (`backend/Dockerfile`) pins `python:3.12-slim` — **a version mismatch between local dev (3.11) and the containerized deployment target (3.12)** worth tracking as its own small risk, unrelated to this roadmap but noted for completeness.
- PyMuPDF: `1.28.0` (per `backend/requirements.txt`). The deep-research report's rotation experiment was run against `1.26.7`/MuPDF `1.26.12` — a different version. The report's conclusion (unrotated-coordinate behavior, `rotation_matrix` needed to convert) is stated by PyMuPDF as a stable, documented API contract, not a version-specific quirk, so it should still hold — but Phase 1's own rotation tests (task in progress) will verify this directly against `1.28.0` rather than relying on the report's experiment.

## Active production model artifact and fallback path

**Verified for this checkout, not for production deployment.** `backend/training/` contains `best_model.pkl`, `label_encoder.pkl`, `preprocessing_pipeline.pkl`, and `vectorizer.pkl`. Per `services/model_predictor.py`'s loader logic (audited earlier), the presence of `preprocessing_pipeline.pkl` means the modern feature-pipeline path is used here, not the `legacy_tfidf` fallback. Running `backend/tests/test_multimodal_pipeline.py` loads `best_model.pkl` via `joblib`/`pickle` and emits an XGBoost warning that the serialized model was produced by an older XGBoost version than `3.3.0` currently installed — the artifact loads successfully despite the warning, but this confirms the artifact predates the current pinned XGBoost version.

**Still unanswered**: whether the *production deployment* (as opposed to this dev checkout) has the same artifacts present, or falls back to `legacy_tfidf`. This requires access to the deployed container/volume, which was not available in this session.

## Worker configuration

**Verified.** `backend/Dockerfile`'s `CMD` runs `uvicorn app:app --workers ${WEB_CONCURRENCY:-1}`; `docker-compose.yml` sets `WEB_CONCURRENCY: ${WEB_CONCURRENCY:-1}`. **Default is single-worker** unless an operator overrides the `WEB_CONCURRENCY` environment variable at deploy time. This means the process-local, in-memory `_retrain_status` dict in `services/retrain_service.py:25` (confirmed to be a plain module-level dict guarded by `_STATUS_LOCK`, not file-backed) is safe under the *default* configuration, but would silently break `GET /api/retrain/status` if concurrency is ever increased above 1 without also moving that status to shared/durable storage. This should be called out explicitly if/when anyone changes `WEB_CONCURRENCY`.

Separately, `services/training_pipeline/continuous_learning.py`'s own state (`_state_path()`, `load_state()`/`save_state()`) **is file-persisted** (JSON on disk), not process-local — more durable than the retrain-service status dict, but not restart-safe in a different way: if the process is killed mid-run, the persisted state can be left reading `"status": "running"` indefinitely, since nothing clears it on an abnormal exit. Not a blocker for this roadmap, but worth a follow-up ticket independent of the ML work.

## Does `POST /api/continuous-learning/trigger` run in-request or in a background thread?

**Verified: background thread, not in-request.** `routers/learning.py:246-256` calls `maybe_trigger_continuous_learning()`, which (`services/training_pipeline/continuous_learning.py:93-146`) calls `services/retrain_service.start_retrain_job()`, which (`retrain_service.py:198-202`) spawns `threading.Thread(target=run, daemon=True).start()` and returns immediately. The HTTP request returns a `"triggered": true/false` status dict without blocking on training. This resolves the report's open question #18.

## Dependencies relevant to this roadmap

**Verified**, from `backend/requirements.txt`:
- `xgboost==3.3.0` — present. The Phase 4 LambdaMART ranker needs no new dependency.
- `scikit-learn==1.9.0`, `scipy==1.18.0` — present. Phase 5's `scipy.optimize.linear_sum_assignment` and any sigmoid/isotonic calibration work need no new dependency.
- `shapely` — **not present**. Approved by user (2026-08-05) to add for Phase 1's STRtree candidate generator; added in this phase (see below).
- `networkx` — not present. Not required by the current roadmap (Phase 1 uses `shapely.STRtree` directly, not a graph library); flagged in the original audit's research findings as a possible future storage-layer upgrade, out of scope here.

## Fate of the four dead engineering modules

Not re-investigated in this phase — the original audit (`04_graph_audit.md §9`) already confirmed via import-grep that `matching_engine.py`, `suggestion_engine.py`, `validation_engine.py` (`engineering/`), and `object_confidence.py` have no live callers outside tests. Per the approved plan, this remains a product decision, not something resolved by further code archaeology. No action taken.

## Summary of Phase 0 status

| Question | Status |
|---|---|
| Nested `ai-dynamic-regex/` directory | **Resolved** — stale duplicate checkout, same origin, safe to ignore/delete |
| `FUSION_WEIGHTS["text"] == 0.48` test | **Resolved** — confirmed failing (`0.32 != 0.48`) by direct test run |
| `preprocessing_pipeline.pkl` presence | **Resolved for dev checkout** — present; production still unconfirmed |
| Worker configuration / `WEB_CONCURRENCY` | **Resolved** — defaults to 1, overridable; risk is conditional on that override |
| `continuous-learning/trigger` execution mode | **Resolved** — background daemon thread, not in-request |
| Dependencies for Phases 4/5 (xgboost, scipy) | **Resolved** — already present |
| Dependency for Phase 1 (shapely) | **Resolved** — approved and added this phase |
| Production deployment's actual model artifact/worker count | **Still unanswered** — requires deployment access not available in this session |
| Dead engineering modules' intended fate | **Still unanswered** — explicit product decision needed, not re-derived here |
