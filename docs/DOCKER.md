# Estima3D with Docker

Runs the complete drawing-summary workflow (upload → extraction → Drawing
Summary → Locate → reports) from this repository without a local Python
environment, Node packages or a Windows folder layout. Commands are PowerShell
from the repository root; `scripts/docker-build.sh` is the Linux equivalent of
the build script.

```
browser ──> 127.0.0.1:${HTTP_PORT} ──> frontend (nginx: web app, /api proxy)
                                          └──> backend:8000 (FastAPI, 1 worker, internal only)
                                                 └──> volume estima3d_data → /data (uploads/, training/)
optional:  ollama (profile "ollama", own volume estima3d_ollama_models)
```

| Service | Image | Notes |
| --- | --- | --- |
| `frontend` | `estima3d-web:<build>` / `:current` | Node 24.15 build stage → nginx 1.27. Serves the SPA (direct links and refresh on every route, including `/drawing-summary/report`), proxies `/api` and `/upload` (200 MB bodies, 35 min timeouts). Published on `127.0.0.1` only. |
| `backend` | `estima3d-api:<build>` / `:current` | Python 3.12.10-slim, the pinned `backend/requirements.txt`, `libgomp1` only. Runs `uvicorn` without reload, one worker, as the unprivileged `appuser` (the entrypoint starts as root only to hand a fresh volume to that user). Not published. |
| `ollama` | `ollama/ollama:0.34.3` | Optional, profile `ollama`, CPU only, models in their own volume, nothing pulled automatically. |
| `backend-tests` | `estima3d-api-tests:<build>` | Profile `test`: the runtime image plus pytest and the tests. Never deployed. |

## 1. Configure

```powershell
Copy-Item .env.example .env
# Replace API_ACCESS_TOKEN in .env with a long random value, e.g.:
-join ((48..57 + 65..90 + 97..122) | Get-Random -Count 40 | % {[char]$_})
```

`.env` is ignored by Git and never enters an image. The access key is the
only credential: every `/api` request needs `Authorization: Bearer <key>`; the
browser asks for it on the first 401 and keeps it in that tab only. It is not a
frontend build variable. Compose refuses to start without it.

Other settings (defaults in `.env.example`): `HTTP_PORT` (8080),
`BACKEND_MEMORY_LIMIT` (3g), upload size and timeouts, artifact retention,
and the optional LLM switches, which stay `false`.

## 2. Build and start

```powershell
.\scripts\docker-build.ps1          # both images, one revision
docker compose up -d
docker compose ps                   # backend "healthy", frontend "running"
```

The script builds both images from the current checkout with the same
`SOURCE_REVISION` (the commit) and `BUILD_ID` (the short commit, or
`<short>-dirty-<UTC time>` when tracked files differ from that commit) and
tags them `:<BUILD_ID>` and `:current`. Building them separately or with plain
`docker compose build` would give both images `unknown`; always use the
script.

Open **http://127.0.0.1:8080** (or your `HTTP_PORT`) and enter the access key
when asked. The first start copies the image's `training/` seed (models,
catalog, datasets) onto the empty volume; readiness can take a minute or two.

## 3. Health, versions and logs

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:8080/healthz                 # nginx
Invoke-RestMethod http://127.0.0.1:8080/version.json            # web image build
$key = (Select-String '^API_ACCESS_TOKEN=(.*)' .env).Matches[0].Groups[1].Value
Invoke-RestMethod http://127.0.0.1:8080/api/version -Headers @{Authorization = "Bearer $key"}   # API image build
docker compose exec backend python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready').read().decode())"
docker compose logs -f backend      # Ctrl+C stops following, not the app
docker compose logs --since 10m frontend
docker stats --no-stream
```

`/version.json` and `/api/version` must report the same `revision` and
`build_id`. The web app also compares them on load: an incompatible API blocks
uploads with a red banner, a different build shows a yellow one.

Health checks are cheap: nginx `/healthz`, backend `/health/live` (image
healthcheck) and `/health/ready` (Compose healthcheck: AISC workbook, promoted
model, training and upload directories). None runs extraction or a model.

## 4. Stop, restart, recreate

```powershell
docker compose stop                 # stop, keep containers and data
docker compose start
docker compose restart backend
docker compose down                 # remove containers + network; volumes stay
docker compose up -d
```

**Never add `-v` / `--volumes` to `down`, and do not run `docker volume rm`,
`docker volume prune` or `docker system prune --volumes`** — the volume
`estima3d_data` holds every uploaded drawing and its extraction.

## 5. Update to a new revision

```powershell
git fetch; git checkout <branch-or-commit>
.\scripts\docker-build.ps1
docker compose up -d                # recreates containers on the new :current images
docker compose ps
```

Data stays on the volume. The volume's `training/` was seeded from the image
that first started on it; later images add new seed files but never overwrite
existing ones (learning state, promoted models and histories live there). The
backend logs `data seeded from <rev>, image is <rev>` when they differ. To
apply a newer shipped model or catalog file deliberately:

```powershell
docker compose exec backend ls /app/training.image          # the new image's seed
docker compose exec backend cp /app/training.image/<file> /data/training/<file>
docker compose restart backend
```

Back up first (section 6).

## 6. Backup and restore

Stop the backend so no extraction writes during the copy, archive the volume
with a throwaway container, start again:

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
docker compose stop backend
docker run --rm -v estima3d_data:/data:ro -v "${PWD}\backups:/backup" alpine:3.20 `
  tar czf /backup/estima3d-data-$(Get-Date -Format yyyyMMdd-HHmmss).tgz -C /data .
