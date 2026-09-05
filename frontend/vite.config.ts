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
    /*
     * Coverage, for `npm run test:coverage` (`scripts/verify.py --coverage`).
     *
     * ONE PROCESS, ALL PROJECTS: the jsdom run and the two Chromium story runs
     * merge into a single report, which is the only honest number -- a
     * component whose tests are stories (`OpeningHand`, `StackPanel`) reads
     * near zero from the unit project alone. `include` is load-bearing:
     * without it the provider instruments `storybook-static/` beside `src/`
     * and the total reads 7%. The thresholds are floors, not targets: each
     * one is the number the file had when it was pinned, raised by the commit
     * that earned more, so coverage can only ratchet up.
     */
    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: ["src/**/*.stories.tsx", "src/testing/**", "src/main.tsx"],
      reporter: ["text-summary", "json-summary", "html"],
      reportsDirectory: "coverage",
      // `COVERAGE_FLOORS=off` drops the floors for a jsdom-only run: most of
      // these numbers are only reachable with the story projects in the same
      // process, so `scripts/verify.py` sets it on a machine without Chromium.
      thresholds:
        process.env.COVERAGE_FLOORS === "off"
          ? undefined
          : {
              // Measured on 2026-09-05 with every project in one process. Global
              // first; then the files TECH_DEBT CG-02 named, each at what it has.
              statements: 88,
              branches: 89,
              functions: 82,
              "src/api/client.ts": { statements: 100 },
              "src/audio/sfx.ts": { statements: 98 },
              "src/components/game/CardGhost.tsx": { statements: 97 },
              "src/components/game/CardHold.tsx": { statements: 100 },
              "src/components/game/CombatArrows.tsx": { statements: 98 },
              "src/components/game/CommandZone.tsx": { statements: 98 },
              "src/components/game/EventTicker.tsx": { statements: 100 },
              "src/components/game/FxLayer.tsx": { statements: 70 },
              "src/components/game/GroupDial.tsx": { statements: 100 },
              "src/components/game/OpeningHand.tsx": { statements: 97 },
              "src/components/game/OpponentBoard.tsx": { statements: 100 },
              "src/components/game/ParticleLayer.tsx": { statements: 94 },
              "src/components/game/StackPanel.tsx": { statements: 96 },
              "src/components/game/Table.tsx": { statements: 82 },
              "src/components/game/ActionPanel.tsx": { statements: 91 },
              "src/components/lobby/InviteDialog.tsx": { statements: 100 },
              "src/components/ui/ControllerPanel.tsx": { statements: 100 },
              "src/fx/actuators.ts": { statements: 100 },
              "src/fx/scheduler.ts": { statements: 100 },
              "src/screens/HomeRoute.tsx": { statements: 76 },
              "src/screens/PodRoute.tsx": { statements: 84 },
            },
    },
    projects: [
      {
        extends: true,
        test: {
          name: "unit",
          environment: "jsdom",
          globals: true,
          include: ["tests/**/*.test.{ts,tsx}"],
          setupFiles: ["tests/setup.ts"],
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
             * DECLARED, AND NOT WHAT THE STORIES ACTUALLY GET. Worth knowing.
             *
             * The tester is an iframe that Storybook's Vitest addon sizes to
             * 1200x900 per story, and it wins: `browser.viewport`,
             * `instances[].viewport`, a `--window-size` launch arg and a
             * `page.viewport()` call from `beforeEach` were all measured, and
             * every one of them was reset before the play function ran.
             *
             * That was harmless for as long as nothing branched on the
             * viewport. It stopped being harmless the moment something did:
             * `HANDHELD_QUERY` is `(max-width: 1366px)`, so at 1200 EVERY story
             * matched it and the compact body rendered in the project whose job
             * is the desktop one.
             *
             * So the layout is decided by the toolbar rather than by the canvas
             * -- `preview.tsx` stamps `data-desktop` or `data-handheld`, and
             * both `styles/handheld.css` and `state/useHandheld.ts` treat an
             * explicit choice as beating the query. This value stays because it
             * is what the suite MEANS, and because the zoom solver reads
             * `clientWidth`, so a canvas that varied by machine would make
             * `data-zoom-board` vary with it.
             */
            viewport: { width: 1600, height: 950 },
          },
        },
      },
      /*
       * The same stories, at a Steam Deck's panel.
       *
       * A THIRD PROJECT RATHER THAN A SECOND VIEWPORT ON THE SECOND, which is
       * the split `playwright.config.ts` already argues for: the desktop
       * numbers every existing story asserts must never move, and they would
       * move the instant this canvas did. Running the whole suite at 1280x800
       * would also fail dozens of stories that are *correctly* designed for a
       * wider board.
       *
       * So it is opt-in by tag. A story tagged `handheld` runs in both, and has
       * to hold at both -- which is the honest statement of what the compact
       * layout promises.
       *
       * The size matters and is not decorative: `handheld.css` re-values
       * `--rail-r`, `--mat-side`, `--pod-seat-h` and `--hand-lift` inside a
       * MEDIA QUERY, so a canvas at 1600 gets the handheld structure (the
       * attribute) with the desktop tokens -- a board that exists nowhere. Only
       * a real 1280x800 canvas exercises both halves at once.
       */
      {
        extends: true,
        plugins: [storybookTest({ configDir: ".storybook", tags: { include: ["handheld"] } })],
        test: {
          name: "storybook-handheld",
          setupFiles: [".storybook/vitest.setup.ts"],
          browser: {
            enabled: true,
            headless: true,
            provider: "playwright",
            instances: [{ browser: "chromium" }],
            // See the note above: declared, and the toolbar is what actually
            // decides the layout. These stories carry `handheld: "on"`.
            viewport: { width: 1280, height: 800 },
          },
        },
      },
    ],
  },
});
