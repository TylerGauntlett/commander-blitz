/**
 * Bundle the shell: `src/main.ts` and `src/preload.ts` into `dist/`.
 *
 * CommonJS, because Electron loads the main process and a sandboxed preload
 * as scripts, not modules. Only `electron` is external: `tar` and
 * `electron-updater` are bundled in, so the packaged app depends on nothing
 * in `node_modules` at runtime. They were external once, on the theory that
 * electron-builder would pack them -- and the first AppImage died on
 * `Cannot find module 'tar'`, because an explicit `files` list in
 * electron-builder.yml replaces the default that would have.
 *
 * `--dev` also writes `dev-content/manifest.json`, so `npm run dev` on a
 * checkout has a "bundled" content directory to point the state at.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { build } from "esbuild";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));
const dev = process.argv.includes("--dev");

await build({
  entryPoints: ["src/main.ts"],
  outfile: "dist/main.cjs",
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
  sourcemap: true,
  // `import.meta.url` has no meaning in a CommonJS bundle; `__filename` does.
  define: { "import.meta.url": "__cb_file_url" },
  banner: { js: 'const __cb_file_url = require("node:url").pathToFileURL(__filename).href;' },
});

await build({
  entryPoints: ["src/preload.ts"],
  outfile: "dist/preload.cjs",
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
});

if (dev) {
  mkdirSync("dev-content", { recursive: true });
  writeFileSync(
    "dev-content/manifest.json",
    JSON.stringify(
      {
        content_version: `${pkg.version}-dev`,
        app_version: pkg.version,
        min_shell_version: pkg.version,
        asset: "",
        sha256: "",
        size: 0,
        built: new Date().toISOString(),
      },
      null,
      2,
    ),
  );
}
