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

## Deploying through the company Vercel account (handoff)

**A Vercel project alone does not run Estima3D.** Vercel serves only the static
`frontend/` build. The FastAPI backend must run separately as a persistent
HTTPS service with a persistent disk; without it the deployed page loads but
cannot upload, extract or show any drawing. The backend cannot be a Vercel
Function: extraction and analysis are single blocking requests (Struct.pdf,
24 pages: extraction ~15 s, analysis ~110 s at ~1.6 GB peak memory) that exceed
Vercel's 120 s proxied-request limit for larger sets, and uploaded documents
and their artifacts must survive restarts. The browser therefore calls the
backend directly, so large PDFs (Struct.pdf is 9.3 MB) never pass through a
Vercel Function body limit.

```
browser ── static app ──────────────> Vercel project (Root Directory: frontend)
   └─ /api, PDFs, uploads ──────────> backend (HTTPS, Bearer key, CORS)
      Authorization: Bearer <key>      └─ persistent disk: uploads/, training/
```

### 1. Backend (any container host with a persistent disk)

Build `backend/Dockerfile` from this branch. `render.yaml` is a ready Render
Blueprint for it; any equivalent host works. Provisioning is paid — decide the
host and budget before creating it.

| Need | Value |
| --- | --- |
| Resources | 2 CPU, 4 GB RAM (2 GB leaves no margin over the ~1.6 GB peak), one instance, `WEB_CONCURRENCY=1` |
| Disk | persistent volume ≥ 20 GB (~300 MB of artifacts per analysed document); set `DATA_DIR` to its mount path |
| Request timeout | ≥ 30 min at the host/proxy (backend budget `UPLOAD_ANALYSIS_TIMEOUT_SECONDS=1800`); upload limit ≥ 200 MB |
| HTTPS | required; the frontend refuses to build against a non-https backend |
| Health check | `/health/ready` (the only unauthenticated route besides `/health/live`) |

Environment (set in the host's secret store, never in Git):

- `APP_ENV=production`
- `API_ACCESS_TOKEN` — a long random value; every route except `/health*`
  then requires `Authorization: Bearer <token>`. **Mandatory**: the API has no
  other authentication.
- `CORS_ALLOW_ORIGIN_REGEX` — the Vercel project's origins, e.g.
  `^https://<project>-[a-z0-9-]+-<team>\.vercel\.app$` for previews; add the
  production domain to `CORS_ALLOW_ORIGINS` when there is one. Set
  `CORS_ALLOW_ORIGINS` to an empty value to drop the localhost defaults.
- `DATA_DIR` — mount path of the persistent disk.
- LLM features stay at their default (off); no Ollama is needed.

`docker-entrypoint.sh` links `uploads/` and `training/` to `DATA_DIR`, seeds
`training/` (models, AISC catalog) from the image without overwriting existing
files, and runs the app unprivileged. A newer model or catalog in a later image
is therefore not applied to an existing disk automatically — copy it from
`/app/training.image` deliberately.

### 2. Frontend (company Vercel project)

- Import the repository; **Root Directory `frontend`**; framework Vite (build
  `npm run build`, output `dist`, both also set in `frontend/vercel.json` with
  SPA routes and security headers).
- Environment variable **`VITE_API_BASE`** = the backend's `https://` origin,
  for each environment you deploy (Preview and/or Production). It is baked in
  at build time; a Vercel build without it fails on purpose.
- Keep **Deployment Protection** enabled (Vercel Authentication) for previews.
- Deploy a preview first. The development-only worktree identity check never
  runs in these builds.

### 3. Access and live verification

Share the `API_ACCESS_TOKEN` value out of band. The app asks for it on the
first 401 and keeps it only in that browser tab (sessionStorage). The
deployment is live only when, against the hosted frontend and backend:

1. `GET <backend>/health/ready` is 200 and `<backend>/api/documents/x` without
   the key is 401.
2. Uploading a copy of Struct.pdf prompts for the key, then succeeds.
3. Extraction completes; Drawing Summary shows L1 = W8X21 (bearing plate
   6"x6"x1/2") and BP1 = 4"x6"x3/4" from S002.
4. "View page" on L1/BP1 opens S002 · PDF p. 2 at the mark.
5. Analysis matches the recorded baseline for Struct.pdf: 1436 predictions,
   62 quantity rows totalling 264.
6. After a backend restart/redeploy the document, its summary and its PDF are
   still served.

## Runtime configuration

- `APP_ENV` — `production` in deployed environments.
- `HTTP_PORT` — public container port.
- `WEB_CONCURRENCY` — keep at 1 unless file-backed review/training state is
  replaced by transactional shared storage.
- `LOG_LEVEL` — Uvicorn log level.
- `CORS_ALLOW_ORIGINS` — comma-separated exact origins.
- `CORS_ALLOW_ORIGIN_REGEX` — origins that change per deployment (Vercel
  previews).
- `API_ACCESS_TOKEN` — when set, every route except `/health*` requires
  `Authorization: Bearer <token>`. Mandatory for any internet-reachable backend.
- `DATA_DIR` — persistent disk for `uploads/` and `training/` (containers).
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