docker compose start backend
```

Restore into a **new** volume, then point the stack at it — the current volume
is left untouched until you decide to remove it yourself:

```powershell
docker volume create estima3d_data_restored
docker run --rm -v estima3d_data_restored:/data -v "${PWD}\backups:/backup:ro" alpine:3.20 `
  tar xzf /backup/<archive>.tgz -C /data
# Use it: add to .env  ESTIMA3D_DATA_VOLUME=estima3d_data_restored  (see below), then
docker compose up -d
```

`backups/` is ignored by Git. Keep archives on encrypted storage: they contain
the uploaded drawings.

## 7. Roll back images (data unaffected)

Every build keeps its `:<BUILD_ID>` tag. Run an earlier pair without
rebuilding:

```powershell
docker images estima3d-api; docker images estima3d-web     # pick a BUILD_ID
$env:IMAGE_TAG = "<old BUILD_ID>"; docker compose up -d --no-build; Remove-Item Env:IMAGE_TAG
```

Rolling back images does not roll back the data volume. A newer build may have
written data an older one does not expect; restore the matching backup into a
new volume (section 6) if that matters. Remove old images only with
`docker image rm estima3d-api:<BUILD_ID>`, never with a prune that includes
volumes.

## 8. Optional LLM (Ollama)

The Drawing Summary and legend LLM features are **off**
(`DRAWING_SUMMARY_LLM_ENABLED=false`, `LEGEND_PROFILE_LLM_ENABLED=false`); the
application never contacts Ollama and works when none is reachable.

Bundled Ollama container (CPU, ~5 GB RAM for `llama3.1:8b`; models are pulled
only when you run the pull):

```powershell
docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull llama3.1:8b     # explicit, ~4.9 GB download
# then in .env: DRAWING_SUMMARY_LLM_ENABLED=true ; OLLAMA_BASE_URL=http://ollama:11434
docker compose up -d backend
```

