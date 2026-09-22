# Migration Notes — v5.2.0 AI-First Platform

## Summary

The platform remains backward compatible. Existing endpoints and response keys
are preserved. Behavior changes are intentional under the AI-first policy.

## Behavioral Changes

1. **Database no longer decides predictions**
   - Before: AISC hit could auto-accept and dominate outcomes.
   - After: AI fusion / XGBoost chooses the label; AISC only verifies.

2. **Review queue policy**
   - Before: essentially “queue if not in AISC”.
   - After: queue on low confidence, modality conflicts, rule issues,
     OCR uncertainty, or unverified medium-confidence predictions.

3. **Confidence weights**
   - Token path: model `0.70`, regex `0.25`, database `0.05`.
   - Multimodal path: text `0.45`, geometry `0.30`, graph `0.15`,
     engineering rules `0.05`, database `0.05`.

4. **New response fields (additive)**
   - `database_role: "verification_only"`
   - `ai_first: true`
   - Multimodal: `component_id`, `material`, `evidence`

## New Modules

| Module | Purpose |
|--------|---------|
| `services/engineering/rule_engine.py` | Structural sanity evidence |
| `services/component_tracker.py` | Permanent component IDs |
| `services/multimodal/duplicate_detector.py` | Merge duplicate detections |
| `services/data_quality.py` | Pre-train quality report |
| `services/model_versioning.py` | Archive / rollback models |

## New Endpoints

- `GET /api/data-quality`
- `GET /api/model-versions`
- `POST /api/model-versions/rollback`

## Compatibility Guarantees

- `/upload/` still returns `results[]` with existing keys.
- `/api/analyze` still returns prediction / regex / confidence / database_match.
- Dynamic Regex remains available as an internal learning service.
- Training, retrain, analytics, validation, takeoff routes remain.

## Operator Checklist

1. Restart backend (`uvicorn app:app --reload`).
2. Run multimodal validation on a known drawing.
3. Confirm high-confidence AI predictions can auto-accept without AISC hit.
4. Confirm low-confidence / conflicting cases still enter Review Queue.
5. Optional: open `/api/data-quality` and `/api/model-versions` before demos.
