---
name: test-select
description: >-
  Select the smallest reliable verification set for a change in this repo, escalating from a
  single test node to integration / build / E2E / full suite only by blast radius. Use whenever
  deciding what to run after an edit.
---

# Test Selection

Identify what changed, then run the lowest sufficient tier. All backend commands run from
`backend/`; all frontend commands from `frontend/`.

## Backend matrix

| Change area | First verification | Escalate to |
|---|---|---|
| Label normalization / parsing (`normalization.py`, `structural_parser.py`, `annotation/*`) | `pytest tests/test_normalization.py tests/test_plate_grammar.py -q` | `test_engineering_pipeline`, `test_anonymous_dimension_*` |
| Candidate generation / recall | `pytest tests/test_groupcv_and_candidate_gen.py -q` | `python scripts/audit_candidate_recall_v16.py`; `test_label_reconstruction_dataset` |
| Ranking / calibration (`prediction/ranking.py`, `calibration.py`, `label_ranker_hook.py`) | `pytest tests/test_label_ranker_hook.py tests/test_ranker_feature_consistency.py -q` | `test_label_ranker_field_safety`, `test_protected_exact_label`, a `scripts/evaluate_label_ranker*.py` run |
| Prediction orchestration / contract | `pytest tests/test_prediction_orchestrator.py tests/test_canonical_contract.py -q` | `test_documents_api`, `test_multimodal_pipeline` |
| Extraction / engineering / geometry | `pytest tests/test_engineering_pipeline.py -q` | `test_graph_feature_*`, `test_dense_page_geometry_cap`, `test_pdf_rotation_coordinates` |
| Multimodal fusion | `pytest tests/test_modular_multimodal_fusion.py tests/test_multimodal_validation_engine.py -q` | `test_multimodal_pipeline`, `test_multimodal_correction_engine` |
| Human review / selections persistence | `pytest tests/test_human_review_selection_api.py tests/test_human_selections.py -q` | `test_import_review_decisions`, `test_ml_association_review_*` |
| ML training / continuous learning | `pytest tests/test_continuous_learning_pipeline.py tests/test_feature_pipeline.py -q` | `test_evaluate_pipeline_holdout`; then `ml-audit` |
| Feature schema / parity | `pytest tests/test_feature_schema_order.py tests/test_ranker_feature_consistency.py -q` | full `pytest -q` (shared contract) |
| Router / API only | `pytest tests/test_documents_api.py -q` (or the matching router test) | route test + underlying service test |
| Wide/shared refactor (contracts, preprocessing, config) | targeted suites above | `pytest -q` once, late |

## Frontend matrix

| Change area | First verification | Escalate to |
|---|---|---|
| Single component/page | `npx vitest run src/<path>.test.jsx` | `npm run test` for the touched area |
| `predictionContract.js` / `PredictionExplainability.jsx` (shared) | `npx vitest run src/lib/predictionContract.test.js src/components/PredictionExplainability.test.jsx` | `npm run test` + `npm run build` + one browser flow |
| `api/client.js` | `npm run test` | `npm run build` + browser flow against a running backend |
| Any JSX change | add `npm run build` | — |
| API ↔ frontend contract change | backend contract test + `npm run test` + `npm run build` | one Extract→Analyze→Results browser flow |

## Rules

- Escalate only when: a shared/public contract changed, shared infra/preprocessing changed,
  multiple subsystems participate, persistence/schema changed, a wide refactor occurred, or the
  narrower tier cannot observe the reported behavior.
- Never run a broader tier merely because the narrower one passed.
- Never claim success from a passing unit test when the report is an observable UI/runtime bug.
- Report any pre-existing failures separately from failures your change caused.
- Return the exact commands chosen and one line on why each is necessary.
