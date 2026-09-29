import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Long analysis requests must not be cut off by the dev proxy.
// Keep above backend UPLOAD_ANALYSIS_TIMEOUT_SECONDS (default 30 min).
const PROXY_TIMEOUT_MS = 35 * 60 * 1000;

// Identity of the worktree this dev server runs from, compared at runtime with
// the backend's `/api/dev/identity` (see src/api/devIdentity.js).
function devPair(target) {
  const worktree = fs.realpathSync(path.resolve(__dirname, ".."));
  let revision = null;
  try {
    revision = execSync("git rev-parse HEAD", { cwd: worktree, encoding: "utf8" }).trim();
  } catch {
    // Not a git checkout: the worktree path still identifies the pair.
  }
  return { worktree, revision, proxy_target: target };
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_PROXY_TARGET || "http://127.0.0.1:8000";

  // `autoRewrite` is required: with `changeOrigin` the backend sees the target
  // host, so any redirect it emits would otherwise send the browser to
  // http://127.0.0.1:8000/... which is a different origin than the dev server.
  const proxyOptions = {
    target,
    changeOrigin: true,
    autoRewrite: true,
    followRedirects: false,
    timeout: PROXY_TIMEOUT_MS,
    proxyTimeout: PROXY_TIMEOUT_MS,
    configure: (proxy) => {
      proxy.on("error", (err, req) => {
        console.error(`[proxy] ${req.method} ${req.url} failed: ${err.message}`);
      });
    },
  };

  return {
    plugins: [react()],
    define:
      command === "serve" && mode !== "test"
        ? { __DEV_PAIR__: JSON.stringify(devPair(target)) }
        : {},
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.js"],
      // Named icon imports otherwise resolve the full MUI icons package and
      // hit EMFILE on constrained macOS file-descriptor limits.
      alias: {
        "@mui/icons-material": path.resolve(__dirname, "./src/test/muiIconsStub.jsx"),
      },
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        // `/upload` is also a client-side route. A browser navigation to the
        // Upload page must fall through to the SPA; forwarding it to the API,
        // which only accepts POST, answers 405 and the page never loads.
        "/upload": {
          ...proxyOptions,
          bypass: (req) =>
            req.method === "GET" &&
            (req.headers.accept || "").includes("text/html")
              ? "/index.html"
              : undefined,
        },
        "/api": proxyOptions,
      },
    },
  };
});
