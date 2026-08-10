/**
 * Storybook's half of the frontend's test pyramid.
 *
 * The suites split by what they can see. `tests/` runs in jsdom, which has no
 * layout engine at all -- no `ResizeObserver`, no `@property`, no `clamp()`, and
 * every `getBoundingClientRect()` is zeros. That is fine for asserting what a
 * component renders and useless for asserting how it looks, which is most of
 * what this UI does: the board is a cascade of custom properties solved at
 * runtime. `e2e/` sees all of it but needs a live Python engine to reach any
 * given position. Stories sit in the gap -- a real browser and the real
 * stylesheets, driven from a fixture, with no backend at all.
 */

import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  framework: { name: "@storybook/react-vite", options: {} },
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-docs", "@storybook/addon-a11y", "@storybook/addon-vitest"],

  /*
   * `public/` holds 54 vendored Scryfall mana symbols, and `ManaSymbol` loads
   * each as `/symbols/<CODE>.svg`. Without this every cost row on every card in
   * every story is broken images -- and it fails quietly, because a broken
   * <img> still occupies its box.
   */
  staticDirs: ["../public"],

  core: { disableTelemetry: true },

  viteFinal: async (viteConfig) => {
    /*
     * Storybook loads and merges `vite.config.ts`, which brings `server.port:
     * 5173` and `strictPort: true` along with it. Left alone, Storybook then
     * refuses to boot next to a running `npm run dev` -- and says only that the
     * port is taken, which points at the wrong file entirely.
     */
    viteConfig.server = {
      ...viteConfig.server,
      port: undefined,
      strictPort: false,
      host: "127.0.0.1",
      proxy: {
        /*
         * The same three routes `vite.config.ts` proxies, so a story can draw
         * real art when uvicorn happens to be up. It usually is not, and that
         * is a supported way to run: the proxy answers 500, `<img>` fires
         * onerror, and `CardFace` draws its "no art" plate. The error handler
         * is there only to keep a hundred ECONNREFUSED traces out of the
         * terminal -- the default art mode is stubbed and offline anyway.
         */
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          configure: (proxy) => proxy.on("error", () => undefined),
        },
        "/art": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          configure: (proxy) => proxy.on("error", () => undefined),
        },
        "/health": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          configure: (proxy) => proxy.on("error", () => undefined),
        },
      },
    };
    return viteConfig;
  },
};

export default config;
