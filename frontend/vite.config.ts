import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
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
  /*
   * Two suites, split by what they can see.
   *
   * `unit` is the config this file has always had, nested one level: jsdom, no
   * layout, milliseconds. `storybook` runs every story in a real Chromium, which
   * is the only way to assert on a UI whose measurements come out of the
   * cascade -- jsdom has no `ResizeObserver`, does not implement `@property`,
   * and returns zeros from every `getBoundingClientRect`.
   *
   * `npm test` deliberately runs only `unit`, so the stage in `scripts/verify.py`
   * keeps meaning what it always meant and the repo still works on a machine
   * that has never downloaded a browser.
   */
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: "unit",
          environment: "jsdom",
          globals: true,
          include: ["tests/**/*.test.{ts,tsx}"],
        },
      },
      {
        extends: true,
        plugins: [storybookTest({ configDir: ".storybook" })],
        test: {
          name: "storybook",
          // The setup file only flags that this is the runner, so `preview.tsx`
          // can hold motion still here and let it play in the browser. It must
          // not call `setProjectAnnotations` -- the addon has applied the
          // preview's annotations itself since 10.3.
          setupFiles: [".storybook/vitest.setup.ts"],
          browser: {
            enabled: true,
            headless: true,
            provider: "playwright",
            instances: [{ browser: "chromium" }],
            /*
             * Fixed on purpose. The zoom solver reads `clientWidth`/
             * `clientHeight`, so a canvas that varied with the machine would
             * make `data-zoom-board` vary with it -- and the stories that
             * assert on card geometry would pass or fail by monitor.
             */
            viewport: { width: 1600, height: 950 },
          },
        },
      },
    ],
  },
});
