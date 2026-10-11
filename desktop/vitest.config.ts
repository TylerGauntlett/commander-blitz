import { defineConfig } from "vitest/config";

/**
 * Node, not jsdom, and no Electron: everything under `src/` that decides
 * something -- the sidecar's lifecycle, the content swap, the update check,
 * the restart with rollback -- takes its process, filesystem and network
 * calls as arguments, and the tests hand it fakes. The Electron wiring in
 * `main.ts` and `preload.ts` is thin and is not under test here; `--smoke`
 * covers it in the packaged AppImage.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/main.ts", "src/preload.ts", "src/shellUpdater.ts", "src/ipc.ts"],
    },
  },
});
