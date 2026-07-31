# API Documentation

Interactive OpenAPI documentation is served at `/docs`; the machine schema is
`/openapi.json`.

## Staged document workflow

- `POST /api/documents` — validate and store PDF; returns stable `document_id`.
- `GET /api/documents/{document_id}` — document stage and metadata.
- `POST /api/documents/{document_id}/extract` — OCR, layout, table,
  dimension, callout, and engineering-object extraction.
- `POST /api/documents/{document_id}/analyze` — geometry, graph, exact-section
  prediction, correction, explanation, and validation. Optional Excel is
  ground truth only.
- `GET /api/documents/{document_id}/artifacts/{name}` — canonical cached stage
  artifact.
- `POST /upload/` — backward-compatible upload-only alias.

## Token prediction compatibility

- `POST /api/analyze` — canonical v2 prediction for one token.
- `POST /api/analyze/batch` — canonical v2 predictions for multiple tokens.
- `POST /api/multimodal/extract` and `/api/multimodal/analyze` — multipart
  compatibility adapters over the staged document services.
- `GET /api/multimodal/capabilities` — providers and AI/database policy.

Every new prediction includes `section`, `family`, structured `confidence`,
`top_candidate_sections`, `why_selected`, `why_rejected`, and text, geometry,
graph, OCR, and engineering evidence. Legacy aliases remain available.

## Review and learning

- `GET /api/unknown-tokens`
- `POST /api/approve-token`
- `POST /api/reject-token`
- `POST /api/review-batch`
- `GET /api/approved-tokens`
- `GET /api/history`
- `GET /api/data-quality`
- `POST /api/retrain/start`
- `GET /api/retrain/status`
- `GET /api/continuous-learning/status`
- `POST /api/continuous-learning/trigger`
- `GET /api/datasets/versions`
- `GET /api/models/versions`

## Engineering

- `POST /api/engineering/excel/parse`
- `GET /api/engineering/aisc-catalog`
- `GET /api/engineering/artifacts/{document_id}/{name}`
- `GET /api/engineering/pdf/{filename}`
- `GET|POST /api/engineering/corrections`

## Takeoff and Excel ground truth

- `GET /api/takeoff/pairs`
- `POST /api/takeoff/dataset/build`
- `GET /api/takeoff/dataset/summary`
- `GET /api/takeoff/validate/{pair_id}`
- `GET /api/takeoff/evaluations`
- `GET /api/takeoff/evaluations/{filename}`
- `POST /api/takeoff/generate` — accepts an analyzed `document_id`; never
  re-extracts the drawing.
- `GET /api/takeoff/exports/{filename}`

## Knowledge and operations

- `GET /api/knowledge-base`
- `GET /api/knowledge-base/{cls}`
- `GET /api/dynamic-regex`
- `GET /api/statistics`
- `GET /api/model-comparison`
- `POST /api/reload-model`
- `GET /health` — application status.
- `GET /health/live` — process liveness.
- `GET /health/ready` — model/database readiness; returns 503 when unavailable.

## Production API policy

- Terminate TLS at the ingress/load balancer.
- Restrict CORS with `CORS_ALLOW_ORIGINS`.
- Enforce authentication and authorization at the ingress until native
  identity is added.
- Set request-body limits at Nginx and the edge.
- Treat training, correction, retrain, rollback, and artifact endpoints as
  privileged operations.
