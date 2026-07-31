# Production Deployment

## Container deployment

1. Copy `.env.example` to `.env`.
2. Set `CORS_ALLOW_ORIGINS` to the exact HTTPS frontend origin.
3. Confirm promoted artifacts exist in `backend/training/`.
4. Build and start:

```bash
docker compose up --build -d
docker compose ps
curl -fsS http://localhost/healthz
curl -fsS http://localhost:8000/health/ready
```

Only the frontend is published by default. Nginx proxies API traffic to the
private backend service.

## Runtime configuration

- `APP_ENV` — `production` in deployed environments.
- `HTTP_PORT` — public container port.
- `WEB_CONCURRENCY` — keep at 1 unless file-backed review/training state is
  replaced by transactional shared storage.
- `LOG_LEVEL` — Uvicorn log level.
- `CORS_ALLOW_ORIGINS` — comma-separated exact origins.
- `MAX_UPLOAD_BYTES` — documented application upload ceiling; enforce the same
  or lower value at the edge.

## Persistent data

Back up:

- `backend/training/` — models, datasets, review state, reports, registries;
- the upload volume when source retention is required;
- `backend/database/` when changing AISC reference versions.

Use encrypted storage, retention policies, and restricted service-account
permissions. Do not bake engineer-uploaded files into images.

## Health and rollout

- Liveness: `/health/live`
- Readiness: `/health/ready`
- API docs: `/docs`

Readiness checks the AISC workbook, promoted model, training directory, and
upload directory. Use rolling replacement only after readiness succeeds.

## Security boundary

The repository does not implement user identity or tenant isolation. Before
internet exposure:

1. place the service behind an authenticated gateway;
2. require TLS;
3. restrict privileged learning, correction, model, and artifact routes;
4. configure malware scanning for uploads;
5. centralize audit logs and redact uploaded document content;
6. apply rate limits and request timeouts;
7. run containers as non-root with read-only root filesystems where feasible.

## Scaling constraint

Review state and some registries are file-backed. Multiple backend workers or
replicas can race on local files despite process-local locks. Production should
use one worker until these stores are moved to a transactional database/object
store. CPU-heavy inference can be scaled with a job queue or isolated inference
workers after that migration.

## Verification checklist

- Backend full test suite passes.
- Frontend production build passes.
- OpenAPI schema generates.
- A real PDF returns explainability v2 fields.
- PDF+Excel evaluation confirms Excel is ground-truth-only.
- Review Queue, Validation, and Prediction Details render the same evidence.
- Backup and restore of `backend/training/` has been tested.
- Authentication, TLS, rate limits, monitoring, and alerting are configured at
  the platform layer.
