---
name: git-integrate
description: >-
  Audit and safely integrate a partner branch, commit, cherry-pick, or cross-worktree change
  into this repo. Handles mixed commits (real code + unwanted datasets/models/artifacts),
  unrelated-change detection, worktree isolation, and before/after verification. Invoke
  explicitly for any integration work.
disable-model-invocation: true
---

# Git Integration

This repo runs several worktrees of the same repository (`git worktree list`) and takes
partner branches (e.g. Hiba's backend-safety line merged into Bassam's integration line).
Integration mistakes here are expensive — go slow and read-only first.

## Before any mutation

1. Record `git rev-parse --show-toplevel`, `git branch --show-current`, `HEAD`, upstream, and
   `git status --short --branch`. Capture the current diff.
2. **Preserve everything uncommitted.** The working tree normally carries in-progress changes
   under `backend/training/*.csv|*.jsonl|*.json`, `backend/training/documents/`,
   `backend/services/`, and `frontend/src/`. Never discard them. Note stashes (`git stash list`)
   and tags (`git tag --points-at`) and do not delete them.
3. Inspect the candidate read-only:
   - `git log --oneline --decorate <base>..<candidate>`
   - `git diff --name-status <base>...<candidate>` and `--stat`
   - classify every path: wanted code · tests · docs · **artifacts to reject**
     (`backend/training/models/**`, `backend/training/experiments/**`, `backend/database/**`,
     `*.pkl/*.joblib/*.pt/*.onnx`, `*.xlsx/*.pdf/*.zip`, anything > ~1 MB) · unrelated changes
   - flag contract touches: `prediction/contract.py`, `routers/**`,
     `frontend/src/lib/predictionContract.js`, `frontend/src/api/client.js`
4. Prefer an **isolated worktree** for non-trivial integration:
   `git worktree add ../aidr-integrate-<topic> -b integrate/<topic> <base>`
   so a failed integration cannot touch the active working tree.
5. State the method (clean cherry-pick / cherry-pick + manual resolution / reproduce selected
   hunks manually / reject) and why, before executing.

## Applying

6. Cherry-pick / apply only the wanted commits or hunks. For a mixed commit, prefer
   `git cherry-pick -n <sha>` then unstage and discard the artifact paths before continuing.
7. Do not let rejected artifacts churn: after applying, `git status` must show no
   `backend/training/models`, `experiments`, `database`, or binary changes you did not intend.

## After applying

8. `git diff` and `git diff --check` on the result.
9. Targeted verification for the changed behavior (`test-select` skill); broader suite only if
   a shared contract or preprocessing path moved.
10. Confirm no unrelated or artifact files were introduced; confirm pre-existing user changes
    are intact.
11. Commit or push **only** if the user explicitly asked. If committing legitimate artifacts is
    intended, include `[allow-artifacts]` in the message (the commit hook requires it).
12. Report: base/candidate SHAs, worktree used, files applied vs rejected, conflicts resolved,
    tests run, and final `git status`.

Never: `reset --hard`, `clean -fd`, `checkout` over user work, rebase/force-push, branch or
worktree deletion, or stash drop — unless the user explicitly instructs it this session.
