# 09 — Open Questions

Questions that cannot be answered from the repository alone, organized by audit area. These require domain-expert input, missing data, or access to systems/history outside this static code read.

## Repository hygiene

1. **Untracked nested directory `ai-dynamic-regex/` at the repo root** — `git status` shows it as untracked, containing its own `.git` and a copy of `backend/`/`frontend/`. Is this an accidental nested clone, a leftover from a repo-rename, or intentional (e.g. a submodule setup gone wrong)? It was excluded from this audit; if it contains diverged work, that work is currently invisible to `git log`/`git status` on the outer repo.

## Geometry (see `03_geometry_audit.md`)

2. **Why these specific raw-coordinate constants?** (`250` drawing cap, `180.0`/`160.0`/`120.0`/`48.0` grid cell sizes, `8.0°` angle tolerance, `18.0` prediction-dedup distance, `400` symbol-area cutoff, `8.0`/`12.0`/`40.0`/`180.0` leader/dimension bounds). No comment, config, or commit message documents empirical tuning vs. arbitrary starting guesses. Git blame/PR history was not consulted as part of this static read.
3. **Does PyMuPDF's `get_drawings()` already compensate for page rotation**, or can a rotated page (`page.rotation != 0`) produce geometry whose orientation is inconsistent with the visually-displayed drawing? Requires running PyMuPDF against a rotated-page test PDF — not verifiable by static code read alone.
4. **Is real-world drawing scale ever recovered elsewhere** (e.g. inside `document_intelligence.py`'s title-block/schedule detection, which was referenced but not read in full during this pass) and simply never threaded into the geometry layer? If a scale signal already exists somewhere, P1.1 in the roadmap becomes a wiring task instead of a new detection algorithm.
5. **Is the 250-drawing-cap's zero-area sort bias a known, accepted trade-off, or an unnoticed defect?** No comment addresses this specific interaction, and no test exercises the >250-drawing path.

## Graph (see `04_graph_audit.md`)

6. **Are `matching_engine.py`, `suggestion_engine.py`, `validation_engine.py` (`engineering/`), and `object_confidence.py` intentionally staged-but-unwired** (a planned future integration point) **or genuinely orphaned legacy code?** Import-grep confirms zero live callers, but no TODO, feature flag, or config switch referencing them was found either. This needs a decision from whoever owns the roadmap, not further code archaeology (P0.5).
7. **Why do three different "how far is nearby" constants exist** (`graph_builder.max_edge_distance=160`, `structural_graph.max_near_distance=180`, `validation_engine.far_label_distance=140`)? Deliberately tuned per use case, or copy-paste drift across files authored at different times?
8. **What real-world node-count-per-page distribution was the 60/350-item windowing actually sized against?** The caps suggest defending against dense CAD PDFs, but there's no visibility into typical/worst-case node counts in the real corpus this system processes — needed to judge how often the windowing drops genuinely-proximate pairs in practice vs. being a theoretical risk.
9. **Are the coordinate units for the various tolerance constants** (`8px` vertical gap, `40-90` unit distance gates in `structural_graph.py`, `160/180/140` "nearby" radii) **calibrated against real engineering-meaningful distances, or arbitrary?** Needs a domain expert (structural engineer familiar with these drawings) to judge, since the codebase doesn't document the assumed real-world scale behind them.

## Prediction / ranking (see `02_logic_inventory.md §G`)

10. **Is calibration (`calibration.py`) ever actually exercised in production**, or does `dataset_manager.APPROVED_COLUMNS`'s current schema gap (no `ranking_score`/`correct` columns) mean it has never fired outside synthetic tests? Confirm with whoever owns the approved-dataset pipeline.
11. **Is `preprocessing_pipeline.pkl` actually present in the production deployment**, or does the live system still run through `model_predictor.py`'s `"legacy_tfidf"` fallback path? This determines whether the 23-column engineered feature set (`feature_extractor.py`) is actually consumed by the deployed family classifier. Not determinable without inspecting the deployed `training/` artifact directory.
12. **Why do `orchestrator.py`'s conflict thresholds (`0.45`) and `multimodal/validation_engine.py`'s (`0.35`/`0.2`) differ** for the same geometry/graph/rule signals — intentional (different purposes) or accidental drift?
13. **Is `test_multimodal_pipeline.py`'s `FUSION_WEIGHTS["text"] == 0.48` assertion currently passing in CI?** `ATTENTION_PRIORS["text"]` in `modular_fusion.py` is `0.32` today — either there's a monkeypatch not found during this audit, or the test is failing/skipped. Needs a CI run to confirm; not verifiable by static read.

## Testing / metrics (see `05_testing_metrics_audit.md`)

14. **Whether `evaluate_pipeline.py` Section B (top-1/3/5 accuracy) is ever run against genuinely held-out data**, or always against the same `approved_dataset.csv` that also feeds calibration and continuous-learning training splits — this would make reported accuracy optimistic relative to true generalization. No documented train/eval separation policy was found.
15. **Does a hand-annotated geometry/graph ground-truth dataset already exist somewhere not reviewed in this audit** — e.g. in the untracked `ai-dynamic-regex/` directory (item 1) or in `.gitignore`'d artifact directories under `backend/training/engineering_artifacts/`? Their *content* was not inspected (only their existence, via `git status`).
16. **Is `paired_dataset_builder.py`'s `build_pair_rows` output** (which does call real geometry/graph extraction) **ever manually reviewed by a human for geometry/graph sanity**, as a de facto but untracked source of coverage? Not confirmable from code alone.

## Workflow / deployment (see `01_workflow_map.md`)

17. **Is the deployment guaranteed single-worker?** `retrain_service.py`'s job-status tracking is a process-local in-memory dict — with `WEB_CONCURRENCY > 1` or a mid-job restart, `GET /api/retrain/status` would not reflect true state.
18. **Does `POST /api/continuous-learning/trigger` run in-request or spawn its own background thread?** `services/training_pipeline/continuous_learning.py` was not read in full during this pass.
19. **Is the `routers/engineering.py` "multimodal" parallel entry point** (`/api/multimodal/*`, `/api/engineering/excel/parse`) **intentionally kept live as an alternate integration surface, or is it legacy from before `/api/documents` existed?** No frontend caller was found for it.
20. **Is there any authentication/authorization layer** on any route, in any router, or in `app.py`? None was found — confirm whether this is an intentional single-tenant/local-tool design decision or a gap that matters for the deployment context this repo runs in.

## Decisions requiring domain-expert (structural engineering) input

21. Whether the geometry-classification gap identified in `03_geometry_audit.md §8` (no beam-vs-grid-line-vs-border-vs-hatch distinction) should be closed primarily via geometry heuristics (length/aspect-ratio/layer), text-proximity heuristics (current approach), or a hybrid — a domain expert's sense of which signal is more reliable in this system's typical drawing corpus would materially change the roadmap's P1.4/P1.7 design.
22. Whether the `rule_engine.py` weight constants (`1.2/1.1/1.3/0.6/0.4` per finding, `0.45×` for warnings) reflect genuine engineering risk-weighting judgment that should be preserved as-is, or were placeholder values nobody has revisited — needed before P2.2/P2.3 use them as a baseline to beat.
23. What tolerance for association error is acceptable in this domain (e.g., is a label pointing to the wrong-but-adjacent member in a dense connection detail a minor or major error for takeoff purposes)? This directly affects how aggressively P1.6's bipartite matching and P1.4's region segmentation should be tuned.
