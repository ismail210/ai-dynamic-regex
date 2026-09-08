---
paths:
  - "frontend/src/**/*.{js,jsx}"
  - "frontend/*.js"
---

# Frontend rules

See `docs/FRONTEND.md` first. Stack: React 18 + Vite + Material UI (v9) + TanStack Table +
Axios + React Router + Recharts + react-pdf. **JavaScript/JSX only — no TypeScript, no `tsc`.**
No ESLint config exists; do not add one for a local change.

- All HTTP calls belong in `src/api/client.js`. Pages/components import client functions; never
  create an Axios request or hardcode an absolute API host in a component (breaks the
  same-origin Vite proxy / production Nginx proxy).
- `src/lib/predictionContract.js` is the sole boundary for reading family / section /
  confidence / explanations. Do not recreate fallback chains in components.
- `src/components/PredictionExplainability.jsx` is the shared evidence renderer for Review Queue
  details, Validation component details, and Prediction Details — change it once, not per page.
- Shared state is in `src/context/`. Do not introduce another state-management layer for a
  local synchronization problem.
- Follow existing MUI patterns and `src/theme.js`; reuse `src/components/` and `src/lib/utils.js`
  before adding a component or helper.
- Verify: `npm run test` (Vitest) for the touched `*.test.jsx`, then `npm run build`. For a
  user-visible bug, reproduce the browser flow (browser on demand) after the tests pass.
- Preserve API contract shape unless a matching backend change is in the same task.
