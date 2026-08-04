import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Long analysis requests must not be cut off by the dev proxy.
const PROXY_TIMEOUT_MS = 15 * 60 * 1000;

export default defineConfig(({ mode }) => {
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
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.js"],
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
