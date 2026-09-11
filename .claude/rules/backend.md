---
paths:
  - "backend/app.py"
  - "backend/config.py"
  - "backend/routers/**/*.py"
  - "backend/services/prediction/**/*.py"
  - "backend/services/multimodal/**/*.py"
  - "backend/services/label_reconstruction/**/*.py"
---

# Backend API + prediction rules

See `docs/SERVICES.md` and `docs/API.md` first.

- Routers are HTTP transport only — validation, serialization, status codes. Business logic
  belongs in `backend/services/`. Routers may import services; services must not import routers.
- Production inference has exactly one owner: `services/prediction/orchestrator.py`. Do not add
  a second inference path or call model primitives (`model_predictor.py`,
  `exact_section_predictor.py`) directly from a router.
- The v2 response contract lives in `prediction/contract.py`; ranked candidates + selection /
  rejection rationale + modality evidence come from `prediction/explanation_engine.py`;
  confidence policy from `confidence_engine.py`; auto-accept vs review from `review_policy.py`.
  Every prediction response must keep confidence, ranked candidates, reasons, and
  text/geometry/graph/engineering evidence. Do not drop or rename these fields.
- `multimodal/fusion_engine.py` is a compatibility adapter — it does not do independent
  inference. `multimodal/modular_fusion.py` does the real fusion scoring.
- `label_reconstruction/` and `ml_association/` are shadow modules: not wired into production,
  protected by `test_*_not_wired_into_production.py`. Keep them isolated.
- The AISC database is queried for verification only, after selection, and cannot change the
  selected candidate.
- Preserve request/response schemas the frontend depends on unless the task changes the
  contract; when it does, update `frontend/src/lib/predictionContract.js` and
  `frontend/src/api/client.js` in the same change.
- Verify: `cd backend && python -m pytest tests/test_<area>.py -q` (e.g.
  `test_prediction_orchestrator`, `test_canonical_contract`, `test_documents_api`,
  `test_label_ranker_hook`). Add a regression test when externally observable behavior changes.
