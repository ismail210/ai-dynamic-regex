---
name: safe-change
description: >-
  Default implementation workflow for this repo: minimal repository reading, minimal diff,
  reuse of existing code and contracts, targeted verification, and no unrelated edits. Use for
  most bug fixes and small-to-medium feature work in backend/ or frontend/.
---

# Safe Change

1. **Git state** — `git status --short --branch`, `git diff --stat`, `git branch --show-current`.
   Note pre-existing modified/untracked files; you will report them separately and not touch them.
2. **Observable success condition** — state it in one sentence before touching code.
3. **Targeted search** — stop as soon as you have the causal path:
   - LSP definition / references / call hierarchy for a known symbol
   - `rg` / `git grep` for exact identifiers, routes, error strings, contract keys
   - Explore subagent only if the above fail
4. **Causal / dependency path** — read only the files and line ranges on the path. For backend,
   respect the layering in `docs/SERVICES.md` (routers → services; one inference owner:
   `services/prediction/orchestrator.py`).
5. **Reproduce** — for a bug, reproduce it or capture a baseline first (a failing test, an API
   response, a rendered value).
6. **Root cause** — name it before editing.
7. **Minimum change** — modify the existing path; do not fork a parallel one. Reuse existing
   helpers/contracts (`prediction/contract.py`, `frontend/src/lib/predictionContract.js`,
   shared parsers, `src/api/client.js`) before writing new ones.
8. **Targeted validation** — changed-file check + the narrowest test:
   backend `cd backend && python -m pytest tests/test_<x>.py::<name> -q`;
   frontend `npx vitest run <file>` then `npm run build` if JSX changed.
9. **Escalate verification** only when blast radius requires it — use the `test-select` skill.
10. **Inspect the diff** (`git diff`) and delete: duplicated logic, single-use helpers less
    clear than inline code, impossible branches, unrequested compatibility/back-compat,
    comments that restate code, unrelated edits, speculative abstraction.
11. **Simplify** — for a non-trivial diff run the `simplify` skill; re-run affected tests if it
    edits code.
12. **Final git status** — confirm only intended files changed; pre-existing changes untouched.
13. **Report** — root cause · files changed · verification + results · pre-existing issues seen
    · remaining uncertainty.

Do not run the full backend suite by default. Do not refactor unrelated code. Do not wire in
`label_reconstruction` / `ml_association`. Do not write to hook-protected artifact paths.
