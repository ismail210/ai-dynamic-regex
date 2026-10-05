/**
 * Access key for a hosted backend that sets `API_ACCESS_TOKEN`. The key is
 * never built into the bundle: the user enters it after the backend answers
 * 401, and it is kept in this tab's sessionStorage only.
 */

const STORAGE_KEY = "estima3d.apiAccessKey";
const listeners = new Set();

export function getAccessKey() {
  try {
    return sessionStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setAccessKey(key) {
  try {
    sessionStorage.setItem(STORAGE_KEY, key);
  } catch {
    /* storage unavailable: the key lasts until the next reload */
  }
}

/** Headers for requests that bypass the API client (pdf.js, downloads). */
export function authHeaders() {
  const key = getAccessKey();
  return key ? { Authorization: `Bearer ${key}` } : {};
}

// Sticky: the startup restore can be refused before the prompt has mounted
// (the layout waits for lazy page chunks), and must still open it.
let denied = false;

export function reportAccessDenied() {
  denied = true;
  listeners.forEach((listener) => listener());
}

export function onAccessDenied(listener) {
  listeners.add(listener);
  if (denied) listener();
  return () => listeners.delete(listener);
}