An Ollama already running on the Windows host is reached through
`http://host.docker.internal:11434`, not `localhost` (the container's own).
Check it from the container before enabling anything:

```powershell
docker compose exec backend python -c "import urllib.request;print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags',timeout=5).read()[:200])"
```

Verified on Docker Desktop for Windows (2026-10-08): the host's Ollama,
listening on 127.0.0.1:11434 only, answered from the backend container at
`host.docker.internal:11434`, while `http://ollama:11434` does not resolve
unless the `ollama` profile runs. With the LLM switches off neither is ever
called. On a Linux host, `host.docker.internal` needs
`extra_hosts: ["host.docker.internal:host-gateway"]` on the backend and an
Ollama listening on the Docker bridge address; the bundled service avoids both.

## 9. Tests in the image's environment

```powershell
$env:SOURCE_REVISION = git rev-parse HEAD; $env:BUILD_ID = "tests"
docker compose --profile test build backend-tests
docker compose --profile test run --rm backend-tests                       # full suite
docker compose --profile test run --rm backend-tests python -m pytest -q tests/test_access_token.py
# Reference drawings (optional): TESTING_PROJECTS_DIR=<folder> in .env, mounted read-only
```

The test service mounts, read-only, what tests read but no image contains:
`docs/` (as `/docs`), `backend/training/eval_cache_backups/` and the backend
tree as `/backend` for tests that address `<repo>/backend/...`. Two results
differ from a developer checkout by design: `test_dev_identity` needs `git` and
a work tree (the dev-only pairing route; containers use `/api/version`), and
`test_geometry_evidence_contract.py` has the repository's existing
`CompletionStatus` collection error. pytest therefore exits 1.

Frontend tests and the production build: `cd frontend; npm ci; npm run test; npm run build`
(the image build runs `npm ci` + `npm run build` itself).

## 10. What the data volume holds

`/data/uploads/` — uploaded PDFs (and spreadsheets). `/data/training/` —
per-document state (`documents/`), extraction and analysis artifacts
(`engineering_artifacts/`, regenerable, capped by `ARTIFACT_RETENTION_DOCUMENTS`),
legend-profile cache, review and learning state, histories, registries, and the
models / datasets seeded from the image. `/data/.seeded-from` — the revision
that seeded it. Nothing else in the backend container is written except `/tmp`.

Kept out of every image (`backend/.dockerignore`, `frontend/.dockerignore`):
`.env*`, virtual environments, `node_modules`, uploads, per-document runtime
data, caches, evaluation snapshots; the runtime image also omits tests,
scripts and reports. No project PDF, credential or Ollama model is baked in.

## 11. Single instance

Run exactly one backend container with one worker. Documents, review and
learning state, registries and caches are files on the data volume guarded by
process-local locks, and Locate keeps per-process plan caches. Two workers or
replicas would race on those files and miss each other's caches. Horizontal
scaling needs those stores moved to a transactional database / object store
first (see docs/DEPLOYMENT.md, "Scaling constraint").

## 12. Private pilot on a Linux host (plan, not deployed)

- **Host**: one VM, Ubuntu 24.04 LTS or similar, Docker Engine + Compose
  plugin, 4 vCPU / 8 GB RAM (backend ceiling 3 GB, measured peaks in section
  13; leaves room for the OS, nginx and an occasional second job), 50 GB SSD
  for the data volume (~300 MB of regenerable artifacts per analysed document,
  capped by `ARTIFACT_RETENTION_DOCUMENTS`). No GPU. Add ~8 GB RAM only if the
  optional Ollama service is enabled.
- **Build**: `git clone`, `cp .env.example .env`, set the key,
  `scripts/docker-build.sh`, `docker compose up -d`. Images are built on the
  host from a reviewed commit; nothing is pushed to a registry. A later
  private registry is optional.
- **HTTPS**: keep `HTTP_PORT` bound to 127.0.0.1 and put a host reverse proxy
  in front (Caddy or nginx with a Let's Encrypt or company certificate) on 443,
  with `client_max_body_size 200m` and ≥ 35 min read timeouts like the bundled
  nginx. Open only 443 (and SSH from the admin network) in the firewall.
- **Authentication**: the existing access key (`API_ACCESS_TOKEN`) protects
  every API route; share it out of band and rotate it by changing `.env` and
  `docker compose up -d backend`. There is no per-user identity: for a pilot
  beyond a few trusted users, add the proxy's or an SSO gateway's
  authentication in front (docs/DEPLOYMENT.md, "Security boundary").
- **Secrets**: `.env` with mode 600, owned by the deploy user; never in Git,
  images or logs. Back up separately from the data archives.
- **Backups**: nightly section-6 archive via cron (stop backend, tar, start;
  a few seconds of downtime), copied off-host to encrypted storage, 14 daily +
  8 weekly kept. Test a restore into a new volume monthly.
- **Monitoring**: `docker compose ps` health, `/healthz`, disk free on the
  volume, `docker stats` memory against the 3 GB ceiling; logs via
  `docker compose logs` or the host's journald driver.
- **Updates**: section 5 after a backup; rollback per section 7.
- **Before release of the combined product**: the summary branch this image
  set was built from has not yet been integrated with the newer partner work
  on `main` (section 14).

## 13. Measured on Docker Desktop (Windows 11, WSL 2, 16 CPUs / 7.4 GB VM)

Fresh uploads into an empty `estima3d_data` volume, LLM off, one at a time:

| Step | Time | Backend memory (peak) |
| --- | --- | --- |
| First start, empty volume (seed 401 MB of `training/`) | healthy in ~7 s | 233 MiB idle |
| OSSE - ST.pdf, 26 pages, 16 MB: upload + extraction | 14.3 s | 366 MiB |
| Yellow Spring ST1.pdf, 40 pages: extraction | 30.1 s | 697 MiB |
| Brandywine Structural4.pdf, 43 pages: extraction | 36.1 s | 821 MiB |
| Cached extraction after container recreation | 1.2–2.2 s | — |
| OSSE report: Locate for 33 listed locations | 4 s | 631 MiB |
| Locate across many plan views (Brandywine) | first page ~2–3 s | 1.34 GB, then ~1.17 GB held |
| nginx | — | < 15 MiB |

Locate keeps each analysed plan page in a per-process cache that is not
evicted, so the backend's resident memory steps up with the plan pages looked
at and stays there until the container restarts. The 3 GB ceiling
(`BACKEND_MEMORY_LIMIT`) covers the measured peaks with room for analysis
(~1.6 GB measured earlier on a 24-page set); a restart releases the cache.
Run one heavy job (extraction, analysis, a full-report lookup, the test suite)
at a time on an 8 GB machine. Image sizes: `estima3d-api` ~3.1 GB (Python
packages 1.6 GB, `training/` seed 420 MB), `estima3d-web` 78 MB.

## 14. Release prerequisite: integrate with `main`

These images are built from `bassam/drawing-summary-osse` (summary work at
`dcca690`) plus this containerization branch. `origin/main` has moved on with
partner work (`56a0bbc`, `68bb739`: sheet index, grid intelligence,
engineering intelligence) that is not in this branch; a trial merge conflicts
in six files. The combined product must be integrated through the repository's
user-invoked `/git-integrate` flow, with new cache versions above both sides,
before an image of it is released. The containerization changes no file that
the partner commits change (checked against `e32cc5b..68bb739`), so it carries
over to the integrated tree; rebuild and re-verify the images there.
