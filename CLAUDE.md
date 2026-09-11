# AI Structural Steel Takeoff Platform — working rules

FastAPI backend + React/Vite frontend for multimodal extraction → prediction → validation →
human review → continuous learning → takeoff generation for structural-steel drawings.

Authoritative docs (read on demand, do not copy their content here):
`docs/ARCHITECTURE.md` · `docs/FOLDERS.md` · `docs/SERVICES.md` · `docs/TRAINING.md` ·
`docs/API.md` · `docs/FRONTEND.md` · `docs/ENGINEERING_VALIDATION.md` · `README.md`.

## Architecture invariants (do not break without explicit intent)

- Production per-token prediction enters **only** through
  `backend/services/prediction/orchestrator.py`. Nothing else owns inference.
- The canonical v2 explainability contract (`prediction/contract.py`,
  `prediction/explanation_engine.py`) is rendered identically by Review Queue, Validation, and
  Prediction Details. Do not fork its shape.
- Excel is **ground truth only** — never a prediction input. The AISC database
  (`backend/database/`) **verifies only** and must not change prediction selection.
- Routers depend on services; domain services must **not** import routers; frontend consumes
  API contracts only.
- `backend/services/label_reconstruction/` and `backend/services/ml_association/` are shadow
  work and are **not wired into production**. Guard tests
  (`test_*_not_wired_into_production.py`) enforce this — do not wire them in.
- Training augmentation happens only after the leakage-safe split; dataset and model versions
  are immutable; promotion is gated, not automatic.

## Change discipline

- Preserve all existing user changes. Never revert, reset, stash, clean, or checkout over work.
- Inspect working-tree state and the relevant diff before editing.
- Search for an existing implementation / helper / contract / test before adding one.
- Trace call sites before changing shared code; prefer modifying the existing path over adding
  a parallel one.
- Make the smallest coherent change. No opportunistic refactors outside the causal path.
- Do not add compatibility layers, defensive branches, abstractions, wrappers, files,
  dependencies, or restating comments unless the task requires them.
- Preserve public API / contract shapes unless the task is explicitly changing them.
- Before finishing a non-trivial change: run the `simplify` skill, then re-run affected tests.

## Repository safety

- A `PreToolUse` hook blocks writes to `backend/database/`, `backend/training/models/`,
  `backend/training/experiments/`, gitignored bulk data dirs, model binaries
  (`.pt/.pkl/.joblib/.onnx/...`), `frontend/dist/`, uploads, caches. Do not work around it.
- Runtime-updated training files (`backend/training/*.csv|*.jsonl|*.json`,
  `backend/training/documents/`) are normal to edit — the hook allows them.
- Never run destructive git operations, force-push, commit, or push unless explicitly asked.
- This repo uses multiple worktrees and partner-branch integration. Use the `git-integrate`
  skill for any cherry-pick / partner-merge / cross-worktree work.
- Report pre-existing modifications and pre-existing test failures separately from your changes.

## Search

- Prefer LSP (definitions / references / call hierarchy / types) for known symbols.
- Then exact search (`rg`, `git grep`). Read minimal files and line ranges, not whole modules.
- Use the Explore subagent only when targeted search fails.

## Commands (verified)

Backend — run from `backend/` (README uses a `venv`; system `python` also works here):
- all tests: `python -m pytest -q`   (≈699 tests; only for wide/shared changes)
- one test: `python -m pytest tests/test_<x>.py::<name> -q`
- API server: `python -m uvicorn app:app --reload`  (port 8000, OpenAPI at `/docs`)

Frontend — run from `frontend/`:
- tests: `npm run test`   (Vitest; `.test.jsx` colocated)
- one file: `npx vitest run src/pages/ResultsPage.test.jsx`
- build: `npm run build`   (Vite; JS/JSX, there is no `tsc` step)
- dev: `npm run dev`  (port 5173; keep `VITE_API_BASE` empty — same-origin via Vite proxy)

Use the `test-select` skill to choose the narrowest sufficient tier. Never escalate to a
broader tier just because a narrower one passed — escalate on blast radius only.

## Verification

- State the observable success condition before implementing.
- Narrowest relevant tests first; broader/E2E only when the change's blast radius justifies it.
- For runtime/UI bugs, reproduce the observable behavior (browser on demand); a green unit
  test is not proof.
- Inspect the final `git diff`; run the code-simplicity / deletion pass; retest if it changed code.
- Report the exact checks run and their outcomes.

## ML work

- See `.claude/rules/ml.md`. Use the `ml-audit` skill / `ml-auditor` agent before trusting an
  experiment or a claimed metric gain.
- Compare against the correct existing baseline with the same frozen holdout and metric defs.

## Output

Concise: root cause · files changed · behavior changed · verification performed · remaining
uncertainty · any pre-existing issues observed.
