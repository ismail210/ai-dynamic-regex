#!/usr/bin/env node
/**
 * Start this worktree's paired development frontend and backend.
 *
 *   node scripts/dev.mjs                                        # 5173 -> 8000
 *   node scripts/dev.mjs --frontend-port 5174 --backend-port 8001  # second worktree
 *
 * Options (or environment variables):
 *   --frontend-port  ESTIMA3D_FRONTEND_PORT  default 5173
 *   --backend-port   ESTIMA3D_BACKEND_PORT   default 8000
 *   --python         ESTIMA3D_PYTHON         default backend/venv, backend/.venv, then `python`
 *
 * Both ports are checked before anything starts and a busy port is an error:
 * Vite never drifts to another port and the frontend's proxy target is always
 * this pair's backend. Stopping either process stops the pair.
 */

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fs.realpathSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."));
const BACKEND_DIR = path.join(ROOT, "backend");
const FRONTEND_DIR = path.join(ROOT, "frontend");
const VITE_BIN = path.join(FRONTEND_DIR, "node_modules", "vite", "bin", "vite.js");
const HOST = "127.0.0.1";
const BACKEND_READY_TIMEOUT_MS = 180_000;

function fail(message) {
  console.error(`\n[dev] ${message}\n`);
  process.exit(1);
}

function option(name, envName, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  if (index >= 0) {
    const value = process.argv[index + 1];
    if (!value || value.startsWith("--")) fail(`--${name} needs a value.`);
    return value;
  }
  return process.env[envName] || fallback;
}

function port(name, envName, fallback) {
  const raw = option(name, envName, fallback);
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    fail(`--${name} must be a port number, got "${raw}".`);
  }
  return value;
}

const samePath = (a, b) =>
  path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

function isPortFree(portNumber) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => server.close(() => resolve(true)));
    server.listen(portNumber, HOST);
  });
}

async function identityAt(portNumber) {
  try {
    const response = await fetch(`http://${HOST}:${portNumber}/api/dev/identity`, {
      signal: AbortSignal.timeout(2000),
    });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

async function requireFreePorts(frontendPort, backendPort) {
  const busy = [];
  for (const [role, portNumber] of [
    ["frontend", frontendPort],
    ["backend", backendPort],
  ]) {
    if (await isPortFree(portNumber)) continue;
    const identity = await identityAt(portNumber);
    const owner = identity ? ` (serving worktree ${identity.worktree})` : "";
    busy.push(`  ${role} port ${portNumber} is already in use${owner}`);
  }
  if (busy.length) {
    fail(
      `Cannot start the dev pair:\n${busy.join("\n")}\n\n` +
        "Stop the process holding the port, or start this worktree on a free pair, e.g.\n" +
        "  node scripts/dev.mjs --frontend-port 5174 --backend-port 8001",
    );
  }
}

function resolvePython() {
  const explicit = option("python", "ESTIMA3D_PYTHON", "");
  const candidates = explicit
    ? [explicit]
    : [
        path.join(BACKEND_DIR, "venv", "Scripts", "python.exe"),
        path.join(BACKEND_DIR, "venv", "bin", "python"),
        path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe"),
        path.join(BACKEND_DIR, ".venv", "bin", "python"),
      ]
        .filter((candidate) => fs.existsSync(candidate))
        .concat("python");
  for (const candidate of candidates) {
    const probe = spawnSync(candidate, ["-c", "import uvicorn, fastapi"], { stdio: "ignore" });
    if (probe.status === 0) return candidate;
  }
  fail(
    `No Python with uvicorn and fastapi found (tried: ${candidates.join(", ")}).\n` +
      "Pass --python <path-to-python> or set ESTIMA3D_PYTHON.",
  );
}

const children = [];
let stopping = false;

function stopPair(exitCode) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode !== null) continue;
    if (process.platform === "win32") {
      // A venv python.exe is a launcher; /T also stops the interpreter it spawned.
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      child.kill("SIGTERM");
    }
  }
  process.exit(exitCode);
}

function start(role, command, args, options) {
  const child = spawn(command, args, { stdio: "inherit", ...options });
  child.on("exit", (code) => {
    if (stopping) return;
    console.error(`\n[dev] ${role} exited (code ${code}); stopping the pair.`);
    stopPair(1);
  });
  children.push(child);
  return child;
}

async function waitForBackend(backend, backendPort) {
  const deadline = Date.now() + BACKEND_READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (backend.exitCode !== null) return null;
    const identity = await identityAt(backendPort);
    if (identity) return identity;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return null;
}

async function main() {
  const frontendPort = port("frontend-port", "ESTIMA3D_FRONTEND_PORT", 5173);
  const backendPort = port("backend-port", "ESTIMA3D_BACKEND_PORT", 8000);
  if (frontendPort === backendPort) fail("Frontend and backend ports must differ.");
  if (!fs.existsSync(VITE_BIN)) fail("Frontend dependencies are missing: run `npm install` in frontend/.");

  await requireFreePorts(frontendPort, backendPort);
  const python = resolvePython();
  const target = `http://${HOST}:${backendPort}`;

  process.on("SIGINT", () => stopPair(0));
  process.on("SIGTERM", () => stopPair(0));

  console.log(`[dev] starting backend on ${target} (${python})`);
  const backend = start(
    "backend",
    python,
    ["-m", "uvicorn", "app:app", "--host", HOST, "--port", String(backendPort)],
    // The identity endpoint only exists in development.
    { cwd: BACKEND_DIR, env: { ...process.env, APP_ENV: "development" } },
  );

  const identity = await waitForBackend(backend, backendPort);
  if (!identity) {
    console.error(`[dev] backend did not report its identity on ${target}.`);
    stopPair(1);
  }
  if (!samePath(identity.worktree, ROOT)) {
    console.error(`[dev] ${target} answered as ${identity.worktree}, not ${ROOT}.`);
    stopPair(1);
  }

  start(
    "frontend",
    process.execPath,
    [VITE_BIN, "--host", HOST, "--port", String(frontendPort), "--strictPort"],
    {
      cwd: FRONTEND_DIR,
      // An absolute VITE_API_BASE (e.g. from a local .env) would bypass the
      // pair's proxy; force same-origin calls.
      env: { ...process.env, VITE_PROXY_TARGET: target, VITE_API_BASE: "" },
    },
  );
  console.log(
    `[dev] pair for ${ROOT} @ ${(identity.revision || "unknown").slice(0, 7)}\n` +
      `[dev]   frontend http://${HOST}:${frontendPort}  ->  backend ${target}`,
  );
}

main();
