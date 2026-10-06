/**
 * Development-only pairing check: the Vite dev server injects the worktree it
 * runs from (`__DEV_PAIR__`, see vite.config.js) and API calls are refused
 * unless the backend's `/api/dev/identity` names the same worktree and the
 * Drawing Summary API this frontend renders. A no-op in builds and tests.
 */

// `drawing_intelligence.definitions` (grouped mark definitions) arrived with v2.
export const EXPECTED_SUMMARY_API = "drawing_intelligence_v3";

const devPair = typeof __DEV_PAIR__ !== "undefined" ? __DEV_PAIR__ : null;
const baseURL = import.meta.env.VITE_API_BASE || "";

// Reads may reuse a passing check this recent; writes always check afresh.
const REUSE_MS = 5000;

const RESTART_HINT = "Start a matching pair with `node scripts/dev.mjs` from this worktree.";

function normalizePath(value) {
  return String(value || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

const shortRevision = (revision) => (revision ? revision.slice(0, 7) : "unknown");

/** Compare the dev server's identity with the backend's. Pure, for tests. */
export function compareIdentity(expected, backend) {
  const target = expected.proxy_target;
  if (normalizePath(backend.worktree) !== normalizePath(expected.worktree)) {
    return {
      ok: false,
      problem:
        `The backend at ${target} is running from ${backend.worktree}, but this ` +
        `frontend is from ${expected.worktree}. ${RESTART_HINT}`,
    };
  }
  if (backend.summary_api !== EXPECTED_SUMMARY_API) {
    return {
      ok: false,
      problem:
        `The backend at ${target} serves summary API ${backend.summary_api || "none"}, ` +
        `but this frontend renders ${EXPECTED_SUMMARY_API}. Restart the backend.`,
    };
  }
  if (backend.revision !== expected.revision) {
    return {
      ok: true,
      warning:
        `The backend started at revision ${shortRevision(backend.revision)} and the ` +
        `frontend at ${shortRevision(expected.revision)}. Restart the pair if either ` +
        `side's code changed since.`,
    };
  }
  return { ok: true };
}

async function fetchIdentity() {
  const target = devPair.proxy_target;
  let response;
  try {
    response = await fetch(`${baseURL}/api/dev/identity`, { cache: "no-store" });
  } catch {
    return {
      ok: false,
      problem: `The dev server is not reachable, so the backend at ${target} cannot be checked. ${RESTART_HINT}`,
    };
  }
  if (response.status === 404) {
    return {
      ok: false,
      problem:
        `The backend at ${target} has no development identity endpoint, so it is ` +
        `not this worktree's backend (another worktree, an older revision, or ` +
        `APP_ENV is not "development"). ${RESTART_HINT}`,
    };
  }
  if (!response.ok) {
    return {
      ok: false,
      problem:
        `The backend at ${target} is not reachable (the dev proxy answered HTTP ` +
        `${response.status}). ${RESTART_HINT}`,
    };
  }
  return compareIdentity(devPair, await response.json());
}

const listeners = new Set();
let pending = null;
let last = null; // { result, at, key }

/**
 * Check the backend. A backend can stop or be replaced by another worktree's
 * while this page stays open, so `fresh` checks (every write: upload,
 * extraction, analysis) always ask again; reads reuse a recent passing result.
 * Concurrent callers share one in-flight check.
 */
export function checkBackendIdentity({ fresh = true } = {}) {
  if (!devPair) return Promise.resolve({ ok: true });
  if (!fresh && last?.result.ok && Date.now() - last.at < REUSE_MS) {
    return Promise.resolve(last.result);
  }
  pending ??= fetchIdentity().then((result) => {
    pending = null;
    const key = JSON.stringify(result);
    const changed = key !== last?.key;
    last = { result, at: Date.now(), key };
    if (changed) listeners.forEach((listener) => listener(result));
    return result;
  });
  return pending;
}

/** Subscribe to identity changes; called at once with the latest result. */
export function onBackendIdentity(listener) {
  listeners.add(listener);
  if (last) listener(last.result);
  return () => listeners.delete(listener);
}
