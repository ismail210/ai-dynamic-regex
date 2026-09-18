---
name: deploy-readiness
description: >-
  Gate for any deployment of this repo (Vercel or otherwise): correct branch, clean/understood
  working tree, targeted tests, production build, secret/env validation, preview deploy,
  Playwright smoke test, then explicit confirmation before production. Use whenever asked to
  deploy, ship, release, or "push this live."
---

# Deploy Readiness

This repo is FastAPI backend + React/Vite frontend (see `CLAUDE.md`, `docs/ARCHITECTURE.md`).
**Only the frontend static build is a Vercel-shaped deployment.** See "Architecture fit" below
before assuming Vercel covers the whole app.

## Gate sequence — do not skip or reorder a step

1. **Correct branch** — `git branch --show-current`; confirm it matches what the user asked to
   deploy. Stop and ask if ambiguous.
2. **Clean / understood working tree** — `git status --short`. Every uncommitted change must be
   either committed, explicitly intended to ship uncommitted (rare — confirm with the user), or
   explicitly out of scope and reported. Never deploy with silently-ignored local changes.
3. **Detect frontend/backend changes** — `git diff --stat <base>...HEAD` (base = the branch's
   upstream or the commit before the change set). If only `backend/**` changed, say so and skip
   the frontend build/deploy steps (nothing to redeploy on Vercel) — still run backend's own
   targeted tests. If only `frontend/**` changed, no backend action is needed. If both changed,
   run both, and note the two are deployed to different targets (see "Architecture fit").
4. **Targeted tests** — use the `test-select` skill for the changed area, not the full suite by
   default. Escalate only if the change's blast radius requires it.
5. **Production build** — `cd frontend && npm run build`. A failing build blocks everything past
   this point. Do not deploy an unbuilt or stale build.
6. **Secret/env validation** — confirm required env vars exist in the target (Vercel project
   settings / target platform), by name only. **Never read, print, log, or paste actual `.env`
   values or secrets in any tool output, report, or commit** — the repo's `secret_file_guard.py`
   hook enforces this for file access; treat it as an invariant here too, including for values
   read via a CLI (`vercel env ls` prints names, not values — do not force-print values). Also
   confirm no secret is hardcoded in source about to be deployed (`git grep` for likely key
   patterns in the diff being shipped, not the whole repo).
7. **Preview deployment** — deploy to a preview/staging target first. Never target production
   directly from this pipeline.
8. **Playwright smoke test** — against the preview URL, exercise the actual navigation, not a
   generic page-load check: `/upload-extract`, `/analysis` (Results), `/review-drawing` (Drawing
   Review), `/semantic-review` (Semantic Review). For each: page renders, no console errors, no
   failed network requests (check via the Playwright MCP's console/network inspection, not just
   visual load). A green build is not proof; the preview must actually render and navigate.
9. **Production confirmation** — **always stop and ask the user explicitly before promoting to
   production**, even if every prior step passed and even if the user's original request said
   "deploy." State what will change (branch, commit, target) and wait for a clear yes.
10. **Deployment/log verification** — after production promotion, check the deployment status and
    logs for errors; report them. Do not declare success from "the command exited 0" alone.

## Hard constraints

- Never modify DNS records, automatically or otherwise, without a separate explicit user request
  naming the DNS change.
- Never modify environment variables on any target (preview or production) — reading names to
  confirm they exist (step 6) is fine; setting, changing, or deleting a value is not, even a
  value the user pasted in chat, without a separate explicit request naming that exact change.
- Never delete or replace an existing Vercel (or other) project. If a target project doesn't
  exist and one seems needed, stop and ask — do not create one silently.
- Never silently overwrite an existing production deployment — the confirmation in step 9 must
  state what is being replaced, not just what is being added.
- Never run a production deploy command without the confirmation in step 9, regardless of how
  the user phrased the original request.
- Never expose `.env` contents, tokens, or connection strings in output, even redacted-looking
  partials copied from a real value.

## Using the `deploy-to-vercel` skill

The `deploy-to-vercel` skill (official, `vercel-labs/agent-skills`) handles the actual CLI/git
mechanics (link, push, `vercel deploy`, retrieving the preview URL). It is **not** a substitute
for this gate — it doesn't run tests, build, or a smoke test on its own, and it will happily run
`--prod` immediately if a user's phrasing implies production. Run this skill's gate sequence
first; invoke `deploy-to-vercel` only for the mechanical steps once steps 1–6 above are satisfied,
and never let its "ask before pushing" prompt substitute for step 9's production confirmation.

**Monorepo note:** this repo's Vercel-deployable unit is `frontend/`, not the repo root (the
root also contains `backend/`, which is not deployed to Vercel — see below). A Vercel project
for this repo needs its "Root Directory" set to `frontend/`; `deploy-to-vercel`'s auto-detection
assumes the deploy target is the current/repo directory, so pass `frontend/` explicitly as the
`[path]` argument or confirm the linked project's root directory setting before the first deploy.

## Architecture fit

- **Frontend** (`frontend/`, Vite static build, no `tsc` step, MUI/Recharts/react-pdf): a good
  fit for Vercel — static output, standard build command (`npm run build`), no server-side
  runtime requirements at request time.
- **Backend** (`backend/`, FastAPI): **not** a good fit for Vercel serverless functions.
  Reasons: `UPLOAD_ANALYSIS_TIMEOUT_SECONDS=900` (a 15-minute analysis timeout) exceeds ordinary
  serverless execution limits; the pipeline writes to persistent volumes
  (`backend/uploads/`, `backend/training/`, `ARTIFACT_RETENTION_DOCUMENTS`) that a stateless
  serverless function cannot rely on between invocations; the existing `docker-compose.yml`
  already models this as a long-running container with a healthcheck, not a function. If asked
  to deploy the backend to Vercel, report this mismatch instead of forcing it, and point at the
  existing Docker-based deployment path or one of the future-option platforms below.
- **Future options (not installed, record only)** — Cloudflare (Workers/Pages), Netlify, Render,
  Railway, Fly.io. Render/Railway/Fly are the closer architectural fit for the backend (support
  long-running containers, persistent volumes); do not install tooling for any of these without
  a separate explicit request.

## Output

Report which gate step you reached, the exact commands run, their results, and — for anything
short of full production deployment — that no production deployment occurred.
