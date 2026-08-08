import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The dev server proxies /api, /health and /art to the FastAPI process, so the
 * client can use same-origin relative URLs and never needs a base-URL setting.
 *
 * `/art` is easy to forget and fails in a confusing way: without it the dev
 * server answers `GET /art/forest.jpg` with index.html (the SPA fallback), the
 * <img> fires onerror, and every card falls back to its "no art" plate -- while
 * a preview build against the same API works perfectly.
 *
 * `host` is pinned to 127.0.0.1 on purpose. Vite's default is "localhost",
 * which Node 17+ resolves to ::1 and then binds IPv6-only -- so anything asking
 * for 127.0.0.1 (Playwright's health check, curl, the engine's CORS origins)
 * gets connection refused against a server that is plainly running.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/art": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
